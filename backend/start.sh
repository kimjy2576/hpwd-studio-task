#!/bin/bash
# ════════════════════════════════════════════════════════════════════
#  HPWD Backend — Mac/Linux 시작 스크립트
# ════════════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo "[1/3] Python 가상환경 생성 중..."
    python3 -m venv venv
    echo "[2/3] 의존성 설치 중..."
    source venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
else
    source venv/bin/activate
fi

echo "[3/3] 서버 시작 중..."
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  HPWD Backend on http://localhost:8000"
echo "  Health check: http://localhost:8000/health"
echo "  서버 종료: Ctrl+C"
echo "═══════════════════════════════════════════════════════════"
echo ""

python server.py
