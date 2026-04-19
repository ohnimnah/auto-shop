#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo
echo "=============================================="
echo " auto_shop macOS 환경 자동 설치 시작"
echo "=============================================="
echo

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python이 설치되어 있지 않아 자동 설치를 시도합니다..."

  if command -v brew >/dev/null 2>&1; then
    brew install python
    PYTHON_CMD="python3"
  else
    echo "Homebrew를 찾지 못했습니다. 아래 명령으로 Homebrew를 설치한 뒤 다시 실행해주세요:"
    echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
  fi
fi

VENV_PYTHON=".venv/bin/python"

create_venv() {
  echo ".venv 가상환경 생성 중..."
  "$PYTHON_CMD" -m venv .venv
}

if [ ! -d ".venv" ]; then
  create_venv
fi

if [ ! -f "$VENV_PYTHON" ]; then
  echo "깨진 가상환경을 감지했습니다. .venv를 다시 만듭니다..."
  rm -rf .venv
  create_venv
fi

if [ ! -f "$VENV_PYTHON" ]; then
  echo "가상환경 Python 실행 파일을 다시 만들어도 찾지 못했습니다."
  exit 1
fi

echo "pip 업그레이드 및 패키지 설치 중..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt

echo
echo "완료: Python/패키지 설치가 끝났습니다."
echo "다음부터는 run.command로 자동화를 실행하세요."
