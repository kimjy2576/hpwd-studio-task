within ;
package R290Medium "R290 (프로판) 매질 — Modelica.Media 계약 구현 (2026-07-26)

  왜 필요한가:
    R290Tab 은 Real 기반 함수 모음이라 물리적 유효성과 스케일 정보가
    어디에도 담기지 않는다. 그 결과
      - 초기화가 비물리 영역을 지날 때마다 개별 지점에서 터진다
        (실측: evap.b=-29088, W_sat 분모 음수, Q_lat smooth-max NaN)
      - nominal 이 없어 뉴턴이 스케일을 오판한다
        (실측: h_ref=362350 인데 nom=1, 잔차 8.77e+11)
    터지는 곳마다 클램프를 박는 것은 하드코딩이다.

    Modelica.Media 계약을 구현하면
      - SI 타입(SpecificEnthalpy 등)이 nominal 을 자동 제공
      - ThermodynamicState 레코드가 상태 유효성을 캡슐화
      - Modelica.Fluid / ThermoPower 컴포넌트와 호환
      - 기호 야코비안이 표준 경로를 탄다 (Dymola 가 쉬운 이유)

  구현 방침:
    계산 알맹이는 R290Tab 의 해석형 함수(_a 계열)를 그대로 쓴다.
    이 패키지는 계약을 채우는 껍데기다.
