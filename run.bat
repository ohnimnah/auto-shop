@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   auto_shop Launcher
echo ============================================================
echo.

if not exist "launcher_gui.py" (
    echo launcher_gui.py 파일을 찾을 수 없습니다.
    echo auto_shop 폴더에서 실행했는지 확인하세요.
    pause
    exit /b 1
)

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" > nul 2>&1
    if errorlevel 1 (
        echo 깨진 가상환경을 감지했습니다. Windows 환경을 다시 준비합니다...
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\bootstrap_windows.ps1"
        if errorlevel 1 (
            echo Windows 환경 준비에 실패했습니다.
            pause
            exit /b 1
        )
    )
)

if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

echo 런처를 시작합니다...
echo.
%PY_CMD% launcher_gui.py

echo.
pause
