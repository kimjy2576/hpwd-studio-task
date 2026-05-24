# HPWD L1 사이클 (Modelica) — 작업 현황

> 마지막 업데이트: 2026-05-23. 다음 세션은 이 문서를 먼저 읽고 이어갈 것.

## 목표
임의 배치(어큐뮬레이터·IHX 자유조합) 가능한 냉동사이클 솔버를
**OpenModelica + HelmholtzMedia(R290)** 의 acausal equation 기반으로 구축.
L1 = 1차 설계용 "대강" 모델 (압축기 이론식 / HX UA / EEV 등엔탈피+orifice / charge 대략).

## 환경
- OpenModelica 1.26.7, MSL 4.1.0
- HelmholtzMedia: `package M = HelmholtzMedia.HelmholtzFluids.Propane` (R290, Lemmon 2009)
- 물성 API: setState_pT/ph/ps, setSat_p, saturationTemperature(p),
  bubbleEnthalpy(sat)/dewEnthalpy(sat), density/specificEnthalpy/specificEntropy
- 작업 디렉토리(컨테이너): `/home/claude/modelica-test/`
- 재구축 절차: `apt install openmodelica` → `installPackage(Modelica,"4.1.0")`
  → `git clone github.com/thorade/HelmholtzMedia` → loadFile 순서 HPWD→EvapUA→Control→Cycle

## 파일
- `HPWD.mo` — RefPort(connector), Source/Sink, **Comp_Theoretical**(이론 압축기, +N ramp), Comp_AHRI(L2로 강등), EEV_L1
- `EvapUA.mo` — Cond_UA_eq / Evap_UA_eq (equation 버전, momentum + 운전점 start), satProps/airProps function, algorithm 버전(단독검증 reference)
- `Cycle.mo` — EEV_Orifice(고정 phi·momentum), **EEV_Orifice_ctrl**(개도입력→phi가변·momentum), Volume(+fixedState), Cycle_L1_dyn(구버전), Cycle_L1_ramp(개루프), **Cycle_L1_ramp_PI**(PI SH제어 — 현재 메인)
- `Control.mo` — PI_Controller

## 구조 (핵심 — 이미 확정/통과)
- **volume = 압력 state**: der(rho·V)=Σṁ, der(U)=Σ(ṁ·actualStream(h)), p·h from state
- **flow = 유량 state (momentum)**: `der(ṁ) = (p_a − p_b − ΔP_fric)/L_inertia`
  - 이유: 마찰을 algebraic(ΔP=R·ṁ)으로 두면 over-specified (volume 압력과 충돌).
    momentum이면 ṁ가 state가 되어 volume(p)과 flow(ṁ)가 분리됨 (ThermoPower 패턴).
- 압축기는 ṁ 직접 결정: ṁ = η_vol·V_disp·(N/60)·ρ_suc (momentum 아님)
- EEV: dP_orifice = (ṁ/(Cv·A·φ))²/(2ρ), der(ṁ)=(Δp−dP_orifice)/L

### 통과한 단계
- [x] structural singular → 4 volume 분리로 해결
- [x] high-index → 마찰 ΔP(ṁ 함수)로 해결
- [x] over-specified → momentum der(ṁ)로 해결
- [x] checkModel: balanced (Cycle_L1_ramp 189=189)
- [x] build (C 컴파일) 성공
- [x] **★ cold-start 수렴 — 해결됨 (아래)**
- [x] **★ L1 폐루프 첫 정상상태 확보 — 완료 (아래)**

## ★ cold-start 관문 — 해결 (2026-05-23)
이전 막힘: `Cycle_L1_dyn`이 **운전점**(분리압력 19/5.5bar, ṁ start 0.005)에서
**steady-state init(der=0 + charge 구속)**을 동시에 풀려다 cold algebraic loop 발산
(물성 density iteration이 p=2e9 비현실 영역 탐색).

**해결책: rest(정지) 평형에서 출발 (`Cycle_L1_ramp`).**
- 4 volume을 **동일 균압(p_rest=9bar)·동일 엔탈피(h_rest=400kJ/kg, 2상 x≈0.4)** 로
  `fixedState=true` 고정 초기화 → 모든 ṁ=0, 모든 Q=0(냉매한계 clamp), **모든 der=0**.
  즉 자명한 평형점이라 init이 풀 게 없음 → "initialization finished **without homotopy**".
