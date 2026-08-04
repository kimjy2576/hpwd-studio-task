#!/usr/bin/env bash
# WS-B 플래그 매트릭스 (G2 위임, 2026-08-04)
# 목적: L3C 이벤트 라이브록 복권을 죽이는 런타임 처방 확정.
#   근거: semiLinear 면 이벤트 폭풍(evap/cond.mdot[k]=0) → 등간격 모드
#   이벤트 반복 라이브록. t=0.1635 / t=30.04 락 실측. tanh 블렌드는
#   D3(2026-08-03) 기각이므로 모델 수술 금지 — 런타임 플래그만 탐색.
# 사용: bash ws/ws_b_flags.sh   (레포 루트 기준 상대 실행 OK)
# 산출: /tmp/wsb_flags/summary.txt — 조합별 완주/판정 표
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
W=/tmp/wsb_flags
MODEL=HPWDcycle.Cycle_L3C_coldstart_charge
STOP=600
TMO=2400          # 런당 40분 상한
REPS=2            # 복권 판정용 반복
mkdir -p "$W"; cd "$W"

# ── 1회 빌드 (컨테이너 검증 완료 로드체인) ─────────────────────────
cat > build.mos <<EOF
loadModel(Modelica); getErrorString();
loadFile("$REPO/modelica/R290Tab.mo"); getErrorString();
loadFile("$REPO/modelica/R290Medium.mo"); getErrorString();
loadFile("$REPO/modelica/R290Oil.mo"); getErrorString();
loadFile("$REPO/modelica/HXGeom.mo"); getErrorString();
loadFile("$REPO/modelica/HXCorr.mo"); getErrorString();
loadFile("$REPO/modelica/HPWD.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDon.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDevap.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDevapC.mo"); getErrorString();
loadFile("$REPO/modelica/Control.mo"); getErrorString();
loadFile("$REPO/modelica/HPWDcycle.mo"); getErrorString();
b := buildModel($MODEL, stopTime=$STOP, tolerance=1e-3,
  method="dassl", outputFormat="csv",
  variableFilter="time|M_total|Pc_bar|Pe_bar|SH|eevctl.n_pulse|seq.f|comp.h_dis");
print("EXE=" + b[1] + "|\n"); print(getErrorString());
EOF
if [ ! -x "$W/$MODEL" ]; then
  echo "[build] omc..."; omc build.mos > build.log 2>&1
  grep -q "EXE=$W/$MODEL" build.log || { echo "빌드 실패 — build.log 확인"; exit 1; }
fi

# ── 조합 정의 ──────────────────────────────────────────────────────
CFGS="base:
noeq:-noEquidistantTimeGrid
nores:-noRestart
noeq_nores:-noEquidistantTimeGrid -noRestart
ida:-s=ida
cvode:-s=cvode"

# ── 병렬 발사 ──────────────────────────────────────────────────────
echo "$CFGS" | while IFS=: read -r name flags; do
  for r in $(seq 1 $REPS); do
    d="$W/$name.r$r"; mkdir -p "$d"
    ( cd "$d" && cp "$W/$MODEL"* . 2>/dev/null
      s=$(date +%s)
      timeout $TMO "./$MODEL" $flags > run.log 2>&1
      echo "RC=$? WALL=$(( $(date +%s) - s ))s" > done.txt ) &
  done
done
wait
echo "[run] 전 조합 종료"

# ── 판정 집계 ──────────────────────────────────────────────────────
{
  echo "=== WS-B 플래그 매트릭스 $(date '+%F %T') ==="
  echo "조합 | rep | RC/wall | t_end | judge"
  echo "$CFGS" | while IFS=: read -r name flags; do
    for r in $(seq 1 $REPS); do
      d="$W/$name.r$r"; csv="$d/${MODEL}_res.csv"
      rcw=$(cat "$d/done.txt" 2>/dev/null || echo "?")
      if [ -f "$csv" ]; then
        te=$(tail -1 "$csv" | cut -d, -f1)
        jg=$(python3 "$REPO/ws/judge.py" "$csv" 2>/dev/null | head -1)
      else te="-"; jg="CSV 없음"; fi
      echo "$name | r$r | $rcw | t=$te | $jg"
    done
  done
} | tee "$W/summary.txt"
echo
echo "판정 기준: REPS 전부 t=600 완주 + 드리프트 |≤0.4%| 인 조합 = 처방 확정."
echo "결과 회신: summary.txt 내용 붙여넣기 (+ 가능하면 완주 조합 1개의 CSV)."
