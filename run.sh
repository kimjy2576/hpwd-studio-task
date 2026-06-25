#!/bin/bash
# HPWD-Studio 실행 (UI+API 단일 서버). 루트에서 ./run.sh
# 포트 변경: PORT=9000 ./run.sh
cd "$(dirname "$0")/backend"
exec bash start.sh
