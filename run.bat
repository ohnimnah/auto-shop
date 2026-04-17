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

set "BOOTSTRAP_PY="
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    py -3 -V >nul 2>&1
    if not errorlevel 1 (
        set "BOOTSTRAP_PY=py -3"
    ) else (
        python --version >nul 2>&1
        if not errorlevel 1 set "BOOTSTRAP_PY=python"
    )

    if not defined BOOTSTRAP_PY (
        echo Python을 찾을 수 없습니다.
        echo Python 3를 먼저 설치한 뒤 다시 실행해주세요.
        pause
        exit /b 1
    )

    echo 가상환경이 없어 새로 준비합니다...
    %BOOTSTRAP_PY% -m venv .venv
    if errorlevel 1 (
        echo 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
    set "PY_CMD=.venv\Scripts\python.exe"
)

%PY_CMD% -c "import selenium, PIL, bs4, googleapiclient, google.oauth2, webdriver_manager, numpy, cv2" >nul 2>&1
if errorlevel 1 (
    echo 필요한 패키지를 설치합니다...
    %PY_CMD% -m pip install --upgrade pip
    if errorlevel 1 (
        echo pip 업그레이드에 실패했습니다.
        pause
        exit /b 1
    )
    %PY_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo 패키지 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

echo 런처를 시작합니다...
echo.
%PY_CMD% launcher_gui.py

echo.
pause
