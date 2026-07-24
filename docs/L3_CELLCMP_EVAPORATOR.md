# L3 셀 단위 대조 — 증발기 (2026-07-23)

## 결론

**증발기에는 수정할 버그 없음.** OMC−Python 잔차 −2.1 %는
**반칸(half-cell) 이산화 규약 차이**로 설명되며, 격자 세분화 시 소멸함.
응축기의 `D` 누락(실제 버그, `5a479c8`)과는 성격이 다름.

부산물로 **OMC Nseg≥20 시뮬 정체**(`is_wet` Boolean 이벤트 채터링)를 발견 —
(B)안 격자 일반화의 실제 블로커.

## BC / 대상

P_e 5.0889 bar / h_in 364.157 kJ/kg / ṁ 2.06593 g/s /
공기 20 °C, RH 0.8, 2.42 CMM. 회로 `row_parallel` 정렬(Nt=4 병렬 컬럼).
OMC `Evap_On_Dyn`(t=600 정착) vs Python `evaporator_on_design.step()`.
Python h_o는 `cf_j`로 OMC값(180.156)에 정렬해 공기측 효과 분리.

## 기하·물성은 전부 일치 (응축기와 대조적)

| 항 | OMC | PY | 차 |
|---|---|---|---|
| h_o | 180.16 | 178.2 | 1.1 % |
| eta_o (건) | 0.8712 | 0.872 | 0.1 % |
| T_ref (2상) | 2.28 | 2.32 °C | 0.04 K |
| h_i (dryout 후 평탄) | 347 | 348 | 0.3 % |
| A_i_eff 역산비 | — | 1.00 | — |
| Q_lat (컬럼) | 46.46 | 48.11 | −3.4 % |
| **Q_total (컬럼)** | **115.59** | **118.03** | **−2.1 %** |

구간별(PY x 기준): 2상 −4.2 % / dryout(0.87~1) −2.0 % / 과열 +23.7 %(6셀, 절대 1.7 W)

## Nseg 스윕 — 반칸 가설 결정검정

세그당 면적·공기유량을 Nseg에 맞춰 스케일(총량 불변)한 변형 모델로 측정.
⚠️ `A_i_seg`/`A_o_seg`/`m_air_seg`는 Nseg=10 기준 하드코딩 → 함께 스케일하지 않으면
총면적이 배로 뜀. Nseg는 배열 차원 결정 = structural이라 `-override` 불가, 모델 변형 필요.

| N_seg | OMC Q_col | PY Q_col | 갭 | OMC SH | PY SH |
|---|---|---|---|---|---|
| 5 | 114.60 | 119.23 | **−3.9 %** | 4.93 | 9.94 |
| 10 | 115.59 | 118.06 | **−2.1 %** | 6.02 | 8.66 |
| 20 | 116.12 | 117.63 | **−1.3 %** | 6.60 | 8.19 |
| 30 | (미측정) | 117.46 | — | — | 8.00 |

(n20은 후술 채터링 수정 + IDA/KLU 적용 후 측정. 수정 전에는 정체로 측정 불가)

갭이 N에 반비례해 축소하고 **양쪽이 마주보며 수렴**(OMC 증가 ↔ PY 감소),
1/N 외삽 시 둘 다 116.5~117.3 W/컬럼. SH도 동일 거동(4.93→6.02 ↔ 9.94→8.00).
→ **원인 = OMC `h_ref[k]`가 셀 출구 상태, Python `x_ref`가 셀 입구 기준.**
셀별 x 오프셋 실측 중앙 −0.009 = 셀당 Δx 0.017의 정확히 절반으로 정합.

## 발견 1 — OMC Nseg≥20 정체: 원인 2중, 둘 다 해소

### (a) 습/건 Boolean 상태이벤트 채터링 → tanh 가중으로 제거

바이너리 직접 실행 + `-lv=LOG_EVENTS`로 실측:

```
이벤트 20회, t=15.807 → 16.378 (목표 600 s의 2.7 %)
간격 0.1539 s → 0.002372 s (65배 기하수축) = 전형적 Zeno
영교차: evap.T_w[61..65] < evap.T_dp   ← is_wet 조건 그대로
```

인접 셀 벽온도가 노점을 차례로 통과하며 이벤트 연쇄 → 적분 스텝 붕괴.
n10은 셀 수가 적어 통과했던 것뿐.

**수정** (`Evap_On_Dyn`): `is_wet` Boolean 분기를 연속 가중으로 대체.

