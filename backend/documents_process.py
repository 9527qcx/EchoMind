"""文档接收与处理，当前先实现临时保存和哈希计算。"""

import hashlib
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile
import aiofiles.os

MAX_FILE_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class UploadTooLargeError(ValueError):
    """上传文件超过大小限制。"""


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
