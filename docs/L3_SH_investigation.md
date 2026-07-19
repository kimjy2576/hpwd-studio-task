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

---

## 부록 3: 공기 그리드 구조 차이 (확인됨, 정량 연결은 미완)

vendor solver 공기측 코드 정독 결과 — 공기 그리드 차원이 OMC와 다름.

### 확인된 구조 차이
OMC: 공기 그리드 T_aen[Nr+1, Nseg] = [5,10]. **column(Nt) 차원 없음.**
  · 냉매 kOf[p,s]로 [row×seg]=40셀이 1개 경로.
  · 공기 스트림 Nseg=10개, 각 스트림이 4 row 순차 통과.
  · Nt=4는 물리적 병렬 tube(m_ref_col=m/4)지만 열 그리드는 [row,seg] 단일.
Python: 공기 그리드 T_air_3d[Nt][Ns][Nr] = [4][10][5]. **column별 독립.**
  · row_parallel = col당 냉매 1경로 × 4 = 4개 독립 경로.
  · 공기 스트림 Nt×Ns=40개, 각 냉매경로가 자기 col 공기(1/4)만 씀.

→ OMC = 냉매경로↔공기 [row,seg] 그리드 공유(공기 10스트림).
  Python = 4쌍의 독립 (냉매경로 ↔ 자기 col 공기).

### 공기유량·온도는 유사
Python m_air_cell=0.00121 vs OMC m_air_seg=0.00119 (Δ1.3%).
OMC 공기 seg별 온도차 있음(seg1 r5=13.75 vs seg10 r5=15.94) = seg별 스트림 확인.
seg/row serpentine 방향(pathSeg vs pass_idx%2)도 동일.

### 미해결 — 정량 연결
공기 그리드 차원 차이(OMC [row,seg] vs Python [col,seg,row])는 확인했으나,
이것이 정확히 어떻게 과열셀 38% vs 12.5%를 만드는지 셀 열수지 완전추적은 미완.
구조차가 냉매-공기 유효 접촉 면적/온도 분포를 바꿔 완전증발 시점을 이동시키는
것으로 추정되나, 확증하려면 양측 셀별 Q 완전 대조 필요.

### 조사 총평 (정직한 상태)
- 확실: 면적·물성·공기측 h_o·microfin·병렬수(G)·냉매 row순서·seg순서·dryout
  임계값·셀 h_i 전부 동등/유사. 이들은 원인 아님.
- 확실: 공기 그리드 차원이 다름(OMC 2D [row,seg] vs Python 3D [col,seg,row]).
- 미확증: 위 구조차 → 과열분포차의 정량 인과. 추가 셀추적 필요.
- 이번 조사서 초기 오진 다수 정정(흐름정렬/물성/dryout 등 모두 동등 판명).

---

## 부록 4: 진짜 근본원인 발견 — dryout 셀 T_wall 수렴 불안정

부록 1~3의 후보(회로/공기그리드/dryout임계값)를 실험으로 모두 배제한 뒤,
셀별 Q 추적으로 진짜 원인 발견.

### 공기 그리드 차원은 원인 아님 (실험으로 배제)
vendor solver에 column 공기 병합(OMC 2D 모사) 실험 삽입 → SH 변화 없음
(13.9K 동일). row_parallel서 모든 column이 대칭이라 병합 무의미.
→ 공기 그리드 차원(2D vs 3D)은 과열분포 원인 아님 확정.

