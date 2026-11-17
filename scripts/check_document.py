"""读取已上传原文件，验证文本解析，不修改数据库。"""

import argparse
import asyncio
import re
from pathlib import Path

from backend.documents_process import DocumentProcessor


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file_hash", help="数据库中的文件哈希")
    parser.add_argument("filename", help="数据库中的原文件名")
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


if __name__ == "__main__":
    asyncio.run(main())