"""第四阶段：通过 FastAPI 调用带 Redis 会话记忆的 Agent。"""

import os
from pathlib import Path
from uuid import uuid4

import requests
import streamlit as st
import json
from typing import Iterator


API_BASE_URL = os.getenv("ECHOMIND_API_URL", "http://127.0.0.1:8000").rstrip("/")
USER_ID = 1  # 沿用原项目前端的演示用户，登录功能尚未实现。


st.set_page_config(page_title="EchoMind · 知识与记忆", page_icon="💬", layout="wide")
st.markdown(
    f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)

# 当前尚未实现登录，暂用演示用户。
if "user_id" not in st.session_state:
    st.session_state.user_id = USER_ID



# 1. 页面状态：消息用于显示；session_id 用于找回后端的 Redis 会话。
if "knowledge_bases" not in st.session_state:
    st.session_state.knowledge_bases = ["默认知识库"]
    st.session_state.selected_kb = "默认知识库"
    st.session_state.upload_version = 0

if "conversation" not in st.session_state:
    st.session_state.conversation = {
        "session_id": str(uuid4()),
        "messages": [],
    }

def request_knowledge_bases() -> list[str]:
    """从后端查询当前用户的知识库列表。"""
    with requests.get(
        f"{API_BASE_URL}/get_knowledge_bases",
        params={"user_id": USER_ID},
        timeout=(3, 10),
    ) as response:
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise ValueError("知识库列表响应格式不正确。")

    names = data.get("knowledge_bases")

    if not isinstance(names, list):
        raise ValueError("knowledge_bases 必须是列表。")

    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("知识库名称格式不正确。")

    return names


def request_create_knowledge_base(name: str) -> None:
    """请求后端创建知识库，失败时抛出异常。"""
    with requests.post(
        f"{API_BASE_URL}/create_knowledge_base",
        json={
            "knowledge_base_id": name,
            "user_id": USER_ID,
        },
        timeout=(3, 10),
    ) as response:
        response.raise_for_status()

def create_knowledge_base() -> None:
    """表单回调先更新数据，再由 Streamlit 重新绘制页面。"""
    name = st.session_state.new_kb_name.strip()
    if not name:
        st.session_state.notice = ("warning", "请输入知识库名称。")
        return
    elif name in st.session_state.knowledge_bases:
        st.session_state.notice = ("warning", "这个知识库已经存在。")
        return
    else:
        try:
            request_create_knowledge_base(name)
            st.session_state.knowledge_bases.append(name)
            st.session_state.selected_kb = name
            st.session_state.notice = ("success", f"已创建知识库：{name}")
            return
        except requests.HTTPError as exc:
            if exc.response.status_code == 409:
                st.session_state.notice = ("warning", "这个知识库已经存在。")
            else:
                st.session_state.notice = (
                    "error",
                    f"创建失败，HTTP 状态码：{exc.response.status_code}。",
                )
            return
        except requests.RequestException:
            st.session_state.notice = (
                "error",
                "创建请求未完成，请检查后端连接，并刷新页面确认结果。",
            )
            return

def request_document_upload(file, knowledge_base: str) -> dict:
    """上传一份文件。"""
    with requests.post(
        f"{API_BASE_URL}/document_upload",
        data={
            "knowledge_base_id": knowledge_base,
            "user_id": USER_ID,
        },
        files={
            "file": (
                file.name,
                file.getvalue(),
                file.type or "application/octet-stream",
            ),
        },
        timeout=(3, 60),
    ) as response:
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise ValueError("上传响应格式不正确。")

    if not isinstance(data.get("is_duplicate"), bool):
        raise ValueError("上传响应缺少重复文件标记。")

    return data


def request_knowledge_base_files(knowledge_base: str) -> list[dict]:
    """查询当前知识库的真实文件列表。"""
    with requests.get(
        f"{API_BASE_URL}/get_knowledge_base_files",
        params={
            "knowledge_base_id": knowledge_base,
            "user_id": USER_ID,
        },
        timeout=(3, 10),
    ) as response:
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise ValueError("文件列表响应格式不正确。")

    files = data.get("files")

    if not isinstance(files, list):
        raise ValueError("files 必须是列表。")

    for item in files:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str)
            for key in ("file_hash", "file_name", "uploaded_at")
        ):
            raise ValueError("文件信息格式不正确。")

    return files

