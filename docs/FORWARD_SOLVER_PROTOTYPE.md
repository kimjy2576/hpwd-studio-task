# 정방향 플랜트 solver 프로토타입 — 개념 실증

## 배경
현재 solver.py는 역방향: SH_target 지정 → P_evap 역산 (정상상태 A-2용).
동적 시뮬에서 실제 EEV 제어(개도로 SH 제어)를 표현하려면 정방향 플랜트
(개도 입력 → SH 출력)가 필요. 세 번째 닫힘조건을 충전량 보존으로.

## 사이클 DOF 구조 (규명)
독립 방정식 2개(질량연속, 엔탈피폐합), 미지수 3개(P_evap, P_cond, h_suc).
→ 1개 부족. 세 번째 조건 필수:
- 역방향: SH = target
- 정방향: ΣM_holdup = M_charge (충전량 보존)

물리적으로 세 번째 조건의 정체는 냉매 충전량. 충전량이 각 HX의
액-기 분포(void fraction)를 정하고 → SC/SH 결정.

## 정방향 짝짓기 (solver_forward.py)
- P_evap ← 질량연속 (m_comp = m_eev)
- P_cond ← 충전량보존 (ΣM_holdup = M_charge)  ← 새 세번째식
- h_suc  ← 엔탈피폐합
- SH, SC ← 출력 (강제 안 함)

기반: M_holdup이 L2/L3 HX에 이미 구현됨 (void 적분).
P_cond↑ → 응축 진행 → holdup↑ (물리적으로 정확, 단조증가 확인).

## 검증 3가지 — 모두 성공
(a) 수렴: P_evap/P_cond 수렴 (충전량 잔차 게인 튜닝 여지).
(b) 개도→SH 반응: 개도 18→30 → SH 32.42→21.44 감소.
    (개도↑ → EEV유량↑ → 냉매공급↑ → 과열↓, 물리적으로 정확)
    ★ 역방향은 개도 무관 SH 고정(12.37)이었음 → 정방향의 결정적 차이.
(c) 역방향 정합: 정방향(M_charge=6.005g) → P_evap=4.71/P_cond=12.61/SH=26.1
    역방향(SH_target=None, 개도 23.586) → P_evap=4.75/P_cond=12.64/SH=25.5
    차이 P_evap 0.04, P_cond 0.03 → 같은 물리적 해.
    ★ 두 solver가 같은 점 = 동적(제어기)=정상상태(역산) 해 일치 실증.

## 남은 작업 (본격 구현)
1. 게인 튜닝 — 충전량 잔차 완전 수렴 (현재 0.13g 잔류), 적응 게인.
2. 오일 용해 냉매 모델 — R290 100g 중 ~68g이 압축기 오일 용해+내부.
   현재 압축기는 충전량/오일 미모델. HX holdup만이라 절대 충전량 부정합.
   용해도 X_ref(P_suc,T_oil) 상관식 + M_oil 파라미터 필요.
3. 배관 holdup — HX 외 체적 (~일부).
4. L1 대응 — M_holdup 없음 → SC 지정으로 대체 (보류).
5. 동적 통합 — 정방향 플랜트 위에 EEV PI 제어기 (개도로 SH 제어).
   정상상태는 역방향(SH_target→개도역산) 유지 (빠름).

## 파일
- backend/cycle_runner/solver_forward.py (프로토타입)
- 기존 solver.py (역방향) 그대로 — 정상상태 A-2용
