@echo off
cd /d "%~dp0"
rem Stop any process listening on port 8000 to prevent port binding conflicts
powershell -NoProfile -Command "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue" >nul 2>&1
where uv >nul 2>&1
if not errorlevel 1 goto with_uv
python --version >nul 2>&1
if errorlevel 1 goto no_python
if not exist .venv python -m venv .venv
.venv\Scripts\pip install fastapi uvicorn python-multipart
goto start_server
:with_uv
if not exist .venv uv venv
uv pip install fastapi uvicorn python-multipart
:start_server
rem Note: Start browser with a brief delay so uvicorn binds port 8000 first
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
.venv\Scripts\python main.py
if errorlevel 1 goto error
exit /b
:no_python
echo Python or uv is not installed or not in PATH.
pause
exit /b
:error
echo Server stopped unexpectedly.
pause