```modelica
parameter Real dT_wet=0.2 "습/건 전이대 [K] (→0이면 기존 계단)";
w_wet = 0.5*(1 + tanh((T_dp - T_w)/dT_wet));
b     = 1 + w_wet*(hfgWater(T_w)*dWsdT(T_w,Patm)/cp_a);   // w→0이면 b=1
eta_o = finEffWet(h_o, b, ...);                            // b=1이면 eta_o_dry와 정확 일치
Q_air = w_wet*Q_wet + (1-w_wet)*Q_sens;
Q_lat = w_wet*0.5*(z + sqrt(z^2 + eps_Q^2));               // smooth max, z=Q_air-Q_sens
```

- 이벤트 완전 소거: n20 상태이벤트 **20회 → 0회**
- 극한 일치: n10 회귀 Q_col 115.59 → 115.63 (**+0.03 %**), SH 6.02 → 6.06 K
- 물리적 타당: 노점 근방 부분습윤은 실재 영역이라 계단이 오히려 인공적
- 전례: 같은 모델 microfin EF가 이미 `tanh(xq/0.03)` 블렌딩 사용
- `dT_wet`은 물리 보정계수가 아니라 **수치 전이대** — §5 실격 항목과 성격이 다름
  (기본값이 물리 극한을 재현)

### (b) 조밀 야코비안 → 희소 솔버(IDA/KLU) 필요

이벤트 0회가 된 뒤에도 DASSL로는 **stopTime=30조차 200 s 내 미완주**.
상태 160개(h_ref 80 + T_w 80), DASSL 조밀 야코비안은 평가 O(n²)·LU O(n³)이고
RHS 자체도 셀당 물성·상관식 호출로 무거움.

```
DASSL      : stopTime=30  → 200 s 초과 미완주
IDA + KLU  : stopTime=600 → 196 s 완주 (-s=ida -idaLS=klu)
```

**격자 일반화(핸드오프 §1의 2단계)의 실질 조건 = 적절한 솔버 사용.**
모델 수정 불필요, 런타임 플래그로 해결됨.

### (c) 솔버 비교 실측 — gbode가 최적

값은 **전 솔버 소수 3자리까지 완전 일치** (정확도 희생 없음).

| 모델 | 상태수 | dassl | ida | ida+klu | gbode |
|---|---|---|---|---|---|
| Cond_On_Dyn (60셀) | 120 | 0 s | 0 s | — | 1 s |
| Evap_On_Dyn n10 (40셀) | 80 | **실패** (>150 s) | 25 s | 26 s | **1 s** |
| Evap_On_Dyn n20 (80셀) | 160 | **실패** | — | 196 s | **4 s** |
| Cycle_L3_coldstart_dyn | — | 2 s | **1 s** | — | **실패** |
| Cycle_coupled_closed | — | 0 s | 0 s | — | 0 s |
| Cycle_coupled_open | — | 0 s | 0 s | — | 0 s |

**ida만 전 모델 성공.** gbode는 사이클의 비선형 대수계를 못 풀고 t≈0.002 s에 실패
(`Solving non-linear system 1795 failed`), dassl은 습코일 증발기 동특성에서 미완주.
값은 전 조합 일치(사이클 4자리, 커플드 최대편차 0.0002 %).

가르는 것은 단품/시스템이 아니라 **비선형 대수계 유무**:
동특성 재구성 후의 단품 HX는 순수 ODE(상태 h_ref·T_w에서 전부 명시적)라 gbode의
bi-rate가 유효하고, 사이클·커플드는 압력·유량 대수 구속이 있어 DAE 솔버(ida/dassl)가 필요함.
본 저장소에서는 둘이 우연히 일치하지만 일반 규칙은 아님.

### 회귀 검증 — tanh 수정이 사이클에 미친 영향

수정 전(`3f57e49`) 대비 `Cycle_L3_coldstart_dyn` t=120 s, dassl:

| 변수 | 수정 전 | 수정 후 | 차 |
|---|---|---|---|
| Pc_bar | 10.4520 | 10.4513 | −0.01 % |
| Pe_bar | 6.2432 | 6.2428 | −0.01 % |
| Q_cond | 597.32 | 597.38 | +0.01 % |
| Q_evap | 414.55 | 414.55 | −0.00 % |
| W_comp | 146.31 | 146.31 | −0.00 % |

회귀 없음. (SH=0.000은 수정 전에도 동일 — 이 모델의 기존 상태이며 별건)

