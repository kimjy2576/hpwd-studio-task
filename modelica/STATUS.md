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

## 파일
- `HPWD.mo` — RefPort(connector), Source/Sink, **Comp_Theoretical**(이론 압축기), Comp_AHRI(L2로 강등), EEV_L1
- `EvapUA.mo` — Cond_UA_eq / Evap_UA_eq (equation 버전, momentum + 운전점 start), satProps/airProps function, algorithm 버전(단독검증 reference)
- `Cycle.mo` — EEV_Orifice(momentum), Volume(control volume), **Cycle_L1_dyn**(4 volume 사이클)
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
- [x] checkModel: 182 = 182 balanced
- [x] build (C 컴파일) 성공
- [x] 초기화(initialization): 운전점 start 세팅 + `-iim=none`으로 통과

### ★ 현재 막힌 관문
**적분 첫 스텝 algebraic loop가 cold-start로 수렴 실패.**
- cond/evap 3-zone 열교환 + 압축기 + momentum 이 한 스텝에 동시에 풀려야 함
- 그 안의 물성 밀도 iteration(setState_ph→setState_pT→setState_pd)이
  나쁜 guess로 발산 (p=2.04e9 같은 비현실 영역 탐색)
- nls=kinsol 등으로도 안 뚫림(70초 timeout, 발산은 아니고 헤맴)
- **단독 컴포넌트는 전부 검증됨 → 모델 구조는 맞음. 순수 수렴 문제.**

## 다음 세션 첫 작업 (우선순위)
1. **단계적 기동(N ramp)** — 가장 유망. `comp.N = 3000*min(1, time/10)` 으로
   정지 근처(ṁ≈0)에서 출발해 운전점으로 끌고 가 cold loop 회피
2. algebraic loop tearing — `-d=bltdump`로 loop 구조 보고 tearing 변수(h_out 등)에 guess
3. 물성 d_guess 주입 — HelmholtzMedia setState_ph가 density 초기값 받는지 확인

→ 닫히면 L1 첫 정상상태(Pe·Pc·ṁ·SH·SC + charge) 확보

## 운전점 / 파라미터 (R290 HPWD, 진영님 "얼추 맞음" 확인)
- HP(고압) 19 bar, 토출 h≈700 kJ/kg / LP(저압) 5.5 bar, 증발후 h≈590 kJ/kg
- ṁ ≈ 0.005 kg/s
- **evap 5.5bar**: Tsat 4.9°C, h_l 212, h_v 580, h_out(SH15) 607 kJ/kg
- **cond 19bar**: Tsat 54.8°C, h_l 352, h_v 625, h_out 336(과냉)~440(2상) kJ/kg
- momentum L_inertia: cond/evap 1e5, eev 1e6 / 마찰 R_fric: evap 2e6, cond 1e7
- 압축기: V_disp 10e-6, N 3000, η_vol 0.85, η_isen 0.65
- volume V: 각 5e-4 (charge ≈ Σρ·V, 대략)

## 단독 검증 정상상태 (start 이식용 reference)
- evap: SH = 14.7447, h_out = 607135.8
- cond: 기본 SC=0, h_out=438017.5, q=0.3148 / SC활성점 SC=19.941, Q_SC=118.86
- 압축기 이론 단독: ṁ=0.004952, h_dis=680.9k, W=454W (AHRI 대비 ṁ +8%, h_dis −3%)

## 로드맵
L1 폐루프 완성 → L2(Comp_AHRI/Winandy, EEV Sami-Schnotale, MovingBoundary HX, charge_inventory)
→ L3 → fidelity 비교. 추후: 동특성(EEV 응답지연), surrogate 데이터, 캔버스→.mo 생성기.
