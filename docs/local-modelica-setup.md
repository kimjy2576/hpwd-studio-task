# HPWD Studio — 로컬 Modelica 백엔드 셋업 가이드

> 캔버스(프론트엔드)는 **Railway에 배포**돼 있어서 브라우저로 바로 접속함 (설치 X).
> **Modelica 엔진은 로컬 PC에서만 동작** (OpenModelica + HelmholtzMedia 필요).
> 그래서 로컬에 백엔드 서버를 띄우고, 캔버스가 그 로컬 서버를 가리키게 하는 게 핵심임.
> (Python 엔진만 쓸 거면 로컬 서버 없이 Cloud(Railway)로 충분. Modelica는 아래 셋업 필요.)

**캔버스 주소 (항상 이걸로 접속):** https://hpwd-studio-task-production.up.railway.app

**구성**
- 프론트엔드 → Railway 배포 (브라우저)
- 로컬 백엔드 → `python server.py` (FastAPI, Python·Modelica 두 엔진)
- Modelica 엔진 → OpenModelica(omc) + HelmholtzMedia(R290) + repo 안의 `.mo` 모델

**현재 Modelica로 도는 컴포넌트** (각 컴포넌트의 **Off = L1** fidelity만): Compressor(이론), EEV, Evaporator, Condenser. Semi/On은 Python 엔진으로 동작. 냉매는 **R290(Propane)** 전용.

---

## 버전 1 — 새 컴퓨터 (아무것도 안 깔림)

### A. 사전 설치 (3개)

1. **Git for Windows** — https://git-scm.com/download/win
   설치 후 확인: `git --version`

2. **Python 3.11 또는 3.12** — https://www.python.org/downloads/
   ⚠️ 설치 첫 화면에서 **"Add python.exe to PATH" 체크** 필수
   확인: `python --version`

3. **OpenModelica (64-bit)** — https://openmodelica.org/download/download-windows/
   - 1.26.x 권장. 설치 중 PATH 추가 옵션 켜기 (보통 기본값). **설치 용량 크고 시간 좀 걸림.**
   - **새 PowerShell 창** 열고 확인: `omc --version` → `OpenModelica 1.26.x` 나와야 함
   - 안 잡히면 시스템 PATH에 `C:\Program Files\OpenModelica1.26.x-64bit\bin` 추가 후 **새 창**
   - ⚠️ 이게 빠지면 `/health`의 `reason`이 **"omc 없음"** 으로 뜨고 Modelica 토글이 회색됨. omc는 **반드시 새 창**에서 확인 (PATH 변경은 새 창부터 적용).

### B. 코드 / 라이브러리 받기

PowerShell 열고 (홈 디렉토리에 받음 — `$HOME`은 현재 윈도우 계정의 홈, 계정명 신경 안 써도 됨):

```powershell
cd $HOME
git clone https://github.com/kimjy2576/hpwd-studio-task.git
git clone https://github.com/thorade/HelmholtzMedia.git
```

> repo가 비공개면 clone 시 GitHub 로그인(또는 PAT) 요구됨.

받고 나면 (`$HOME` 예: `C:\Users\<내계정>`):
- HPWD 코드 → `$HOME\hpwd-studio-task`
- HelmholtzMedia → `$HOME\HelmholtzMedia`
  (라이브러리 진입점: `HelmholtzMedia\HelmholtzMedia\package.mo` ← 폴더가 한 번 더 중첩됨)

### C. Python 패키지 설치

```powershell
cd $HOME\hpwd-studio-task\backend
pip install -r requirements.txt
```

(fastapi, uvicorn, pydantic, CoolProp, scipy — CoolProp 빌드에 좀 걸림)

### D. 서버 띄우기

```powershell
cd $HOME\hpwd-studio-task\backend
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
echo $env:HELMHOLTZ_PATH        # 경로 맞는지 눈으로 확인
python server.py
```

