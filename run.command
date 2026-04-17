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
if [ -x ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
fi

if [ ! -f "launcher_gui.py" ]; then
  echo "launcher_gui.py 파일을 찾을 수 없습니다."
  echo "auto_shop_remote_fresh 폴더에서 실행했는지 확인하세요."
  read -r -p "Enter를 누르면 종료합니다..."
  exit 1
fi

echo "런처를 시작합니다..."
echo
"$PYTHON_CMD" launcher_gui.py

echo
read -r -p "Enter를 누르면 종료합니다..."
