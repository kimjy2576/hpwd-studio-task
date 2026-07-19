# Mixed-Fidelity Cycle Runner — 실현 가능성 및 파일 전략

## 1. 요구사항 (사용자 정의)

기존 Cycle Runner는 L1/L2/L3 **레벨별로** 냉매/공기/커플드 사이클을 구현했음.
새 Cycle Runner는 **컴포넌트별 자유 조합**:

1. **냉매 루프 (고정 위상)**: 압축기 → 응축기 → 팽창밸브 → 증발기 → (압축기)
2. **공기 루프 (고정 위상 + 팬 가변)**: 드럼 → 필터 → 증발기 → 응축기 → (드럼),
   단 **팬은 임의 위치 삽입 가능**
3. **각 컴포넌트 fidelity 독립 지정**: 사용자가 컴포넌트마다 L1/L2/L3 선택
4. **별도 탭**: 기존 HPWD-Studio 탭과 분리된 Cycle Runner 탭

---

## 2. 실현 가능성: **가능함** (근거 확인 완료)

### 2.1 인터페이스 일관성 (결정적 근거)
검증된 12칸 냉매 컴포넌트의 입출력이 **fidelity 무관하게 동일**:

| 컴포넌트 | 입력 (공통) | 출력 (공통) |
|---|---|---|
| 압축기 L0.5/0.7/1.0 | P_suc, P_dis | m_dot, T_dis |
| EEV L0.6/0.8/0.95 | P_in, h_in, P_out, opening | m_dot_ref, h_out |
| 응축기 L0.3/0.7/0.95 | P_cond, h_in, m_dot_ref | P_ref_out |
| 증발기 L0.3/0.7/0.95 | P_evap, h_in, m_dot_ref | P_ref_out |

→ 고차 fidelity는 **부가 출력만 추가**(dP_bend, dP_air 등), 핵심 포트 불변.
→ **L1/L2/L3를 그대로 갈아끼워도 배관 인터페이스가 맞음.**

### 2.2 step 시그니처 통일
전 컴포넌트(냉매+공기)가 `step(input, params, state, dt)` 동일 시그니처.
→ 사이클 러너가 컴포넌트를 **동일한 방식으로 호출** 가능. dispatch만 하면 됨.

### 2.3 냉매-공기 커플링 지점
응축기·증발기가 양쪽 루프에 걸침. HX step은:
  냉매 입력: P_evap/P_cond, h_in, m_dot_ref
  공기 입력: T_air_in, RH_air_in, V_air_CMM
  출력: P_ref_out, h_out (냉매) + T_air_out, Q (공기)
→ 두 루프가 HX에서 **Q(열)와 상태로 커플링**. 표준 구조.

### 2.4 검증된 자산
12칸 전부 Python step()으로 물리 검증 완료 (이번 세션 포함).
h_o 계산 정합, T_wall 안정화 등 컴포넌트 신뢰성 확보.

---

## 3. 사이클 러너 아키텍처 (제안)

### 3.1 냉매 루프 solver
고정 위상 4-컴포넌트 순환. 미지수: 사이클 상태점 (P_evap, P_cond,
각 상태 h). 반복 수렴 (fixed-point 또는 Newton):
```
초기 추정: P_evap, P_cond, 과열도, 과냉도
반복:
  압축기(P_suc=P_evap, P_dis=P_cond) → m_dot, h_dis
  응축기(P_cond, h_dis, m_dot) → h_cond_out (+ 공기측 Q_cond)
  EEV(P_cond, h_cond_out, P_evap, opening) → m_dot_eev, h_eev_out
  증발기(P_evap, h_eev_out, m_dot) → h_evap_out (+ 공기측 Q_evap)
  잔차: m_dot 일치(압축기=EEV), 증발기 출구 과열도 목표
  P_evap, P_cond 갱신
수렴 → 사이클 상태점 확정
```

### 3.2 공기 루프 solver
드럼 → 필터 → [팬?] → 증발기 → [팬?] → 응축기 → [팬?] → (드럼).
팬 위치가 가변 → 공기 경로를 **순서 리스트**로 표현:
```
air_path = [drum, filter, evaporator, condenser]  # 고정 코어
fan_position = k  # 사용자 지정 (0~len)
air_path.insert(fan_position, fan)
```
각 컴포넌트 순차 실행, 공기 상태(T, W, 유량, dp) 전달.
팬은 dp 상승(유량 구동), 나머지는 dp 강하 + 상태 변화.

