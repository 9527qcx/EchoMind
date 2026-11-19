"""验证本地 Milvus 连接，不修改集合或文档数据。"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from pymilvus import AsyncMilvusClient


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main() -> None:
    uri = os.getenv("MILVUS_URI")

    if not uri:
        raise ValueError("请在 .env 中配置 MILVUS_URI。")

    client = AsyncMilvusClient(
        uri=uri,
        timeout=5,
    )

    try:
        collections = await client.list_collections(timeout=5)

        print("Milvus 连接成功。")
        print("当前集合：", collections)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())