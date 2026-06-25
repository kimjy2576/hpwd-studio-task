# HPWD Studio

R290(프로판) 히트펌프 세탁건조기(HPWD) **사이클 설계 지원 도구**. 스키매틱 캔버스 UI + 듀얼 컴퓨트 엔진(Python·Modelica) + fidelity‑ladder Modelica 모델 + 인터랙티브 모델 문서.

- **실행 방식: 로컬 단일 서버 (UI+API).** 레포 루트에서 `./run.sh` (Mac/Linux) 또는 `run.bat` (Windows) → 브라우저에서 `http://localhost:8000`
- **사내 공유:** 같은 서버가 `0.0.0.0`로 바인딩 → 같은 망의 동료는 `http://<서버IP>:8000` 으로 접속 (기동 시 콘솔에 IP 안내)
- **모델 문서:** `http://localhost:8000/model-docs/` — 컴포넌트 × fidelity(OFF/SEMI/ON/FUTURE) 물리·수치 레퍼런스
- 냉매: **R290(Propane) 전용**
- (legacy) Railway 클라우드 배포도 가능하나 기본 경로는 로컬 서버로 전환됨

---

## 목차

1. [개요 · 아키텍처](#1-개요--아키텍처)
2. [빠른 시작 (캔버스)](#2-빠른-시작-캔버스)
3. [로컬 백엔드 셋업 (Modelica 엔진)](#3-로컬-백엔드-셋업-modelica-엔진)
4. [Modelica 모델 직접 실행 (개발)](#4-modelica-모델-직접-실행-개발)
5. [모델 문서 (model-docs)](#5-모델-문서-model-docs)
6. [R290Tab 물성 재생성](#6-r290tab-물성-재생성)
7. [레포 구조](#7-레포-구조)
8. [트러블슈팅](#8-트러블슈팅)
9. [한눈 체크리스트](#9-한눈-체크리스트)

---

## 1. 개요 · 아키텍처

HPWD Studio는 세 부분으로 구성됩니다.

```
 브라우저 ──▶ http://localhost:8000  (또는 사내 http://<서버IP>:8000)
                  │
                  ▼
          단일 서버 (backend/server.py · FastAPI · :8000)
            ├─ 프론트엔드(public/) 정적 서빙 — same-origin (URL 분기·CORS 불필요)
            ├─ Python 엔진 (CoolProp)  ── Semi/On fidelity
            └─ Modelica 엔진 (omc)     ── Off=L1 컴포넌트 + 전체 사이클 통합
                                          └─ HelmholtzMedia + R290Tab + modelica/*.mo
```

- **단일 서버** — `backend/server.py`(FastAPI)가 **UI(public/)와 API를 한 포트(:8000)에서 동시 서빙**. 프론트는 same-origin(`window.location.origin`)으로 API 호출 → 로컬·사내서버 어디서 열든 자동으로 맞음. `0.0.0.0` 바인딩이라 같은 망에서 IP로 공유 가능.
- **프론트엔드 (캔버스)** — `public/index.html` 외 `on-design-studio` / `calibration-studio` / `component-studio` / `model-docs`. 냉동·공기 사이클 스키매틱, 파라미터 편집, LLM 어시스턴트.
- **백엔드 (컴퓨트)** — 엔드포인트: `/health`, `/components`, `/compute`, `/compute_modelica`, `/run_cycle`, `/run_air_cycle`, `/run_coupled_cycle` 등. Python·Modelica 두 엔진.
- **Modelica 모델** — `modelica/*.mo`. fidelity ladder + 사이클/시스템 통합 모델. omc로 실행.

**세 가지 사용 방식**

| 방식 | 설명 | 설치 |
|---|---|---|
| (A) 캔버스 (로컬 단일 서버) | `./run.sh` → `http://localhost:8000`. 컴포넌트 단위 계산, 가장 쉬움 | Python 엔진은 바로. Modelica 엔진은 omc 설치(§3) |
| (B) Modelica 직접 실행 | 사이클/시스템 통합, 개발용(§4) | omc + HelmholtzMedia + R290Tab (로컬) |
| (C) 모델 문서 열람 | 물리·수치 레퍼런스(§5) | 불필요 (`/model-docs/`) |

> **Python 엔진**만 쓸 거면 `./run.sh`로 띄우고 바로 사용(omc 불필요).
> **Modelica 엔진**(Off=L1 컴포넌트 + 전체 사이클)은 그 서버 PC에 omc 설치 시 자동 사용 → §3 셋업.
> **사내 공유**는 같은 서버를 `http://<서버IP>:8000`으로 동료가 접속(별도 설정 없음).
> 현재 Modelica로 도는 컴포넌트의 **Off=L1** fidelity: Compressor(이론)·EEV·Evaporator·Condenser. Semi/On은 Python 엔진.

---

## 2. 빠른 시작

**로컬 단일 서버 (UI+API)** — 레포 루트에서:

```bash
# Mac/Linux
./run.sh                 # 포트 변경: PORT=9000 ./run.sh

# Windows
run.bat
```

- 최초 실행 시 `backend/venv` 생성 + 의존성 설치(CoolProp/scipy 등, 수 분). 이후엔 바로 기동.
- 콘솔에 접속 URL이 출력됨:
  - **로컬:** `http://localhost:8000`
  - **사내 공유:** `http://<서버IP>:8000` (같은 망의 동료가 접속)
- 브라우저로 접속하면 캔버스가 뜨고, **API는 자동으로 같은 서버**를 가리킴(별도 Backend URL 설정 불필요).
- **Modelica 엔진**을 쓰려면 그 서버 PC에 OpenModelica(omc) 설치 필요(§3). 없으면 Python 엔진으로 자동 동작.
- 우상단 **Backend 뱃지**에서 상태/엔진(Python·Modelica) 토글. cloud(Railway)나 커스텀 URL이 필요하면 `?backend=<url>` 또는 뱃지에서 지정 가능.

> **사내 서버에 상시 공유**하려면: 사내 PC/서버에서 위 명령으로 띄우고(방화벽에서 해당 포트 허용), 동료에게 `http://<서버IP>:8000` 공유. 백그라운드 상시 구동은 `nohup ./run.sh &`(Linux) 또는 작업 스케줄러/서비스 등록.

### 업데이트 (레포가 바뀌었을 때)

이미 clone 받아둔 PC에서 최신 변경을 반영하려면:

```bash
cd <레포 경로>          # 예: cd ~/hpwd-studio-task
git pull                # 최신 코드 받기 (백엔드·프론트 모두 갱신됨)
# (서버가 떠 있으면) Ctrl+C 로 종료 후 다시:
./run.sh                # Windows: run.bat
```

- **브라우저는 하드리프레시**(Ctrl+Shift+R) — 프론트(public/)가 바뀐 경우 캐시 때문에 그냥 새로고침은 반영 안 될 수 있음.
- `requirements.txt`가 바뀐 PR을 받았으면 의존성도 갱신 필요(`backend/venv` 재사용 시 자동 설치 안 됨):
  ```bash
  cd backend && source venv/bin/activate && pip install -r requirements.txt   # Windows: venv\Scripts\activate
  ```
  (또는 `backend/venv` 폴더를 지우고 `./run.sh` → 최초 설치 로직이 다시 도는 방식도 가능)
- **사내 서버**라면: 위를 서버 PC에서 하고 서버 재시작하면 접속자 전원에게 최신본이 반영됨(각자 브라우저 하드리프레시).

---

## 3. Modelica 엔진 셋업 (OpenModelica)

> §2 단일 서버는 omc가 있으면 Modelica 엔진을, 없으면 Python 엔진을 자동 사용. **Modelica 엔진(Off=L1 + 전체 사이클)을 쓰려면** 서버 PC에 OpenModelica + HelmholtzMedia 설치가 필요. 아래는 그 셋업.

**구성**
- 단일 서버 → `./run.sh` (UI+API, FastAPI, Python·Modelica 두 엔진)
- Modelica 엔진 → OpenModelica(omc) + HelmholtzMedia(R290) + repo 안의 `.mo` 모델

### 버전 1 — 새 컴퓨터 (아무것도 안 깔림)

#### A. 사전 설치 (3개)

1. **Git for Windows** — https://git-scm.com/download/win · 확인 `git --version`
2. **Python 3.11 또는 3.12** — https://www.python.org/downloads/
   ⚠️ 설치 첫 화면에서 **"Add python.exe to PATH" 체크** 필수 · 확인 `python --version`
3. **OpenModelica (64-bit)** — https://openmodelica.org/download/download-windows/
   - 1.26.x 권장. 설치 중 PATH 추가 옵션 켜기(기본값). 설치 용량 크고 시간 좀 걸림.
   - **새 PowerShell 창** 열고 확인 `omc --version` → `OpenModelica 1.26.x` 나와야 함
   - 안 잡히면 시스템 PATH에 `C:\Program Files\OpenModelica1.26.x-64bit\bin` 추가 후 **새 창**
   - ⚠️ 이게 빠지면 `/health`의 `reason`이 **"omc 없음"**으로 뜨고 Modelica 토글이 회색됨. omc는 **반드시 새 창**에서 확인(PATH 변경은 새 창부터 적용).

#### B. 코드 / 라이브러리 받기

PowerShell 열고 (홈 디렉토리에 받음 — `$HOME`은 현재 윈도우 계정 홈, 계정명 신경 안 써도 됨):

```powershell
cd $HOME
git clone https://github.com/kimjy2576/hpwd-studio-task.git
git clone https://github.com/thorade/HelmholtzMedia.git
```

받고 나면 (`$HOME` 예: `C:\Users\<내계정>`):
- HPWD 코드 → `$HOME\hpwd-studio-task`
- HelmholtzMedia → `$HOME\HelmholtzMedia`
  (라이브러리 진입점: `HelmholtzMedia\HelmholtzMedia\package.mo` ← 폴더가 한 번 더 중첩됨)

#### C. Python 패키지 설치

```powershell
cd $HOME\hpwd-studio-task\backend
pip install -r requirements.txt
```

(fastapi, uvicorn, pydantic, CoolProp, scipy — CoolProp 빌드에 좀 걸림)

#### D. 서버 띄우기

```powershell
cd $HOME\hpwd-studio-task\backend
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
echo $env:HELMHOLTZ_PATH        # 경로 맞는지 눈으로 확인
python server.py
```

- ⚠️ `HELMHOLTZ_PATH`는 **슬래시 `/`** 여야 함(역슬래시 쓰면 Modelica 문자열 깨짐). 위 `.Replace('\','/')`가 현재 계정 홈을 자동으로 슬래시 경로로 바꿔줌 → 계정명 달라도 그대로 동작.
- ⚠️ `PORT` — 단일 서버 기본은 8000(`./run.sh`). 8000을 Docker·LLM 서버가 잡으면 `PORT=8010` 등으로 변경(아래 예시는 8010 기준).
- 성공 로그: `Uvicorn running on http://0.0.0.0:8010` + `Frontend(public/) mounted at /` + `Modelica bridge imported (components: [...])`. 이 포트로 브라우저 접속 시 UI·API가 same-origin이라 Backend URL 설정 불필요.
- ⚠️ **이 창을 닫거나 Ctrl+C 하면 서버가 즉시 죽음.** 캔버스 쓰는 내내 열어둘 것. 다른 명령은 **새 창**에서.
- 💡 omc PATH 충돌이 잦으면 → `$env:OMC_BIN="C:\...\omc.exe"`로 PATH 우회 가능(아래 **빠른 복붙 B** / 트러블슈팅 **해결 3**).

#### E. 서버 확인 (새 PowerShell 창)

```powershell
Invoke-RestMethod http://localhost:8010/health
```

- `status: ok`, `modelica_engine: available=True` → OK
- `available=False`면 `reason` 확인(대개 HELMHOLTZ_PATH 문제 → D 다시)

#### F. 브라우저 접속

띄운 포트로 접속하면 됨 — 예: `http://localhost:8010`. 프론트가 same-origin으로 API를 자동 인식(별도 Backend URL 설정 없음). 사내 공유는 `http://<서버IP>:8010`.

### 버전 2 — 원래 작업하던 컴퓨터 (설치됨, 재부팅/재설정만)

**재부팅하면 날아가는 것:** ① 환경변수(세션 한정) ② 띄워둔 서버
**그대로 남는 것:** 설치 프로그램, clone한 코드, 캔버스 설정(localStorage의 Backend URL·엔진 선호)

```powershell
# (변경 있었을 때만) 최신 코드
cd $HOME\hpwd-studio-task; git pull

# 포트 비었는지 확인
Get-NetTCPConnection -LocalPort 8010 -State Listen -EA SilentlyContinue

# 서버 띄우기 (환경변수는 매번 다시!)
cd $HOME\hpwd-studio-task\backend
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
python server.py

# (새 창) 확인
Invoke-RestMethod http://localhost:8010/health
```

- 백엔드·프론트 모두 같은 서버라 **코드 바뀌면 서버 재시작 + 브라우저 하드리프레시(Ctrl+Shift+R)**.
- 프론트는 same-origin으로 API 자동 인식. 다른 호스트의 백엔드를 쓰려면 Backend 뱃지 → Custom URL 또는 `?backend=<url>`.

### 빠른 복붙 (원래 PC, 한 줄)

**A. 표준 — omc가 PATH에 잡힌 창에서:**
```powershell
cd $HOME\hpwd-studio-task\backend; $env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/'); $env:PORT="8010"; python server.py
```

**B. OMC_BIN 경로 직접 지정 (권장) — PATH 신경 안 써도 됨.**

① 일회용 (이 창에서만):
```powershell
cd $HOME\hpwd-studio-task\backend
$env:OMC_BIN = "C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe"   # 실제 omc.exe 경로
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
python server.py
```

② 영구 (한 번만 박으면 새 창마다 자동 적용):
```powershell
[Environment]::SetEnvironmentVariable("OMC_BIN", "C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe", "User")
# 이후 새 창부터는 OMC_BIN 줄 빼도 됨
```

> `OMC_BIN`은 백엔드(`bridge.py` `_omc_bin()`, `server.py` `_modelica_status()`)가 PATH보다 **우선** 사용. `where.exe omc`가 못 찾아도 동작.

---

## 4. Modelica 모델 직접 실행 (개발)

캔버스/백엔드 없이 **omc로 직접** 모델을 빌드·시뮬레이션. 사이클/시스템 통합 모델은 이쪽이 본령.

### 로드 순서 (의존성 — 이 순서 지킬 것)

```modelica
loadModel(Modelica);
loadFile("<HOME>/HelmholtzMedia/HelmholtzMedia/package.mo");
cd("<HOME>/hpwd-studio-task/modelica");
loadFile("R290Tab.mo");   // R290 (p,h) 물성층 — 수치 enabler
loadFile("HPWDair.mo");   // 습공기 물성 + 공기 컴포넌트 (Fan/Drum/Filter/AirVolume)
loadFile("HPWD.mo");      // 압축기(Winandy/Theoretical)·EEV(L1)·RefPort
loadFile("HXCorr.mo");    // HX 공기측 상관식
loadFile("EvapUA.mo");    // EvapUA · FlowSource · SinkOpen · satProps (HPWDhx)
loadFile("EevMB.mo");     // EEV_MB (SEMI)
loadFile("CondMBe.mo");   // CondenserSS (SEMI 정상상태 MB 응축기) + propsCond
loadFile("EvapMBe.mo");   // EvaporatorMBdyn (SEMI 동적 MB 증발기) + FlowBC
loadFile("Control.mo");   // PI_Controller
loadFile("CycleMBe.mo");  // 순수 SEMI 사이클 (CycleDynL2 등)
loadFile("Coupled.mo");   // OFF 냉매 + 폐공기루프 (혼합)
loadFile("CoupledSEMI.mo");// 전체 SEMI (CplSEMI.Cycle_SEMI_full + 공기커플 MB HX 변형)
```

### 주요 시스템 모델

| 모델 | 설명 |
|---|---|
| `CycleMBe.CycleDynL2` | 순수 SEMI 사이클 — Comp_Winandy + CondenserSS + EEV_MB + EvaporatorMBdyn, 직접연결(볼륨 없음) |
| `Coupled.Cycle_coupled_closed` | OFF 냉매(이론압축기·ε‑NTU HX) + 폐공기루프(PI EEV) |
| `Coupled.Cycle_coupled_closed_L2air` | 위 + Fan_L2·Drum_L2 (OFF 냉매 + SEMI 공기) |
| `CplSEMI.Cycle_SEMI_full` | **전체 SEMI** — SEMI 냉매 MB HX(AirPort 커플) + SEMI 공기루프(Fan_L2·Drum_L2) |

### 실행 예 (`run.mos`)

```modelica
// ... 위 로드 순서 그대로 ...
simulate(CplSEMI.Cycle_SEMI_full, stopTime=4000, numberOfIntervals=4000, tolerance=1e-6);
```

omc 실행: `omc run.mos`

### ⚠️ stopTime · stepSize (중요)

- **`numberOfIntervals`는 stopTime과 같게** (예: stopTime=4000 → 4000, 즉 1초 간격). DASSL 최대스텝이 출력간격에 묶여, 간격이 크면 첫 스텝에서 강성 init이 실패함. 1초 간격이면 안전.
- `-override=stopTime=...` 및 `_init.xml`의 stopTime 수정은 **현재 omc 버전에서 무효**. stopTime 바꾸려면 `simulate(..., stopTime=N)`로 **재컴파일**해야 함.

### 결과 읽기

- **OMEdit**: `.mat`(예: `CplSEMI.Cycle_SEMI_full_res.mat`)를 열어 변수 플롯.
- **Python**: `scipy.io.loadmat`로 `_res.mat` 직접 파싱(`readSimulationResult()`는 이 omc 환경에서 불안정).
- 참고 검증 운전점(전체 SEMI, 4000s 건조): Pc≈17.4 / Pe≈6.9 bar, SH≈16K, **SMER≈3.22 kg/kWh**, 응축수=drum 제거수분 정합.

---

## 5. 모델 문서 (model-docs)

컴포넌트 × fidelity(OFF/SEMI/ON/FUTURE) **물리·수치 레퍼런스**. 각 모델의 수학적 정의·Nomenclature·Code Mapping·검증·한계.

- **서버**: 단일 서버 실행 후 `http://localhost:8000/model-docs/` (사내: `http://<서버IP>:8000/model-docs/`)
- **로컬**: `public/model-docs/index.html`를 브라우저로 직접 열어도 됨(설치 불필요).
- 사이드바: Compressor / Evaporator / Condenser / EEV / Fan / Drum / Filter / Moist Air / **수치·수렴** / Lint Transport. **수치·수렴** 트랙은 물리와 분리된 수렴 테크닉(R290Tab 물성층 등).

---

## 6. R290Tab 물성 재생성

`modelica/R290Tab.mo`는 CoolProp(HEOS Propane)에서 생성한 **미분가능 (p,h) 테이블**(2상 안전, 해석 도함수). 폐루프 수렴의 근본 — 자세한 원리는 model-docs **수치·수렴 → R290Tab** 참고.

```powershell
cd $HOME\hpwd-studio-task\modelica\media
python gen_r290.py     # CoolProp → r290_table.npz
python emit_full.py    # r290_table.npz → ../R290Tab.mo
```

- 격자: p[1.5, 35] bar × 60, h × (120~) kJ/kg. 기준상태가 HelmholtzMedia와 일치 → h값 교환 가능.
- 냉매·격자·CoolProp 버전 바꿀 때만 재생성.

---

## 7. 레포 구조

```
hpwd-studio-task/
├─ README.md                  ← 이 파일
├─ run.sh / run.bat           로컬 단일 서버 실행 (UI+API)
├─ server.py                  (legacy) Railway 정적 서버 — 로컬에선 불필요
├─ Procfile, railway.json     (legacy) Railway 배포 설정
├─ public/
│  ├─ index.html              캔버스 UI (프론트엔드)
│  └─ model-docs/index.html   모델 문서 (fidelity ladder)
├─ modelica/                  Modelica 모델 (.mo)
│  ├─ R290Tab.mo              R290 (p,h) 물성층 (수치 enabler)
│  ├─ HPWDair.mo              습공기 + 공기 컴포넌트(Fan/Drum/Filter/AirVolume)
│  ├─ HPWD.mo                 압축기(Winandy/Theoretical)·EEV(L1)·RefPort
│  ├─ HXCorr.mo               HX 공기측 상관식
│  ├─ EvapUA.mo               EvapUA·FlowSource·SinkOpen·satProps
│  ├─ EevMB.mo                EEV_MB (SEMI)
│  ├─ CondMBe.mo              CondenserSS (SEMI MB 응축기)
│  ├─ EvapMBe.mo              EvaporatorMBdyn (SEMI 동적 MB 증발기)·FlowBC
│  ├─ CycleMBe.mo             순수 SEMI 사이클 (CycleDynL2 …)
│  ├─ Coupled.mo              OFF 냉매 + 폐공기루프 (혼합)
│  ├─ CoupledSEMI.mo          전체 SEMI (CplSEMI.Cycle_SEMI_full)
│  ├─ Control.mo              PI_Controller
│  └─ media/                  R290Tab 생성기 (gen_r290.py, emit_full.py)
├─ backend/                   로컬 컴퓨트 백엔드
│  ├─ server.py               FastAPI (Python·Modelica 엔진)
│  ├─ bridge.py(외)·components·design·modelica
│  ├─ requirements.txt        Python 의존성
│  └─ Dockerfile, start.bat/sh
├─ docs/
│  ├─ local-modelica-setup.md 로컬 셋업 (본 README §3의 원본)
│  └─ modelica-decision.md    Modelica 채택 의사결정 기록
└─ SKILL.md, skills/          설계 지원 에이전트 스킬 문서
```

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `/health`가 `{"detail":"Not Found"}` (404) | 그 포트에 **HPWD가 아닌 다른 서버**(Docker/Open WebUI/llama 등) | 포트 점유자 정리 또는 **HPWD를 다른 포트로**(`$env:PORT="8010"`) |
| Status **"Failed to fetch" / Disconnected** | 로컬 서버가 안 떠 있음(창 닫힘/Ctrl+C/크래시) | 서버 다시 띄우기 |
| `/health` reason **"omc 없음"** | OpenModelica 미설치, 또는 (자주) 설치는 됐는데 서버 띄운 창의 PATH에 omc 없음 | 서버 창에서 `omc --version` 확인 → 아래 **omc PATH** 참고 |
| `/health` reason **"HelmholtzMedia 없음: <경로>"** | `HELMHOLTZ_PATH` 미설정/틀림 | `$HOME` 방식으로 재설정 → `Test-Path`로 파일 존재 확인 |
| Modelica 토글이 **회색** (연결은 됨) | 위 둘 중 하나 | `Invoke-RestMethod .../health \| ConvertTo-Json -Depth 5`로 reason 보기 |
| 새 창에서 띄웠더니 `available=False` | `$env:HELMHOLTZ_PATH`가 안 잡힘(환경변수는 창마다 따로) | 같은 창에서 HELMHOLTZ_PATH 다시 설정 후 재시작 |
| 포트 8000 자꾸 충돌 | Docker 등이 8000 점유 | **PORT=8010** 등 다른 포트 |
| 같은 포트에 python 2개 listen | 이전 서버가 안 죽음 | `Get-NetTCPConnection -LocalPort <포트> -State Listen`로 PID 확인 → `Stop-Process` |

**포트 점유자 확인:**
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8010 -State Listen -EA SilentlyContinue).OwningProcess | Select Id, ProcessName, Path
```

### ⚠️ omc가 깔려있는데도 reason이 "omc 없음"일 때 (자주 겪음)

**원인:** 서버는 **자기를 띄운 PowerShell 창의 PATH**를 물려받음. 그 창이 OpenModelica 설치 *전*에 열렸거나 PATH 변경을 아직 못 받았으면 — omc가 설치돼 있어도 서버가 못 찾음. (다른 창에서 `omc --version`이 되더라도 **서버 띄운 그 창**에 없으면 소용 없음.)

진단 — 서버 띄운 바로 그 창에서 `omc --version` 실패하면 그 창 PATH에 omc 없음(원인 확정).

- **해결 1 (즉시)** — 서버 창에서 omc bin을 PATH 앞에 끼우고 띄움:
  ```powershell
  $env:PATH = "C:\Program Files\OpenModelica1.26.x-64bit\bin;" + $env:PATH
  ```
- **해결 2 (영구)** — User PATH에 박고 **새 창**부터:
  ```powershell
  [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\OpenModelica1.26.x-64bit\bin", "User")
  ```
- **해결 3 (PATH 완전 우회, 권장)** — `OMC_BIN`으로 omc.exe 경로 직접 지정(백엔드가 PATH보다 우선):
  ```powershell
  $env:OMC_BIN = "C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe"
  ```

**알아두면 좋은 것**
- 환경변수(`$env:...`)는 **PowerShell 창마다 따로**. 새 창 열면 다시 설정.
- 서버는 띄운 창에 붙어 있음 → **그 창 닫으면 서버 죽음.** 서버 창과 작업 명령 창 분리.
- 터미널 붙여넣기: **Ctrl+Shift+V** 또는 **Shift+Insert**.
- 첫 Modelica 호출만 느림(omc 빌드) → 타입별 1회 빌드 후 캐시.
- UI·API가 same-origin 단일 서버라 mixed-content·CORS 이슈 없음. 사내 공유 시 방화벽에서 해당 포트(기본 8000) 허용 필요.

---

## 9. 한눈 체크리스트

**새 PC:** Git → Python(3.11+) → (Modelica 쓸 거면) OpenModelica 설치 → repo clone → `./run.sh`(최초 venv 자동) → 브라우저 `http://localhost:8000` → (Modelica면 `HELMHOLTZ_PATH` 설정 후 재기동) → 엔진 선택 → 테스트.  사내 공유는 `http://<서버IP>:8000`.

**원래 PC (업데이트):** `git pull` → (서버 떠 있으면 Ctrl+C) → `./run.sh`(Windows: `run.bat`) → 브라우저 하드리프레시(Ctrl+Shift+R) → `/health` 확인.  `requirements.txt` 바뀌었으면 venv에 `pip install -r backend/requirements.txt`. (Modelica는 `HELMHOLTZ_PATH` 재설정)

**모델 직접 실행(개발):** §4 로드 순서대로 `loadFile` → `simulate(모델, stopTime=N, numberOfIntervals=N)` → `.mat`를 OMEdit/Python으로 읽기.
