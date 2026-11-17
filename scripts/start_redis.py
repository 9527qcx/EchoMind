"""在 Windows 前台运行项目独立的 Memurai for Redis 8.2（无需 Docker）。"""

from pathlib import Path
import socket
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PORT = 6380


def main() -> int:
    install_dir = ROOT / ".local" / "memurai" / "Memurai"
    executable = install_dir / "memurai.exe"
    required = (executable, install_dir / "rejson.dll", install_dir / "redisearch.dll")
    if not all(path.is_file() for path in required):
        print("Local Redis binaries are missing. See docs/local-redis.md for setup.")
        return 1

    # 启动新实例前检查端口，避免和正在运行的服务冲突。
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", PORT))
    except OSError:
        print(f"Port {PORT} is already in use. Run scripts/check_redis.py to check that service.")
        return 1

    data_dir = ROOT / ".local" / "redis-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / ".local" / "memurai" / "echomind.conf"
    config_path.write_text(
        "\n".join(
            [
                "bind 127.0.0.1",
                "protected-mode yes",
                f"port {PORT}",
                f'license-file "{(install_dir / "memurai-license-dev.txt").as_posix()}"',
                f'loadmodule "{(install_dir / "rejson.dll").as_posix()}"',
                f'loadmodule "{(install_dir / "redisearch.dll").as_posix()}"',
                f'dir "{data_dir.as_posix()}"',
                "appendonly yes",
                "appendfsync everysec",
                'save ""',
                f'logfile "{(data_dir / "redis.log").as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Starting local Redis on 127.0.0.1:{PORT}. Press Ctrl+C to stop.", flush=True)
    try:
        return subprocess.run([str(executable), str(config_path)], cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