- 압축기 N을 `N_eff = N·min(1, time/t_ramp)` 로 0→3000 ramp(t_ramp=20s)해 운전점으로 연속 견인.
- **핵심 통찰**: 진짜 lever는 *N ramp가 아니라 rest 평형 init*. ablation 결과 t_ramp=0(즉시 풀 N)
  으로도 수렴함 → rest에서 출발하면 첫 스텝이 평형이라 안전. ramp는 과도구간 overshoot만 완화(보조).
- charge는 결과값: rest 9bar/400kJ/kg → **Σρ·V ≈ 88.96 g** (운전점 init의 M_total=0.1kg과 근사).

## L1 첫 정상상태 (Cycle_L1_ramp, dassl, tol 1e-6, 120s)
| 항목 | 값 | 검증 |
|---|---|---|
| Pc (응축/HP) | 16.59 bar | — |
| Pe (증발/LP) | 3.19 bar | — |
| ṁ_comp | 2.524 g/s | — |
| SH (증발출구) | 35.5 K | — |
| SC (응축출구) | 0 K (2상 토출) | — |
| W_comp | 361 W | h_dis=620.7+361/0.00252=763.7=vol1.h ✓ |
| charge | 88.96 g | Δ(0→120s)=1.6e-12 g → **질량보존 완벽** ✓ |
| EEV | 등엔탈피 | vol2.h=vol3.h=391.37 kJ/kg ✓ |

→ 폐루프가 열역학적으로 자기일관(압축기 에너지밸런스 정확·EEV 등엔탈피·질량보존). **블로커 해소.**

## SH 제어 (Cycle_L1_ramp_PI, PI → 가변 EEV, 2026-05-23)
PI_Controller(Control.mo)를 evap.SH 측정 → EEV 개도로 연결. EEV는 EEV_Orifice_ctrl
(phi 큐빅맵 c1=0.5,c2=0.3,c3=0.2 → opening 50%=phi 0.35로 고정 orifice 베이스라인과 일치).
SH_target=6K, Kp=2, Ki=0.5, opening_init=50, clamp[5,100], 적분기 I(fixed=true).

### ★ 핵심 발견: SH=6 도달은 charge authority 문제
밸브만으론 한계. charge별 정상상태(PI 수렴):
| charge | Pc | Pe | ṁ | SH | opening |
|---|---|---|---|---|---|
| 89g  | 20.5 | 7.18 | 6.15 | 8.99 | **100% 포화** |
| 102g | 21.95| 7.91 | 6.83 | 7.02 | 100% 막포화 |
| **120g** | 23.40| 8.33 | 7.24 | **6.00** | 95.1% (여유) |
| 138g | 24.25| 8.30 | 7.21 | 6.00 | 87.6% |

- 89g(rest 9bar/400kJ/kg)에선 밸브 100% 열어도 SH 바닥 ~9K → **밸브 authority 부족**.
- charge ≥ ~120g(rest h_rest=360kJ/kg)부터 밸브가 포화에서 풀리고 **SH=6.00K 정확히 추종**.
- → Cycle_L1_ramp_PI 기본 h_rest=360e3(120g)로 설정. SH=6 락, opening 95%, W 559W.
- 부수: charge↑ 하면 Pc/Pe도 동반 상승(89→120g: Pc 20.5→23.4, Pe 7.2→8.3). 따라서
  *SH와 Pc/Pe를 독립 타겟팅하려면 추가 DOF 필요*(N 또는 UA/airflow). EEV 1개론 SH만 제어 가능.

## 공기 풍량 가정 변경 + 응축기 right-sizing (2026-05-23)
공기루프(팬·필터·덕트·드럼) 미완 → decoupled 고정 air boundary 유지하되, 단일루프 지향으로
**cond·evap 풍량 모두 3.0 CMM** 으로 통일(기존 cond 25.42 / evap 2.54).

### 발견: 3.0 CMM에선 응축기가 air-starved
- cond 풍량 25.42→3.0 (×1/8.5) → C_air ≈510→57 W/K. 기존 cond UA(63)와 맞먹어 NTU≈1, ε↓
  → 같은 열 버리려 Tcond↑ → **Pc 23.4→28.3bar 급등**(R290 부품 설계압 ~30bar 근접, 저COP).
- air-side 천장: cond UA→∞ 여도 Q≤C_air·(Tcond−35) 라 Pc 바닥 ~23.5bar(k=5 UA315 확인).

