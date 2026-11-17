# 当前阶段：Agent 与 Redis 多轮对话

本阶段沿用原项目的三个核心构件：

1. `create_agent`：构建 Agent，当前工具为空，后续加入知识检索和记忆工具。
2. `AsyncRedisSaver`：保存和恢复 Agent 状态，包括用户和助手消息。
3. `thread_id`：用来定位一个会话的检查点。

参考：https://github.com/Dreamt0511/EchoMind/blob/master/backend/agent.py

## 最重要的两段代码

`backend/agent.py` 创建 Agent：

```python
create_agent(
    model=get_model(),
    tools=[],
    system_prompt=SYSTEM_PROMPT_DEFAULT,
    context_schema=ContextSchema,
    checkpointer=checkpointer,
)
```

每次传入本轮问题和会话定位信息：

```python
await agent.ainvoke(
    {"messages": [{"role": "user", "content": user_message}]},
    {"configurable": {"thread_id": thread_id}},
    context=ContextSchema(user_id=user_id, knowledge_base_id=knowledge_base_id),
)
```

同一 `thread_id` 会读取已有消息，加入本轮问题、生成回复，再保存新的状态。
所以前端无需重复上传整个历史列表。

## 页面记录和后端记忆

| 数据 | 保存位置 | 用途 |
| --- | --- | --- |
| 页面 messages | Streamlit session_state | 绘制聊天气泡 |
| session_id | Streamlit session_state，并随请求传入后端 | 标识当前会话 |
| Agent messages 等状态 | Redis 检查点 | 为模型恢复上下文 |

页面的旧版单轮记录没有导入 Redis，本阶段首次验收前请点击“清空对话”。

## 与原项目的两处调整

- 原项目使用 `user_id` 作为 `thread_id`。本地学习版组合用户 ID 和会话 UUID：
  `echomind:{user_id}:{session_id}`。同一会话切换知识库保留上下文；不同用户或会话隔离。
  `user_id=1` 仍是演示值，尚未实现登录鉴权。
- Redis 检查点连接由 `main.py` 的 lifespan 持有，应用关闭时才释放。
  同时关闭模型的 HTTP 客户端，避免应用重建时复用旧事件循环或已关闭的连接。

`ContextSchema` 的 user_id、knowledge_base_id、top_k 与原项目保持一致，后续工具会使用这些字段。
当前保留 `/chat` 返回完整文本，`POST /stream_chat` 返回逐行 JSON 文本事件。
前端通过 Python requests 读取事件，再用 Streamlit 占位区域逐步绘制回答。

## 清空与过期

“清空对话”清除页面气泡，并生成新的会话 UUID。旧会话检查点按 TTL 到期清理，
没有即时删除 Redis 中旧数据。TTL 沿用原项目：60 分钟，读取时刷新。

重启后端后，只要页面仍保留同一会话 ID、检查点尚未过期，就能继续对话。
刷新页面会产生新会话；历史会话列表与页面消息恢复功能尚未实现。

这里是会话内的短期记忆。跨会话的长期记忆提取、用户画像、文档检索及长对话压缩会分步实现。

## 已验证

- 同一会话包含之前的用户与助手消息。
- 改变会话 ID 或用户 ID 时，历史相互隔离；同一会话切换知识库保留历史。
- 应用关闭并重新创建 Agent 和连接后，能从 Redis 恢复状态。
- 页面切换知识库保留当前会话；清空后使用新的会话。
- 模型连接在应用关闭后释放，下一次启动创建新连接。
- 真实模型能够在多轮和应用重建后找回测试代号；测试会话已清理。
