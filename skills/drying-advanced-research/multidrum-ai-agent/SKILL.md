---
name: 멀티드럼 AI Agent
description: >
  멀티드럼 HPWD의 세탁(진동)·건조 설계 요청 — 성능 예측, 최적 설계안 도출,
  설계 개선점 제안 —에서 트리거. 신규 실험 데이터가 들어오면 해석 툴 보정계수를
  자동 갱신한다. 해석 툴·메타모델(DNN)·최적화 툴을 자연어로 오케스트레이션해
  용량/형상/시스템연계/구조/배치 컨셉 설계를 지원한다.
project: 멀티드럼 AI Agent 개발
version: 1.0.0
metadata:
  authorName: 김진영
  authorEmail: e-mail@gmail.com   # ⚠️TODO 실제 이메일로 교체
  domain: drying-advanced-research
  lastUpdated: 2026-06-10
  runnerCompatibility: agnostic   # 자체 sLLM(Ollama+Qwen 3 14B) 독립 구동 — 특정 벤더 런타임 비의존
  skillType: not-executable
---

# 멀티드럼 AI Agent

> 멀티드럼 HPWD(히트펌프 세탁건조기)의 컨셉 설계를 돕는 AI Agent.
> 세탁(진동)·건조 성능을 기반으로 설계 반복 횟수와 실험 의존도를 줄여,
> 컨셉 설계 리드타임 단축 + 초기 단계 설계 품질 향상 → 개발 효율 향상을 목표로 한다.

---

## 0) Folder Structure

```
multidrum-ai-agent/
├─ SKILL.md
├─ references/                  # Agent 운영 규칙·도메인 정의 (SKILL이 직접 참조)
│  ├─ terms.md                  # SMER·진동지표·보정계수·DNN 등 도메인 사전
│  ├─ business-rules.md         # 세탁/건조 분기·해석툴 선택·보정·외삽 경고 규칙
│  ├─ mapping.md                # 자연어 → 설계인자/KPI 매핑
│  ├─ design-space.md           # 설계 인자 정의·범위·단위·제약 (탐색공간/외삽 기준)
│  └─ output-format.md          # 답변 포맷 + KPI 테이블 + Pareto/그래프 표기
├─ docs/                        # RAG 지식 문서(md) — sLLM 지식 보강 · 자동 생성/보강 대상
│  ├─ components/               # 부품: eev, heat_exchanger, r290_compressor
│  ├─ concepts/                 # 개념: smer, cop_eei, eei_calculation
│  ├─ cycle_physics/            # 사이클 물리: hpwd_cycle_cop
│  ├─ design_guides/            # 설계 가이드: design_guide_smer
│  ├─ standards/                # 규격: iec61121_smer, eei_energy_label
│  └─ troubleshooting/          # 트러블슈팅: poor_drying
│                               #   (각 폴더에 _TEMPLATE.md = 신규 문서 작성 템플릿)
├─ qdrant_db/                   # 벡터DB — docs 임베딩 적재 (Qdrant, 로컬 파일 모드)
├─ mcp/                         # 도구 공유용 MCP 서버 — 멀티드럼 + 사내 타 에이전트가 호출
│  ├─ server.py                 # scripts/ 도구를 MCP tool로 등록·노출 (해석·보정·DNN·최적화·DB조회)
│  └─ tools.md                  # 노출 tool 입출력 스키마·권한 정책
├─ scripts/                     # 도구 실제 구현 (mcp/server.py가 래핑해 노출)
│  ├─ run_recurdyn.py           # 세탁 진동 해석(Recurdyn) 호출
│  ├─ run_dry_1d.py             # 건조 1D 사이클 시뮬레이션 (로컬 서버)
│  ├─ calibrate.py              # 실험DB 비교 → 해석 툴 보정계수 갱신
│  ├─ build_seed_db.py          # 핵심 설계인자 케이스별 성능DB(Seed) 생성
│  ├─ train_dnn.py              # Surrogate 메타모델(DNN) 학습
│  ├─ optimize.py               # 단목적/다목적 최적화
│  ├─ build_vectordb.py         # docs/*.md → 청크 → 임베딩 → qdrant_db 적재
│  └─ generate_questions.py     # 평가 질문 자동 생성 (골든셋)
└─ data/
   ├─ experiment_db/            # 실험 DB (Ground Truth)
   ├─ seed_db/                  # 성능 DB (Seed Data)
   └─ calibration/              # 보정계수 이력
```

