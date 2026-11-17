"""使用原项目的 AsyncRedisSaver 验收检查点写入、重连读取与测试数据清理。"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.redis.aio import AsyncRedisSaver


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    thread_id = f"echomind-installation-check-{uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": [{"role": "user", "content": "installation check"}]}
    checkpoint["channel_versions"] = {"messages": "1"}
    ttl = {"default_ttl": 1}

    async with AsyncRedisSaver.from_conn_string(redis_url, ttl=ttl) as saver:
        await saver.asetup()
        print("PASS: AsyncRedisSaver index setup")
        saved_config = await saver.aput(
            config,
            checkpoint,
            {"source": "input", "step": 0, "parents": {}},
            {"messages": "1"},
        )
        print("PASS: checkpoint write")

    # 重新创建连接，确认数据保存在 Redis 中，而不是当前 Python 对象里。
    async with AsyncRedisSaver.from_conn_string(redis_url, ttl=ttl) as saver:
        await saver.asetup()
        try:
            restored = await saver.aget(saved_config)
            assert restored is not None, "Checkpoint was not found."
            assert restored["channel_values"] == checkpoint["channel_values"], "Checkpoint content differs."
            print("PASS: checkpoint read after reconnect")
        finally:
            # 只删除本次脚本用随机 thread_id 创建的测试数据。
            await saver.adelete_thread(thread_id)
            print("PASS: test checkpoint cleanup")


if __name__ == "__main__":
    asyncio.run(main())
