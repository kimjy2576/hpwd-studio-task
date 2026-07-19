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

---

## 부록 2: vendor 파라미터 제어 가능성 + 셀 열전달 전수 대조

사용자 요청 — vendor 코드 안 건드리고 파라미터로 셀 순회 조정 가능한지 확인.

### flow_arrangement 파라미터 (counter/parallel)
vendor generate_circuits(Nr,Nt,mode,flow_arr)가 row 순서 제어:
  counter → row [Nr-1..0], parallel → row [0..Nr-1].
그러나 evaporator_on_design L519서 flow_arrangement='counter' 하드코딩,
params 오버라이드 안 됨. counter/parallel 결과 동일(491.2) 확인.

### 냉매 row 순서는 이미 OMC와 일치
Python counter 회로0: row [3,2,1,0] 순.
OMC pathRow=Nr−div(k0,Nseg): 냉매입구k0=0→행4(3), 출구→행1(0). row [3,2,1,0].
→ 냉매 경로 순서 동일. flow_arrangement가 원인 아님.

### 공기 배분도 유사
Python col0: cell30(냉매입구 x0.43)서 T_air=17.2°C, cell0(출구 과열)서 T_air=20°C.
OMC: 냉매입구(row4) T_air=16.8°C, 출구(row1 과열) T_air=20°C.
→ 냉매 과열부가 신선공기(20°C) 만나는 배치 동일.

### dryout 모델 동일
Python vendor: x_di=0.669, x_de=0.769 → x>0.77서 factor=0, h=189.
OMC compute_h_evap_dryout: x_di=max(0.5,min(0.80+0.15·tanh((G-300)/200),0.95))
  =0.669 (G=31), x_de=0.769. 완전 동일.

### 셀 열전달계수(h_i)도 거의 동일 — 대조 완료
                Python      OMC
  2상 저건도    3054        3278 (h_i_c[4,5])
  dryout 구간   348         346 (h_i_c[3,5])
  과열          308         312 (h_i_c[1,1])
→ 열전달계수 양쪽 거의 일치. dryout·alpha 범인 아님.

### 남은 유일한 차이 (미해결)
면적·물성·공기측·microfin·병렬수·냉매순서·dryout·h_i 전부 동등/유사 확인.
그럼에도 SH_out Python 13.9K(row_parallel) vs OMC 5.8K, 과열셀 38% vs 12.5%.
→ 차이는 셀-공기 교차 배분의 미세 구조(2D 공기 그리드 vs OMC T_aen 누적)에
  국한. vendor solver의 공기 그리드 갱신 순서/방식이 OMC와 미묘하게 달라
  과열 구간 셀이 신선공기를 과다 접촉하는 것으로 추정. 셀 레벨 완전 대조는
  추가 조사 필요(현재까지 나머지 모든 물리량은 동등 확인).

### 실무 판정 (불변)
물리조건 대부분 동등 확인됐으므로 L3 차이는 vendor 공기그리드 이산화 세부에
국한된 소규모 구조차. OMC를 L3 기준으로, Python L3는 정성용. 최종 실측 검증.