---

## 1) Purpose

- 이 Skill은 멀티드럼 HPWD 설계자의 자연어 요청에 대해, 세탁(진동)·건조 성능 기반의 설계 지원을 일관된 절차로 제공한다.
- **트리거는 키워드 정확 매칭이 아니라 의도(intent) 기반이다.** 설계자가 아래 작업유형을 정확한 문구로 말하지 않아도, sLLM(Qwen 3)과 RAG가 요청의 의미를 파악해 가장 가까운 작업유형으로 분류·라우팅한다. 구어체·축약·모호한 표현도 의미가 닿으면 트리거된다.
- 작업유형 (요청의 의미가 다음 중 하나에 가까우면 트리거):
  - **ⓐ 성능 예측** — 어떤 설계안·조건의 성능이 궁금한 모든 표현
    예: "이 설계안 진동 어때?" / "용량 키우면 잘 마르나?" / "이 형상 SMER 얼마 나와?" / "흔들림 괜찮을까?"
  - **ⓑ 최적 설계안 도출** — 목표·제약을 만족하는 설계를 찾으라는 표현
    예: "진동 최소 배치 찾아줘" / "SMER 0.6 이상 만족하는 설계" / "효율 최대로 뽑아줘" / "제일 좋은 조합은?"
  - **ⓒ 설계 개선점 제안** — 현재 설계를 더 낫게 만드는 방향을 묻는 표현
    예: "여기서 뭘 바꾸면 좋아져?" / "진동 줄이려면?" / "개선 포인트 알려줘" / "왜 성능이 안 나와?"
  - **ⓓ 해석 툴 보정** — 신규 실험 데이터 입력 또는 실험-해석 불일치를 알리는 표현
    예: 신규 실험 DB 업로드 / "이 시험 결과로 해석 보정해줘" / "해석값이 실험이랑 차이나"
- 의미가 모호하면 단정하지 않고 되묻는다(역질문, §9·§12). 구어·동의어 → 표준 설계인자/지표 매핑은 `references/mapping.md`, 용어는 `references/terms.md`를 따른다.
- 설계 대상 범위는 **용량 · 형상 · 시스템 연계 · 구조 · 배치** 전반을 포함한다.

---

## 2) Scope

**포함**

- 세탁(진동) 설계 지원: 기존 `NX 도면 설계 → Recurdyn 진동 해석 → 실험` 루프의 **설계 회수 단축**
- 건조 설계 지원: 기존 `NX 도면 설계 → 실험` 루프에 **1D 시뮬레이션을 신규 도입**하여 설계 정확도↑ · 설계 시간↓
- **실험 DB 기반 해석 툴 자동 검증·보정**: 신규 실험 입력 시 해석값과 비교 → 보정계수 자동 갱신 → Seed DB·메타모델 갱신
- **RAG 기반 사내 지식 활용·보강**: 부품·개념·사이클물리·설계가이드·규격·트러블슈팅 문서(`docs/`)를 의미검색해 sLLM 답변 근거로 사용하고, 약점 발견 시 관련 md를 자동 생성·보강
- 6개 구성요소(실험DB · 해석툴 · 성능DB(Seed) · 메타모델(DNN) · 최적화툴 · Agent sLLM) 오케스트레이션 — sLLM(Qwen 3)은 RAG로 세탁/건조 도메인 지식을 보강
- 컨셉~초기 단계 설계의 성능 예측 / 최적화 / 개선 제안 (세탁·건조 양측)

**제외**

- 최종 양산 설계 확정 및 양산 검증 (본 Skill은 컨셉·초기 설계 지원 범위)
- NX 도면 직접 작성 (설계 인자/파라미터 입력 기반으로 동작)
- 원천 실험 데이터 계측 자체 (실험DB는 입력 자산으로 전제, 단 보정·검증 용도로는 활용)
- 멀티드럼 외 타 제품군

---

## 3) Folder Contract (필수 구성)

