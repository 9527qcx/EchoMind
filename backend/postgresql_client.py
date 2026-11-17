"""PostgreSQL 客户端：管理连接池，后续添加知识库与文档操作。"""

import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class PostgreSQLParentClient:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")

        if not self.dsn:
            raise ValueError("请在项目根目录的 .env 中配置 DATABASE_URL。")

        self.pool: asyncpg.Pool | None = None

    async def init_pool(self) -> None:
        """创建连接池。"""
        if self.pool is not None:
            return

        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=1,
            max_size=5,
            timeout=5,
            command_timeout=30,
            server_settings={"timezone": "Asia/Shanghai"},
        )



    async def ping(self) -> bool:
        """执行简单查询，验证数据库连接。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        async with self.pool.acquire(timeout=5) as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1

    async def create_knowledge_base(
        self,
        knowledge_base_id: str,
        user_id: int,
    ) -> dict[str, bool | str]:
        """确保用户存在，并为用户创建知识库。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        knowledge_base_id = knowledge_base_id.strip()

        if not knowledge_base_id:
            raise ValueError("知识库名称不能为空。")

        if user_id < 1:
            raise ValueError("用户 ID 必须是正整数。")

        async with self.pool.acquire(timeout=5) as conn:
            async with conn.transaction():
                # 用户不存在时创建；已存在则保留。
                await conn.execute(
                    """
                    INSERT INTO users (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id,
                )

                # 利用联合主键处理重复创建。
                created_id = await conn.fetchval(
                    """
                    INSERT INTO knowledge_bases (
                        knowledge_base_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (knowledge_base_id, user_id)
                    DO NOTHING
                    RETURNING knowledge_base_id
                    """,
                    knowledge_base_id,
                    user_id,
                )

        if created_id is None:
            return {
                "success": False,
                "message": "该知识库已存在。",
                "knowledge_base_id": knowledge_base_id,
            }

        return {
            "success": True,
            "message": "知识库创建成功。",
            "knowledge_base_id": created_id,
        }

    async def get_user_knowledge_bases(self, user_id: int) -> dict:
        """查询指定用户的知识库列表。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        async with self.pool.acquire(timeout=5) as conn:
            rows = await conn.fetch(
                """
                SELECT knowledge_base_id
                FROM knowledge_bases
                WHERE user_id = $1
                ORDER BY created_at DESC, knowledge_base_id ASC
                """,
                user_id,
            )

        knowledge_bases = [
            row["knowledge_base_id"]
            for row in rows
        ]

        return {
            "success": True,
            "message": "知识库列表查询成功。",
            "knowledge_bases": knowledge_bases,
            "count": len(knowledge_bases),
        }

    async def add_file_metadata(
        self,
        file_hash: str,
        file_name: str,
        knowledge_base_id: str,
        user_id: int,
    ) -> bool:
        """登记文件；新增返回 True，重复返回 False。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        async with self.pool.acquire(timeout=5) as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO users (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id,
                )

                await conn.execute(
                    """
                    INSERT INTO knowledge_bases (
                        knowledge_base_id,
                        user_id
                    )
                    VALUES ($1, $2)
                    ON CONFLICT (knowledge_base_id, user_id)
                    DO NOTHING
                    """,
                    knowledge_base_id,
                    user_id,
                )

                inserted_hash = await conn.fetchval(
                    """
                    INSERT INTO file_metadata (
                        file_hash,
                        file_name,
                        knowledge_base_id,
                        user_id
                    )
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (
                        file_hash,
                        knowledge_base_id,
                        user_id
                    )
                    DO NOTHING
                    RETURNING file_hash
                    """,
                    file_hash,
                    file_name,
                    knowledge_base_id,
                    user_id,
                )

        return inserted_hash is not None

    async def get_knowledge_base_files(
        self,
        knowledge_base_id: str,
        user_id: int,
    ) -> dict:
        """查询指定用户、指定知识库的文件列表。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        async with self.pool.acquire(timeout=5) as conn:
            rows = await conn.fetch(
                """
                SELECT file_hash, file_name, uploaded_at
                FROM file_metadata
                WHERE knowledge_base_id = $1
                  AND user_id = $2
                ORDER BY uploaded_at DESC, file_hash ASC
                """,
                knowledge_base_id,
                user_id,
            )

        files = [dict(row) for row in rows]

        return {
            "success": True,
            "message": "文件列表查询成功。",
            "count": len(files),
            "files": files,
        }

    async def delete_file(
        self,
        file_hash: str,
        knowledge_base_id: str,
        user_id: int,
    ) -> bool:
        """移除指定用户、指定知识库中的文件记录。"""
        if self.pool is None:
            raise RuntimeError("PostgreSQL 连接池尚未初始化。")

        async with self.pool.acquire(timeout=5) as conn:
            deleted_hash = await conn.fetchval(
                """
                DELETE FROM file_metadata
                WHERE file_hash = $1
                  AND knowledge_base_id = $2
                  AND user_id = $3
                RETURNING file_hash
                """,
                file_hash,
                knowledge_base_id,
                user_id,
            )

        return deleted_hash is not None

    async def close(self) -> None:
        """关闭连接池，释放数据库连接。"""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
