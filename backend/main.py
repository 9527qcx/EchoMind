"""应用入口，与原项目一样通过 include_router 注册业务接口。"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from backend.agent import create_chat_agent
from backend.api import router
from backend.config import TTL_CONFIG
from backend.llm import close_model
from backend.postgresql_client import PostgreSQLParentClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时准备连接与 Agent，退出时释放资源。"""
    postgresql_client = PostgreSQLParentClient()

    try:
        await postgresql_client.init_pool()
        app.state.postgresql_client = postgresql_client

        redis_url = os.getenv(
            "REDIS_URL",
            "redis://127.0.0.1:6380/0",
        )

        async with AsyncRedisSaver.from_conn_string(
            redis_url=redis_url,
            ttl=TTL_CONFIG,
            connection_args={
                "socket_connect_timeout": 3,
                "socket_timeout": 5,
            },
        ) as checkpointer:
            await checkpointer.asetup()
            app.state.checkpointer = checkpointer

            try:
                app.state.agent = create_chat_agent(checkpointer)
                yield
            finally:
                if hasattr(app.state, "agent"):
                    del app.state.agent
                del app.state.checkpointer

    finally:
        try:
            await postgresql_client.close()
        finally:
            await close_model()


app = FastAPI(
    title="EchoMind 接口文档",
    description="提供聊天、知识库和长期记忆功能。",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.include_router(router)
