# HPWD-Studio Backend

Python 컴포넌트 시뮬 계산을 처리하는 FastAPI 서버.

---

## 개요

HPWD-Studio (브라우저 React 앱)는 일부 컴포넌트의 계산을 이 백엔드에 위임합니다.
컴포넌트의 `backend === 'python'`이면 시뮬 엔진이 자동으로
`http://localhost:8000/compute`를 호출합니다.

```
Studio (브라우저)  ──(HTTP)──>  FastAPI 서버 (이 폴더)
                                    │
                                    └─> Python 컴포넌트 (components/)
```

백엔드가 꺼져 있으면 Studio는 자동으로 JS 구현으로 fallback하므로 시뮬은 끊기지 않습니다.

---

## 사전 준비

- Python 3.10 이상
- pip
- (Windows) `python --version`이 PATH에서 동작해야 함

---

## 실행 — Windows

`backend` 폴더에서 `start.bat` 더블클릭. 또는:

```cmd
cd backend
start.bat
```

최초 실행 시:
1. `venv\` 자동 생성
2. `requirements.txt` 자동 설치
3. 서버 시작 (http://localhost:8000)

이후 실행은 venv 재사용해서 즉시 시작.

## 실행 — Mac/Linux

```bash
cd backend
chmod +x start.sh    # 최초 1회만
./start.sh
```

또는 수동:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

---

## 동작 확인

서버 시작 후 브라우저에서:
```
http://localhost:8000/health
```

다음 응답이면 정상:
```json
{ "status": "ok", "version": "0.1.0", "components": ["adder"] }
```

Studio 새로고침하면 상단 toolbar에 `● Backend (1)` 초록 배지 표시.

---

## API

| Endpoint | Method | 설명 |
|---|---|---|
| `/health` | GET | 살아있는지 + 컴포넌트 목록 |
| `/components` | GET | 모든 컴포넌트 요약 |
| `/components/{name}` | GET | 특정 컴포넌트의 modelDescription |
| `/compute` | POST | 컴포넌트 1 step 계산 |

### POST /compute 예시

```json
// Request
{
  "component": "adder",
  "input":  { "a": 3, "b": 5 },
  "params": { "gain": 2.0, "offset": 0 },
  "state":  {},
  "dt": 1.0
}

// Response
{
  "outputs":  { "sum": 16.0 },
  "newState": {},
  "error": null
}
```

---

## 새 컴포넌트 추가

1. `components/` 폴더에 새 `.py` 파일 생성 (예: `my_hx.py`)
2. 3가지 정의:

   ```python
   modelDescription = {
       "typeNo": 105,
       "name": "My HX",
       "category": "refrigerant",
       "backend": "python",
       "variables": [...],
   }

   def step(input, params, state, dt):
       # 물리 계산
       return {"outputs": {...}, "newState": state}

   def validate(params):  # 선택
       return []
   ```

3. 서버 재시작 → 자동 등장

예시: `components/adder.py` 참고.

---

## 트러블슈팅

**포트 8000 이미 사용 중**:
```cmd
set PORT=8001
python server.py
```
Studio의 `BACKEND_URL`도 같이 변경 필요.

**Studio가 "Backend OFF"만 표시**:
- 서버 켜져 있는지 (`http://localhost:8000/health` 직접 확인)
- F12 콘솔에서 CORS 에러 확인
- 방화벽이 localhost 차단 안 하는지

**pip install 실패**:
사내 프록시 환경에서:
```cmd
pip install -r requirements.txt --index-url https://your-internal-pypi/
```

**Python 못 찾음 (Windows)**:
- Python 설치 시 "Add to PATH" 체크 안 했을 가능성
- `py -3 -m venv venv`로 시도
- 또는 Python 재설치하며 PATH 추가

---

## 다음 단계

현재: **Day 1 — Adder 1개로 백엔드 통신 검증**

이후:
- Day 2: Compressor + CoolProp
- Day 3: 나머지 6개 컴포넌트 (Condenser, EEV, TXV, Evap, Fan, Drum)
- Day 4: Component Studio에 Python 모드
- Day 5: 사내 서버 배포

---

## Railway 배포 (선택적 — 클라우드에서 24/7 가능)

브라우저로 Studio 접속하는 사용자가 본인 PC에 백엔드를 안 띄워도 동작하게 하려면
백엔드를 Railway에 배포.

### 절차
1. https://railway.app 로그인 → 기존 hpwd-studio-task 프로젝트 열기
2. `+ New` → `GitHub Repo` → 같은 `kimjy2576/hpwd-studio-task` 선택
3. 새 서비스 생성 후 **Settings → Root Directory를 `backend`로 지정**
4. 자동으로 `backend/Dockerfile`과 `backend/railway.json` 인식
5. Deploy 클릭 → 빌드 후 `https://hpwd-backend-production.up.railway.app` 같은 URL 부여

### 검증
브라우저에서:
```
https://<배포된-URL>/health
```
→ `{"status":"ok","components":["adder"]}` 응답이면 OK.

### Studio가 자동으로 사용
Studio의 `BACKEND_URL`은 환경 자동 인식:
- localhost 접속 → `http://localhost:8000` 사용 (개발 모드)
- Railway URL 접속 → 배포된 백엔드 URL 사용

URL 토글 UI는 Studio 상단 BackendStatus 옆 dropdown.

---

**Maintainer**: HPWD Platform Team