| 경로 | 용도 |
|---|---|
| `references/business-rules.md` | 세탁/건조 라우팅, 해석툴 선택, 보정, 메타모델 외삽 경고 규칙 |
| `references/mapping.md` | 자연어 표현 → 설계인자/KPI 매핑 |
| `references/design-space.md` | 설계 인자 정의·범위·단위·제약 (최적화 탐색공간·외삽 경계 기준) |
| `docs/` | RAG 지식 문서(md) — 의미검색 대상, 약점 시 자동 생성·보강 (폴더별 `_TEMPLATE.md`) |
| `qdrant_db/` | `docs/` 임베딩 벡터DB (Qdrant 로컬 파일 모드) |
| `data/experiment_db/` | 보정·검증의 Ground Truth 실험 데이터 |
| `data/seed_db/` | 해석 툴로 생성한 케이스별 성능 DB(메타모델 학습 Seed) |
| `data/calibration/` | 도메인·조건별 보정계수와 갱신 이력 |
| `scripts/run_recurdyn.py` | 세탁 진동 해석 — **Recurdyn(상용 라이선스) 의존** |
| `scripts/run_dry_1d.py` | 건조 1D 사이클 시뮬 — **로컬 서버 의존** |
| `scripts/calibrate.py` | 실험-해석 잔차 산출 → 보정계수 갱신 |
| `scripts/train_dnn.py` | Seed DB 기반 Surrogate 메타모델(DNN) 학습 |
| `scripts/optimize.py` | 메타모델 목적함수 기반 단/다목적 최적화 |
| `scripts/build_vectordb.py` | `docs/*.md` → 청크 → 임베딩 → `qdrant_db` 적재 |
| `mcp/server.py` | `scripts/` 도구를 MCP tool로 노출 (사내 타 에이전트 공유) |

---

## 4) Runner & Architecture Notes

- **실행 형태**: 자체 sLLM 기반 독립 에이전트 (특정 벤더 runner 비의존 -> `agnostic`)
  - **모든 기능은 sLLM과의 자연어 대화로 구동** — sLLM이 중심에서 도구·데이터·RAG를 오케스트레이션 (모든 것이 LLM과 엮여 동작)
  - sLLM 모델: Qwen 3 14B, **Ollama 로컬 서빙**
  - 오케스트레이션: LangGraph (tool 호출 순서·분기·반복·에러 복구를 상태 그래프로 정의)
  - RAG: 전문용어 해석 + 결과 데이터 분석 보조
- **해석 툴 구동 환경 (runner와 별개)**
  - Recurdyn(세탁 진동): **Windows + 상용 라이선스** 환경 -> Agent와 별도 머신/배치 큐로 호출 (컨테이너 직접 실행 불가)
  - 건조 1D 시뮬(신규 구축): **로컬 서버에서 실행**
- **LLM 비기반(비표준) 환경에서의 사용**: 직접 실행형이 아니라 **시스템 재구축 명세 문서**로 사용한다. 아래 아키텍처가 그 정의 역할을 한다.

### 시스템 아키텍처 (sLLM 중심 오케스트레이션)

본 Agent는 LLM과의 대화로 구동되므로 모든 구성요소가 sLLM과 엮여 동작한다. sLLM이 의도를 분류하고 작업유형별로 도구를 호출하며, RAG가 전문용어 해석·결과 데이터 분석을 보조한다.

```
        설계자  <->  자연어 대화
                       |
   +-------------------v-----------------------------+
   |  Agent sLLM  (Qwen 3 · Ollama 서빙)             |   <- 모든 구동의 중심
   |   · LangGraph 오케스트레이션                    | <=> RAG [docs/ · qdrant_db/]
   |   · RAG: 전문용어 해석 + 결과 데이터 분석        | <=> DB  [실험 DB · Seed DB]
   +-------------------+-----------------------------+
            의도 분류 -> 작업유형별로 도구 호출
   +-------------------+-------------------+-------------------+
   v                   v                   v                   v
 메타모델            해석 툴             최적화 툴           실험 DB 업로드
 (DNN)            Recurdyn / 1D       <-> 메타모델 다회       -> 보정 체인
```

작업유형별 실행 경로:

- **ⓐ 성능 예측**
  - 기본: sLLM -> **메타모델(DNN)** -> 성능값 (빠른 도출)
  - 정밀 분석 요청 시: sLLM -> **해석 툴**(Recurdyn/1D) -> 시계열 결과 -> **RAG+DB로 분석**
- **ⓑ 최적 설계안 도출**
  - sLLM -> **최적화 툴 <-> 메타모델 다회 호출** (둘 사이 통신 많음) -> 최적해 / Pareto
- **ⓒ 설계 개선점 제안**
  - sLLM -> 메타모델 또는 해석 툴 **결과 데이터** 읽기 -> **RAG+DB로 분석** -> 설계 인자 개선점 제안
