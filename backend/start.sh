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

# ── omc: OMC_BIN 미설정 & PATH에도 없으면 표준 위치 자동 탐지 ──
if [ -z "$OMC_BIN" ] && ! command -v omc >/dev/null 2>&1; then
    for cand in /usr/bin/omc /usr/local/bin/omc /opt/openmodelica/bin/omc /Applications/OpenModelica.app/Contents/Resources/omc; do
        if [ -x "$cand" ]; then export OMC_BIN="$cand"; break; fi
    done
fi
if [ -n "$OMC_BIN" ]; then
    echo "  omc: OMC_BIN = $OMC_BIN"
elif command -v omc >/dev/null 2>&1; then
    echo "  omc: PATH에서 발견 ($(command -v omc))"
else
    echo "  omc: 미발견 (OpenModelica 미설치거나 비표준 위치 — §3 트러블슈팅)"
fi

# ── Modelica(OM) 엔진: HELMHOLTZ_PATH 미설정이면 흔한 위치 자동 탐지 ──
# (omc 설치 여부는 백엔드가 자동 감지. 여기선 HelmholtzMedia만 잡아줌)
if [ -z "$HELMHOLTZ_PATH" ]; then
    for cand in \
        "../../HelmholtzMedia/HelmholtzMedia/package.mo" \
        "$HOME/HelmholtzMedia/HelmholtzMedia/package.mo" \
        "../HelmholtzMedia/HelmholtzMedia/package.mo"; do
        if [ -f "$cand" ]; then
            export HELMHOLTZ_PATH="$(cd "$(dirname "$cand")" && pwd)/package.mo"
            break
        fi
    done
fi
if [ -n "$HELMHOLTZ_PATH" ] && [ -f "$HELMHOLTZ_PATH" ]; then
    echo "  Modelica 엔진: HelmholtzMedia 감지 ($HELMHOLTZ_PATH) → omc 있으면 자동 활성"
else
    echo "  Modelica 엔진: HelmholtzMedia 미감지 → Python 엔진만 (OM 쓰려면 §3 설치)"
fi
echo ""
echo "  HPWD-Studio (UI+API) 시작 — 아래 URL로 접속"
echo ""

python server.py
