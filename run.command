#!/bin/bash

# Always run from this script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo
echo "============================================================"
echo " Musinsa Automation (macOS용) - Quick Start"
echo "============================================================"
echo

# Pick Python command available on macOS
PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi
if [ -x ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
fi

if [ ! -f "setup.py" ]; then
  echo "setup.py 파일을 찾을 수 없습니다."
  echo "auto_shop 폴더에서 실행했는지 확인하세요."
  read -r -p "Enter를 누르면 종료합니다..."
  exit 1
fi

if [ "$1" = "setup" ]; then
  echo
  echo "초기 설정을 시작합니다..."
  echo
  "$PYTHON_CMD" setup.py
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "gui" ]; then
  echo
  echo "GUI 실행기를 시작합니다..."
  echo
  "$PYTHON_CMD" launcher_gui.py
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "bootstrap" ]; then
  echo
  echo "Python/패키지 자동 설치를 시작합니다..."
  echo
  chmod +x bootstrap_mac.sh
  ./bootstrap_mac.sh
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "watch" ]; then
  echo
  echo "감시 모드로 자동화를 시작합니다..."
  echo
  "$PYTHON_CMD" main.py --watch
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "upload" ]; then
  echo
  echo "바이마 업로드를 시작합니다..."
  echo
  "$PYTHON_CMD" buyma_upload.py
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "thumb" ]; then
  echo
  echo "이미지 썸네일 편집을 시작합니다..."
  echo
  "$PYTHON_CMD" launcher_gui.py
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

if [ "$1" = "buildapp" ]; then
  echo
  echo "아이콘 포함 앱 빌드를 시작합니다..."
  echo
  "$PYTHON_CMD" build_app.py
  read -r -p "Enter를 누르면 종료합니다..."
  exit 0
fi

while true; do
  echo
  echo "옵션을 선택하세요:"
  echo
  echo "[0] 필수 자동 설치 (Python/패키지)"
  echo "[1] 설정 (처음 한 번만 실행)"
  echo "[2] 자동화 시작 (URL 자동 입력)"
  echo "[3] 감시 모드 시작 (새 링크 자동 반영)"
  echo "[4] 종료"
  echo "[5] GUI 실행기 열기"
  echo "[6] 아이콘 앱 빌드 (.app/.exe)"
  echo "[7] 바이마 업로드"
  echo "[8] 이미지 썸네일 편집"
  echo
  read -r -p "선택 (0-8): " choice

  case "$choice" in
    0)
      chmod +x bootstrap_mac.sh
      ./bootstrap_mac.sh
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    1)
      "$PYTHON_CMD" setup.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    2)
      "$PYTHON_CMD" main.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    3)
      "$PYTHON_CMD" main.py --watch
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    4)
      echo "종료합니다."
      exit 0
      ;;
    5)
      "$PYTHON_CMD" launcher_gui.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    6)
      "$PYTHON_CMD" build_app.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    7)
      "$PYTHON_CMD" buyma_upload.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    8)
      "$PYTHON_CMD" launcher_gui.py
      read -r -p "Enter를 누르면 메뉴로 돌아갑니다..."
      ;;
    *)
      echo "잘못된 입력입니다. 0~8 중에서 선택해주세요."
      ;;
  esac
done
