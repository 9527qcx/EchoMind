"""读取配置并创建模型客户端。"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import DefaultAsyncHttpxClient, DefaultHttpxClient


# 固定从项目根目录读取，启动命令所在目录不会影响 .env 的位置。
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ModelConfigError(ValueError):
    """缺少模型连接配置。"""


@lru_cache(maxsize=1)
def get_model() -> ChatOpenAI:
    """首次调用时创建客户端，后续请求复用同一个客户端。"""
    config_names = ("OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL")
    missing = [name for name in config_names if not os.getenv(name, "").strip()]
    if missing:
        raise ModelConfigError(f"请在项目根目录的 .env 中配置：{', '.join(missing)}")

    return ChatOpenAI(
        api_key=os.environ["OPENAI_API_KEY"].strip(),
        base_url=os.environ["OPENAI_API_BASE"].strip(),
        model=os.environ["OPENAI_MODEL"].strip(),
        use_responses_api=False,
        timeout=45,
        max_retries=0,
        max_tokens=512,
        # 显式创建 HTTP 客户端，使连接随应用生命周期关闭和重建。
        http_client=DefaultHttpxClient(),
        http_async_client=DefaultAsyncHttpxClient(),
    )


async def close_model() -> None:
    """应用关闭时释放 HTTP 连接，避免下一次启动复用旧事件循环的客户端。"""
    if not get_model.cache_info().currsize: # pylint: disable=too-many-function-args
        return
    model = get_model()
    try:
        try:
            await model.root_async_client.close()
        finally:
            model.root_client.close()
    finally:
        get_model.cache_clear()
