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
end R290Medium;