셀 수가 아니라 **모델 성격**이 가름 — 응축기는 상태가 더 많은데도 dassl로 문제 없음.
증발기만 다른 점은 (i) 습핀 b 증폭으로 습/건 셀의 벽 시간상수 τ=C/(hA)가 집단으로 갈림,
(ii) `dT_wet=0.2 K`의 tanh 경사(전이 중심 감도 dw/dT_w≈2.5/K).
gbode의 bi-rate(이중속도) 적분이 여기에 유효한 것으로 **추정**되나 기전은 미확정 —
확정하려면 dT_wet 스윕(0.05/0.2/1.0)에서 실행시간이 1/dT_wet로 가는지 보면 됨.

실무 휴리스틱: **습기·물질전달이 있는 모델은 gbode 먼저 시도.**
단 근거는 증발기 1건이므로 사이클·드럼 등에는 재측정 필요.

### (d) 솔버 지정 방법 — annotation은 최상위 모델에만 적용됨

`__OpenModelica_simulationFlags(s="gbode")`를 **컴포넌트 클래스**(`Evap_On_Dyn`)에
붙이면 파싱은 되지만(`getAnnotationNamedModifiers` → `{"s"}`) **무시됨**.
실측: 컴포넌트에 붙인 상태로 `simulate(NsegVar.Evap_n20)` → 400 s 미완주,
빌드된 바이너리를 플래그 없이 실행해도 100 s 미완주.
같은 annotation을 **최상위 모델**(`NsegVar.Evap_n10`)에 붙이자 컴파일 포함 **27 s** 완주.

→ 스튜디오는 `backend/modelica/bridge.py`의 `_SOLVER`로 일괄 지정
(`method="{_SOLVER}"`, 7곳). **기본값 `ida`** (전 모델 성공하는 유일 솔버),
전환은 `HPWD_OMC_SOLVER=dassl|gbode|ida`.
gbode는 단품 세밀격자 연구용 opt-in.
미측정 공백: `GenCycle`/`GenAirCycle`은 캔버스에서 런타임 생성되어 정적 측정 불가
(구조가 유사한 커플드 사이클에서 ida 정상).

## 발견 2 — Python vendor 습/건 플래그 진동 (`a243da2` 시그니처 재현)

```
경로순 습(W)/건(d):
 OMC  WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWdddddddddd   전환 1회
 PY   WWWWWWWWWWWWWWWWWWWWdddWWWdddddddddddddd   전환 3회 ← 진동
```
벽온도가 노점 아래→위로 단조 상승하는 구간이라 물리적 전환은 1회여야 함.
셀 21~26에서 건→습→건 뒤집힘 = vendor `is_wet`↔`T_wall` 순환 불안정.
현 BC·row_parallel에서는 국소적(해당 셀 1.7 W대)이라 영향 작으나,
**회로모드에 따라 증폭됨**: single 회로에서 SH 17.45 K vs row_parallel 8.15 K.
GT를 기준자로 쓰는 이상 언젠가 해소 필요(수정안은 `a243da2` 참조: T_w 클램프 /
under-relax 강화 / wet-dry 이력 고정). 지금은 크기가 작아 보류.

## 결과 — 반칸 가설 확정

갭 −3.9 → −2.1 → −1.3 %로 1/N 축소, OMC 상승 ↔ PY 하강으로 **116.8 W/컬럼 부근 수렴**.
증발기에 물리 불일치 없음이 정량 확정됨.

## 하네스 주의점 (재사용 시)

- Python 기본 회로는 `single`(전체 직렬, G 4배) → Modelica Nt 병렬과 불일치.
  `circuit_mode='row_parallel'` 정렬 필수. 미정렬 시 가짜 일치가 나옴(응축기 사례).
- Python segments는 격자순 → (row,seg) 경로 후보 전수 x·T_ref 단조 검증으로 재구성.
  증발기 채택: row_rev=1, serpentine, phase=0 (OMC pathRow/pathSeg와 동위상).
- OMC final parameter는 결과 CSV·init.xml 모두 미출력 → `.mos`에서 동일 함수 체인 직접 평가.
- 컨테이너: 백그라운드는 `setsid`로 띄울 것(`nohup &`는 툴 셸 종료 시 사망).
  `pkill -f <패턴>`은 자기 명령줄까지 매칭해 셀프킬 위험.
- `simulate()`는 리턴해야 로그가 보임 → 이벤트 진단은 **빌드된 바이너리 직접 실행**
  (`./Model -lv=LOG_EVENTS`)으로 스트리밍 관찰. 솔버 교체도 `-s=ida -idaLS=klu`로 재빌드 없이 가능.
- `Nseg`는 배열 차원 결정 = structural → `-override` 불가, 모델 변형 필요.
  이때 `A_i_seg`/`A_o_seg`/`m_air_seg`(Nseg=10 기준 하드코딩)를 함께 스케일하지 않으면 총량이 어긋남.
