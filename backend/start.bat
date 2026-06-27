@echo off
chcp 65001 >nul
REM ════════════════════════════════════════════════════════════════════
REM  HPWD Backend — Windows 시작 스크립트
REM  venv 생성 + 의존성 검증/설치(불완전 venv 자동 복구) 후 서버 시작
REM ════════════════════════════════════════════════════════════════════

setlocal
cd /d %~dp0

set "VENV_PY=venv\Scripts\python.exe"

REM ── venv 없으면 생성 ──
if not exist "%VENV_PY%" (
    echo [1/3] Python 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Python이 설치되어 있지 않거나 PATH에 없습니다. Python 3.10+ 설치 후 재시도.
        pause
        exit /b 1
    )
)

REM ── 의존성 검증: import 실패하면 설치 (중단/불완전 venv 자동 복구) ──
"%VENV_PY%" -c "import fastapi, uvicorn, pydantic, CoolProp, scipy" >nul 2>nul
if errorlevel 1 (
    echo [2/3] 의존성 설치 중... ^(최초 실행 또는 누락 복구 — 수 분 소요^)
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: 의존성 설치 실패 ^(네트워크 확인, 또는 backend\venv 폴더 삭제 후 재시도^).
        pause
        exit /b 1
    )
)

echo [3/3] 서버 시작 중...

REM ── local.env (있으면) 로드: 비표준 경로를 여기 한 번만 박으면 배치만으로 OK ──
REM   형식: KEY=VALUE 한 줄씩 (OMC_BIN / HELMHOLTZ_PATH / PORT / HOST). '#' 주석.
REM   이미 설정된 env는 안 덮음(명시 env > local.env) → run_local.bat의 HOST 보존
if exist "local.env" (
    echo   local.env 로드
    for /f "usebackq eol=# tokens=1* delims==" %%A in ("local.env") do if not defined %%A set "%%A=%%B"
)

REM ── omc: OMC_BIN 미설정 & PATH에도 없으면 표준 설치 위치 자동 탐지 ──
REM   (버전 폴더명 1.26.x/1.25.x.. 자동 처리. 찾으면 OMC_BIN으로 박아 python에 전달)
if "%OMC_BIN%"=="" (
    where omc >nul 2>nul || (
        for /d %%D in ("C:\Program Files\OpenModelica*-64bit") do if exist "%%D\bin\omc.exe" set "OMC_BIN=%%D\bin\omc.exe"
        for /d %%D in ("C:\Program Files\OpenModelica*") do if exist "%%D\bin\omc.exe" set "OMC_BIN=%%D\bin\omc.exe"
        for /d %%D in ("%USERPROFILE%\AppData\Local\Programs\OpenModelica*") do if exist "%%D\bin\omc.exe" set "OMC_BIN=%%D\bin\omc.exe"
    )
)
if not "%OMC_BIN%"=="" (
    echo   omc: OMC_BIN = %OMC_BIN%
) else (
    where omc >nul 2>nul && echo   omc: PATH에서 발견 || echo   omc: 미발견 ^(OpenModelica 미설치거나 비표준 위치 — §3 트러블슈팅^)
)

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

REM venv python으로 직접 실행 (activate PATH 의존 제거 → '모듈 없음' 오류 방지)
"%VENV_PY%" server.py

pause
