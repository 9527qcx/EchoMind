"""读取已上传原文件，验证文本解析，不修改数据库。"""

import argparse
import asyncio
import re
from pathlib import Path
from backend.postgresql_client import PostgreSQLParentClient
from backend.documents_process import DocumentProcessor


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file_hash", help="数据库中的文件哈希")
    parser.add_argument("filename", help="数据库中的原文件名")
    parser.add_argument("--knowledge-base", default="默认知识库")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument(
        "--save-parents",
        action="store_true",
        help="将本次分块生成的父块保存到 PostgreSQL",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{64}", args.file_hash):
        parser.error("file_hash 必须是 64 位小写十六进制字符串。")

    file_path = (
        Path(__file__).resolve().parents[1]
        / ".local"
        / "uploads"
        / "files"
        / args.file_hash
    )

    processor = DocumentProcessor()
    documents = await processor.load_documents(
        file_path=file_path,
        filename=args.filename,
    )

    print(f"文档对象数：{len(documents)}")
    print(f"总字符数：{sum(len(doc.page_content) for doc in documents)}")
    print("第一份文档的前 300 个字符：")
    print(documents[0].page_content[:300])

    parent_data_list, child_documents = await asyncio.to_thread(
        processor.split_documents,
        documents,
        filename=args.filename,
        file_hash=args.file_hash,
        knowledge_base_id=args.knowledge_base,
        user_id=args.user_id,
    )

    print(f"父块数量：{len(parent_data_list)}")
    print(f"子块数量：{len(child_documents)}")

    if parent_data_list:
        print("第一个父块 ID：", parent_data_list[0]["parent_id"])
        print("第一个父块字符数：", len(parent_data_list[0]["text"]))

    if child_documents:
        first_child = child_documents[0]
        print("第一个子块字符数：", len(first_child.page_content))
        print("第一个子块关联的父块：", first_child.metadata["parent_id"])

    if args.save_parents:
        await save_parent_chunks(
            parent_data_list=parent_data_list,
            args=args,
        )


async def save_parent_chunks(
    parent_data_list: list[dict],
    args: argparse.Namespace,
) -> None:
    client = PostgreSQLParentClient()

    count_sql = """
        SELECT COUNT(*)
        FROM parent_chunks
        WHERE file_hash = $1
          AND knowledge_base_id = $2
          AND user_id = $3
    """
    scope = (
        args.file_hash,
        args.knowledge_base,
        args.user_id,
    )

    try:
        await client.init_pool()

        async with client.pool.acquire(timeout=5) as conn:
            existing_count = await conn.fetchval(
                count_sql,
                *scope,
            )

        # 验证脚本重复运行时，避免再次生成一批父块。
        if existing_count > 0:
            print(f"已有 {existing_count} 个父块，跳过保存。")
            return

        await client.add_parent_chunk_batch(
            parent_data_list=parent_data_list,
            user_id=args.user_id,
        )

        async with client.pool.acquire(timeout=5) as conn:
            saved_count = await conn.fetchval(
                count_sql,
                *scope,
            )

        print(f"保存后，数据库中该文件的父块数：{saved_count}")

    finally:
        await client.close()



if __name__ == "__main__":
    asyncio.run(main())