"""读取已有父块，生成子块并验证 Milvus 入库。"""

import argparse
import asyncio
import hashlib
import json
import os

from langchain_core.documents import Document
from pymilvus import AsyncMilvusClient

from backend.documents_process import DocumentProcessor
from backend.embeddings import get_embeddings
from backend.knowledge_base_manager import KnowledgeBaseManager
from backend.postgresql_client import PostgreSQLParentClient


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file_hash")
    parser.add_argument("--knowledge-base", default="默认知识库")
    parser.add_argument("--user-id", type=int, default=1)
    args = parser.parse_args()

    if args.user_id < 1:
        parser.error("用户 ID 必须是正整数。")

    collection_name = os.getenv(
        "MILVUS_KNOWLEDGE_COLLECTION",
        "echomind_knowledge_base",
    )
    dense_dim = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    postgres = PostgreSQLParentClient()
    milvus = None

    try:
        await postgres.init_pool()

        async with postgres.pool.acquire(timeout=5) as conn:
            parents = await conn.fetch(
                """
                SELECT parent_id, text, file_name
                FROM parent_chunks
                WHERE file_hash = $1
                  AND knowledge_base_id = $2
                  AND user_id = $3
                ORDER BY parent_id
                """,
                args.file_hash,
                args.knowledge_base,
                args.user_id,
            )

        if not parents:
            raise ValueError("没有找到父块，请先完成父块入库。")

        milvus = AsyncMilvusClient(
            uri=os.environ["MILVUS_URI"],
            timeout=30,
        )
        await milvus.load_collection(collection_name)

        # json.dumps 将字符串转换为安全的带引号表达式。
        filter_expr = (
            f"user_id == {args.user_id} "
            f"and knowledge_base_id == "
            f"{json.dumps(args.knowledge_base, ensure_ascii=False)} "
            f"and file_hash == {json.dumps(args.file_hash)}"
        )

        existing = await milvus.query(
            collection_name=collection_name,
            filter=filter_expr,
            output_fields=["parent_id"],
            limit=1,
        )

        if existing:
            print("该文件已有子块，跳过本次验证写入。")
            return

        processor = DocumentProcessor()
        children = []

        for row in parents:
            parent_document = Document(
                page_content=row["text"],
                metadata={
                    "parent_id": row["parent_id"],
                    "file_hash": args.file_hash,
                    "knowledge_base_id": args.knowledge_base,
                    "user_id": args.user_id,
                    "file_name": row["file_name"],
                },
            )

            chunks = await asyncio.to_thread(
                processor.child_splitter.split_documents,
                [parent_document],
            )

            for chunk in chunks:
                chunk.metadata["child_chunk_hash"] = hashlib.sha256(
                    chunk.page_content.encode("utf-8")
                ).hexdigest()

            children.extend(chunks)

        manager = KnowledgeBaseManager(
            client=milvus,
            embeddings=get_embeddings(),
            collection_name=collection_name,
            dense_dim=dense_dim,
        )

        result = await manager.add_chunks_batch(
            knowledge_base_id=args.knowledge_base,
            chunks=children,
            user_id=args.user_id,
        )

        print("读取父块数：", len(parents))
        print("生成子块数：", len(children))
        print("成功写入子块数：", result["insert_count"])

        saved = await milvus.query(
            collection_name=collection_name,
            filter=filter_expr,
            output_fields=["parent_id"],
            limit=1,
        )

        parent_ids = {row["parent_id"] for row in parents}

        if not saved or saved[0]["parent_id"] not in parent_ids:
            raise RuntimeError("子块读回或父块关联验证失败。")

        print("子块读回成功，parent_id 对应已有父块。")

    finally:
        try:
            if milvus is not None:
                await milvus.close()
        finally:
            await postgres.close()


if __name__ == "__main__":
    asyncio.run(main())