def request_document_delete(
    file_hash: str,
    knowledge_base: str,
    user_id: int,
) -> None:
    """从当前用户、当前知识库移除文档记录。"""
    with requests.delete(
        f"{API_BASE_URL}/document_delete",
        params={
            "file_hash": file_hash,
            "knowledge_base_id": knowledge_base,
            "user_id": user_id,
        },
        timeout=(3, 10),
    ) as response:
        response.raise_for_status()

def request_reply(question: str, knowledge_base: str, session_id: str) -> Iterator[str]:
    """把问题发给后端，再取出 JSON 响应里的 answer。"""
    with requests.post(
        f"{API_BASE_URL}/stream_chat",
        json={
            "message": question,
            "knowledge_base": knowledge_base,
            "user_id": USER_ID,
            "session_id": session_id,
        },
        stream=True,
        timeout=(3, 60),
    ) as response:
        response.raise_for_status()
        response.encoding = "utf-8"
        received_text =  False

        for line in response.iter_lines(
            chunk_size=1,
            decode_unicode=True,
        ):
            if not line:
                continue

            event = json.loads(line)

            if not isinstance(event, dict) :
                raise ValueError("后端返回的事件格式不正确。")

            if event.get("type") == "answer":
                content = event.get("content")

                if not isinstance(content, str):
                    raise ValueError("回答片段必须是文本。")

                if content:
                    received_text = True
                    yield content

            elif event.get("type") == "error":
                raise RuntimeError(
                    event.get("content") or "生成回答失败。"
                )

        if not received_text:
            raise RuntimeError("模型没有返回回答文本。")


# 2. 侧栏：先确定当前知识库，主区域再使用它的数据。
with st.sidebar:
    st.markdown("## ◌ EchoMind")
    st.caption("念念不忘，必有回响")
    st.divider()
    try:
        names = request_knowledge_bases()
    except (requests.RequestException, ValueError):
        st.error("知识库列表加载失败，请检查后端服务。")
        if st.button("重新加载"):
            st.rerun()
        st.stop()

        # 保留默认入口，并去掉重复名称。
    names = list(dict.fromkeys(["默认知识库", *names]))
    st.session_state.knowledge_bases = names

    # 当前选中的知识库已不存在时，回到默认入口。
    if st.session_state.selected_kb not in st.session_state.knowledge_bases:
        st.session_state.selected_kb = "默认知识库"
    st.selectbox(
        "当前知识库",
        options=list(st.session_state.knowledge_bases),
        key="selected_kb",
    )

    with st.expander("＋ 创建知识库"):
        with st.form("create_kb", clear_on_submit=True):
            st.text_input("知识库名称", key="new_kb_name", max_chars=50)
            st.form_submit_button(
                "创建", on_click=create_knowledge_base, use_container_width=True
            )

    if "notice" in st.session_state:
        level, message = st.session_state.pop("notice")
        getattr(st, level)(message)

    current_kb = st.session_state.selected_kb

    st.divider()
    st.markdown("#### 文档")

    # 展示上一次上传的结果。
    for level, message in st.session_state.pop("upload_results", []):
        getattr(st, level)(message)

    selected_files = st.file_uploader(
        "选择文档",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        key=f"uploads_{current_kb}_{st.session_state.upload_version}",
        help="上传到当前知识库，单个文件最多 20 MB。",
    )

    if st.button(
        "上传到知识库",
        use_container_width=True,
        disabled=not selected_files,
    ):
        results = []

        with st.spinner("正在上传文档……"):
            for file in selected_files:
                try:
                    result = request_document_upload(file, current_kb)

                    if result["is_duplicate"]:
                        results.append((
                            "info",
                            f"{file.name}：文件已存在。",
                        ))
                    else:
                        results.append((
                            "success",
                            f"{file.name}：上传成功，尚未解析。",
                        ))

                except requests.HTTPError as exc:
                    results.append((
                        "error",
                        f"{file.name}：上传失败，HTTP "
                        f"{exc.response.status_code}。",
                    ))

                except (requests.RequestException, ValueError):
                    results.append((
                        "error",
                        f"{file.name}：上传结果未确认，"
                        "请查看文件列表后再重试。",
                    ))

        st.session_state.upload_results = results

        # 全部确认成功或重复时，清空文件选择框。
        if all(level != "error" for level, _ in results):
            st.session_state.upload_version += 1

        st.rerun()

    # 文件列表由后端提供，不再读取页面里的演示字典。
    try:
        file_list = request_knowledge_base_files(current_kb)
    except (requests.RequestException, ValueError):
        file_list = None
        st.error("文件列表加载失败，请检查后端服务。")

    if file_list is not None:
        if not file_list:
            st.caption("文档列表为空")

        for file_info in file_list:
            info_column, action_column = st.columns([6, 1],
                                                    gap="small",
                                                    vertical_alignment="center")
            with info_column:
                st.text(file_info["file_name"])
                st.caption(
                    f"上传时间：{file_info['uploaded_at']} · 尚未解析"
                )

            with action_column:
                if st.button(
                    "",
                    icon=":material/delete_outline:",
                    type="tertiary",
                    key=f"remove_{current_kb}_{file_info['file_hash']}",
                    help=f"从当前知识库移除：{file_info['file_name']}",
                ):
                    try:
                        request_document_delete(
                            file_info["file_hash"],
                            current_kb,
                            st.session_state.user_id,
                        )
                    except requests.HTTPError as exc:
                        if exc.response.status_code == 404:
                            st.session_state.notice = (
                                "info",
                                "文件记录已不存在，列表已刷新。",
                            )
                        else:
                            st.session_state.notice = (
                                "error",
                                f"移除失败，HTTP {exc.response.status_code}。",
                            )
                    except requests.RequestException as exc:
                        st.session_state.notice = (
                            "error",
                            "移除结果未确认，请检查后端和文件列表。",
                        )
                    else:
                        st.session_state.notice = (
                            "success",
                            "文档已从当前知识库移除。",
                        )

                    st.rerun()

    st.divider()
    st.caption("模型问答 · 通过后端连接")
    st.caption("知识库和已上传文档保存在后端；刷新页面会开始新会话。")