- **ⓓ 해석 툴 보정** (연구자가 실험 DB 업로드 -> 자동 체인)
  - 실험 DB 업로드 -> **해석 툴 보정** -> **Seed DB 구축** -> **메타모델 재구축** (전 과정 자동)

전 작업 공통: Ollama 서빙 · LangGraph 오케스트레이션 · RAG(전문용어 해석 · 데이터 분석 지원)

### Deployment (사내 공유 — B: 도구 공유)

무거운 컴포넌트(Qwen via Ollama · 해석 툴 · Qdrant)는 PC마다 설치하기 부담스러워, 사내 온프레미스 서버에 배치해 공유한다. 도구는 MCP로 노출해 멀티드럼 외 사내 타 에이전트도 호출한다.

- **컴포넌트 배치**
  - sLLM(Qwen): GPU 서버에 Ollama 서빙 -> **Ollama API로 다중 클라이언트 공유** (이건 MCP가 아님)
  - RAG(`docs/` · `qdrant_db/`) · 메타모델 · 최적화: 서버
- **도구 공유 = MCP**: `mcp/server.py`가 해석·보정·메타모델·최적화·DB조회를 MCP tool로 노출 -> 멀티드럼 sLLM + 사내 타 에이전트가 동일 규약으로 호출
- **사용자(클라이언트)**: 경량 웹/CLI로 접속, 무거운 연산은 서버가 수행
- **사내망 전제**: 온프레미스 · 사내망 내 처리(외부 인터넷 불요) · 권한은 MCP tool 단위로 통제

---

## 5) Domain Knowledge Pack (심화)

### 5.1 Terms Depth Level

- 현재 레벨: `detailed`
- 용어 파일: `references/terms.md` (세탁 진동 / 건조 사이클 / 메타모델·최적화·보정 3개 군)

### 5.2 Business Rule Priority

규칙 충돌 시 우선순위:

1. **설계 안전·물리 제약** (진동 허용 기준, 구조 한계, 사이클 물리 정합성)
2. **해석 경로 정합성** (세탁 = Recurdyn, 건조 = 1D 시뮬 — 임의 교차 금지)
3. **보정·신뢰 범위** (최신 보정계수 적용, 메타모델은 Seed DB 학습 범위 내에서만 신뢰)
4. **근거 기반 답변** (RAG 검색 결과·도구 결과 데이터에 근거, 무근거 추측·단정 금지)
5. **출력 형식 규칙** (KPI 테이블/포맷/단위)

### 5.3 Rule Traceability

| Rule ID | 설명 | 근거 소스 | 검증 방법 |
|---|---|---|---|
| BR-001 | 세탁 요청은 Recurdyn, 건조 요청은 1D 시뮬로 라우팅 | `references/business-rules.md` | 도메인 분기 케이스 회귀 테스트 |
| BR-002 | 메타모델 예측은 Seed DB 범위 내에서만 신뢰. 외삽 시 경고 + 해석툴 재호출 권고 | `references/business-rules.md` | 범위 밖 입력 케이스 검사 |
| BR-003 | 최적화 상위 후보해는 해석 툴로 재검증 후 제시 | `references/business-rules.md` | tool-call 로그 검사 |
| BR-004 | 성능 답변에 도메인 KPI 명시 (세탁=진동지표, 건조=SMER·건조시간 등) | `references/output-format.md` | 출력 스냅샷 검사 |
| BR-005 | 설계안은 범위 5종(용량/형상/시스템연계/구조/배치)에 매핑해 표기 | `references/output-format.md` | 출력 필드 검사 |
| BR-006 | 신규 실험 입력 시 동일 조건 해석과 비교해 보정계수 갱신 -> Seed DB 재구축 -> 메타모델 재학습까지 자동 수행 | `references/business-rules.md` | 보정 전후 잔차 감소 검증 |
| BR-007 | 성능 예측 기본은 메타모델(DNN), "정밀 분석" 요청 시 해석 툴 시계열로 수행 | `references/business-rules.md` | 작업깊이별 도구 선택 로그 검사 |
| BR-008 | 분석·개선점·전문용어 답변은 RAG 검색 + 도구 결과 데이터에 근거, 무근거 단정 금지 | `references/business-rules.md` | 근거 인용 누락·환각 검사 |

---

## 6) Terms (요약)

