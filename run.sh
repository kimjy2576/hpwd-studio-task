#!/bin/bash
# HPWD-Studio 실행 (사내 공유) — UI+API 단일 서버, 0.0.0.0 바인딩.
#   같은 망의 동료가 http://<이 PC IP>:8010 으로 접속 가능 (기동 시 주소 출력).
#   이 PC에서만 쓰려면 ./run_local.sh 사용. 포트 변경: PORT=9000 ./run.sh
cd "$(dirname "$0")/backend"
exec bash start.sh
