#!/bin/bash

# Always run from this script directory.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo
echo "============================================================"
echo " auto_shop Launcher"
echo "============================================================"
echo

PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi

if [ ! -f "launcher_gui.py" ]; then
  echo "launcher_gui.py 파일을 찾을 수 없습니다."
  echo "auto_shop_remote_fresh 폴더에서 실행했는지 확인하세요."
  read -r -p "Enter를 누르면 종료합니다..."
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
else
  if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
    echo "Python 3를 찾을 수 없습니다."
    echo "먼저 Python을 설치한 뒤 다시 실행해주세요."
    read -r -p "Enter를 누르면 종료합니다..."
    exit 1
  fi

  echo "가상환경이 없어 새로 준비합니다..."
  "$PYTHON_CMD" -m venv .venv || {
    echo "가상환경 생성에 실패했습니다."
    read -r -p "Enter를 누르면 종료합니다..."
    exit 1
  }
  PYTHON_CMD=".venv/bin/python"
fi

"$PYTHON_CMD" -c "import selenium, PIL, bs4, googleapiclient, google.oauth2, webdriver_manager, numpy, cv2" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "필요한 패키지를 설치합니다..."
  "$PYTHON_CMD" -m pip install --upgrade pip || {
    echo "pip 업그레이드에 실패했습니다."
    read -r -p "Enter를 누르면 종료합니다..."
    exit 1
  }
  "$PYTHON_CMD" -m pip install -r requirements.txt || {
    echo "패키지 설치에 실패했습니다."
    read -r -p "Enter를 누르면 종료합니다..."
    exit 1
  }
fi

echo "런처를 시작합니다..."
echo
"$PYTHON_CMD" launcher_gui.py

echo
read -r -p "Enter를 누르면 종료합니다..."
