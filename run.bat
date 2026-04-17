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
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

echo 런처를 시작합니다...
echo.
%PY_CMD% launcher_gui.py

echo.
pause