- **세탁(진동)**: 진동 가속도·변위, 불평형(unbalance), 고유진동수·공진, 감쇠·서스펜션, Recurdyn(다물체 동역학 해석)
- **건조**: SMER(단위 전력당 수분 제거량, kg/kWh), 건조시간, 에너지 등급, 1D 사이클 시뮬
- **공통(AI)**: 성능 DB(Seed Data), Surrogate 메타모델(DNN), 단목적/다목적 최적화, Pareto front
- **RAG·검색**: 임베딩, 청크, 벡터DB(Qdrant), 의미검색(Top-K), 문서 자동 보강
- **Agent**: sLLM(Qwen 3), Ollama(로컬 서빙), LangGraph(오케스트레이션)
- **보정**: 보정계수(calibration coefficient), 잔차(residual), Ground Truth(실험값)

> 상세 정의·동의어·단위 규칙은 `references/terms.md`에 유지한다.

---

## 7) Roles

- **Owner**: 김진영
- **Contributor(s)**: 세탁기차세대플랫폼Task (세탁/진동·건조·해석·데이터 협업)

---

## 8) Inputs

- 시작에 필요한 입력/전제
  - 설계 도메인(세탁/건조) 및 설계 인자 (용량/형상/시스템연계/구조/배치)
  - 목표 KPI 또는 제약 조건 (최적화/개선 시)
  - 실험 DB · 성능 DB(Seed) 접근 권한
  - 보정 시: 동일 운전조건을 식별할 실험 메타(조건 키)
- input file dependency
  - 파일명: `request.json` (대화형은 Interpreter가 동등 JSON을 생성)
  - 형식: JSON (UTF-8)
  - 생성 주체: 설계자 입력/Interpreter 변환
  - 설계 인자 키·범위는 `references/design-space.md` 정의를 따른다

입력 JSON 스키마 (`//` 주석은 설명용):

```json
{
  "task": "predict",                 // predict | optimize | improve | calibrate
  "domain": "dry",                   // wash | dry
  "design_factors": {                // design-space.md 정의 인자 (해당 task에 필요한 것만)
    "drum_capacity_l": 12.0,
    "geometry":  { "drum_dia_mm": 600, "duct_len_mm": 350 },
    "structure": { "spring_k_Npm": 12000, "damper_c_Nsm": 50 },
    "layout":    { "compressor_pos": "rear" },
    "system":    { "refrigerant": "R290", "charge_g": 150 }
  },
  "objectives": [                    // optimize / improve 시
    { "metric": "smer", "goal": "max" },
    { "metric": "dry_time_min", "goal": "min" }
  ],
  "constraints": [                   // 탐색 범위 (design-space 한계 내)
    { "param": "drum_capacity_l", "min": 10, "max": 14 }
  ],
  "options": {
    "precision": "fast",             // fast = 메타모델 | detailed = 해석툴 시계열
    "optimization": "multi"          // single | multi
  },
  "experiment_data": null            // calibrate 시: 실험 데이터 파일 경로
}
```

작업유형별 필수 필드:

| task | 필수 필드 |
|---|---|
| `predict` (ⓐ) | `domain`, `design_factors`, `options.precision` |
| `optimize` (ⓑ) | `domain`, `objectives`, `constraints`, `options.optimization` |
| `improve` (ⓒ) | `domain`, `design_factors`(현재안), `objectives`(개선 목표) |
| `calibrate` (ⓓ) | `domain`, `experiment_data` |

## 9) Steps

> 3-7단계 권장. 각 단계는 실행 가능 문장으로 작성.

1. **질의 파싱 (의도 분류)** — 요청에서 도메인(세탁/건조) · 작업유형(예측/최적화/개선/보정) · 설계 인자를 추출한다 (정확한 문구 아니어도 sLLM+RAG가 의미로 분류, §1).
   - 예시: "드럼 용량 X로 키우면 진동 어때?" → `domain=세탁`, `task=예측`, `factor=용량`
   - 실패 예시: 도메인·인자 모두 누락 → BR-001 적용 전에 역질문(§12)
2. **매핑** — `references/mapping.md`로 자연어 표현을 설계 인자/KPI로 매핑한다.
   - 예시: "물이 잘 안 빠짐"(건조) → `Measure=SMER 저하`, "흔들림"(세탁) → `Measure=진동 가속도`
   - 실패/예외 예시: 사전에 없는 모호 표현(예: 웅웅거림)은 후보 제시 후 역질문
