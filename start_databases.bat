@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem EchoMind local database launcher. No credentials are stored in this file.
set "ECHOMIND_ROOT=%~dp0"
set "ECHOMIND_PYTHON=%ECHOMIND_ROOT%.venv\Scripts\python.exe"
set "ECHOMIND_PG_SERVICE=postgresql-x64-17"
set "ECHOMIND_EXIT_CODE=0"
rem Health checks target the local Redis instance started by this launcher.
set "REDIS_URL=redis://127.0.0.1:6380/0"

pushd "%ECHOMIND_ROOT%" >nul
if errorlevel 1 (
    echo ERROR: Cannot open the project directory.
    if /I not "%~1"=="--no-pause" pause
    exit /b 1
)

echo === EchoMind local databases ===
echo.

if not exist "%ECHOMIND_PYTHON%" (
    echo ERROR: Project Python is missing: .venv\Scripts\python.exe
    echo Create the virtual environment and install requirements first.
    goto :failed
)

if not exist "scripts\start_redis.py" (
    echo ERROR: scripts\start_redis.py is missing.
    goto :failed
)

"%ECHOMIND_PYTHON%" -c "import dotenv; import redis" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Redis check dependencies are missing.
    echo Run .venv\Scripts\python.exe -m pip install -r requirements-backend.txt
    goto :failed
)

echo [1/2] Checking PostgreSQL service...
powershell.exe -NoLogo -NoProfile -NonInteractive -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "try {" ^
    "    $service = Get-Service -Name $env:ECHOMIND_PG_SERVICE;" ^
    "    if ($service.Status -ne 'Running') {" ^
    "        Start-Service -Name $service.Name;" ^
    "        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(30));" ^
    "    };" ^
    "    $info = Get-CimInstance Win32_Service | Where-Object { $_.Name -eq $env:ECHOMIND_PG_SERVICE };" ^
    "    $parts = $info.PathName.Split([char]34);" ^
    "    if ($parts.Length -gt 1) { $executable = $parts[1] } else { $executable = ($info.PathName -split '\s+', 2)[0] };" ^
    "    $ready = Join-Path (Split-Path -Parent $executable) 'pg_isready.exe';" ^
    "    if (-not (Test-Path -LiteralPath $ready)) { throw 'pg_isready.exe was not found next to the PostgreSQL service executable.' };" ^
    "    & $ready -h 127.0.0.1 -p 5432 -t 10;" ^
    "    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL is not ready on 127.0.0.1:5432.' };" ^
    "    Write-Host 'PASS: PostgreSQL is running on 127.0.0.1:5432.';" ^
    "} catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
    echo If starting the service was denied, right-click this BAT and choose Run as administrator.
    goto :failed
)

echo.
echo [2/2] Checking Redis with JSON and Search support...
"%ECHOMIND_PYTHON%" scripts\check_redis.py >nul 2>&1
if not errorlevel 1 goto :redis_ready

rem A listening but incompatible instance must not be started over.
"%ECHOMIND_PYTHON%" -c "import socket; s=socket.socket(); s.settimeout(2); result=s.connect_ex(('127.0.0.1',6380)); s.close(); raise SystemExit(0 if result==0 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: Port 6380 is occupied, but the Redis capability check failed.
    "%ECHOMIND_PYTHON%" scripts\check_redis.py
    goto :failed
)

if not exist ".local\redis-data" (
    mkdir ".local\redis-data"
    if errorlevel 1 goto :failed
)

echo Starting project Redis in the background...
powershell.exe -NoLogo -NoProfile -NonInteractive -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "try {" ^
    "    $outputLog = Join-Path $env:ECHOMIND_ROOT '.local\redis-data\launcher.out.log';" ^
    "    $errorLog = Join-Path $env:ECHOMIND_ROOT '.local\redis-data\launcher.err.log';" ^
    "    $process = Start-Process -FilePath $env:ECHOMIND_PYTHON -ArgumentList @('scripts/start_redis.py') -WorkingDirectory $env:ECHOMIND_ROOT -WindowStyle Hidden -RedirectStandardOutput $outputLog -RedirectStandardError $errorLog -PassThru;" ^
    "    Write-Host ('Redis launcher PID: ' + $process.Id);" ^
    "} catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto :failed

for /L %%I in (1,1,15) do (
    "%ECHOMIND_PYTHON%" scripts\check_redis.py >nul 2>&1
    if not errorlevel 1 goto :redis_ready
    powershell.exe -NoLogo -NoProfile -NonInteractive -Command "Start-Sleep -Seconds 1"
)

echo ERROR: Redis did not become ready.
echo Check .local\redis-data\launcher.err.log and .local\redis-data\redis.log.
goto :failed

:redis_ready
"%ECHOMIND_PYTHON%" scripts\check_redis.py
if errorlevel 1 goto :failed
echo.
echo SUCCESS: PostgreSQL and Redis are ready.
echo Closing this window does not stop the database services.
goto :finished

:failed
set "ECHOMIND_EXIT_CODE=1"
echo.
echo Database startup did not complete. See the error above.

:finished
echo.
if /I not "%~1"=="--no-pause" pause
popd
exit /b %ECHOMIND_EXIT_CODE%
