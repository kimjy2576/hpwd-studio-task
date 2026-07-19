# Cycle Runner — 첫 케이스 단계 계획 (Walking Skeleton)

## 전략: 한 케이스를 끝까지 관통 → 접근 검증 → 확장

전체를 다 만들기 전에, **하나의 fidelity 조합으로 냉매 사이클을 처음부터
끝까지 수렴**시켜 접근이 통하는지 먼저 검증. 아키텍처 문제를 일찍 발견.

---

## 첫 케이스 선정: 전부 L3 냉매 사이클 (정상상태)

### 왜 이 케이스인가
1. **검증 기준 확보**: 12칸 검증 BC가 이미 닫힌 사이클로 정합됨.
   - 압축기出(650771) → 응축기入(651260) Δ489 ✓
   - EEV入 과냉액 26.4°C, EEV出 등엔탈피 → 증발기入 Δ1070 ✓
   - 증발기出 → 압축기入 과열 7.9°C ✓
   → solver가 수렴하면 **이 상태점(P_evap=5.09, P_cond=9.88)이 나와야 함**.
     정답을 알고 시작 = 디버깅 명확.
2. **L3 = 가장 검증된 fidelity** (이번 세션 h_o/T_wall 수정 완료).
3. **정상상태 = 동적보다 단순** (시간적분 없이 수렴만).

### 첫 케이스 목표 (성공 기준)
냉매 사이클 solver가 수렴 → 검증 BC 상태점 재현:
  P_evap ≈ 5.09 bar, P_cond ≈ 9.88 bar, m_dot ≈ 0.00207,
  4개 상태점 h가 12칸 BC와 일치 (±수%).

---

## 단계 분해 (각 단계 = 독립 검증 가능)

### 1단계: 냉매 루프 solver (정상상태, 전부 L3) ← 첫 목표
목표: 압축기→응축기→EEV→증발기 순환을 수렴시켜 12칸 BC 재현.

구현:
```
backend/cycle_runner/refrigerant_loop.py
  · 미지수: P_evap, P_cond (2개 주 미지수)
  · 고정 입력: N(rpm), EEV opening, 공기 BC (HX 열전달용), 과열도 목표
  · fixed-point 반복:
      압축기(P_evap, P_cond, N) → m_dot, h_dis
      응축기(P_cond, h_dis, m_dot, 공기BC) → h_cond_out
      EEV(P_cond, h_cond_out, P_evap, opening) → m_dot_eev, h_eev_out
      증발기(P_evap, h_eev_out, m_dot, 공기BC) → h_evap_out
      잔차1: m_dot(압축기) − m_dot(EEV) = 0  → P_cond 조정
      잔차2: 증발기 출구 과열도 − 목표 = 0   → P_evap 조정
      (또는 charge 보존을 잔차로)
  · 수렴 판정 + 상태점 반환
```
검증: 수렴값이 12칸 BC(P_evap=5.09, P_cond=9.88)와 일치하나.
난제 예상: 수렴 안정성 (초기 추정, 완화계수). 압력 갱신 방향.

### 2단계: fidelity dispatch (L1/L2/L3 교체 가능)
목표: 1단계 solver에서 컴포넌트를 registry로 교체.
```
backend/cycle_runner/registry.py
  COMPONENT_REGISTRY = {
    'compressor': {1: comp_theoretical, 2: comp_winandy, 3: comp_chamber},
    'eev': {1:..., 2:..., 3:...}, 'condenser': {...}, 'evaporator': {...}
  }
```
검증: 전부 L1으로도 수렴하나. L3↔L1 섞어도 수렴하나 (mixed 첫 확인).

### 3단계: 공기 루프 solver (팬 가변 위치)
목표: 드럼→필터→증발기→응축기 순환, 팬 임의 위치.
```
backend/cycle_runner/air_loop.py
  air_path = [drum, filter, evaporator, condenser]  # 고정
  air_path.insert(fan_position, fan)  # 팬 삽입
  순차 실행, 공기 상태(T,W,유량,dp) 전달
```
검증: 공기측 9칸 검증 BC 재현. 팬 위치별 dp 균형.

### 4단계: 냉매-공기 연성
목표: HX(증발기·응축기)에서 두 루프 Q 일치까지 반복.
```
backend/cycle_runner/coupled_solver.py
  반복:
    공기 루프 → HX 공기 입구 상태
    냉매 루프 (공기 상태로 Q) → HX 열전달
    공기 루프에 Q 반영
  수렴 (Q 일치)
```
검증: 연성 수렴. 냉매+공기 동시 정합.

### 5단계: 동적 확장 (콜드스타트)
목표: 시간 스텝 루프로 정지→기동→정상상태.
```
backend/cycle_runner/dynamic_runner.py
  초기: P_equalize, T_amb, N=0, charge 분배 (charge_inventory)
  for t: N ramp, step(state,dt), charge 재분배, 상태 기록
```
검증: 정상상태 도달값이 1~4단계 정상상태와 일치.

### 6단계: API + 프론트 탭
목표: FastAPI 엔드포인트 + 별도 Cycle Runner 탭.
검증: UI서 fidelity 선택, 팬 위치, 실행 → 결과 표시.

---

## 지금 착수: 1단계만

1단계(냉매 루프 정상상태, 전부 L3)를 먼저 구현하고 **12칸 BC 재현으로
검증**. 통하면 2단계 이후로 확장. 안 통하면 여기서 접근 수정.

→ 첫 삽: refrigerant_loop.py, 수렴 루프 골격.
   목표 수렴값 = P_evap 5.09, P_cond 9.88 (검증 기준 있음).

### 1단계 내부 세부 순서
(a) 컴포넌트 배관 함수 (각 step 호출 + 입출력 연결) — 반복 없이 1-pass
    먼저. 12칸 BC 넣으면 4점 정합 나오나 확인 (수렴 전 sanity).
(b) 압력 미지수 2개 fixed-point 반복 추가. 초기추정→수렴.
(c) 수렴값이 검증 BC와 일치 확인. 완화계수 튜닝.
(d) 커밋. 2단계로.

→ (a)부터: 반복 없는 1-pass 배관으로 컴포넌트 연결이 맞는지부터.
