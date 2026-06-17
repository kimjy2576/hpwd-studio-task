package EvapMBe "방정식형 이동경계 증발기 (L2) — dry, v1(상수 HTC, 구조 검증)"
  // 이동경계 정식화: 2상 zone(길이 ζL) + 과열 zone((1−ζ)L), 경계 ζ가 상태.
  // 상태 5개: ζ, P_e, h_out, T_w1, T_w2.  포화선 도함수는 FD(상태엔 선형) → 수동 der 전개.
  // v1은 α를 상수로 두고 MB 구조/동특성/벽을 검증. v2에서 HXCorr(Chen·DB·Wang)로 교체.
  package M = HelmholtzMedia.HelmholtzFluids.Propane;

  model EvaporatorMBdyn
    HPWD.RefPort port_a "입구 (2상, EEV측)";
    HPWD.RefPort port_b "출구 (과열, 압축기측)";
    // 형상
    parameter Real D_i = 0.0065 "관 내경 [m]";
    parameter Real L_tube = 10.0 "총 관 길이 [m]";
    parameter Real A_air = 4.0 "공기측 전열면적 [m²]";
    // HTC (v1 상수) [W/m²K]
    parameter Real h_ref_2ph = 2000.0 "2상 냉매측";
    parameter Real h_ref_SH = 200.0 "과열 냉매측";
    parameter Real h_air = 60.0 "공기측";
    // 공기 경계
    parameter Modelica.Units.SI.Temperature T_air_in = 293.15 "공기 입구 [K]";
    parameter Real V_air_CMM = 2.54 "공기 유량 [m³/min]";
    parameter Real rho_air = 1.2, cp_air = 1006.0;
    // 벽 열용량 [J/K]
    parameter Real C_w1 = 200.0, C_w2 = 100.0;
    // FD 섭동
    parameter Real dP = 50.0, dh = 200.0;
    // 파생
    final parameter Real V_tot = 3.141592653589793*D_i^2/4.0*L_tube "냉매 내부 체적";
    final parameter Real A_ht = 3.141592653589793*D_i*L_tube "내부 전열면적";
    final parameter Real C_air = rho_air*(V_air_CMM/60.0)*cp_air "공기 열용량률 [W/K]";
    final parameter Real eps_air = 1.0 - exp(-h_air*A_air/C_air) "공기측 ε (ζ 무관)";
    // 상태
    Real zeta(start = 0.8, fixed = true) "2상 zone 분율";
    Modelica.Units.SI.AbsolutePressure P_e(start = 5.5e5, fixed = true) "증발압력";
    Real h_out(start = 597e3, fixed = true) "과열 출구 엔탈피";
    Modelica.Units.SI.Temperature T_w1(start = 285.0, fixed = true) "2상 벽온";
    Modelica.Units.SI.Temperature T_w2(start = 288.0, fixed = true) "과열 벽온";
    // 관측/대수
    Real mdot_in, mdot_out, h_in, mdot_b, x_in, SH_out, Q_total, Q1, Q2, T_sat_C;
  protected
    M.SaturationProperties sat, satP;
    Real h_l, h_v, Tsat, rho_l, rho_v, gamma, rho1, hbar1, rho2, hbar2, Tref2;
    Real h_lP, h_vP, rho_lP, rho_vP, gammaP, rho1P, rho2P, hbar2P, hbar2h, rho2h;
    Real dhv_dP, drho1_dP, drho2_dP, drho2_dh, ru1, ru2, CE1P, CE2P, CE2h, xm, xmP;
  equation
    // ── 포트 (증발기가 압력 P_e를 보유; 양 포트 동압)
    P_e = port_a.p;
    port_a.p = port_b.p;
    h_in = inStream(port_a.h_outflow);
    mdot_in = port_a.m_flow;
    mdot_out = -port_b.m_flow;
    port_b.h_outflow = h_out;
    port_a.h_outflow = h_v;
    // ── 질량 균형 (수동 der 전개; 계수는 algorithm서 FD)
    V_tot*(drho1_dP*der(P_e)*zeta + rho1*der(zeta)) = mdot_in - mdot_b;
    V_tot*((drho2_dP*der(P_e) + drho2_dh*der(h_out))*(1.0 - zeta) - rho2*der(zeta)) = mdot_b - mdot_out;
    // ── 에너지 균형 (ρu = ρh̄ − P)
    V_tot*(CE1P*der(P_e)*zeta + ru1*der(zeta)) = mdot_in*h_in - mdot_b*h_v + Q1;
    V_tot*((CE2P*der(P_e) + CE2h*der(h_out))*(1.0 - zeta) - ru2*der(zeta)) = mdot_b*h_v - mdot_out*h_out + Q2;
    // ── 열전달 (벽 → 냉매)
    Q1 = h_ref_2ph*A_ht*zeta*(T_w1 - Tsat);
    Q2 = h_ref_SH*A_ht*(1.0 - zeta)*(T_w2 - Tref2);
    // ── 벽 에너지 (공기 → 벽 − 벽 → 냉매)
    C_w1*der(T_w1) = eps_air*C_air*zeta*(T_air_in - T_w1) - Q1;
    C_w2*der(T_w2) = eps_air*C_air*(1.0 - zeta)*(T_air_in - T_w2) - Q2;
    // ── 관측
    Q_total = Q1 + Q2;
    SH_out = M.temperature(M.setState_ph(P_e, h_out)) - Tsat;
    T_sat_C = Tsat - 273.15;
    x_in = (h_in - h_l)/(h_v - h_l);
  algorithm
    // base @ P_e
    sat := M.setSat_p(P_e);
    Tsat := M.saturationTemperature(P_e);
    h_l := M.bubbleEnthalpy(sat);
    h_v := M.dewEnthalpy(sat);
    rho_l := M.bubbleDensity(sat);
    rho_v := M.dewDensity(sat);
    xm := 0.5*((h_in - h_l)/(h_v - h_l) + 1.0);
    gamma := 1.0/(1.0 + (1.0 - xm)/xm*rho_v/rho_l);
    rho1 := rho_l*(1.0 - gamma) + rho_v*gamma;
    hbar1 := 0.5*(h_in + h_v);
    hbar2 := 0.5*(h_v + h_out);
    rho2 := M.density(M.setState_ph(P_e, hbar2));
    Tref2 := M.temperature(M.setState_ph(P_e, hbar2));
    // perturb P_e
    satP := M.setSat_p(P_e + dP);
    h_lP := M.bubbleEnthalpy(satP);
    h_vP := M.dewEnthalpy(satP);
    rho_lP := M.bubbleDensity(satP);
    rho_vP := M.dewDensity(satP);
    xmP := 0.5*((h_in - h_lP)/(h_vP - h_lP) + 1.0);
    gammaP := 1.0/(1.0 + (1.0 - xmP)/xmP*rho_vP/rho_lP);
    rho1P := rho_lP*(1.0 - gammaP) + rho_vP*gammaP;
    hbar2P := 0.5*(h_vP + h_out);
    rho2P := M.density(M.setState_ph(P_e + dP, hbar2P));
    // perturb h_out
    hbar2h := 0.5*(h_v + (h_out + dh));
    rho2h := M.density(M.setState_ph(P_e, hbar2h));
    // FD 도함수
    dhv_dP := (h_vP - h_v)/dP;
    drho1_dP := (rho1P - rho1)/dP;
    drho2_dP := (rho2P - rho2)/dP;
    drho2_dh := (rho2h - rho2)/dh;
    // 에너지 계수
    ru1 := rho1*hbar1 - P_e;
    ru2 := rho2*hbar2 - P_e;
    CE1P := drho1_dP*hbar1 + rho1*(dhv_dP/2.0) - 1.0;
    CE2P := drho2_dP*hbar2 + rho2*(dhv_dP/2.0) - 1.0;
    CE2h := drho2_dh*hbar2 + rho2*0.5;
  end EvaporatorMBdyn;

  model FlowBC "유량 경계. m_flow = m_flow_set + k_p·p (k_p>0이면 압축기형 자기조절)"
    HPWD.RefPort port;
    parameter Real m_flow_set = -0.005 "기저 유량 (음=유출=소스)";
    parameter Real k_p = 0.0 "압력비례 계수";
    parameter Real h_set = 287e3;
  equation
    port.m_flow = m_flow_set + k_p*port.p;
    port.h_outflow = h_set;
  end FlowBC;

  model EvapMBdyn_test "소스(2상 0.002) → 증발기 → 압축기형 싱크(P_e 자기조절)"
    EvaporatorMBdyn evap;
    FlowBC inlet(m_flow_set = -0.002, k_p = 0.0, h_set = 287e3) "2상 유입";
    FlowBC outlet(m_flow_set = 0.0, k_p = 0.002/5.5e5, h_set = 0.0) "압축기형: ṁ=k·P_e, 정상서 0.002";
  equation
    connect(inlet.port, evap.port_a);
    connect(outlet.port, evap.port_b);
  end EvapMBdyn_test;
  model EvapMBdyn_pert "교란 start(ζ=0.5,P_e=4.5bar,벽=293)서 수렴 확인"
    EvaporatorMBdyn evap(zeta(start=0.5), P_e(start=4.5e5), T_w1(start=293.15), T_w2(start=293.15), h_out(start=590e3));
    FlowBC inlet(m_flow_set=-0.002, k_p=0.0, h_set=287e3);
    FlowBC outlet(m_flow_set=0.0, k_p=0.002/5.5e5, h_set=0.0);
  equation
    connect(inlet.port, evap.port_a);
    connect(outlet.port, evap.port_b);
  end EvapMBdyn_pert;
end EvapMBe;
