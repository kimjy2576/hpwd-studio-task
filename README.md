# HPWD Studio — Task 과제 전용 프로토타입

세탁건조기 사이클 전용 UI. 냉동사이클(압축기-응축기-LEV-증발기) + 공기사이클(드럼-필터-증발기-응축기-팬) 고정 schematic, 클릭 기반 파라미터 편집, LLM 어시스턴트 shell.

## 배포
Railway에서 GitHub 연동 → 자동 배포 (Python `http.server` 기반 정적 서빙).

## 구조
- `public/index.html` — HPWD Studio UI
- `server.py` — 정적 파일 서버
- `Procfile`, `railway.json` — Railway 배포 설정
