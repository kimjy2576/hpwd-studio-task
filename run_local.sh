#!/bin/bash
# HPWD-Studio 로컬 전용 실행 — 이 PC에서만 접속 (사내 공유 OFF)
#   HOST=127.0.0.1 로 바인딩. 사내 공유하려면 ./run.sh 사용.
#   포트 변경: PORT=9000 ./run_local.sh
cd "$(dirname "$0")/backend"
export HOST=127.0.0.1
exec bash start.sh