3. **라우팅 규칙 확정** — `references/business-rules.md` 우선순위로 해석 경로·보정계수 적용·메타모델 사용 여부를 정한다.
   - 예시: 세탁 → Recurdyn(BR-001), 최신 보정계수 적용, 입력이 Seed 범위 밖이면 경고(BR-002)
   - 실패/예외 예시: 세탁+건조 복합 요청은 도메인별 분리, 보정계수 없는 신규 조건은 미보정 해석+주의 표기
4. **실행** — 작업유형별로 분기한다.
   - ⓐ 예측: 기본 메타모델(DNN) → KPI. 정밀 요청 시 해석툴 시계열 → RAG+DB 분석(BR-007)
   - ⓑ 최적화: 최적화 툴이 메타모델 목적함수를 평가해 최적해/Pareto 도출 → 상위해는 해석툴 재검증(BR-003)
   - ⓒ 개선: 메타모델/해석툴 결과를 RAG+DB로 분석 → 설계 인자 개선점 제안(BR-008)
   - ⓓ 보정: 신규 실험 vs 동일 조건 해석 비교(잔차) → 보정계수 갱신 → Seed DB 재구축 → 메타모델 재학습 자동(BR-006)
   - 예외: 최적해 없음(제약 과도)은 제약 완화 제안 / 메타모델 외삽은 해석툴 재호출(BR-002) / 도구 실행 실패는 에러 복구·재시도
5. **출력** — `references/output-format.md` 규칙으로 KPI 테이블 + 근거 + (해당 시) Pareto/그래프/보정 리포트를 생성한다.
   - 예시: 설계 범위 5종에 매핑해 표기(BR-005), 단위 명시(BR-004), 보정은 전후 잔차 비교 명시
   - 실패/예외 예시: RAG 근거 없으면 확인 불가로 표기, 무근거 단정 금지(BR-008)

---

## 10) Artifacts

- **중간 산출물**: 설계 인자 JSON, 케이스 매트릭스, 메타모델 예측 결과, 최적화 후보해, 잔차/보정계수 로그
- **최종 산출물** (작업유형별): ⓐ KPI 예측값 · ⓑ 최적 설계안+Pareto front · ⓒ 개선점 리포트 · ⓓ 보정 리포트(전후 잔차) — 모두 RAG 근거(출처 문서) 인용 포함(BR-008)
- **그래프 포맷**
  - 렌더: `Plotly(HTML, 인터랙티브)` / `matplotlib(PNG·SVG, 정적·리포트용)` / `PDF(임베드)`
  - 차트 종류: parity plot(예측 vs 실측), Pareto front(다목적), 감도 tornado, 최적화 수렴곡선, 진동 FFT·시간이력, 건조곡선·P-h 선도
- **포맷**: .json, .csv, .md, .pdf, 그래프(.html/.png/.svg)

---

## 11) MCP / Tooling Spec

- MCP Servers: multidrum-mcp (해석·보정·메타모델·최적화·DB조회 도구를 MCP tool로 노출, 사내 타 에이전트 공유)
- MCP 설치/초기화 방법: ⚠️TODO ./setup multidrum-mcp + ollama pull qwen3:14b + LangGraph 그래프 정의
- 사용 스크립트: scripts/run_recurdyn.py · run_dry_1d.py · calibrate.py · train_dnn.py · optimize.py · build_vectordb.py
- 권한/신뢰 정책: MCP tool 단위 권한 통제(RBAC) · 사내망 내 처리
- 네트워크 또는 시스템 제약: 외부 인터넷 불요 / Ollama는 GPU 서버 / Recurdyn은 Windows 상용 라이선스 머신

---

## 12) Exceptions

- **도메인 모호(세탁/건조 불명)**: 어느 성능 기준인지 역질문 후 진행
- **메타모델 외삽(Seed 범위 밖)**: 경고를 명시하고 해석 툴 재호출을 권고 (BR-002)
- **건조 1D 시뮬 미수렴(DAE 초기화)**: 주요 변수 `start` 값 부여 + N ramp-up 단계적 기동 가이드 제시
- **Recurdyn 실행/라이선스 오류**: ⚠️TODO 대체 경로(배치 큐/캐시된 Seed 결과) 안내
- **보정 조건 불일치**: 실험-해석의 운전조건이 매칭되지 않으면 매칭 가능한 케이스만 보정, 잔차가 임계 초과 시 보정 보류 + 경고
- **목표 KPI 미달(최적해 없음)**: 제약 완화 시나리오 또는 설계 범위 확장 제안
- **작업 의도 모호(ⓐⓑⓒⓓ 불명)**: 어느 작업유형인지 역질문, mapping.md로 정규화 (도메인 모호와 별개 축)
- **MCP tool 호출 실패/권한 거부**: 타임아웃·미응답 시 재시도·캐시 결과 안내, 권한 없는 접근은 거부 후 사유 명시 (RBAC)
- **요청이 Scope 밖(양산확정·NX도면·타제품군)**: 지원 범위 아님을 안내하고 가능한 대안 제시