- ⚠️ `HELMHOLTZ_PATH`는 **슬래시 `/`** 여야 함 (역슬래시 `\` 쓰면 Modelica 문자열이 깨짐). 위 `.Replace('\','/')` 한 줄이 현재 계정 홈(`$HOME`)을 자동으로 슬래시 경로로 바꿔줌 → 계정명(`kimjy`, `kimjy2576.kim` 등) 달라도 그대로 동작. (`-replace`는 정규식이라 백슬래시 escape가 필요해 헷갈림 → `.Replace()` 사용)
- ⚠️ `PORT=8010` — 8000은 Docker·다른 LLM 서버가 자주 잡아서 충돌남. 8010으로 띄우는 걸 권장
- 성공 로그: `Uvicorn running on http://0.0.0.0:8010` + `Modelica bridge imported (components: [...])`
- ⚠️ **이 창을 닫거나 Ctrl+C 하면 서버가 즉시 죽음.** 캔버스 쓰는 내내 열어둘 것. 다른 명령은 **새 창**에서.

### E. 서버 확인 (새 PowerShell 창에서)

```powershell
Invoke-RestMethod http://localhost:8010/health
```

- `status: ok`, `modelica_engine: available=True` → OK
- `available=False`면 `reason` 확인 (대개 HELMHOLTZ_PATH 문제 → D 다시)

### F. 캔버스 연결

1. 브라우저에서 https://hpwd-studio-task-production.up.railway.app 접속
2. 우상단 **Backend 뱃지** 클릭 → **Custom URL** 칸에 `http://localhost:8010` 입력 → **SET**
3. **Status → Connected**, Components 16 확인
4. **Compute Engine → Modelica** 클릭
5. 한 번 설정하면 브라우저(localStorage)에 저장됨 → 이후 자동 유지

### G. 동작 테스트

- 왼쪽 라이브러리에서 **Compressor**(또는 Evaporator/Condenser/EEV) 드래그 → 입력값 자동 채워짐 → **Run**
- 첫 Modelica 호출은 모델 빌드 (~10–30초, 서버 로그에 `POST /compute_modelica`), 이후 캐시로 즉시
- Python 엔진 결과와 거의 동일하게 나오면 정상

---

## 버전 2 — 원래 작업하던 컴퓨터 (설치됨, 재부팅/재설정만)

**재부팅하면 날아가는 것:** ① 환경변수(세션 한정) ② 띄워둔 서버
**그대로 남는 것:** 설치 프로그램, clone한 코드, 캔버스 설정(localStorage의 Backend URL·엔진 선호)

### Step 1 — 최신 코드 받기 (변경 있었을 때만)

```powershell
cd $HOME\hpwd-studio-task
git pull
```
- **백엔드** 바뀜 → 서버 재시작 필요
- **프론트엔드** 바뀜 → Railway 자동 재배포(몇 분) 후 캔버스 하드리프레시(Ctrl+Shift+R)

### Step 2 — 포트 비었는지 확인

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen -EA SilentlyContinue
```
- 아무것도 안 나오면 깨끗함 (8010 사용 가능)
- 뭐가 나오면 그 PID를 `Stop-Process -Id <PID> -Force` 하거나, 다른 포트 사용

### Step 3 — 서버 띄우기 (환경변수는 매번 다시!)

```powershell
cd $HOME\hpwd-studio-task\backend
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
python server.py
```
- 이 창은 열어둘 것 (서버 점유)

### Step 4 — 확인 (새 창)

```powershell
Invoke-RestMethod http://localhost:8010/health
```
→ `status: ok`, `modelica_engine: available=True`

### Step 5 — 캔버스

1. https://hpwd-studio-task-production.up.railway.app (프론트 업데이트 있었으면 Ctrl+Shift+R)
2. Backend 설정은 localStorage에 저장돼 있어 **보통 자동 재연결**됨 (Status → Connected, Modelica 자동 활성)
3. 자동 연결 안 되면: Backend 뱃지 → **Custom URL** `http://localhost:8010` → **SET**

### 빠른 복붙 (원래 PC, 한 줄)

```powershell
cd $HOME\hpwd-studio-task\backend; $env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/'); $env:PORT="8010"; python server.py
```
→ 그 다음 캔버스에서 연결만 확인 (이미 저장돼 있으면 자동).

> **omc PATH 분쟁이 잦은 PC라면** — `OMC_BIN`을 한 번 박아두면 PATH 무관하게 동작:
> ```powershell
> [Environment]::SetEnvironmentVariable("OMC_BIN", "C:\Program Files\OpenModelica1.26.x-64bit\bin\omc.exe", "User")
> # 새 창부터 자동 적용. 자세한 건 트러블슈팅의 "해결 3" 참고.
> ```

---

## 트러블슈팅 (이번에 실제로 겪은 것들)

| 증상 | 원인 | 해결 |
|---|---|---|
| `/health`가 `{"detail":"Not Found"}` (404) | 그 포트에 **HPWD가 아닌 다른 서버**가 떠 있음 (Docker / Open WebUI / llama 등) | 포트 점유자 확인 후 정리하거나, **HPWD를 다른 포트로**(`$env:PORT="8010"`) |
| Status **"Failed to fetch" / Disconnected** | 로컬 서버가 안 떠 있음 (창 닫힘 / Ctrl+C / 크래시) | 서버 다시 띄우기 (Step 3) |
| `/health` reason **"omc 없음"** | OpenModelica 미설치, **또는 (자주) 설치는 됐는데 서버를 띄운 창의 PATH에 omc가 없음** | 서버 창에서 `omc --version` 확인 → 안 되면 아래 **"⚠️ omc가 깔려있는데 'omc 없음'"** 참고 |
| `/health` reason **"HelmholtzMedia 없음: <경로>"** | `HELMHOLTZ_PATH` 미설정 또는 경로 틀림 (계정명 다름 등) | `$HOME` 방식으로 재설정 (아래) → `Test-Path`로 파일 존재 확인 |
| Modelica 토글이 **회색** (연결은 됨) | 위 둘 중 하나 (reason 확인) | `Invoke-RestMethod .../health | ConvertTo-Json -Depth 5` 로 reason 보기 |
| 새 창에서 서버 띄웠더니 `available=False` | `$env:HELMHOLTZ_PATH`가 안 잡힘 (환경변수는 **창마다 따로**) | 같은 창에서 HELMHOLTZ_PATH 다시 설정 후 재시작 |
| 포트 8000이 자꾸 충돌 | Docker 컨테이너 등이 8000 점유 | **PORT=8010** 등 다른 포트 사용 (권장) |
| 같은 포트에 python 2개가 listen | 이전 서버가 Ctrl+C로 안 죽음 | `Get-NetTCPConnection -LocalPort <포트> -State Listen` 으로 PID 확인 → `Stop-Process` |

**포트 점유자 확인 명령:**
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8010 -State Listen -EA SilentlyContinue).OwningProcess | Select Id, ProcessName, Path
```

### ⚠️ omc가 깔려있는데도 `/health` reason이 "omc 없음"일 때 (실제로 자주 겪음)

**원인:** 서버는 **자기를 띄운 PowerShell 창의 PATH**를 물려받음. 그 창이 OpenModelica 설치 *전*에 열렸거나, 설치로 바뀐 PATH를 아직 못 받았으면 — omc가 설치돼 있어도 서버(`shutil.which("omc")`)가 못 찾음. (다른 창에서 `omc --version`이 되더라도, **서버 띄운 그 창**에 없으면 소용 없음.)

**진단 — 서버 띄운 바로 그 창에서:**
```powershell
omc --version
```
여기서 실패하면 그 창 PATH에 omc 없음 (= 원인 확정).

**omc.exe 위치 찾기** (omc 되는 창에서, 또는 검색):
```powershell
where.exe omc
# 안 나오면:
Get-ChildItem "C:\Program Files\OpenModelica*\bin\omc.exe","C:\OpenModelica*\bin\omc.exe" -EA SilentlyContinue | Select FullName
```

**해결 1 (즉시)** — 서버 창에서 omc bin을 PATH 앞에 끼우고 서버 띄움 (경로는 실제 설치 경로로):
```powershell
$env:PATH = "C:\Program Files\OpenModelica1.26.x-64bit\bin;" + $env:PATH
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
omc --version          # 이제 버전이 떠야 함
python server.py
```

**해결 2 (영구)** — User PATH에 한 번 박고 **새 창**부터 사용:
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\OpenModelica1.26.x-64bit\bin", "User")
# 이후 새로 여는 PowerShell 창은 omc가 항상 잡힘 (기존 창엔 적용 안 됨 → 새 창 열 것)
```

**해결 3 (PATH 완전 우회)** — `$OMC_BIN` 환경변수로 omc.exe 경로 **직접 지정** (백엔드가 이 변수를 PATH보다 우선 사용):
```powershell
$env:OMC_BIN = "C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe"   # omc.exe 까지 풀경로
$env:HELMHOLTZ_PATH = "$HOME\HelmholtzMedia\HelmholtzMedia\package.mo".Replace('\','/')
$env:PORT="8010"
python server.py    # PATH에 omc 없어도 동작. where.exe omc 가 못 찾아도 OK.
```
> 가장 깔끔한 방법. PATH 분쟁(설치 위치 못 찾음 / 다른 omc와 충돌 / 새 창마다 prepend) 다 우회. `$env:OMC_BIN` 한 줄만 박으면 됨. **영구 등록**하려면 User 환경변수에 박으면 새 창마다 자동 적용:
> ```powershell
> [Environment]::SetEnvironmentVariable("OMC_BIN", "C:\Program Files\OpenModelica1.26.3-64bit\bin\omc.exe", "User")
> ```

> 핵심: **서버는 반드시 `omc --version`이 되는 창에서 띄울 것** (해결 1·2의 경우). `OMC_BIN`(해결 3)을 쓰면 `where.exe omc`가 못 찾아도 동작함.

**알아두면 좋은 것**
- 환경변수(`$env:...`)는 **PowerShell 창마다 따로**. 새 창 열면 다시 설정해야 함.
- 서버는 띄운 창에 붙어 있음 → **그 창 닫으면 서버 죽음.** 서버 창과 작업 명령 창을 분리할 것.
- 터미널 붙여넣기: **Ctrl+Shift+V** 또는 **Shift+Insert** (Ctrl+V 아님).
- 첫 Modelica 호출만 느림(omc 빌드). 컴포넌트 타입별로 **1회 빌드 후 캐시** → 이후 즉시.
- 캔버스가 https(Railway)에서 http://localhost 백엔드를 부르는 구조 (Chrome은 localhost는 mixed-content 허용). 사내망/프록시 환경에서 막히면 clone한 `public/index.html`을 로컬에서 직접 열어도 됨.

---

## 한눈 체크리스트

**새 PC:** Git → Python(3.11+) → OpenModelica 설치 → repo 2개 clone → `pip install -r requirements.txt` → `HELMHOLTZ_PATH`·`PORT` 설정 → `python server.py` → `/health` 확인 → 캔버스 Custom URL `http://localhost:8010` SET → Modelica 선택 → 테스트.

**원래 PC:** (필요시 `git pull`) → 포트 확인 → `HELMHOLTZ_PATH`·`PORT` 설정 → `python server.py` → `/health` 확인 → 캔버스 자동 재연결 확인.
