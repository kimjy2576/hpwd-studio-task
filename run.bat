@echo off
REM HPWD-Studio 실행 (사내 공유) — UI+API 단일 서버, 0.0.0.0 바인딩.
REM   같은 망의 동료가 http://<이 PC IP>:8010 으로 접속 가능 (기동 시 주소 출력).
REM   이 PC에서만 쓰려면 run_local.bat 사용. 루트에서 run.bat 더블클릭/실행.
cd /d %~dp0backend
call start.bat
