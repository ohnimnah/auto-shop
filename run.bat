@echo off
chcp 949 > nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   무신사 자동화 스크립트 Windows용 - 빠른 시작
echo ============================================================
echo.

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

if not exist "setup.py" (
    echo setup.py 파일을 찾을 수 없습니다.
    echo 이 파일이 auto_shop 폴더에 있는지 확인하세요.
    pause
    exit /b 1
)

set "arg1=%~1"
set "arg1=%arg1: =%"
set "arg1=%arg1:[=%"
set "arg1=%arg1:]=%"
set "arg1=%arg1:'=%"
set "arg1=%arg1:\"=%"

if /I "%arg1%"=="1" goto do_install
if /I "%arg1%"=="install" goto do_install
if /I "%arg1%"=="bootstrap" goto do_install

if /I "%arg1%"=="2" goto do_setup
if /I "%arg1%"=="setup" goto do_setup

if /I "%arg1%"=="3" goto do_run
if /I "%arg1%"=="run" goto do_run

if /I "%arg1%"=="4" goto do_watch
if /I "%arg1%"=="watch" goto do_watch

if /I "%arg1%"=="5" goto do_upload
if /I "%arg1%"=="upload" goto do_upload

if /I "%arg1%"=="6" goto do_thumb
if /I "%arg1%"=="thumb" goto do_thumb

if /I "%arg1%"=="7" goto do_thumb_auto
if /I "%arg1%"=="thumb-auto" goto do_thumb_auto

if /I "%arg1%"=="8" goto do_save_images
if /I "%arg1%"=="save-images" goto do_save_images
if /I "%arg1%"=="images" goto do_save_images

if /I "%arg1%"=="9" goto do_gui
if /I "%arg1%"=="gui" goto do_gui

if /I "%arg1%"=="0" goto do_exit
if /I "%arg1%"=="exit" goto do_exit

goto menu_loop

:menu_loop
echo.
echo 옵션을 선택하세요:
echo.
echo 1. 필수 자동 설치
echo 2. 초기 설정
echo 3. 자동화 시작
echo 4. 감시 모드
echo 5. 바이마 업로드
echo 6. 썸네일 편집
echo 7. 썸네일 자동
echo 8. 링크 이미지 저장
echo 9. GUI 실행기 열기
echo 0. 종료
echo.

set "choice="
set /p choice="선택 (0-9): "
set "choice=%choice: =%"
set "choice=%choice:[=%"
set "choice=%choice:]=%"
set "choice=%choice:'=%"
set "choice=%choice:\"=%"

if "%choice%"=="1" goto do_install
if "%choice%"=="2" goto do_setup
if "%choice%"=="3" goto do_run
if "%choice%"=="4" goto do_watch
if "%choice%"=="5" goto do_upload
if "%choice%"=="6" goto do_thumb
if "%choice%"=="7" goto do_thumb_auto
if "%choice%"=="8" goto do_save_images
if "%choice%"=="9" goto do_gui
if "%choice%"=="0" goto do_exit

echo 잘못된 입력입니다. 0-9 중에서 선택해주세요.
echo.
goto menu_loop

:do_install
echo.
echo Python/패키지 자동 설치를 시작합니다...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_windows.ps1"
pause
goto menu_loop

:do_setup
echo.
echo 초기 설정을 시작합니다...
echo.
%PY_CMD% setup.py
pause
goto menu_loop

:do_run
echo.
echo 자동화를 시작합니다...
echo.
%PY_CMD% main.py
pause
goto menu_loop

:do_watch
echo.
echo 감시 모드를 시작합니다...
echo.
%PY_CMD% main.py --watch
pause
goto menu_loop

:do_upload
echo.
echo 바이마 업로드를 시작합니다...
echo.
%PY_CMD% buyma_upload.py
pause
goto menu_loop

:do_thumb
echo.
echo 썸네일 편집을 실행합니다...
echo.
%PY_CMD% launcher_gui.py
pause
goto menu_loop

:do_thumb_auto
echo.
echo 썸네일 자동 기능은 GUI에서 실행합니다...
echo.
%PY_CMD% launcher_gui.py
pause
goto menu_loop

:do_save_images
echo.
echo 링크 이미지 저장을 시작합니다...
echo.
%PY_CMD% main.py --download-images
pause
goto menu_loop

:do_gui
echo.
echo GUI 실행기를 시작합니다...
echo.
%PY_CMD% launcher_gui.py
pause
goto menu_loop

:do_exit
echo 종료합니다.
exit /b