### Pc<25bar 만드는 레버 (air 3.0/3.0, charge 120g, SH=6 락 유지)
| 조정 | UA_cond | N | Pc | Pe | ṁ | W | 비고 |
|---|---|---|---|---|---|---|---|
| 기준 | 63 | 3000 | 28.3 | 8.6 | 7.4 | 659 | air-starved |
| UA×2 | 126 | 3000 | 24.96 | 8.5 | 7.4 | 593 | 막 <25 |
| **UA×3** | **189** | **3000** | **24.0** | **8.4** | **7.3** | **573** | **채택(여유·풀용량)** |
| UA×2+N↓ | 126 | 2400 | 23.24 | 9.2 | 6.4 | 443 | 최고효율(용량↓) |

→ **Cycle_L1_ramp_PI 기본값 = air 3.0/3.0 + cond UA(24/150/15, 합189)**. 정상상태:
  Pc 24.0 / Pe 8.44 bar, ṁ 7.33 g/s, SH 6.00K, EEV 95%, W 573W, Q_evap≈1128W, **COP≈2.0**, charge 120g.
- 물리 해석: 3.0 CMM 단일루프엔 *기존 응축기가 undersized*. UA 3배 = 핀/패스 추가로 응축기 키운 것.
- N-trim(2400rpm)은 Pc·W 동시 ↓(효율 best)지만 용량 ↓ → 건조 용량 요구에 따라 선택.

## 다음 세션 첫 작업 (우선순위)
1. **Pe 타겟팅** — Pc는 응축기 right-size로 <25 확보(24.0bar). 남은 건 Pe(현재 8.4bar, 타겟 5.5).
   Pe↓ 하려면 evap UA↓ 또는 N↑ 또는 charge 재배분. SH=6 유지하며 evap측 sweep.
   (단, 실제 타겟 5.5/19은 25.42CMM 조건 기준이라 3.0CMM 단일루프에선 운전점 자체가 다를 수 있음.)
2. EEV PI 게인 튜닝 — 현재 t≈20에서 SH 4.5K로 살짝 언더슈트 후 6K 정착. Kp/Ki·anti-windup 검토.
3. 동특성: t_ramp·L_inertia·R_fric 민감도, overshoot, 정착시간(현재 SH~70s).

## 운전점 / 파라미터 (R290 HPWD, 진영님 "얼추 맞음" 확인)
- (타겟) HP 19 bar, 토출 h≈700 / LP 5.5 bar, 증발후 h≈590 kJ/kg, ṁ≈0.005 kg/s, SH 15
- rest 평형 출발: p_rest 9bar, h_rest 400kJ/kg (2상 x≈0.4 → charge 89g)
- **evap 5.5bar**: Tsat 4.9°C, h_l 212, h_v 580, h_out(SH15) 607 kJ/kg
- **cond 19bar**: Tsat 54.8°C, h_l 352, h_v 625, h_out 336(과냉)~440(2상) kJ/kg
- momentum L_inertia: cond/evap 1e5, eev 1e6 / 마찰 R_fric: evap 2e6, cond 1e7
- 압축기: V_disp 10e-6, N 3000, η_vol 0.85, η_isen 0.65, t_ramp 20
- volume V: 각 5e-4

## 단독 검증 정상상태 (start 이식용 reference)
- evap: SH = 14.7447, h_out = 607135.8
- cond: 기본 SC=0, h_out=438017.5, q=0.3148 / SC활성점 SC=19.941, Q_SC=118.86
- 압축기 이론 단독: ṁ=0.004952, h_dis=680.9k, W=454W (AHRI 대비 ṁ +8%, h_dis −3%)

## 알려진 경고 (무해, 시뮬 정상완료)
- HelmholtzMedia `RSS_ls/lambda_ls used before defined` — 라이브러리 내부 전도도식, 결과영향 없음
- 과도구간(t≈20 overshoot) `setState_pTX: d_min/d_max did not bracket the root` — root-finder가 회복, 비치명적

## 로드맵
L1 폐루프 완성(✓) → SH PI제어(✓) → Pc/Pe 타겟팅(N·UA) → L2(Comp_AHRI/Winandy, EEV Sami-Schnotale, MovingBoundary HX, charge_inventory)
→ L3 → fidelity 비교. 추후: 동특성(EEV 응답지연), surrogate 데이터, 캔버스→.mo 생성기.