---

## 13) Eval (적용 평가)

### Blocking Eval

- OwnerAssigned
- RiskReviewed (Recurdyn 환경·데이터 접근 권한)
- AccessRuleSet (실험/Seed DB 권한)
- CriticalRulesMapped (BR-001~006)

### Output Eval

- PurposeClarity (성능예측/최적화/개선/보정 의도 명확)
- Traceability (적용 Rule·해석 경로·보정계수 버전 설명 가능)
- QualityCheckDone (Seed 범위·해석툴 재검증·보정 전후 잔차)
- FormatCompliance (KPI 테이블·단위·설계 범위·그래프 표기)

---

## 14) Test Cases & Human Evaluation (필수 권장)

- 디테일의 절대 기준을 먼저 정하지 않는다.
- 실전 기준은 “이 SKILL 기반 Agent의 설계 지원 성능이 만족스러운가”이며, 이것이 detail threshold가 된다.
- 세탁·건조 대표 시나리오를 먼저 만들고 Human Reviewer가 채점한다.

**권장 운영**

- 초기 골든셋: 세탁·건조 합산 20~50개 시나리오
- 릴리즈 게이트 세트: 20~30개 대표 시나리오(정상/엣지/실패 포함)
- 운영 중 실패 케이스는 회귀 세트로 누적

**평가 항목**

- 정답성(Accuracy) — 예측/최적화 결과가 해석·실험과 정합
- 규칙 준수도 — 도메인 라우팅·외삽 경고·재검증·보정
- 출력 형식 적합성 — KPI/단위/Pareto/그래프 표기
- 근거 추적성 — 어떤 해석 경로·Rule·보정계수를 적용했는지 설명 가능

**Human Review 등급**

- 5: 즉시 실무 사용 가능 (수정 불필요)
- 4: 경미 수정 후 사용 가능
- 3: 부분 사용 가능 (보완 필요)
- 2: 사용 곤란 (재작업 필요)
- 1: 실패

**합격 기준**

- 평균 4.0 이상
- 치명 항목(정답성·규칙 준수도)에서 3 미만 0건
- 릴리즈 게이트 세트(20~30개) 통과율 85% 이상

---

## 15) Non-Executable SKILL Requirement

- 본 SKILL.md는 실행 지시서이자, 멀티드럼 AI Agent 시스템의 **재구축(re-build) 명세서**로도 사용된다.
- 품질 기준:
  - 제3자가 SKILL.md만으로 6개 구성요소와 데이터 흐름(§4, 보정 루프 포함)을 재구축할 수 있어야 한다.
  - 아키텍처, 입력/출력 계약, 핵심 절차·알고리즘(해석 → Seed DB → DNN → 최적화 → sLLM, + 실험DB 보정 루프), 예외 처리, 의존성이 재현 가능 수준으로 명시되어야 한다.
  - 코드가 없어도 설계·구현이 가능하고, 코드가 있으면 동일 동작을 검증할 수 있어야 한다.

---

## Appendix A) `references/terms.md` 예시

```
# Terms

| Term | Definition | Synonyms | Notes |
|---|---|---|---|
| SMER | 단위 전력당 수분 제거량(kg/kWh) | 건조 효율 | 건조 핵심 KPI |
| 진동 가속도 | 캐비닛/드럼 진동 크기 | 흔들림 | 세탁 핵심 KPI, 허용 기준 존재 |
| Seed Data | 해석 툴로 생성한 케이스별 성능 DB | 성능 DB | 메타모델 학습 입력 |
| Surrogate 메타모델 | 해석을 대체하는 빠른 예측 모델(DNN) | 대리 모델 | Seed 범위 내 유효 |
| 보정계수 | 해석값을 실험값에 맞추는 계수 | calibration coeff. | 신규 실험 입력 시 자동 갱신 |
| Pareto front | 다목적 최적화의 비지배 해 집합 | 파레토 해 | 트레이드오프 제시 |
```

## Appendix B) `references/business-rules.md` 예시

