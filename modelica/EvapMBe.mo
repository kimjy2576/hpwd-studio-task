package EvapMBe "방정식형 이동경계 증발기 (L2) — dry, v2(HXCorr Chen/DB/Wang + counter 누적공기)"
  // 상태 5개: ζ, P_e, h_out, T_w1, T_w2. 벽 열용량 보유(L2 동특성).
  // 열전달: 2상 Chen / 과열 Dittus-Boelter / 공기 Wang j (+ Schmidt 핀). 알고리즘 EvapMB와 동일.
  // 공기: counter 누적 (SH zone 먼저 → 2상 zone, 직렬 C_air). dry(잠열 없음).
  // 포화선 도함수는 FD(상태에 선형). 전달물성은 alpha에만(대수) → der 계수 무관.
  package M = HelmholtzMedia.HelmholtzFluids.Propane;

  model EvaporatorMBdyn
    HPWD.RefPort port_a "입구 (2상, EEV측)";
    HPWD.RefPort port_b "출구 (과열, 압축기측)";
    // ── 형상 (알고리즘 EvapMB 검증 케이스와 동일) ──
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
    // ── 공기 (dry: W=0) ──
    parameter Real T_air_in_C = 45.0 "공기 입구 [°C]";
    parameter Real V_air_CMM = 2.54;
    // ── 벽 열용량 [J/K] ──
    parameter Real C_w1 = 300.0, C_w2 = 150.0;
    // ── FD 섭동 ──
    parameter Real dP = 50.0, dh = 200.0;
    // ── 파생 형상 ──
    final parameter Real P_fin = 0.0254/FPI;
    final parameter Real A_tube_outer = 3.141592653589793*D_o*L_tube_total;
    final parameter Real n_fins_per_tube = L_tube_total/N_tubes/P_fin;
    final parameter Real A_per_fin = 2.0*(P_t*P_l - 3.141592653589793*D_o^2/4.0);
    final parameter Real A_fin_total = N_tubes*n_fins_per_tube*A_per_fin;
    final parameter Real A_o = A_tube_outer + A_fin_total;
    final parameter Real A_i = 3.141592653589793*D_i*L_tube_total;
    final parameter Real V_tot = 3.141592653589793*D_i^2/4.0*L_tube_total;
    final parameter Real A_cross = 3.141592653589793*D_i^2/4.0;
    final parameter Real Dc = D_o + 2.0*t_fin;
    final parameter Real gap = P_fin - t_fin;
    final parameter Real sig_c = max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    final parameter Real A_c = sig_c*A_o_face;
    final parameter Real T_air_in = T_air_in_C + 273.15;
    final parameter Real m_dot_air = HXCorr.rho_humid_air(T_air_in_C, 0.0, 101325.0)*(V_air_CMM/60.0);
    final parameter Real C_air = m_dot_air*HXCorr.cp_ha_moist(0.0);
    // ── 상태 ──
    Real zeta(start = 0.8, fixed = true) "2상 zone 분율";
    Modelica.Units.SI.AbsolutePressure P_e(start = 5.5e5, fixed = true);
    Real h_out(start = 600e3, fixed = true);
    Modelica.Units.SI.Temperature T_w1(start = 295.0, fixed = true);
    Modelica.Units.SI.Temperature T_w2(start = 300.0, fixed = true);
    // ── 관측/대수 ──
    Real mdot_in, mdot_out, h_in, mdot_b, x_in, SH_out, Q_total, Q1, Q2, T_sat_C;
    Real Q1_air, Q2_air, T_air_mid, T_air_out;
    Real UA_ref_2ph, UA_ref_SH, UA_ser_2ph, UA_ser_SH, Cmin_SH, Cr_SH, NTU_SH, eps_SH;
    Real alpha_2ph, alpha_SH, alpha_air, eta_fin, eta_overall;
  protected
    M.SaturationProperties sat, satP;
    M.ThermodynamicState st_l, st_v, st_lq, st_vq, st10;
    Real h_l, h_v, Tsat, rho_l, rho_v, gamma, rho1, hbar1, rho2, hbar2, Tref2;
    Real h_lP, h_vP, rho_lP, rho_vP, gammaP, rho1P, rho2P, hbar2P, hbar2h, rho2h;
    Real dhv_dP, drho1_dP, drho2_dP, drho2_dh, ru1, ru2, CE1P, CE2P, CE2h, xm, xmP;
    Real mu_l, mu_v, k_l, cp_l, Pr_l, mu10, k10, cp10, cp_vs, Pcrit, Mmol;
    Real x_avg_2ph, q_flux, G_2ph, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air;
  equation
    // ── 포트 (증발기가 압력 P_e 보유)
    P_e = port_a.p;
    port_a.p = port_b.p;
    h_in = inStream(port_a.h_outflow);
    mdot_in = port_a.m_flow;
    mdot_out = -port_b.m_flow;
    port_b.h_outflow = h_out;
    port_a.h_outflow = h_v;
    // ── 질량 균형 (수동 der 전개)
    V_tot*(drho1_dP*der(P_e)*zeta + rho1*der(zeta)) = mdot_in - mdot_b;
    V_tot*((drho2_dP*der(P_e) + drho2_dh*der(h_out))*(1.0 - zeta) - rho2*der(zeta)) = mdot_b - mdot_out;
    // ── 에너지 균형 (ρu = ρh̄ − P)
    V_tot*(CE1P*der(P_e)*zeta + ru1*der(zeta)) = mdot_in*h_in - mdot_b*h_v + Q1;
    V_tot*((CE2P*der(P_e) + CE2h*der(h_out))*(1.0 - zeta) - ru2*der(zeta)) = mdot_b*h_v - mdot_out*h_out + Q2;
    // ── 직렬 UA per zone (알고리즘 EvapMB 동일: air↔ref 직렬 ε-NTU)
    UA_ref_2ph = alpha_2ph*A_i*zeta;
    UA_ref_SH = alpha_SH*A_i*(1.0 - zeta);
    UA_ser_2ph = (alpha_air*A_o*eta_overall*zeta)*UA_ref_2ph/(alpha_air*A_o*eta_overall*zeta + UA_ref_2ph + 1e-12);
    UA_ser_SH = (alpha_air*A_o*eta_overall*(1.0 - zeta))*UA_ref_SH/(alpha_air*A_o*eta_overall*(1.0 - zeta) + UA_ref_SH + 1e-12);
    // ── 공기측 (counter 누적: SH zone 먼저 → 2상; air↔ref 직렬 ε, Cr→0)
    Cmin_SH = min(mdot_in*cp_vs, C_air);
    Cr_SH = Cmin_SH/max(mdot_in*cp_vs, C_air);
    NTU_SH = UA_ser_SH/max(Cmin_SH, 1e-9);
    eps_SH = (1.0 - exp(-NTU_SH*(1.0 - Cr_SH)))/(1.0 - Cr_SH*exp(-NTU_SH*(1.0 - Cr_SH)) + 1e-12);
    Q2_air = eps_SH*Cmin_SH*(T_air_in - Tsat);
    T_air_mid = T_air_in - Q2_air/C_air;
    Q1_air = (1.0 - exp(-UA_ser_2ph/C_air))*C_air*(T_air_mid - Tsat);
    T_air_out = T_air_mid - Q1_air/C_air;
    // ── 벽: 공기측 직렬열 수신 − 냉매측 배출. 정상서 Q=Q_air=알고리즘 직렬열 → ζ 일치
    C_w1*der(T_w1) = Q1_air - Q1;
    C_w2*der(T_w2) = Q2_air - Q2;
    Q1 = UA_ref_2ph*(T_w1 - Tsat);
    Q2 = UA_ref_SH*(T_w2 - Tref2);
    // ── 관측
    Q_total = Q1 + Q2;
    SH_out = M.temperature(M.setState_ph(P_e, h_out)) - Tsat;
    T_sat_C = Tsat - 273.15;
    x_in = (h_in - h_l)/(h_v - h_l);
  algorithm
    // ── 포화 + 열역학 (FD 계수용; v1과 동일) ──
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
    hbar2h := 0.5*(h_v + (h_out + dh));
    rho2h := M.density(M.setState_ph(P_e, hbar2h));
    dhv_dP := (h_vP - h_v)/dP;
    drho1_dP := (rho1P - rho1)/dP;
    drho2_dP := (rho2P - rho2)/dP;
    drho2_dh := (rho2h - rho2)/dh;
    ru1 := rho1*hbar1 - P_e;
    ru2 := rho2*hbar2 - P_e;
    CE1P := drho1_dP*hbar1 + rho1*(dhv_dP/2.0) - 1.0;
    CE2P := drho2_dP*hbar2 + rho2*(dhv_dP/2.0) - 1.0;
    CE2h := drho2_dh*hbar2 + rho2*0.5;
    // ── 전달물성 (알고리즘 EvapMB 레시피: 포화 ρ·μ, cp/k는 ±0.1K off-sat) ──
    st_l := M.setState_px(P_e, 0.0);
    st_v := M.setState_px(P_e, 1.0);
    mu_l := M.dynamicViscosity(st_l);
    mu_v := M.dynamicViscosity(st_v);
    st_lq := M.setState_pT(P_e, Tsat - 0.1);
    k_l := M.thermalConductivity(st_lq);
    cp_l := M.specificHeatCapacityCp(st_lq);
    Pr_l := cp_l*mu_l/k_l;
    st10 := M.setState_pT(P_e, Tsat + 10.0);
    mu10 := M.dynamicViscosity(st10);
    k10 := M.thermalConductivity(st10);
    cp10 := M.specificHeatCapacityCp(st10);
    st_vq := M.setState_pT(P_e, Tsat + 0.1);
    cp_vs := M.specificHeatCapacityCp(st_vq);
    Pcrit := M.fluidConstants[1].criticalPressure;
    Mmol := M.fluidConstants[1].molarMass*1000.0;
    // ── 냉매측 α ──
    x_avg_2ph := 0.5*((h_in - h_l)/(h_v - h_l) + 1.0);
    q_flux := mdot_in*(h_v - h_in)/A_i;
    G_2ph := (mdot_in/n_circuits)/A_cross;
    alpha_2ph := HXCorr.h_evap_chen1966(x_avg_2ph, G_2ph, D_i, q_flux, mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_e/Pcrit, Mmol);
    alpha_SH := HXCorr.dittus_boelter(mu10, k10, cp10, mdot_in/n_circuits, D_i, true);
    // ── 공기측 α (Wang j + Schmidt 핀) ──
    T_air_avg := 0.5*(T_air_in + Tsat);
    mu_a := HXCorr.mu_air(T_air_avg);
    Pr_a := HXCorr.Pr_air(T_air_avg);
    G_air := m_dot_air/A_c;
    Re_Dc := G_air*Dc/mu_a;
    j_air := HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air := j_air*G_air*1006.0/Pr_a^(2.0/3.0);
    eta_fin := HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
    eta_overall := (A_tube_outer + A_fin_total*eta_fin)/A_o;
  end EvaporatorMBdyn;

  model FlowBC "유량 경계. m_flow = m_flow_set + k_p·p"
    HPWD.RefPort port;
    parameter Real m_flow_set = -0.003;
    parameter Real k_p = 0.0;
    parameter Real h_set = 287e3;
  equation
    port.m_flow = m_flow_set + k_p*port.p;
    port.h_outflow = h_set;
  end FlowBC;

  model EvapMBdyn_test "소스(2상) → 증발기 → 압축기형 싱크(P_e 자기조절). 45°C 공기 dry."
    EvaporatorMBdyn evap;
    FlowBC inlet(m_flow_set = -0.005, k_p = 0.0, h_set = 287e3);
    FlowBC outlet(m_flow_set = 0.0, k_p = 0.005/5.5e5, h_set = 0.0);
  equation
    connect(inlet.port, evap.port_a);
    connect(outlet.port, evap.port_b);
  end EvapMBdyn_test;
end EvapMBe;
