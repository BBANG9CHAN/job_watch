#!/usr/bin/env bash
# Job Watch - macOS / Linux 실행 스크립트
#   bash start.sh            포그라운드 실행 (Ctrl+C 로 종료)
#   서버에서 상시 실행하려면 README 의 systemd / Docker 항목 참고
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -x .venv/bin/python ]; then
    echo "[setup] 가상환경을 만들고 패키지를 설치합니다..."
    "$PY" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
[ -f .env ] || cp .env.example .env

export PYTHONIOENCODING=utf-8
exec .venv/bin/python run.py "$@"