```
# Business Rules

## BR-001: 도메인 라우팅
- 조건: 요청 도메인이 세탁 또는 건조
- 규칙: 세탁 → Recurdyn 진동 해석, 건조 → 1D 사이클 시뮬
- 예외: 도메인 불명 시 역질문 후 결정
- 검증: 세탁/건조 각 5건 분기 결과 비교

## BR-002: 메타모델 외삽 경고
- 조건: 입력 설계 인자가 Seed DB 학습 범위를 벗어남
- 규칙: 예측을 제시하되 외삽 경고를 명시하고 해석 툴 재호출 권고
- 검증: 범위 경계 밖 입력 케이스에서 경고 출력 확인

## BR-003: 최적해 재검증
- 조건: 최적화 툴이 메타모델 기반으로 후보해를 도출
- 규칙: 상위 후보해는 해석 툴로 재검증 후 최종 제시
- 검증: tool-call 로그에 해석 재호출 존재 여부

## BR-004: 도메인 KPI 명시
- 조건: 성능 예측/최적화 결과를 답변
- 규칙: 세탁은 진동 지표, 건조는 SMER·건조시간 등 도메인 KPI를 단위와 함께 명시
- 검증: 출력 스냅샷에 KPI·단위 존재 확인

## BR-005: 설계 범위 매핑
- 조건: 설계안·개선점을 제시
- 규칙: 범위 5종(용량/형상/시스템연계/구조/배치)에 매핑해 표기
- 검증: 출력이 5종 범위에 매핑되는지 확인

## BR-006: 해석 툴 보정계수 갱신
- 조건: 신규 실험 데이터가 입력되고, 동일 운전조건의 해석 결과가 존재
- 규칙: 실험-해석 잔차를 산출해 보정계수를 갱신하고, 갱신본을 해석 툴 기본값으로 반영
- 후속: 보정된 조건으로 Seed DB 갱신 → 메타모델 재학습 트리거
- 예외: 조건 매칭 실패 또는 잔차가 임계 초과 시 보정 보류 + 경고
- 검증: 보정 전후 잔차 감소 여부, 보정계수 이력 기록
```

## Appendix C) `references/output-format.md` 예시

```
# Output Format

- 정량 결과는 KPI 테이블로 출력하고 단위를 컬럼/주석에 명시
- 설계안은 범위 5종(용량/형상/시스템연계/구조/배치)에 매핑해 표기
- 다목적 결과는 Pareto front를 함께 제시
- 그래프 렌더는 Plotly(HTML)/matplotlib(PNG·SVG)/PDF 중 맥락에 맞게 선택

예시(건조 성능 예측):
| 설계안 | 용량 | SMER (kg/kWh) | 건조시간 (min) | 비고 |
|---|---|---:|---:|---|
| Base | 표준 | 0.61 | 180 | 기준 |
| Case-1 | +10% | 0.58 | 195 | 용량↑ 시 효율 trade-off |

예시(보정 리포트):
| 조건 | 지표 | 해석(보정 전) | 실험 | 잔차 | 보정계수 | 해석(보정 후) |
|---|---|---:|---:|---:|---:|---:|
| C-07 | SMER | 0.65 | 0.61 | +0.04 | 0.94 | 0.61 |
```

## Appendix D) `references/test-cases.md` 예시

```
# Test Cases

## 목표
- 세탁/건조 대표 20~30개 릴리즈 게이트 시나리오로 품질 확인

## 샘플 케이스
| TC ID | 입력 질의 | 기대 결과 요약 | 적용 Rule ID | Reviewer Score (1-5) |
|---|---|---|---|---|
| TC-001 | 드럼 용량 +10% 시 건조 성능 예측 | 메타모델 SMER/건조시간 KPI 테이블 | BR-001, BR-004 | 5 |
| TC-002 | 진동 최소화 최적 배치 도출 | Recurdyn 재검증된 최적 배치 + Pareto | BR-001, BR-003 | 4 |
| TC-003 | Seed 범위 밖 형상 입력 | 외삽 경고 + 해석툴 재호출 권고 | BR-002 | 4 |
| TC-004 | 신규 건조 실험 입력 후 보정 요청 | 잔차 산출 + 보정계수 갱신 + 전후 잔차 리포트 | BR-006 | 5 |

## 리포트 규칙
- 평균 점수·항목별 점수·실패 케이스 재현 절차를 함께 기록
- 실패 케이스는 다음 릴리즈 회귀 세트로 편입
```