### 3.3 냉매-공기 연성
증발기·응축기가 양쪽에 등장 → 두 루프를 함께 반복:
```
반복:
  공기 루프 실행 → 증발기/응축기 공기 입구 상태 확정
  냉매 루프 실행 (공기 상태 받아 Q 계산) → HX 열전달 확정
  공기 루프에 HX Q 반영 → 공기 출구 갱신
수렴 (Q 일치)
```

### 3.4 fidelity dispatch
```python
COMPONENT_REGISTRY = {
  'compressor': {1: compressor_theoretical, 2: compressor_winandy, 3: compressor_chamber},
  'eev':        {1: eev_off_design, 2: eev_moving_boundary, 3: eev_on_design},
  'condenser':  {1: condenser_off_design, 2: condenser_moving_boundary, 3: condenser_on_design},
  'evaporator': {1: evaporator_off_design, 2: evaporator_moving_boundary, 3: evaporator_on_design},
  'drum': {...}, 'filter': {...}, 'fan': {...},
}
# 사용자 선택: {'compressor': 3, 'condenser': 1, 'evaporator': 3, 'eev': 2}
comp_module = COMPONENT_REGISTRY['compressor'][user_choice['compressor']]
result = comp_module.step(input, params, state, dt)
```
동일 인터페이스라 dispatch가 단순 lookup.

---

## 4. 파일 정리/분류 전략

### 4.1 절대 보존 (ground truth + 검증 자산)
[Python 컴포넌트 — 냉매 12 + 공기]
  backend/components/compressor_{theoretical,winandy,chamber}.py
  backend/components/eev_{off_design,moving_boundary,on_design}.py
  backend/components/condenser_{off_design,moving_boundary,on_design}.py
  backend/components/evaporator_{off_design,moving_boundary,on_design}.py
  backend/components/{drum_on,filter_on,fan_on}.py
  backend/components/{refrigerant_props,air_props,adder}.py
  backend/_vendor/hx_sim/**   ← HX-Sim 엔진, 절대 삭제 금지
→ 이것들이 새 Cycle Runner의 **부품**. 전부 살림.

### 4.2 신규 생성 (Cycle Runner 코어)
  backend/cycle_runner/            (신규 디렉토리)
    ├── registry.py                fidelity dispatch 레지스트리
    ├── refrigerant_loop.py        냉매 4-컴포넌트 순환 solver
    ├── air_loop.py                공기 루프 (팬 가변 위치) solver
    ├── coupled_solver.py          냉매-공기 연성 반복
    └── cycle_api.py               FastAPI 엔드포인트 (탭 백엔드)
  frontend: Cycle Runner 탭 (기존 HPWD-Studio 탭과 별도)

### 4.3 참고용 유지 (재구현 근거, 안 지움)
OMC .mo 파일들은 **물리 검증 기준(reference)**으로 유지:
  modelica/HPWDevap.mo, HPWDon.mo, EvapUA.mo, CondMBe.mo, EvapMBe.mo 등
→ Cycle Runner는 Python 컴포넌트로 구성하나, OMC는 검증 기준으로 남김.
  (이번 세션 h_o 정합처럼 대조 검증에 계속 필요.)

### 4.4 정리 후보 (Cycle Runner와 무관 — 신중히, 별도 판단)
[기존 사이클 조립 — 새 러너로 대체될 것]
  modelica/Cycle.mo, HPWDcycle.mo   (package 충돌 있음, 구 사이클)
  modelica/CmpCycle.mo, CycleMBe.mo (구 사이클 검증)
  modelica/Coupled.mo, CoupledSEMI.mo (구 커플드)
[커플링 테스트]
  modelica/Test{Coupled,CondMBcpl,EvapMBcpl,Air}.mo
[고아 의심]
  modelica/HXCmp.mo (참조 0)
→ ⚠️ 이것들은 **새 러너 완성 후** 구 러너 폐기 시점에 정리 검토.
  지금 지우면 참조 검증/롤백 불가. **보류 권장.**

---

## 5. 권장 진행 순서

1. **Cycle Runner 백엔드 코어부터** (registry → refrigerant_loop →
   air_loop → coupled_solver). Python 컴포넌트 조립, OMC 무관.
2. **단계 검증**: 냉매 루프만 먼저 수렴 확인 (기존 12칸 BC 재현),
   그다음 공기 루프, 그다음 연성.
3. **API + 탭**: 수렴 확인 후 FastAPI 엔드포인트 + 프론트 탭.
4. **구 파일 정리**: 새 러너가 구 러너 대체 확인 후, §4.4 정리 검토.

→ 파일 삭제는 **마지막 단계**. 먼저 만들고, 검증하고, 대체 확인 후 정리.
