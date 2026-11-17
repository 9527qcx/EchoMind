# EchoMind 学习复刻

参考 [Dreamt0511/EchoMind](https://github.com/Dreamt0511/EchoMind) 的学习复刻。当前已实现流式多轮问答、PostgreSQL 知识库管理，以及后端真实文件上传和查询。前端文件按钮仍是演示功能，RAG 和跨会话长期记忆尚未接入。

## 复刻顺序与原项目对应关系

以原项目模块为参照，分步实现并验收。本仓库仍在学习开发中。

| 顺序 | 目标 | 对应原项目 | 当前状态 |
| --- | --- | --- | --- |
| 1 | Streamlit 页面与交互 | frontend/app.py、style.css | 聊天、知识库已接入后端，文档按钮仍为演示功能 |
| 2 | HTTP 接口与单轮模型调用 | main.py、api.py、schemas.py | 已完成 |
| 3 | 模块拆分与兼容的本地 Redis | main.py、api.py、agent.py、config.py | 已完成，6380 上的 JSON/Search 与 AsyncRedisSaver 已验收 |
| 4 | Agent 检查点与多轮对话 | create_agent、AsyncRedisSaver、thread_id | 已完成，接续、隔离、清空及应用重启恢复已验收 |
| 5 | 流式消息与状态事件 | stream_agent_response、/chat_with_agent/stream | 已实现 POST /stream_chat 文本流，工具状态事件待接入 |
| 6 | PostgreSQL 与知识库管理 | postgresql_client.py、api.py | 创建、查询和前端接入已实现 |
| 7 | 文档解析、哈希、父子分块与向量检索 | documents_process.py、hash_storage.py、milvus_client.py | 后端上传、哈希去重、原件保存及文件查询已实现，解析与检索待实现 |
| 8 | 混合检索、RRF、Rerank 与检索工具 | knowledge_base_manager.py、tools.py | 待实现 |
| 9 | 对话持久化、记忆提取与用户画像 | auto_store_memory_from_psql.py、memory_manager.py、redis_cache.py | 待实现 |
| 10 | 动态提示词、摘要中间件与故障降级 | config.py、agent.py、检索模块 | 待实现 |

Agent 已搭建调用与检查点，当前 `tools=[]`，后续逐项接入检索和记忆工具。每一步验收通过后推进。
当前保留 `/chat` 返回完整回答；`POST /stream_chat` 使用相同 JSON 输入，返回逐行 JSON 文本事件。
`llm.py` 是额外拆出的配置辅助模块，沿用已有 `OPENAI_*` 环境变量，与原项目的 `DASHSCOPE_API_KEY/BASE_URL/AGENT_BASE_MODEL` 对应。
本地使用包导入 `backend.*`，从根目录启动。

## 本地 Redis 已准备就绪（无需 Docker）

原项目使用 `AsyncRedisSaver`，需要 RedisJSON 和 Search 命令。普通 Redis 仅能 PING 成功还不够。
本项目已独立准备 Windows 原生 Memurai for Redis 8.2.0，提供原版检查点需要的能力。
主程序与安装包的官方签名已验证，程序位于 `.local/memurai/Memurai/`，
仅监听本机 6380。已有 Redis 5 仍在 6379，没有被替换。

下次启动时，在单独终端运行并保持打开：

```powershell
.\.venv\Scripts\python.exe scripts/start_redis.py
```

如果实例已经在运行，直接执行下面的验收命令，无需重复启动。
现有 `.env` 已更新，模型配置保留：

```dotenv
REDIS_URL=redis://127.0.0.1:6380/0
```

验收连接与模块能力：

```powershell
.\.venv\Scripts\python.exe scripts/check_redis.py
.\.venv\Scripts\python.exe scripts/check_checkpoint.py
```

应看到 connection、RedisJSON、Redis Search 三项 PASS。
检查点脚本进一步验证索引初始化、写入、重连读取和本次测试数据清理。
业务已接入同一检查点组件，每个会话使用独立 `thread_id`。保留时间沿用原项目：60 分钟，读取时刷新。
完整安装说明、数据位置及开发版运行限制见 [本地 Redis 说明](docs/local-redis.md)。
`compose.yaml` 仅保留为可选环境示例，当前流程不使用它。

## PostgreSQL 与建表

需要 Python 3.12、PostgreSQL，以及支持 JSON 和 Search 命令的 Redis。先创建虚拟环境，安装下文依赖，并复制 `.env.example` 为 `.env`，填写自己的配置。

```powershell
python -m venv .venv
Copy-Item .env.example .env
```

在 PostgreSQL 中提前创建 `echomind_db`，依次执行 [用户和知识库建表脚本](backend/sql/001_init.sql)、[文件信息建表脚本](backend/sql/002_file_metadata.sql)。如果已配置 psql 命令：

```powershell
psql -h 127.0.0.1 -U postgres -d echomind_db -f backend/sql/001_init.sql
psql -h 127.0.0.1 -U postgres -d echomind_db -f backend/sql/002_file_metadata.sql
```

应用启动只初始化连接池，不执行建表。本学习版不设置外键，由业务代码维护关联关系；初始化脚本不会自动迁移已有表结构。

在 `.env` 中填写自己的数据库连接信息：

```dotenv
DATABASE_URL=postgresql://postgres:your_password@127.0.0.1:5432/echomind_db
```

密码中有特殊字符时需要 URL 编码。配置 `.env`、虚拟环境、数据库数据、上传原件和日志均不提交到仓库。

## 启动

Windows 下，完成 PostgreSQL 安装和本地 Redis 程序准备后，可以双击项目根目录的 `start_databases.bat`，或在终端执行：

```powershell
.\start_databases.bat
```

脚本检查并复用已经运行的服务，必要时启动 `postgresql-x64-17` 和项目 Redis。Redis 在后台运行，日志位于 `.local/redis-data/`。PostgreSQL 服务停止且当前账号没有启动权限时，右键 BAT 选择“以管理员身份运行”。此脚本只启动数据库，不启动前后端；终端自动化运行可传 `--no-pause`。

在项目根目录的 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-frontend.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.txt
```

在第一个终端启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

在第二个终端启动前端：

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py
```

打开 http://localhost:8501 。模型调用需要项目根目录的 `.env`，已有配置会沿用；新建时参考 `.env.example`：

```dotenv
OPENAI_API_KEY=你的服务商密钥
OPENAI_API_BASE=服务商提供的兼容接口基础地址
OPENAI_MODEL=你已开通的模型名称
```

基础地址通常由服务商指定，不要把完整的 `/chat/completions` 路径填进去。
不要把密钥提交到仓库。修改 `.env` 后重启后端。
后端接口文档：http://127.0.0.1:8000/docs 。

## 一次请求怎么经过前后端与模型

```text
聊天输入 + session_id → request_reply() → POST /stream_chat → agent.astream()
        → Redis 恢复同一 thread_id 的历史 → 模型逐步回答、图保存执行状态
        → 逐行 JSON answer 事件 → 页面更新占位区域 → 完整回答保存到消息列表
```

请求 JSON：

```json
{
  "message": "你好",
  "knowledge_base": "默认知识库",
  "user_id": 1,
  "session_id": "ce87594d-b941-4ac5-bc8c-430258e74da7"
}
```

`/chat` 的响应 JSON 包含 `answer` 和 `session_id`。`/stream_chat` 返回每行一个 JSON 对象，`type=answer` 携带文本，`type=error` 表示生成失败，并非标准 SSE 帧格式。
同一会话继续提问时重复使用相同 `session_id`。流式调用建议显式传入会话 UUID；省略时会创建新会话，但流中当前不回传生成的 ID。
后端校验非空消息（最多 4000 字符）、知识库名称（最多 50 字符）与会话 UUID。
知识库创建和查询已接入 PostgreSQL；聊天中的知识库名称仍只作为上下文传入，尚未用于文档检索。
默认后端地址为 `http://127.0.0.1:8000`，需要更改时可在启动前端的终端中设置 `ECHOMIND_API_URL` 环境变量。

## 当前可体验

- 创建知识库写入 PostgreSQL，页面从后端加载知识库名称。
- 发送本轮问题及会话 ID，Agent 自动从 Redis 恢复历史并调用模型。
- 清空对话时生成新的会话 ID；同一会话切换知识库保留聊天记录与上下文。
- 选择 PDF、DOCX、TXT、Markdown 文件，添加到演示列表，按内容去重并移除。

前端文档按钮目前仍只记录名称、大小和 SHA-256，不上传正文；后端已独立提供真实上传与查询接口，可用 Swagger 验证。回复由模型生成，尚未使用文档检索。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/create_knowledge_base` | JSON 创建知识库 |
| GET | `/get_knowledge_bases` | 按 user_id 查询知识库 |
| POST | `/document_upload` | multipart 表单上传 file、knowledge_base_id、user_id |
| GET | `/get_knowledge_base_files` | 按 knowledge_base_id 和 user_id 查询文件 |

后端上传支持 PDF、DOCX、TXT、MD，单文件最多 20 MB。原件保存在 `.local/uploads/files/{SHA-256}`，元数据保存在 PostgreSQL。同一用户、同一知识库下相同内容仅登记一次。磁盘与数据库不是跨资源事务，登记失败可能留下待清理的原件；当前文件保存成功不代表已解析或建立索引。
前端只发送本轮问题；Agent 从检查点中恢复历史后，再把上下文交给模型。
页面展示用的消息与文档演示数据在 `st.session_state`；知识库名称从 PostgreSQL 加载，后端 Agent 状态保存在 Redis。`thread_id=echomind:{user_id}:{session_id}`，知识库不参与会话身份计算。
刷新页面会产生新会话，当前还未实现从后端加载旧会话列表与消息。
清空会话仅切换新 ID，不立即删除旧检查点；旧数据按 TTL 到期清理。

## 按这个顺序读代码

1. `frontend/app.py` 的“页面状态”：页面需要保存哪些数据。
2. “侧栏”：控件如何读取和改变状态。
3. “聊天区”：如何从消息列表绘制对话，以及如何处理一次输入。
4. `request_reply()`：发送 HTTP 请求、检查状态码、读取回复。
5. `backend/main.py`：创建 FastAPI 应用，注册路由。
6. `backend/api.py`：HTTP 路由与错误响应；`schemas.py` 定义数据结构。
7. `backend/agent.py`：create_agent、thread_id、会话上下文与消息调用。
8. `backend/config.py`：系统提示词与原项目的检查点 TTL 配置。
9. `backend/main.py` 的 lifespan：检查点连接在整个应用运行期间有效。
10. `backend/llm.py`：读取 `.env`，创建模型客户端，并在应用关闭时释放连接。

Streamlit 控件触发交互后，脚本通常会从头执行。`st.session_state` 保留跨次执行的数据，
`st.rerun()` 让刚修改的数据立即反映在页面上。它是页面状态，后面会分别加入后端会话状态与长期记忆。

## 本阶段验收

1. 启动本地 Redis 与两个服务，先清空旧版页面对话，发送“本次会话的测试代号是蓝鲸42”。
2. 再问“本次会话的测试代号是什么？”，应取回蓝鲸42。
3. 创建“技术资料”，在同一会话切换到该知识库，测试代号和页面聊天记录应继续保留。
4. 清空对话后再问，不应带入旧会话历史。
5. 保持页面连接，重启后端，再使用原会话提问，Redis 中未过期的状态应能恢复。
6. 页面文档演示列表仍可添加、去重和移除；通过 Swagger 上传文件并查询，应能看到 PostgreSQL 中的真实文件记录，但尚未用于回答。

自动回归测试需要已配置的真实 PostgreSQL、兼容的 Redis 和模型配置，使用确定性模型验证回答，无需付费模型 API 调用：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

本阶段的核心代码与原项目差异说明见 [多轮对话](docs/conversation.md)。

下一步：接入前端真实文档上传和文件列表，再实现文档解析、父子分块、向量检索、Agent 检索工具与长期记忆。

参考项目：https://github.com/Dreamt0511/EchoMind
