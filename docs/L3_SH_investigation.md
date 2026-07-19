# L3 HX (Evap/Cond On-Design) SH zone 과열 과대 — 근본원인 조사 (정정판)

## 요약
증발기·응축기 L3(vendor HXSolver 셀 유한체적)의 Q가 OMC 대비 +9%.
차이는 **전부 SH(과열) zone**. Python이 과열을 과다하게 냄(SH_out 17K vs
OMC 6K). 근본원인은 **회로(circuit) 구조가 실제로 다름** — 두 층위:
① 냉매 병렬 경로 수가 기본 설정부터 다름(Python single=1 vs OMC 4병렬)
② 병렬 수를 맞춰도 잔존하는 경로 내 셀 순회 순서 차이.

## 물리적 판정: OMC(6K)가 옳음
- Python SH zone eps≈0.98 (냉매출구 19.7°C가 공기입구 20°C 근접) = 건증기서
  비현실적 완전열교환. 2nd law 상한(SH≤17.7K)에 거의 붙음 = 위험신호.
- OMC eps=0.34가 건증기 낮은 HTC를 물리적으로 반영.

## 상관식은 원인 아님
vendor 과열역 Gnielinski=191.7 vs OMC Dittus×EF=200.8 W/m²K, 거의 동일.

## 근본원인 — 회로 구조 차이 (2층위)

### 층위 1: 냉매 병렬 경로 수 (기본 설정부터 다름)
OMC Evap_On_Dyn:
- m_ref_col = port_a.m_flow / Nt = m/4  → **4개 병렬 컬럼** 분배
- 각 컬럼이 M=Nr×Nseg=40셀 직렬 순회 (der(h_ref[k]))
- G_ref = (m/4)/A_cs = 31.1 kg/m²s

Python vendor (solver.py L109-123):
- circuit_mode='single'(기본) → n_circ=1 → 유량 1경로 → G=124.3 kg/m²s (4배!)
- circuit_mode 별 n_circ: single=1, serpentine_1=Nt=4, serpentine_2=2,
  parallel=Nt=4.
→ Python 기본값 single이 OMC(4병렬)와 애초에 다른 회로. 질량유속 4배 차이.

검증: Python을 parallel(n_circ=4, OMC와 동일 병렬수)로 바꾸면
  SH_out 17.4K → 13.9K로 개선(OMC 6K 쪽으로). Q 506 → 491.

### 층위 2: 경로 내 셀 순회 순서 (구조 차이, 잔존)
병렬 수(4)를 맞춰도 SH 13.9K로 OMC 6K와 여전히 거리.
- OMC pathRow(k0,Nr,Nseg)=Nr−div(k0,Nseg): 냉매경로가 row를 특정 순서로
  순회(serpentine), 주석 'p=Nr는 공기출구측=냉매입구'.
- Python vendor의 셀 배열/순회가 이와 달라 과열 셀이 61%(98/160) 차지
  (2상 62 / 과열 98). 과열에 면적 과다 배분.
- 이는 vendor solver 내부 로직이라 파라미터로 정합 불가.

## 판정: 정량보정 보류
- 층위1(병렬수)은 circuit_mode='parallel'로 부분 개선 가능하나 완전정합 안 됨.
- 층위2(셀 순회)는 vendor 백본 수정 필요. hx_sim은 검증 백본이고 L2 2상 등
  공유 → 광범위 영향. reference에 임의 튜닝은 자기모순.

## 권고 (정석 순서)
1. **OMC Evap_On_Dyn을 당장의 L3 기준 채택** — 물리 타당(SH 6K), 검증서
   기준역할 입증. Python L3는 정성/상대비교용.
2. **vendor HXSolver 회로 로직 정합을 별도 과제로**:
   (a) circuit_mode 기본값을 OMC와 같은 병렬수(parallel/serpentine_1)로 맞춤
   (b) 셀 순회 순서를 OMC pathRow(counter-flow serpentine)에 정합
3. **최종 검증은 실측** — 실제 HPWD 증발기 SH 6K/17K 판정. 진짜 GT.

## 정정 이력
초판은 1차 원인을 '공기-냉매 흐름 정렬 차이'로 기술했으나 부정확.
정확히는 ① 병렬 경로 수(single=1 vs 4병렬, G 4배) 기본설정 차이가 1차,
② 경로 내 셀 순회 순서가 2차. Python 기본 circuit_mode='single'이
OMC 4병렬과 다른 것이 핵심 출발점.

## 현황
냉매측 12칸: 10칸 완전일치(<1%), L3 2칸(Evap/Cond 동일 vendor 엔진)만
회로 구조 차이로 +9% 보류. 정성 유효, 정량 보류.

---

## 부록: OMC vs Python 물리조건 전면 대조 (사용자 요청)
"정합성 떠나 동등 조건에서 비교하는 게 우선" — 놓친 물리조건 있나 전수 확인.

### 완전 일치 확인 (놓친 것 없음)
| 항목 | Python | OMC | Δ |
|---|---|---|---|
| Di | 0.0046 | 0.0046 | 0.00% |
| 셀 내면적 A_i_seg | 0.0003468 | 0.0003468 | 0.00% |
| 셀 외면적 A_o_seg | 0.0048955 | 0.0048955 | 0.00% |
| Dc/Xm/XL (핀 기하) | 0.00522/0.00707/0.006123 | 동일 | 0.00% |
| 전체 내면적 A_i | 0.0555 | 0.0555 | 0.00% |
| 공기측 h_o | 176.42 | 176.27 | 0.08% |
| microfin n/e/helix | 54/0.15/15 | 동일 | - |
| Tsat, 포화물성 | 2.31°C | 2.28°C | ~0 |
| 경로당 셀수(n_circ=4) | 40 | 40(M=Nr·Nseg) | 동등 |

→ 면적·물성·공기측·microfin·병렬수 전부 동등. **놓친 물리조건 없음.**

### 유일한 실질 차이: 냉매 셀 순회 순서
Python row_parallel 한 경로(40셀) x 궤적:
  cell30(x=0.43 입구)→39→20→29→10→19→0→9(x=1.0 출구)
  = row별 serpentine이나, 과열부(cell0~9)가 신선공기(20°C)와 만남.
OMC pathRow=Nr−div(k0,Nseg): 냉매 입구 k0=0→행4, 출구 k0=39→행1.
  주석 'p=Nr는 공기출구측=냉매입구'.
→ 두 모델의 냉매-공기 교차 배치가 다름. 과열도 OMC 5.8K vs Python 17.4K.

### 물성 주의 (조사 중 정정)
초기에 CoolProp h_v를 602222로 오독해 'Python 과열이 비현실적'이라 판단했으나,
실제 h_v=577408. OMC h_out=587565도 과열(>h_v) 정상. SH 5.8 vs 17.4K 차이는
물성 아닌 셀 순회 배분에서 기인 확정.

### 최종 결론
물리조건은 전부 동등. L3 Q/SH 차이는 **오직 vendor HXSolver의 냉매 셀 순회
순서(회로 토폴로지)가 OMC pathRow와 다른 것** 하나로 수렴.
- 층위1(병렬수 G): row_parallel로 OMC와 일치시킴(물리적으로 옳음).
- 층위2(셀 순회): vendor 내부 pathRow 구현 차이 — 이것이 잔여 차이의 전부.
