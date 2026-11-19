"""验证问题检索、父块召回，不生成聊天回答。"""

import argparse
import asyncio
import os

from pymilvus import AsyncMilvusClient

from backend.embeddings import get_embeddings
from backend.knowledge_base_manager import KnowledgeBaseManager
from backend.postgresql_client import PostgreSQLParentClient


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--knowledge-base", default="默认知识库")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    collection_name = os.getenv(
        "MILVUS_KNOWLEDGE_COLLECTION",
        "echomind_knowledge_base",
    )
    dense_dim = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    postgres = PostgreSQLParentClient()
    milvus = AsyncMilvusClient(
        uri=os.environ["MILVUS_URI"],
        timeout=30,
    )

    try:
        await milvus.load_collection(collection_name)

        manager = KnowledgeBaseManager(
            client=milvus,
            embeddings=get_embeddings(),
            collection_name=collection_name,
            dense_dim=dense_dim,
        )

        parent_ids = await manager.hybrid_retrieval_knowledge_base(
            query=args.query,
            knowledge_base_id=args.knowledge_base,
            user_id=args.user_id,
            top_k=args.top_k,
        )

        print("召回父块 ID：", parent_ids)

        if not parent_ids:
            print("未检索到相关子块。")
            return

        await postgres.init_pool()

        texts = await postgres.get_parents(
            parent_ids=parent_ids,
            knowledge_base_id=args.knowledge_base,
            user_id=args.user_id,
        )

        if not texts:
            raise RuntimeError(
                "子块已命中，但对应父块不存在，请检查两边的数据关联。"
            )

        print("读取父块数量：", len(texts))

        for index, text in enumerate(texts, start=1):
            print(f"\n父块 {index}：")
            print(text[:500])

    finally:
        try:
            await milvus.close()
        finally:
            await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())