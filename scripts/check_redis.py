"""检查 AsyncRedisSaver 所需的 RedisJSON 和 Search 能力，不写入数据。"""

import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main() -> int:
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0")
    try:
        with Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3) as client:
            client.ping()
            print("PASS: Redis connection")
            # 查询随机键，不写入或输出现有数据。
            client.execute_command("JSON.GET", f"echomind:capability-check:{uuid4().hex}")
            print("PASS: RedisJSON")
            client.execute_command("FT._LIST")
            print("PASS: Redis Search")
    except RedisError:
        print("FAIL: Redis is unavailable, lacks JSON/Search, or access is denied.")
        print("Start the local instance with: .venv\\Scripts\\python.exe scripts/start_redis.py")
        print("Check REDIS_URL and verify the local server supports JSON.GET and FT._LIST.")
        print("A running Redis 5 server without these modules cannot use AsyncRedisSaver directly.")
        return 1
    print("Ready for the original project's AsyncRedisSaver.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
