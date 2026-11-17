# 本地 Redis：Windows 原生方式，无需 Docker

本项目使用 Memurai for Redis 8.2.0，提供 RedisJSON 与 RediSearch。
它替代的是 Redis 服务的本地运行环境，应用层继续使用原项目的 `AsyncRedisSaver`。

官方来源：https://www.memurai.com/get-memurai
功能说明：https://www.memurai.com/blog/memurai-for-redis-8-redis-8-2-compatible-ai-and-performance-now-production-ready-on-windows

## 当前安装

- 官方 MSI 与主程序的 Authenticode 签名均验证有效，签名者为 Janea Systems, Inc.。
- 安装包位于 `.local/downloads/Memurai-for-Redis-v8.2.0.msi`。
- 通过 MSI 的管理解压功能，将程序释放到 `.local/memurai/Memurai/`。
- 没有注册 Windows 服务，也没有添加防火墙规则或修改已有的 Redis 5。
- 项目实例仅监听 `127.0.0.1:6380`，原 Redis 5 继续使用 6379。
- 配置由启动脚本生成到 `.local/memurai/echomind.conf`。
- 数据与日志位于 `.local/redis-data/`，启用了 AOF 持久化。
- `.local/` 已加入 `.gitignore`，不提交程序包、日志、数据与附带的开发许可证。

开发版适合本项目学习测试，官方规定连续运行 10 天后需要重新启动。

## 启动与停止

在项目根目录运行，保持终端打开：

```powershell
.\.venv\Scripts\python.exe scripts/start_redis.py
```

按 Ctrl+C 停止。若提示 6380 已占用，先运行检查脚本，确认是否已经启动；不要重复启动实例。
运行环境为工具沙箱时，原生进程可能需要在沙箱外启动；普通用户终端不受该沙箱限制。

项目根目录 `.env` 已配置：

```dotenv
REDIS_URL=redis://127.0.0.1:6380/0
```

## 验收

```powershell
.\.venv\Scripts\python.exe scripts/check_redis.py
.\.venv\Scripts\python.exe scripts/check_checkpoint.py
```

第一条检查连接、JSON 与 Search。第二条使用原项目版本的 `langgraph-checkpoint-redis==0.4.0`，
初始化索引、写入检查点、关闭连接后重新读取，并清理本次随机会话的测试数据。
检查点验证会在该独立实例上创建组件所需的索引。

这些检查证明运行环境支持检查点，不代表聊天接口已经接入多轮记忆。

## 在新环境重新准备程序

从官方页面下载 **Memurai for Redis 8.2.0 Developer Edition** 的 Windows MSI，
放到 `.local/downloads/Memurai-for-Redis-v8.2.0.msi`。
解压前用 PowerShell 检查签名：

```powershell
Get-AuthenticodeSignature .local\downloads\Memurai-for-Redis-v8.2.0.msi
```

应显示 `Status: Valid`，签名者为 Janea Systems, Inc.。
然后在具有 Windows Installer 所需权限的 PowerShell 中，执行管理解压：

```powershell
$installerPath = (Resolve-Path .local\downloads\Memurai-for-Redis-v8.2.0.msi).Path
$targetPath = Join-Path (Get-Location).Path '.local\memurai'
msiexec.exe /a $installerPath /qn "TARGETDIR=$targetPath"
```

确认 `.local/memurai/Memurai/` 中有 `memurai.exe`、`rejson.dll`、`redisearch.dll` 和随包提供的开发许可证后，
再运行启动与验收命令。管理解压与安装为系统服务是两个不同操作，这里只使用解压。