# 3. 聊天区：从状态渲染历史，再处理本轮输入。
conversation = st.session_state.conversation

title_column, action_column = st.columns([5, 1])
with title_column:
    st.title("让知识有回响")

    count_text = (
        f"{len(file_list)} 份文档"
        if file_list is not None
        else "文档列表未加载"
    )

    st.caption(f"当前知识库：{current_kb} · {count_text}")
with action_column:
    if st.button("清空对话", use_container_width=True, help="清空页面对话，并开始新的会话。"):
        conversation["messages"].clear()
        conversation.pop("chat_error", None)
        conversation["session_id"] = str(uuid4())
        st.rerun()

st.info("已接入会话记忆，同一会话可以连续提问。文档尚未解析，跨会话的长期记忆尚未接入。")

if not conversation["messages"]:
    st.markdown("### 从一个问题开始")
    st.write("在左侧创建知识库、添加文档，然后在下方输入问题。")
    first, second, third = st.columns(3)
    for column, title, description in [
        (first, "01 · 准备资料", "选择知识库，把相关文档放在一起。"),
        (second, "02 · 自然提问", "围绕资料提问，保留完整对话。"),
        (third, "03 · 持续积累", "后续接入知识检索和长期记忆。"),
    ]:
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(description)

for message in conversation["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if error := conversation.get("chat_error"):
    st.error(error)

if question := st.chat_input("输入问题，按 Enter 发送……", max_chars=4000):
    question = question.strip()
    if question:
        conversation["messages"].append({"role": "user", "content": question})
        conversation.pop("chat_error", None)
        with st.chat_message("user"):
            st.markdown(question)

        try:
            answer = ""

            with st.chat_message("assistant"):
                answer_placeholder = st.empty()

                for piece in request_reply(question, current_kb, conversation["session_id"]):
                    answer += piece
                    answer_placeholder.markdown(answer + "▌")

                answer_placeholder.markdown(answer)

            conversation["messages"].append({"role": "assistant", "content": answer})
        except requests.Timeout:
            conversation["chat_error"] = "后端响应超时，请稍后重新发送问题。"
        except requests.ConnectionError:
            conversation["chat_error"] = "无法连接后端，请先启动 FastAPI 服务，再重新发送问题。"
        except requests.HTTPError as exc:
            error_message = f"后端返回错误（HTTP {exc.response.status_code}），请检查后端日志。"
            try:
                error_data = exc.response.json()
                if isinstance(error_data, dict) and isinstance(error_data.get("detail"), str):
                    error_message = error_data["detail"]
            except ValueError:
                pass
            conversation["chat_error"] = error_message
        except RuntimeError as exc:
            conversation["chat_error"] = str(exc)
        except (requests.RequestException, ValueError):
            conversation["chat_error"] = "请求失败或后端响应格式不正确，请检查后端日志。"
        st.rerun()