### 진짜 원인: T_wall 반복 진동 (dryout 셀)
셀별 Q 추적: 냉매 입구 2상 Q는 OMC와 일치(9.3W). 그러나 dryout 구간
(x>0.87, h_i=348) 일부 셀에서 Q가 튐 (#18 Q=3.74, #19 Q=6.28 vs 정상 1.8W).
해당 셀 T_wall 추적 → outer iteration마다 폭주/정상 진동:
  iter A: Q=1.84 T_w=17.6 is_wet=False
  iter B: Q=6.94 T_w=45.7(!) is_wet=False Q_lat=3.78(dry인데 잠열!)
  iter C: Q=1.67 T_w=16.1 is_wet=True
T_w=45.7°C는 비물리(냉매 2.3°C, 공기 18.3°C 사이 벽이 46°C 불가).

### 메커니즘: wet/dry 순환 + dryout R_i 증폭
_solve_segment T_wall 갱신: T_w_new = T_ref_eff + Q_total·R_i (evap).
악순환:
  1. is_wet = (T_w < T_dp) — T_w에 의존
  2. wet이면 Q_total = eta_o·h_o·A_o/cp_a·(h_air − h_s_wall(T_w)) — T_w에 의존
  3. T_w = T_sat + Q_total·R_i — Q에 의존, dryout서 R_i=8.27(h_i=348 낮아 큼)
  → T_w 상승 시 is_wet 뒤집히고 h_s_wall 급변 → Q 급변 → R_i 증폭으로 T_w 폭주
  → under-relaxation(alpha)이 못 잡는 진동. 일부 셀 Q 과대 → 냉매 조기 완전증발
  → 과열 셀 38% (vs OMC 12.5%) → SH 13.9K (vs 5.8K).

### OMC엔 왜 없나
OMC는 T_w를 전역 DAE(der(T_w))로 음함수 풀이 → 셀간 연립으로 안정.
Python vendor는 셀별 명시적 T_wall 반복(forward) → dryout 고R_i서 불안정.
= 수치해법 구조 차이(연립 음함수 vs 셀별 명시반복)가 근본.

### 결론 (최종)
L3 과열 과대의 진짜 원인 = vendor HXSolver의 dryout 셀 T_wall 명시반복이
수렴 불안정(wet/dry 순환 × 고R_i 증폭)하여 일부 셀 Q를 과대평가.
회로·공기그리드·물성·dryout임계값·h_i는 전부 무관(모두 배제됨).
→ vendor 수정 시: T_wall 반복에 (a)강한 under-relaxation 또는 (b)wet/dry
  판정 이력 고정 또는 (c)T_w 물리한계 클램프(T_ref≤T_w≤T_air) 필요.
  단 vendor 백본 수정이라 신중. 당분간 OMC를 L3 기준으로.

---

## 부록 5: (a) under-relaxation 수정 시도 — 순수 alpha는 불충분

부록4에서 규명한 T_wall 진동을 (a) under-relaxation으로 해결 시도.

### 실험: alpha 값별 SH (vendor 원본 무수정, 환경변수 오버라이드)
현재 alpha=0.7 (T_w_new = alpha·계산값 + (1-alpha)·이전).
  alpha=0.7: SH=13.9   alpha=0.5: SH=9.9   alpha=0.3: SH=11.4
  alpha=0.2: SH=8.9    alpha=0.1: SH=0.5
+ max_iter 증가 조합:
  alpha=0.3/it50: SH=8.2   alpha=0.2/it50: SH=9.1
  alpha=0.15/it100: SH=5.4(OMC 5.8 근접!)   alpha=0.1/it100: SH=8.4

### 판정: 순수 alpha는 비단조·불안정 → 근본해결 아님
SH가 alpha에 단조롭지 않음(0.5→9.9, 0.3→11.4 튐). alpha=0.15/it100서
우연히 5.4로 근접하나 이는 "진동이 그 지점서 얻어걸린" 것, 안정수렴 아님.
근원인 wet/dry 이산 스위칭(is_wet=(T_w<T_dp))은 연속 under-relaxation으로
안 잡힘. iter 추적 확인:
  진동 셀: iter4 wet=T→iter6 wet=F(T_w=36)→iter9 wet=T→iter11 T_w=45.7
  (max_iter=12 도달, 미수렴 종료 → 나쁜 값으로 Q 과대).

### 다음 단계 — adaptive under-relaxation (진짜 (a))
순수 고정 alpha 대신 진동 감지 시 alpha 자동 감소가 필요:
  · dT_w 부호 반전(진동) 감지 → alpha ×= 0.5
  · 또는 T_w 이력 3개로 진동 판정 → 감쇠 강화
단 wet/dry 스위칭이 근본이므로 (a)만으론 한계. (c) T_w 물리클램프
(T_ref≤T_w≤T_air) 병행이 실효적일 가능성.

vendor 원본 무손상 유지(모든 실험 훅 제거 확인). 실제 수정은 adaptive
+클램프 설계 후 신중 적용.

---

## 부록 6: 증발기 L3 미세조정 — 셀 1개 차이까지 도달

부록5의 T_wall 안정화 후 증발기 L3 미세조정. 진동 완전 해결 확인.

### 진동 완전 소멸 확인
수정 후 전 셀 수렴(160/160, 미수렴 0). dryout 구간 셀 Q가 균일 안정:
  #18~30 (x 0.86~0.97): Q=1.65~1.84W (과거 6.94W 폭주 완전 소멸).
  OMC dryout 셀 Q~1.62W와 거의 일치.
과열 셀(#34~39): Q 1.49→0.89W 단조감소, T_ref 4.0→10.4°C 정상, T_w 물리범위.

### 최종 정합도 — 셀 1개 차이
             수정전   수정후   OMC
  과열셀     15/40    6/40     5/40
  완전증발   #25      #34      ~#35
  SH_out     13.9K    8.6K     5.8K
  Q(row_par) 491.2    471.9    461.7   Δ+2.2%
완전증발 지점 #34 vs OMC #35 = 셀 1개 차이(40셀 해상도의 2.5%).
잔여 SH 차이는 2상 셀 Q가 OMC보다 미세하게 큼(1.7 vs 1.62)이 34셀 누적되어
1셀 일찍 완전증발 → 과열 1셀 추가.

### 판정: 현 수준 수용 (근본 진동 해결 달성)
추가 조임 옵션 검토:
  A. 클램프 상한 인위 조정 → 다른 조건서 왜곡 위험, 기각.
  B. 현 수준 수용 (셀1개차, Δ+2.2%) — 채택.
  C. 2상 dx를 log-mean ΔT로 정밀화 → 근본적이나 Q 이미 근접(1.7 vs 1.62)
     이라 이득 작고 vendor 핵심 변경 위험. 보류.
셀 1개 차이는 유한체적 이산화(40셀)의 해상도 한계에 근접. T_wall 진동이라는
근본 버그를 해결했고 Δ+2.2%로 3% 이내 → verify_evap L3 ✅ 판정.

### 최종 상태 (냉매측 12칸)
압축기 L1✅L2✅L3✅ | EEV L1✅L2✅L3✅ |
응축기 L1✅L2✅L3🔶(별개 메커니즘) | 증발기 L1✅L2✅L3✅.
→ 11칸 정합(<3%). 응축기 L3만 잔존(입구 과열증기 deSH, dryout 아닌 별개).

---

## 부록 7: 응축기 L3 — 증발기와 다른 원인(공기측 h_o), cf_j로 정합

증발기 L3(T_wall 진동) 해결 후 응축기 L3 조사. 근본 원인이 증발기와 완전히
다름 — 수치버그 아니라 공기측 h_o 가정 차이.

### 증상: 응축 부족 (Q 과소, 증발기와 정반대)
응축기 L3 single: Q=575.2 (Δ-9.1%), x_out=0.315 (2상, 응축 68%만).
OMC: Q=633, x_out=0.172 (응축 82%). Python이 열을 덜 버려 응축 부족.
(증발기는 Q 과대/과열과다였는데 응축기는 Q 과소/응축부족 = 정반대.)

### 근본 원인: 공기측 h_o (179 vs 302, 1.71배)
Python 응축기 h_o=179.2 (표준 j-factor 계산).
OMC 응축기 h_o=302.17 (하드코딩 parameter, 근거주석 없음).
증발기는 양쪽 176 일치(표준계산). 응축기만 h_o 1.71배 차이.

확증 실험: solver L309 h_o를 302 강제 주입 →
  Q 575.2 → 624.6 (Δ-9.1% → -1.3%), x_out 0.315→0.243.
→ h_o가 응축기 Q 결정. h_o 차이가 근본 원인 확정.

### OMC h_o=302 재현 불가 (형상 계산으로는)
h_o=j·G_air·cp/Pr^(2/3). Python 공기유량은 OMC와 일치(0.0484 vs 0.0478).
차이는 A_c(최소유로): Python A_c=0.00782(sigma=0.576) → G_air=6.2 → h_o=179.
OMC h_o=302 되려면 G_air≈14.8 (A_c 1/2.4). FPI를 50까지 올려도 G_air=7.2로
목표 절반. → OMC 302는 Python 표준 형상계산으로 재현 불가. 다른 A_face 또는
공기 가정에서 나온 하드코딩 값.

### 정합 방법: cf_j=1.686 (vendor 무수정)
cf_j(j-factor 보정) 파라미터 이미 노출. cf_j=302/179=1.686 적용 →
  Q=624.6 (Δ-1.3%). 남은 -1.3%는 셀 이산화 등 미세.
단 이는 OMC 값에 맞추는 보정이지 물리적 정답 아님.

### 판정: 증발기와 성격 다름 — 실측 판정 필요
증발기 L3: 수치버그(T_wall 진동) → 코드수정으로 근본해결.
응축기 L3: h_o 가정 차이 → OMC 302 vs Python 179 중 어느게 실제 LG HPWD
  응축기에 맞는지 실측 없이 판정 불가.
- OMC 302 신뢰 시: cf_j=1.686 적용 → Δ-1.3% 정합.
- Python 179 신뢰 시: 현재값 유지, OMC가 과대.
권고: 실제 응축기 공기측 사양/실측 h_o 확인 전까지 cf_j 미적용 유지.
  OMC를 기준삼되 응축기 L3는 h_o 불확실성 명시. 실측 후 확정.

### 최종 상태 (냉매측 12칸)
압축기 L1✅L2✅L3✅ | EEV L1✅L2✅L3✅ |
응축기 L1✅L2✅L3🔶(h_o 가정차, cf_j=1.686 시 Δ-1.3% 정합가능) |
증발기 L1✅L2✅L3✅.
→ 11칸 정합. 응축기 L3는 원인규명 완료(h_o), 정합수단 확보(cf_j), 물리적
  확정은 실측 대기.
