# R290Tab — 미분가능·2상안전 R290 물성층

## 목적
사이클 폐루프 모놀리식 해의 corrector hang 근본원인 해결:
- raw HelmholtzMedia inline 호출 → 반복 중 `setState_pTX` 밀도 root-find 실패(bracketing)
- 2상 영역 `pT` 사용 → ill-posed
- 외부함수 통과 수치 Jacobian → 포화근처 fragile

→ **(p,h) 기반 테이블 + 해석 도함수 주석**으로 셋 다 제거.

## 설계
- **독립변수 (p,h)**: 2상 포함 전영역 well-posed. pT 영구 추방.
- **1D 포화테이블 sat(p)** + **2D (p,h) 테이블**.
- **영역인지 보간**:
  - 2상(hl<h<hv): lever rule (1D 포화 + 건도) → kink 없음
  - 단일상: 코너클램핑 bilinear (보간 코너가 잘못된 상이면 그 압력 포화값 대체)
- **해석 도함수**: 별도 ∂ρ/∂p|h, ∂ρ/∂h|p, ∂T/∂p|h, ∂T/∂h|p 테이블 + Modelica `derivative` 주석 → OM Jacobian 해석화.

## 생성 (CoolProp, HEOS Propane = Lemmon 2009)
- **기준상태가 HelmholtzMedia와 완전 일치 확인** (Tsat/hl/hv/rho 동일) → h값 교환가능, 기존 컴포넌트 검증값(h_in=287e3 등) 그대로 유효.
- 격자: p[1.5,35]bar×60, h[120,720]kJ/kg×140.
- 재생성: `python gen_r290.py` → r290_table.npz → `python emit_full.py` → R290Tab.mo

## 검증 정확도
- rho: 평균 0.014% / p99.9 0.93% / max 3.06% (2상·포화경계 포함 전역)
- T: max 0.44%
- OM 함수 vs CoolProp: 사이클 핵심점 전부 <0.01%
- 도함수 주석: 컴파일+적분 동작 확인 (상태 의존 모델)

## API
- `rho_ph(p,h)`, `T_ph(p,h)` — 영역인지 + 해석 도함수
- `Tsat(p)`, `hl(p)`, `hv(p)`, `rhol(p)`, `rhov(p)` — 포화, 해석 도함수
- `mul/kl/cpl/muv/kv/cpv(p)` — 포화 수송 (액/증기)
- `mu_ph/k_ph/cp_ph(p,h)` — 단일상 수송 (영역인지)

## 다음
1. 컴포넌트 통합: propsEvap/propsCond의 HelmholtzMedia 호출을 R290Tab으로 교체 → 표준상태 재검증
2. flow↔volume 스태거링 (레벨 핀)
3. 사이클 재시도 — 해석 Jacobian + bracketing 제거로 corrector 수렴 기대
