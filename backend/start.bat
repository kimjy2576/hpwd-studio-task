@echo off
REM ════════════════════════════════════════════════════════════════════
REM  HPWD Backend — Windows 시작 스크립트
REM  최초 실행 시: venv 생성 + 의존성 설치
REM  이후 실행 시: 서버만 시작
REM ════════════════════════════════════════════════════════════════════

setlocal
cd /d %~dp0

if not exist venv (
    echo [1/3] Python 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Python이 설치되어 있지 않거나 PATH에 없습니다.
        echo Python 3.10+ 설치 후 다시 시도하세요.
        pause
        exit /b 1
    )

    echo [2/3] 의존성 설치 중...
    call venv\Scripts\activate.bat
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: 의존성 설치 실패
        pause
        exit /b 1
    )
) else (
    call venv\Scripts\activate.bat
)

echo [3/3] 서버 시작 중...
echo.
echo ═══════════════════════════════════════════════════════════
echo  HPWD Backend on http://localhost:8000
echo  Health check: http://localhost:8000/health
echo  서버 종료: Ctrl+C
echo ═══════════════════════════════════════════════════════════
echo.

python server.py

pause
