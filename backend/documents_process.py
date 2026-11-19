"""文档接收与处理，当前先实现临时保存和哈希计算。"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend import config
import hashlib
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile
import aiofiles.os
import asyncio

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyMuPDFLoader,
    TextLoader,
)

MAX_FILE_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class UploadTooLargeError(ValueError):
    """上传文件超过大小限制。"""

class DocumentProcessor:
    """负责加载文档，后续继续加入分块和入库流程。"""
    def __init__(self):
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.parent_chunk_size,
            chunk_overlap=config.parent_chunk_overlap,
            separators=config.separators,
            add_start_index=False,
        )
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.child_chunk_size,
            chunk_overlap=config.child_chunk_overlap,
            separators=config.separators,
            add_start_index=False,
        )

    async def load_documents(
        self,
        file_path: Path,
        filename: str,
    ) -> list[Document]:
        """读取文件，统一返回 LangChain Document 列表。"""
        if not file_path.is_file():
            raise FileNotFoundError("找不到已上传的原文件。")

        return await asyncio.to_thread(
            self._load_documents_sync,
            file_path,
            filename,
        )

    def _load_documents_sync(
        self,
        file_path: Path,
        filename: str,
    ) -> list[Document]:
        # 根据原文件名判断类型，不能使用磁盘上的哈希文件名。
        suffix = Path(filename).suffix.lower()

        if suffix == ".pdf":
            loader = PyMuPDFLoader(str(file_path))
        elif suffix == ".docx":
            loader = Docx2txtLoader(str(file_path))
        elif suffix in {".txt", ".md"}:
            loader = TextLoader(
                str(file_path),
                encoding="utf-8-sig",
            )
        else:
            raise ValueError(f"不支持解析的文件类型：{suffix}")

        documents = loader.load()

        # 保留有文本内容的文档对象。
        documents = [
            document
            for document in documents
            if document.page_content.strip()
        ]

        if not documents:
            raise ValueError(
                "未提取到文本。文件可能为空，或是需要 OCR 的扫描件。"
            )

        for document in documents:
            document.metadata["file_name"] = filename

        return documents

    def split_documents(
        self,
        documents: list[Document],
        filename: str,
        file_hash: str,
        knowledge_base_id: str,
        user_id: int,
    ) -> tuple[list[dict], list[Document]]:
        """生成父块记录，以及携带父块关联信息的子块。"""
        parent_chunks = self.parent_splitter.split_documents(documents)

        parent_data_list = []
        all_child_items = []

        for parent_index, parent_chunk in enumerate(parent_chunks):
            parent_id = str(uuid4())

            parent_data_list.append({
                "parent_id": parent_id,
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id,
                "text": parent_chunk.page_content,
                "file_name": filename,
                "file_hash": file_hash,
            })

            child_chunks = self.child_splitter.split_documents(
                [parent_chunk]
            )

            for child_chunk in child_chunks:
                child_hash = hashlib.sha256(
                    child_chunk.page_content.encode("utf-8")
                ).hexdigest()

                child_chunk.metadata.update({
                    "parent_id": parent_id,
                    "parent_index": parent_index,
                    "file_name": filename,
                    "file_hash": file_hash,
                    "child_chunk_hash": child_hash,
                    "knowledge_base_id": knowledge_base_id,
                    "user_id": user_id,
                })

                all_child_items.append(child_chunk)

        return parent_data_list, all_child_items

class TempDocumentProcessor:
    def __init__(self):
        self.temp_dir = (
            Path(__file__).resolve().parents[1]
            / ".local"
            / "uploads"
            / "tmp"
        )
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        file: UploadFile,
    ) -> tuple[Path, str]:
        """保存上传内容，返回临时文件路径和 SHA-256。"""
        temp_path = self.temp_dir / f"{uuid4().hex}.upload"
        sha256 = hashlib.sha256()
        total_size = 0
        completed = False

        try:
            async with aiofiles.open(temp_path, "wb") as target:
                while True:
                    chunk = await file.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise UploadTooLargeError("单个文件不能超过 20 MB。")

                    sha256.update(chunk)
                    await target.write(chunk)

            if total_size == 0:
                raise ValueError("不能上传空文件。")

            completed = True
            return temp_path, sha256.hexdigest()

        finally:
            if not completed:
                temp_path.unlink(missing_ok=True)

    async def persist_upload(
        self,
        temp_path: Path,
        file_hash: str,
    ) -> Path:
        """将完整上传文件移入原文件目录。"""
        storage_dir = self.temp_dir.parent / "files"
        await aiofiles.os.makedirs(storage_dir, exist_ok=True)

        stored_path = storage_dir / file_hash
        await aiofiles.os.replace(temp_path, stored_path)

        return stored_path
