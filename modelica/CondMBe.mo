package CondMBe "방정식형 응축기 (L2 정상상태) — 3-zone(deSH+2상+SC), demand 강제, dry 공기"
  // 동적 3-zone 이동경계 MB는 SC(과냉액) zone 비압축성 때문에 2상/SC 경계가 불안정(검증완료).
  // → 정상상태를 대수계로 풂: deSH·2상 zone이 응축 demand를 제거하도록 zeta 결정,
  //   SC는 잔여 길이가 과냉량 결정. 알고리즘 CondMB의 선언형(equation-based) 등가물.
  //   2상 Shah / deSH·SC Gnielinski / 공기 Wang, 직렬 UA, 공기 counter(SC→2상→deSH).
  package M = HelmholtzMedia.HelmholtzFluids.Propane;

  function tempPH "(p,h) -> T[K] (R290Tab)"
    input Real p, h;
    output Real T;
  algorithm
    T := R290Tab.T_ph(p, h);
  end tempPH;

  function propsCond "P_c[Pa], h_in[J/kg] -> 응축기 스칼라 물성 (R290Tab)"
    input Real p, h_in;
    output Real Tcond, Trefin, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, cpl_sat, cpv_mean, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5, Pcrit;
  protected
    Real h_cpv, h_v5, h_l5;
  algorithm
    Tcond := R290Tab.Tsat(p);
    Trefin := R290Tab.T_ph(p, h_in);
    h_l := R290Tab.hl(p); h_v := R290Tab.hv(p);
    rho_l := R290Tab.rhol(p); rho_v := R290Tab.rhov(p);
    mu_l := R290Tab.mul(p); k_l := R290Tab.kl(p); cpl_sat := R290Tab.cpl(p);
    Pr_l := cpl_sat*mu_l/k_l;
    h_cpv := 0.5*(h_in + h_v);
    cpv_mean := R290Tab.cp_ph(p, h_cpv);
    h_v5 := h_v + R290Tab.cpv(p)*5.0;
    mu_v5 := R290Tab.mu_ph(p, h_v5); k_v5 := R290Tab.k_ph(p, h_v5);
    Pr_v5 := R290Tab.cp_ph(p, h_v5)*mu_v5/k_v5;
    h_l5 := h_l - R290Tab.cpl(p)*5.0;
    mu_l5 := R290Tab.mu_ph(p, h_l5); k_l5 := R290Tab.k_ph(p, h_l5);
    Pr_l5 := R290Tab.cp_ph(p, h_l5)*mu_l5/k_l5;
    Pcrit := 42.512e5;
  end propsCond;

  model CondenserSS "정상상태 방정식형 응축기 (RefPort TwoPort)"
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
    parameter Real dP_ref = 0.03;
    parameter Real T_air_in_C = 35.0, RH_in = 0.50, V_air_CMM = 25.42;
    // ── 튜브 배열 + micro-fin (내부강화) ──
    parameter String layout = "staggered" "튜브 배열: staggered / inline";
    parameter String tube_type = "smooth" "튜브 내면: smooth / microfin";
    parameter Integer n_microfin = 0 "(microfin) 내부 핀 개수";
    parameter Real e_microfin = 0.0 "(microfin) 핀 높이 [m]";
    parameter Real helix_angle = 0.0 "(microfin) 나선각 [deg]";
    // ── 파생 (형상/공기) ──
    final parameter Real P_fin = 0.0254/FPI;
    final parameter Real A_tube_outer = 3.141592653589793*D_o*L_tube_total;
    final parameter Real n_fins_per_tube = L_tube_total/N_tubes/P_fin;
    final parameter Real A_per_fin = 2.0*(P_t*P_l - 3.141592653589793*D_o^2/4.0);
    final parameter Real A_fin_total = N_tubes*n_fins_per_tube*A_per_fin;
    final parameter Real A_o = A_tube_outer + A_fin_total;
    final parameter Real A_i = 3.141592653589793*D_i*L_tube_total;
    final parameter Real A_cross = 3.141592653589793*D_i^2/4.0;
    final parameter Real Dc = D_o + 2.0*t_fin;
    final parameter Real gap = P_fin - t_fin;
    final parameter Real sig_c = max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    final parameter Real A_c = sig_c*A_o_face;
    final parameter Real T_air_in = T_air_in_C + 273.15;
    final parameter Real W_in = HXCorr.W_humid(T_air_in_C, RH_in, 101325.0);
    final parameter Real m_dot_air = HXCorr.rho_humid_air(T_air_in_C, W_in, 101325.0)*(V_air_CMM/60.0);
    final parameter Real C_air = m_dot_air*HXCorr.cp_ha_moist(W_in);
    // micro-fin EF (기하만 의존 → final parameter). smooth면 ψ=1 → EF=1 (하위호환).
    final parameter Real psi_mf = if tube_type == "microfin" then HXCorr.microfin_area_ratio(n_microfin, e_microfin, helix_angle, D_i) else 1.0;
    final parameter Real EF_cond = HXCorr.microfin_ef("cond", psi_mf, helix_angle);
    final parameter Real EF_sgl = HXCorr.microfin_ef("single", psi_mf, helix_angle);
    // ── 미지수 (zone) — start로 초기추정 ──
    Real zeta_d(start = 0.15), zeta_2(start = 0.51), zeta_sc;
    Real Qd, Q2, Qsc, Q_total;
    Real Ta_2ph, Ta_deSH, Ta_out;
    Real h_out(start = 300e3), SC_out, T_ref_out_C, T_cond_C, T_ref_in_C, quality_out;
    Real mdot, P_c, h_in;
    Real UA_ref_deSH, UA_ref_2ph, UA_ref_SC, UA_ser_deSH, UA_ser_2ph, UA_ser_SC;
    Real Cmin_deSH, Cr_deSH, eps_deSH, Cmin_SC, Cr_SC, eps_SC, eps_2ph, NTU_d, NTU_2, NTU_s;
    Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin, eta_overall;
  protected
    Real h_l, h_v, Tcond, rho_l, rho_v, Trefin;
    Real mu_l, k_l, Pr_l, Pcrit, cpl_sat, cpv_mean, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5;
    Real G_2ph, Re_deSH, Re_SC, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air;
  equation
    // ── 포트 (정상상태: 압력은 상류서 결정, 응축기는 zone/열/출구만 계산) ──
    P_c = port_a.p;
    port_b.p = P_c*(1.0 - dP_ref);
    h_in = inStream(port_a.h_outflow);
    mdot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_out;
    port_a.h_outflow = h_v;
    zeta_sc = 1.0 - zeta_d - zeta_2;
    // ── 물성 (record 격리 함수) + 알파 (equation화) ──
    (Tcond, Trefin, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, cpl_sat, cpv_mean, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5, Pcrit) = CondMBe.propsCond(P_c, h_in);
    G_2ph = (mdot/n_circuits)/A_cross;
    alpha_2ph = HXCorr.h_cond_shah1979(0.5, G_2ph, D_i, mu_l, k_l, Pr_l, P_c/Pcrit)*EF_cond;
    Re_deSH = G_2ph*D_i/mu_v5;
    alpha_deSH = HXCorr.gnielinski(Re_deSH, Pr_v5, k_v5, D_i)*EF_sgl;
    Re_SC = G_2ph*D_i/mu_l5;
    alpha_SC = HXCorr.gnielinski(Re_SC, Pr_l5, k_l5, D_i)*EF_sgl;
    T_air_avg = 0.5*(T_air_in + Tcond);
    mu_a = HXCorr.mu_air(T_air_avg);
    Pr_a = HXCorr.Pr_air(T_air_avg);
    G_air = m_dot_air/A_c;
    Re_Dc = G_air*Dc/mu_a;
    j_air = if layout == "inline" then HXCorr.j_plain_inline(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin) else HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air = j_air*G_air*1006.0/Pr_a^(2.0/3.0);
    eta_fin = HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, layout);
    eta_overall = (A_tube_outer + A_fin_total*eta_fin)/A_o;
    // ── 냉매측 UA (zeta 의존) + 직렬 UA ──
    UA_ref_deSH = alpha_deSH*A_i*zeta_d;
    UA_ref_2ph = alpha_2ph*A_i*zeta_2;
    UA_ref_SC = alpha_SC*A_i*zeta_sc;
    UA_ser_deSH = (alpha_air*A_o*eta_overall*zeta_d)*UA_ref_deSH/(alpha_air*A_o*eta_overall*zeta_d + UA_ref_deSH + 1e-12);
    UA_ser_2ph = (alpha_air*A_o*eta_overall*zeta_2)*UA_ref_2ph/(alpha_air*A_o*eta_overall*zeta_2 + UA_ref_2ph + 1e-12);
    UA_ser_SC = (alpha_air*A_o*eta_overall*zeta_sc)*UA_ref_SC/(alpha_air*A_o*eta_overall*zeta_sc + UA_ref_SC + 1e-12);
    // ── 공기 누적 (counter: SC → 2상 → deSH) + 각 zone ε-NTU ──
    Cmin_SC = min(mdot*cpl_sat, C_air);
    Cr_SC = Cmin_SC/max(mdot*cpl_sat, C_air);
    NTU_s = UA_ser_SC/max(Cmin_SC, 1e-9);
    eps_SC = (1.0 - exp(-NTU_s*(1.0 - Cr_SC)))/(1.0 - Cr_SC*exp(-NTU_s*(1.0 - Cr_SC)) + 1e-12);
    Qsc = eps_SC*Cmin_SC*(Tcond - T_air_in);
    Ta_2ph = T_air_in + Qsc/C_air;
    NTU_2 = UA_ser_2ph/C_air;
    eps_2ph = 1.0 - exp(-NTU_2);
    Q2 = eps_2ph*C_air*(Tcond - Ta_2ph);
    Ta_deSH = Ta_2ph + Q2/C_air;
    Cmin_deSH = min(mdot*cpv_mean, C_air);
    Cr_deSH = Cmin_deSH/max(mdot*cpv_mean, C_air);
    NTU_d = UA_ser_deSH/max(Cmin_deSH, 1e-9);
    eps_deSH = (1.0 - exp(-NTU_d*(1.0 - Cr_deSH)))/(1.0 - Cr_deSH*exp(-NTU_d*(1.0 - Cr_deSH)) + 1e-12);
    Qd = eps_deSH*Cmin_deSH*(Trefin - Ta_deSH);
    Ta_out = Ta_deSH + Qd/C_air;
    // ── demand 강제 (정상상태): deSH·2상 zone이 demand 제거 → zeta_d, zeta_2 결정 ──
    Qd = mdot*(h_in - h_v);
    Q2 = mdot*(h_v - h_l);
    // ── SC: 잔여 zeta_sc가 과냉 결정 ──
    h_out = h_l - Qsc/mdot;
    // ── 관측 ──
    Q_total = Qd + Q2 + Qsc;
    T_cond_C = Tcond - 273.15;
    T_ref_in_C = Trefin - 273.15;
    T_ref_out_C = CondMBe.tempPH(P_c, h_out) - 273.15;
    SC_out = T_cond_C - T_ref_out_C;
    quality_out = (h_out - h_l)/(h_v - h_l);
  end CondenserSS;

  model CondSS_test "FlowSource(과열증기) → 응축기SS → 개방 싱크"
    CondenserSS cond;
    HPWDhx.FlowSource src(p = 17e5, h = 665e3, m_flow_set = 0.0065);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end CondSS_test;

  model CondenserSSwall "냉매 zone quasi-static + 벽 열질량 동적 (중간 길) — HX 금속 warm-up transient 포착, charge 불안정 회피"
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
    parameter Real dP_ref = 0.03;
    parameter Real T_air_in_C = 35.0, RH_in = 0.50, V_air_CMM = 25.42;
    parameter Real C_wd = 200.0, C_w2 = 700.0, C_wsc = 400.0 "zone별 벽 열용량 [J/K]";
    final parameter Real P_fin = 0.0254/FPI;
    final parameter Real A_tube_outer = 3.141592653589793*D_o*L_tube_total;
    final parameter Real n_fins_per_tube = L_tube_total/N_tubes/P_fin;
    final parameter Real A_per_fin = 2.0*(P_t*P_l - 3.141592653589793*D_o^2/4.0);
    final parameter Real A_fin_total = N_tubes*n_fins_per_tube*A_per_fin;
    final parameter Real A_o = A_tube_outer + A_fin_total;
    final parameter Real A_i = 3.141592653589793*D_i*L_tube_total;
    final parameter Real A_cross = 3.141592653589793*D_i^2/4.0;
    final parameter Real Dc = D_o + 2.0*t_fin;
    final parameter Real gap = P_fin - t_fin;
    final parameter Real sig_c = max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    final parameter Real A_c = sig_c*A_o_face;
    final parameter Real T_air_in = T_air_in_C + 273.15;
    final parameter Real W_in = HXCorr.W_humid(T_air_in_C, RH_in, 101325.0);
    final parameter Real m_dot_air = HXCorr.rho_humid_air(T_air_in_C, W_in, 101325.0)*(V_air_CMM/60.0);
    final parameter Real C_air = m_dot_air*HXCorr.cp_ha_moist(W_in);
    // ── 벽 상태 (동적) ──
    Modelica.Units.SI.Temperature T_wd(start = 320.0, fixed = true);
    Modelica.Units.SI.Temperature T_w2(start = 316.0, fixed = true);
    Modelica.Units.SI.Temperature T_wsc(start = 312.0, fixed = true);
    // ── 대수 미지수 ──
    Real zeta_d(start = 0.15), zeta_2(start = 0.51), zeta_sc;
    Real Qd, Q2, Qsc, Qd_air, Q2_air, Qsc_air, Q_total;
    Real Ta_2ph, Ta_deSH, Ta_out, h_out(start = 300e3), SC_out, T_ref_out_C, T_cond_C, T_ref_in_C, Tsc_C;
    Real mdot, P_c, h_in;
    Real UA_ref_deSH, UA_ref_2ph, UA_ref_SC, UA_air_deSH, UA_air_2ph, UA_air_SC, eps_air_d, eps_air_2, eps_air_s;
    Real C_ref_deSH, C_ref_SC;
    Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin, eta_overall;
  protected
    M.SaturationProperties sat;
    M.ThermodynamicState st_l, st_lq, st_v5, st_l5, st_cpv, st_in;
    Real h_l, h_v, Tcond, rho_l, rho_v, Trefin, Tdesh, Tsc;
    Real mu_l, k_l, Pr_l, sig, Pcrit, cpl_sat, cpv_mean, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5;
    Real G_2ph, Re_deSH, Re_SC, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air;
  equation
    P_c = port_a.p;
    port_b.p = P_c*(1.0 - dP_ref);
    h_in = inStream(port_a.h_outflow);
    mdot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_out;
    port_a.h_outflow = h_v;
    zeta_sc = 1.0 - zeta_d - zeta_2;
    UA_ref_deSH = alpha_deSH*A_i*zeta_d;
    UA_ref_2ph = alpha_2ph*A_i*zeta_2;
    UA_ref_SC = alpha_SC*A_i*zeta_sc;
    UA_air_deSH = alpha_air*A_o*eta_overall*zeta_d;
    UA_air_2ph = alpha_air*A_o*eta_overall*zeta_2;
    UA_air_SC = alpha_air*A_o*eta_overall*zeta_sc;
    // ── 냉매 → 벽 (demand 강제 → zeta explicit) ──
    Qd = mdot*(h_in - h_v);
    C_ref_deSH = mdot*cpv_mean;
    UA_ref_deSH = C_ref_deSH*log(max((Trefin - T_wd)/max(Tcond - T_wd, 0.1), 1.0));
    Q2 = mdot*(h_v - h_l);
    Q2 = UA_ref_2ph*(Tcond - T_w2);
    C_ref_SC = mdot*cpl_sat;
    Qsc = C_ref_SC*(1.0 - exp(-UA_ref_SC/C_ref_SC))*(Tcond - T_wsc);
    h_out = h_l - Qsc/mdot;
    Tsc = M.temperature(M.setState_ph(P_c, 0.5*(h_l + h_out)));
    // ── 벽 → 공기 (counter: SC→2상→deSH), 공기 ε-NTU(Cr→0, 벽 등온) ──
    eps_air_s = 1.0 - exp(-UA_air_SC/C_air);
    Qsc_air = eps_air_s*C_air*(T_wsc - T_air_in);
    Ta_2ph = T_air_in + Qsc_air/C_air;
    eps_air_2 = 1.0 - exp(-UA_air_2ph/C_air);
    Q2_air = eps_air_2*C_air*(T_w2 - Ta_2ph);
    Ta_deSH = Ta_2ph + Q2_air/C_air;
    eps_air_d = 1.0 - exp(-UA_air_deSH/C_air);
    Qd_air = eps_air_d*C_air*(T_wd - Ta_deSH);
    Ta_out = Ta_deSH + Qd_air/C_air;
    // ── 벽 동역학 (양쪽이 T_w에 음피드백 → 안정) ──
    C_wd*der(T_wd) = Qd - Qd_air;
    C_w2*der(T_w2) = Q2 - Q2_air;
    C_wsc*der(T_wsc) = Qsc - Qsc_air;
    // ── 관측 ──
    Q_total = Qd + Q2 + Qsc;
    T_cond_C = Tcond - 273.15;
    T_ref_in_C = Trefin - 273.15;
    T_ref_out_C = M.temperature(M.setState_ph(P_c, h_out)) - 273.15;
    SC_out = T_cond_C - T_ref_out_C;
    Tsc_C = Tsc - 273.15;
  algorithm
    sat := M.setSat_p(P_c);
    Tcond := M.saturationTemperature(P_c);
    h_l := M.bubbleEnthalpy(sat);
    h_v := M.dewEnthalpy(sat);
    rho_l := M.bubbleDensity(sat);
    rho_v := M.dewDensity(sat);
    st_in := M.setState_ph(P_c, h_in);
    Trefin := M.temperature(st_in);
    Tdesh := M.temperature(M.setState_ph(P_c, 0.5*(h_in + h_v)));
    st_l := M.setState_px(P_c, 0.0);
    mu_l := M.dynamicViscosity(st_l);
    st_lq := M.setState_pT(P_c, Tcond - 0.1);
    k_l := M.thermalConductivity(st_lq);
    Pr_l := M.specificHeatCapacityCp(st_lq)*mu_l/k_l;
    sig := M.surfaceTension(sat);
    Pcrit := M.fluidConstants[1].criticalPressure;
    cpl_sat := M.specificHeatCapacityCp(st_lq);
    st_cpv := M.setState_pT(P_c, if Trefin > Tcond + 0.2 then 0.5*(Trefin + Tcond) else Tcond + 0.5);
    cpv_mean := M.specificHeatCapacityCp(st_cpv);
    st_v5 := M.setState_pT(P_c, Tcond + 5.0);
    mu_v5 := M.dynamicViscosity(st_v5); k_v5 := M.thermalConductivity(st_v5);
    Pr_v5 := M.specificHeatCapacityCp(st_v5)*mu_v5/k_v5;
    st_l5 := M.setState_pT(P_c, Tcond - 5.0);
    mu_l5 := M.dynamicViscosity(st_l5); k_l5 := M.thermalConductivity(st_l5);
    Pr_l5 := M.specificHeatCapacityCp(st_l5)*mu_l5/k_l5;
    G_2ph := (mdot/n_circuits)/A_cross;
    alpha_2ph := HXCorr.h_cond_shah1979(0.5, G_2ph, D_i, mu_l, k_l, Pr_l, P_c/Pcrit);
    Re_deSH := G_2ph*D_i/mu_v5;
    alpha_deSH := HXCorr.gnielinski(Re_deSH, Pr_v5, k_v5, D_i);
    Re_SC := G_2ph*D_i/mu_l5;
    alpha_SC := HXCorr.gnielinski(Re_SC, Pr_l5, k_l5, D_i);
    T_air_avg := 0.5*(T_air_in + Tcond);
    mu_a := HXCorr.mu_air(T_air_avg);
    Pr_a := HXCorr.Pr_air(T_air_avg);
    G_air := m_dot_air/A_c;
    Re_Dc := G_air*Dc/mu_a;
    j_air := HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air := j_air*G_air*1006.0/Pr_a^(2.0/3.0);
    eta_fin := HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
    eta_overall := (A_tube_outer + A_fin_total*eta_fin)/A_o;
  end CondenserSSwall;

  model CondSSwall_test "FlowSource(과열증기) → 응축기SS+벽 → 개방 싱크"
    CondenserSSwall cond;
    HPWDhx.FlowSource src(p = 17e5, h = 665e3, m_flow_set = 0.0065);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end CondSSwall_test;

end CondMBe;
