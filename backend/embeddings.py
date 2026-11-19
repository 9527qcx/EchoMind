"""读取配置，创建百炼文本向量客户端。"""

import os
from functools import lru_cache
from pathlib import Path

import dashscope
from dotenv import load_dotenv
from langchain_community.embeddings import DashScopeEmbeddings


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@lru_cache(maxsize=1)
def get_embeddings() -> DashScopeEmbeddings:
    config_names = (
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_API_BASE",
        "EMBEDDING_MODEL",
    )

    missing = [
        name
        for name in config_names
        if not os.getenv(name, "").strip()
    ]

    if missing:
        raise ValueError(
            f"请在 .env 中配置：{', '.join(missing)}"
        )

    dashscope.base_http_api_url = (
        os.environ["DASHSCOPE_API_BASE"].strip().rstrip("/")
    )

    return DashScopeEmbeddings(
        model=os.environ["EMBEDDING_MODEL"].strip(),
        dashscope_api_key=os.environ["DASHSCOPE_API_KEY"].strip(),
        max_retries=2,
    )
