@echo off
REM HPWD-Studio 로컬 전용 실행 — 이 PC에서만 접속 (사내 공유 OFF)
REM   HOST=127.0.0.1 로 바인딩. 사내 공유하려면 run.bat 사용.
cd /d %~dp0backend
set "HOST=127.0.0.1"
call start.bat
