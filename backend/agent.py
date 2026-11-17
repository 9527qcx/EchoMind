"""沿用原项目的 create_agent、Redis 检查点与 thread_id。"""

from langchain.agents import create_agent
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph.state import CompiledStateGraph

from backend.config import SYSTEM_PROMPT_DEFAULT
from backend.llm import get_model
from backend.schemas import ContextSchema

import json
from typing import AsyncGenerator

def create_chat_agent(checkpointer: AsyncRedisSaver) -> CompiledStateGraph:
    """每次应用启动创建一次，检查点连接在应用运行期间持续有效。"""
    return create_agent(
        model=get_model(),
        tools=[],  # 下一阶段逐项加入原项目的知识检索和记忆工具。
        system_prompt=SYSTEM_PROMPT_DEFAULT,
        context_schema=ContextSchema,
        checkpointer=checkpointer,
    )


def get_thread_id(user_id: int, session_id: str) -> str:
    # 用户和会话共同定位检查点；切换知识库不改变当前会话。
    return f"echomind:{user_id}:{session_id}"


async def get_agent_response(
    agent: CompiledStateGraph,
    user_message: str,
    knowledge_base_id: str,
    user_id: int,
    session_id: str,
) -> str:
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_message}]},
        {"configurable": {"thread_id": get_thread_id(user_id, session_id)}},
        context=ContextSchema(user_id=user_id, knowledge_base_id=knowledge_base_id),
    )
    # 历史消息由 checkpointer 从 Redis 恢复；前端只需要发送本轮问题。
    reply = result["messages"][-1]
    if not isinstance(reply.content, str) or not reply.content.strip():
        raise ValueError("模型未返回有效文本。")
    return reply.content

async def stream_agent_response(
    agent: CompiledStateGraph,
    user_message: str,
    knowledge_base_id: str,
    user_id: int,
    session_id: str,
) -> AsyncGenerator[str, None]:
    config = {
        "configurable": {
            "thread_id": get_thread_id(user_id, session_id),
        }
    }

    context = ContextSchema(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )

    async for message_chunk, metadata in agent.astream(
        {"messages": [{"role": "user", "content": user_message}]},
        config,
        context=context,
        stream_mode="messages",
    ):
        if metadata.get("langgraph_node") != "model":
            continue

        content = message_chunk.content

        if isinstance(content, str) and content:
            yield json.dumps(
                {"type": "answer", "content": content},
                ensure_ascii=False,
            ) + "\n"
