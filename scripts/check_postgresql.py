"""验证 PostgreSQL 连接池，不修改业务数据。"""

import asyncio

from backend.postgresql_client import PostgreSQLParentClient


async def main() -> None:
    client = PostgreSQLParentClient()

    try:
        await client.init_pool()

        if not await client.ping():
            raise RuntimeError("数据库连接验证失败。")

        print("PASS: PostgreSQL connection pool")
        print("PASS: SELECT 1")
        result = await client.get_knowledge_base_files(
            knowledge_base_id="java资料",
            user_id=1,
        )
        print(result)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())