"
  extends Modelica.Media.Interfaces.PartialTwoPhaseMedium(
    mediumName            = "R290",
    substanceNames        = {"propane"},
    singleState           = false,
    reference_p           = 101325,
    reference_T           = 273.15,
    p_default             = 1.0e6,
    T_default             = 300.0,
    h_default             = 4.0e5,
    fluidConstants        = {Modelica.Media.Interfaces.Types.TwoPhase.FluidConstants(
      iupacName="propane", casRegistryNumber="74-98-6", chemicalFormula="C3H8",
      structureFormula="CH3CH2CH3", molarMass=0.04409562,
      criticalTemperature=369.89, criticalPressure=4251200.0,
      criticalMolarVolume=0.0002, acentricFactor=0.1521,
      triplePointTemperature=85.525, triplePointPressure=0.00017,
      meltingPoint=85.525, normalBoilingPoint=231.036, dipoleMoment=0.084)});

  redeclare record extends ThermodynamicState "상태 레코드"
    AbsolutePressure p "압력 [Pa]";
    SpecificEnthalpy h "비엔탈피 [J/kg]";
    Temperature T "온도 [K]";
    Density d "밀도 [kg/m3]";
  end ThermodynamicState;

  redeclare record extends SaturationProperties "포화 상태"
  end SaturationProperties;

  redeclare function extends setState_phX "압력·엔탈피로 상태 결정"
    // phase 는 계약상 입력이나 우리 물성은 (p,h) 만으로 영역을 판정한다.
    // 기본값 0(자동 판정) 을 명시해 호출부 부담을 없앤다.
  algorithm
    state := ThermodynamicState(
      p = p, h = h,
      T = R290Tab.T_ph_a(p, h),
      d = R290Tab.rho_ph_a(p, h),
      phase = 0);
  end setState_phX;

  redeclare function setState_ph "압력·엔탈피로 상태 결정 (phase 기본값 제공)

    PartialTwoPhaseMedium 의 setState_phX 는 phase 에 기본값이 없어
    호출부가 매번 명시해야 한다. 우리 물성은 (p,h) 만으로 영역을 판정하므로
    phase 를 받되 무시하고 기본값 0 을 준다.
  "
    extends Modelica.Icons.Function;
    input AbsolutePressure p;
    input SpecificEnthalpy h;
    input FixedPhase phase = 0;
    output ThermodynamicState state;
  algorithm
    state := ThermodynamicState(
      p = p, h = h,
      T = R290Tab.T_ph_a(p, h),
      d = R290Tab.rho_ph_a(p, h),
      phase = 0);
  end setState_ph;

  // setSat_p 는 재선언하지 않는다 — MSL4 기본 구현이 algorithm 을 이미 가지며
  // saturationTemperature(재선언됨)를 호출하므로 상속으로 충분하다 (2026-08-02).

  redeclare function extends bubbleEnthalpy "포화액 엔탈피"
  algorithm
    hl := R290Tab.hl_a(sat.psat);
  end bubbleEnthalpy;

  redeclare function extends dewEnthalpy "포화증기 엔탈피"
  algorithm
    hv := R290Tab.hv_a(sat.psat);
  end dewEnthalpy;

  redeclare function extends bubbleDensity "포화액 밀도"
  algorithm
    dl := R290Tab.rhol_a(sat.psat);
  end bubbleDensity;

  redeclare function extends dewDensity "포화증기 밀도"
  algorithm
    dv := R290Tab.rhov_a(sat.psat);
  end dewDensity;

  redeclare function extends saturationTemperature "포화온도"
  algorithm
    T := R290Tab.Tsat_a(p);
  end saturationTemperature;

  redeclare function extends pressure "상태에서 압력"
  algorithm
    p := state.p;
  end pressure;

  redeclare function extends temperature "상태에서 온도"
  algorithm
    T := state.T;
  end temperature;

  redeclare function extends density "상태에서 밀도"
  algorithm
    d := state.d;
  end density;

  redeclare function extends specificEnthalpy "상태에서 비엔탈피"
  algorithm
    h := state.h;
  end specificEnthalpy;

  redeclare function extends density_derh_p "d(rho)/dh at const p"
  algorithm
    ddhp := R290Tab.drho_dh_a(state.p, state.h);
  end density_derh_p;

  redeclare function extends density_derp_h "d(rho)/dp at const h"
  algorithm
    ddph := R290Tab.rho_ph_a_d(state.p, state.h, 1.0, 0.0);
  end density_derp_h;

  // ═══ 보조함수 층 (2026-08-02, P4'-2) ═══
  // R290Tab 과 동명 — 호출부 전환을 기계적 치환(R290Tab.X → Medium.X)으로
  // 만들기 위한 층. A·B군은 해석(_a), C군은 테이블 랩(추후 _a 피팅 이월).
  // 냉매 교체 시 이 집합을 동일 시그니처로 구현하면 된다.

  // ── A군: 해석, 계약과 병존 ──
  function Tsat  input Real p; output Real y; algorithm y := R290Tab.Tsat_a(p);  annotation(Inline=false, derivative=Tsat_d); end Tsat;
  function Tsat_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.Tsat_a_d(p, dp); annotation(Inline=false); end Tsat_d;
  function hl    input Real p; output Real y; algorithm y := R290Tab.hl_a(p);    annotation(Inline=false, derivative=hl_d); end hl;
  function hl_d  input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.hl_a_d(p, dp); annotation(Inline=false); end hl_d;
  function hv    input Real p; output Real y; algorithm y := R290Tab.hv_a(p);    annotation(Inline=false, derivative=hv_d); end hv;
  function hv_d  input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.hv_a_d(p, dp); annotation(Inline=false); end hv_d;
  function rhol  input Real p; output Real y; algorithm y := R290Tab.rhol_a(p);  annotation(Inline=false, derivative=rhol_d); end rhol;
  function rhol_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.rhol_a_d(p, dp); annotation(Inline=false); end rhol_d;
  function rhov  input Real p; output Real y; algorithm y := R290Tab.rhov_a(p);  annotation(Inline=false, derivative=rhov_d); end rhov;
  function rhov_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.rhov_a_d(p, dp); annotation(Inline=false); end rhov_d;
  function T_ph  input Real p; input Real h; output Real T; algorithm T := R290Tab.T_ph_a(p, h); annotation(Inline=false, derivative=T_ph_der); end T_ph;
  function T_ph_der input Real p; input Real h; input Real dp; input Real dh; output Real dT; algorithm dT := R290Tab.T_ph_a_d(p, h, dp, dh); annotation(Inline=false); end T_ph_der;
  function rho_ph input Real p; input Real h; output Real r; algorithm r := R290Tab.rho_ph_a(p, h); annotation(Inline=false, derivative=rho_ph_der); end rho_ph;
  function rho_ph_der input Real p; input Real h; input Real dp; input Real dh; output Real dr; algorithm dr := R290Tab.rho_ph_a_d(p, h, dp, dh); annotation(Inline=false); end rho_ph_der;

  // ── B군: 포화 수송물성, 해석 ──
  function mul input Real p; output Real y; algorithm y := R290Tab.mul_a(p); annotation(Inline=false, derivative=mul_d); end mul;
  function mul_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.mul_a_d(p, dp); annotation(Inline=false); end mul_d;
  function muv input Real p; output Real y; algorithm y := R290Tab.muv_a(p); annotation(Inline=false, derivative=muv_d); end muv;
  function muv_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.muv_a_d(p, dp); annotation(Inline=false); end muv_d;
  function kl  input Real p; output Real y; algorithm y := R290Tab.kl_a(p);  annotation(Inline=false, derivative=kl_d); end kl;
  function kl_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.kl_a_d(p, dp); annotation(Inline=false); end kl_d;
  function kv  input Real p; output Real y; algorithm y := R290Tab.kv_a(p);  annotation(Inline=false, derivative=kv_d); end kv;
  function kv_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.kv_a_d(p, dp); annotation(Inline=false); end kv_d;
  function cpl input Real p; output Real y; algorithm y := R290Tab.cpl_a(p); annotation(Inline=false, derivative=cpl_d); end cpl;
  function cpl_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.cpl_a_d(p, dp); annotation(Inline=false); end cpl_d;
  function cpv input Real p; output Real y; algorithm y := R290Tab.cpv_a(p); annotation(Inline=false, derivative=cpv_d); end cpv;
  function cpv_d input Real p; input Real dp; output Real dy; algorithm dy := R290Tab.cpv_a_d(p, dp); annotation(Inline=false); end cpv_d;

  // ── C군: 테이블 랩 (해석 미보유 — CoolProp→다항 생성기 과제로 이월) ──
  function p_rhoh "역산은 테이블판을 쓴다 (2026-08-02 v3 확정).
    해석 rho_ph_a 는 블렌딩 밴드 경계에서 p 에 대해 국소 비단조
    (12개 h 라인 중 2개, 최대 -0.97 kg/m3 역행 실측)라 역산이 불량정의다.
    뉴턴(클램프 진동)·이분(비단조 오수렴) 모두 야코비안 트래시를 유발했다.
    단조 제약(drho/dp|h > 0)을 하드 제약으로 갖는 재피팅은 CoolProp→다항
    생성기 과제로 이월. 그때까지 rho_ph_a(p_rhoh(rho,h),h) != rho 의
    ~0.1-0.3% 불일치가 남으며 과도 드리프트(+1.29% 실측)의 원천이다."
    input Real rho; input Real h; output Real p;
  algorithm
    p := R290Tab.p_rhoh(rho, h);
    annotation(Inline=false, derivative=p_rhoh_der);
  end p_rhoh;
  function p_rhoh_der "값(테이블 역산)과 정합 — 테이블 rho_ph_d 기반 음함수 정리"
    input Real rho; input Real h; input Real drho; input Real dh; output Real dp;
  protected
    Real p, dRdp, dRdh;
  algorithm
    p    := R290Tab.p_rhoh(rho, h);
    dRdp := R290Tab.rho_ph_d(p, h, 1.0, 0.0);
    dRdh := R290Tab.rho_ph_d(p, h, 0.0, 1.0);
    dp := (drho - dRdh*dh)/(if abs(dRdp) < 1e-12 then 1e-12 else dRdp);
    annotation(Inline=false);
  end p_rhoh_der;
  function h_ps   input Real p; input Real s; output Real h;  algorithm h := R290Tab.h_ps(p, s);    annotation(Inline=true); end h_ps;
  function s_ph   input Real p; input Real h; output Real s;  algorithm s := R290Tab.s_ph(p, h);    annotation(Inline=true); end s_ph;
  function cp_ph  input Real p; input Real h; output Real cp; algorithm cp := R290Tab.cp_ph(p, h);  annotation(Inline=true); end cp_ph;
  function mu_ph  input Real p; input Real h; output Real mu; algorithm mu := R290Tab.mu_ph(p, h);  annotation(Inline=true); end mu_ph;
  function gamma_ph input Real p; input Real h; output Real g; algorithm g := R290Tab.gamma_ph(p, h); annotation(Inline=true); end gamma_ph;

  // ── PH1: 과열도 단일 정의 (2026-08-02) ──
  function SH_ph "부호 있는 과열도 [K] — 2상이면 음수 (feat/analytic-props 7/27 정의의 단일화).
    smooth-max 판(0.5*(x+sqrt(x^2+1e-4)))은 2상 출구를 표현하지 못해 SH 가
    바닥값 0.005 에 고정되고, 이를 소비하는 EEV PI(목표 6K)가 err=-6 상수로
    개도를 계속 조인다(기준선 종점 SH=0.005/개도 44 실측과 정합).
    2상: 남은 증발 엔탈피를 cpv 로 환산해 음수로. 과열: T-Tsat."
    input Real p; input Real h; output Real SH;
  protected
    Real hL, hV, x;
  algorithm
    hL := R290Tab.hl_a(p); hV := R290Tab.hv_a(p);
    x  := (h - hL)/(hV - hL);
    SH := if x < 1.0
          then -(1.0 - max(x, 0.0))*(hV - hL)/max(R290Tab.cpv_a(p), 1.0)
          else R290Tab.T_ph_a(p, h) - R290Tab.Tsat_a(p);
    annotation(Inline=false);
  end SH_ph;

  // ── PH3: 유효영역 계약 (2026-08-02) ──
  // 방어 실행은 물성층(R290Tab 내부 클램프 38건)이 이미 담당한다. 여기서는
  // 도메인을 '계약으로 노출'해 호출부·테스트가 숫자 복제 없이 참조하게 한다.
  // 설계 원칙: 물성 도메인은 물성층이, 상관식 도메인(예: x∈[0.001,0.999])은
  // 호출부가 지킨다 — 2026-08-02 전수조사에서 컴포넌트 9건 전부 후자로 판명.
  constant Real p_min = R290Tab.P0 "물성 유효 하한 [Pa]";
  constant Real p_max = R290Tab.P1 "물성 유효 상한 [Pa]";
  constant Real h_min = R290Tab.H0 "물성 유효 하한 [J/kg]";
  constant Real h_max = R290Tab.H1 "물성 유효 상한 [J/kg]";
  // 연성 유효범위 (경계 밖 아님, 정확도 열화 구간 — P2 실측):
  //   p > 3.0e6 : 임계 근접으로 cp 계열 오차 확대 (34 bar 에서 cpl 3.9%, cpv 4.6%)
  //   rho_ph_a : 블렌딩 밴드 경계에서 p 국소 비단조 (12중 2 h라인, 최대 -0.97 kg/m3)
  //              → 역산 금지 (p_rhoh 는 테이블 역산 사용, v3)

  function domainMargin_ph "정규화 도메인 여유 — min(p축, h축), 음수면 이탈.
    각 축을 전폭으로 나눠 0~0.5 스케일. assert/모니터용 진단 함수."
    input Real p; input Real h; output Real m;
  protected
    Real mp, mh;
  algorithm
    mp := min(p - p_min, p_max - p)/(p_max - p_min);
    mh := min(h - h_min, h_max - h)/(h_max - h_min);
    m  := min(mp, mh);
    annotation(Inline=false);
  end domainMargin_ph;
end R290Medium;
