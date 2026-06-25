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

REM ── Modelica(OM) 엔진: HELMHOLTZ_PATH 미설정이면 흔한 위치 자동 탐지 ──
REM (omc 설치 여부는 백엔드가 자동 감지. 경로 역슬래시는 백엔드가 '/'로 변환)
if "%HELMHOLTZ_PATH%"=="" (
    if exist "..\..\HelmholtzMedia\HelmholtzMedia\package.mo" set "HELMHOLTZ_PATH=%CD%\..\..\HelmholtzMedia\HelmholtzMedia\package.mo"
)
if "%HELMHOLTZ_PATH%"=="" (
    if exist "%USERPROFILE%\HelmholtzMedia\HelmholtzMedia\package.mo" set "HELMHOLTZ_PATH=%USERPROFILE%\HelmholtzMedia\HelmholtzMedia\package.mo"
)
if "%HELMHOLTZ_PATH%"=="" (
    echo   Modelica 엔진: HelmholtzMedia 미감지 - Python 엔진만 ^(OM 쓰려면 §3 설치^)
) else (
    echo   Modelica 엔진: HelmholtzMedia 감지 ^(%HELMHOLTZ_PATH%^) - omc 있으면 자동 활성
)
echo.
echo  HPWD-Studio (UI+API) 시작 - 아래 URL로 접속
echo.

python server.py

pause
