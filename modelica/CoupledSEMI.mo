within ;
package CplSEMI "전체 SEMI 커플 시스템 — MB HX 공기커플 변형(CondenserSS_cpl/EvaporatorMBdyn_cpl) + 통합모델(Cycle_SEMI_full)"

model CondenserSS_cpl
  "정상상태 응축기 + AirPort 공기측 커플 (폐루프용). 냉매측 CondenserSS 동일, 공기입구를 포트서 수신."
  HPWD.RefPort port_a "입구 (과열증기)";
  HPWD.RefPort port_b "출구 (과냉액)";
  HPWDair.AirPort air_a "공기 입구";
  HPWDair.AirPort air_b "공기 출구";
  parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
  parameter Integer N_rows = 2;
  parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
  parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
  parameter Real dP_ref = 0.03;
  parameter Real K_air = 300 "공기측 핀 저항 (Pa·s²/m²)";
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
  // ── 공기입구 (포트서 수신 — 변수) ──
  Real T_air_in, W_in, m_dot_air, C_air;
    Real zeta_d(start = 0.15), zeta_2(start = 0.51), zeta_sc;
    Real Qd, Q2, Qsc, Q_total;
    Real Ta_2ph, Ta_deSH, Ta_out;
    Real h_out(start = 300e3), SC_out, T_ref_out_C, T_cond_C, T_ref_in_C, quality_out;
    Real mdot, P_c, h_in;
    Real UA_ref_deSH, UA_ref_2ph, UA_ref_SC, UA_ser_deSH, UA_ser_2ph, UA_ser_SC;
    Real Cmin_deSH, Cr_deSH, eps_deSH, Cmin_SC, Cr_SC, eps_SC, eps_2ph, NTU_d, NTU_2, NTU_s;
    Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin, eta_overall;
  // ── 공기측 I/O ──
  Real h_in_air, h_out_air, W_out;
  Modelica.Units.SI.Density rho_da;
  Modelica.Units.SI.Velocity u;
  Modelica.Units.SI.Pressure dp_air;
  protected
        Real h_l, h_v, Tcond, rho_l, rho_v, Trefin;
    Real mu_l, k_l, Pr_l, Pcrit, cpl_sat, cpv_mean, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5;
    Real G_2ph, Re_deSH, Re_SC, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air;
equation
  // ── 공기 입구 (포트 수신) ──
  m_dot_air = air_a.m_flow_da;
  air_a.m_flow_da + air_b.m_flow_da = 0;
  W_in = inStream(air_a.W_outflow);
  h_in_air = inStream(air_a.h_tilde_outflow);
  T_air_in = HPWDair.MoistAir.T_from_h(h_in_air, W_in);
  C_air = m_dot_air*HXCorr.cp_ha_moist(W_in);
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
    alpha_2ph = HXCorr.h_cond_shah1979(0.5, G_2ph, D_i, mu_l, k_l, Pr_l, P_c/Pcrit);
    Re_deSH = G_2ph*D_i/mu_v5;
    alpha_deSH = HXCorr.gnielinski(Re_deSH, Pr_v5, k_v5, D_i);
    Re_SC = G_2ph*D_i/mu_l5;
    alpha_SC = HXCorr.gnielinski(Re_SC, Pr_l5, k_l5, D_i);
    T_air_avg = 0.5*(T_air_in + Tcond);
    mu_a = HXCorr.mu_air(T_air_avg);
    Pr_a = HXCorr.Pr_air(T_air_avg);
    G_air = m_dot_air/A_c;
    Re_Dc = G_air*Dc/mu_a;
    j_air = HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air = j_air*G_air*1006.0/Pr_a^(2.0/3.0);
    eta_fin = HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
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
  // ── 공기 출구 (dry: W 불변, 에너지보존) + ΔP ──
  W_out = W_in;
  h_out_air = h_in_air + Q_total/max(m_dot_air, 1e-6);
  rho_da = HPWDair.MoistAir.rho_da_fn(T_air_in, W_in);
  u = m_dot_air/(rho_da*A_o_face);
  dp_air = K_air*u*abs(u);
  air_b.p = air_a.p - dp_air;
  air_a.W_outflow = W_out;
  air_b.W_outflow = W_out;
  air_a.h_tilde_outflow = h_out_air;
  air_b.h_tilde_outflow = h_out_air;
end CondenserSS_cpl;

model EvaporatorMBdyn_cpl
  "동적 MB 증발기 + AirPort 공기측 커플 (제습). 냉매측·벽·algorithm EvaporatorMBdyn 동일, 공기입구 포트 수신."
  HPWD.RefPort port_a "입구 (2상, EEV측)";
  HPWD.RefPort port_b "출구 (과열, 압축기측)";
  HPWDair.AirPort air_a "공기 입구";
  HPWDair.AirPort air_b "공기 출구";
  parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
  parameter Integer N_rows = 2;
  parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
  parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
  parameter Boolean is_wet = true "습표면(제습) 여부";
  parameter Real C_w1 = 300.0, C_w2 = 150.0 "벽 열용량 [J/K]";
  parameter Real dP = 50.0, dh = 200.0 "FD 섭동";
  parameter Real K_air = 300 "공기측 핀 저항 (Pa·s²/m²)";
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
  // ── 공기입구 (포트서 수신 — 변수) ──
  Real T_air_in, W_in, h_air_in, m_dot_air, C_air;
    Real zeta(start = 0.8, fixed = true) "2상 zone 분율";
    Modelica.Units.SI.AbsolutePressure P_e(start = 5.5e5, fixed = true);
    Real h_out(start = 600e3, fixed = true);
    Modelica.Units.SI.Temperature T_w1(start = 295.0, fixed = true);
    Modelica.Units.SI.Temperature T_w2(start = 300.0, fixed = true);
    // ── 관측/대수 ──
    Real mdot_in, mdot_out, h_in, mdot_b, x_in, SH_out, Q_total, Q1, Q2, T_sat_C;
    Real Q1_air, Q2_air, T_air_mid, T_air_out;
    Real h_air_mid, h_air_out, UA_air_2ph, BF, h_app, W_sat_surf, W_air_out, condensate, Q_latent, T_surf_C;
    Real UA_ref_2ph, UA_ref_SH, UA_ser_2ph, UA_ser_SH, Cmin_SH, Cr_SH, NTU_SH, eps_SH;
    Real alpha_2ph, alpha_SH, alpha_air, eta_fin, eta_overall;
  // ── 공기측 I/O (포트) ──
  Real h_out_air_tilde;
  Modelica.Units.SI.Density rho_da;
  Modelica.Units.SI.Velocity u;
  Modelica.Units.SI.Pressure dp_air;
  protected
        Real P_ec "물성조회용 clamp 압력";
    Real h_l, h_v, Tsat, rho_l, rho_v, gamma, rho1, hbar1, rho2, hbar2, Tref2;
    Real h_lP, h_vP, rho_lP, rho_vP, gammaP, rho1P, rho2P, hbar2P, hbar2h, rho2h;
    Real dhv_dP, drho1_dP, drho2_dP, drho2_dh, ru1, ru2, CE1P, CE2P, CE2h, xm, xmP;
    Real mu_l, mu_v, k_l, cp_l, Pr_l, mu10, k10, cp10, cp_vs, Pcrit, Mmol;
    Real x_avg_2ph, q_flux, G_2ph, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air;
equation
  // ── 공기 입구 (포트 수신; 내부는 HXCorr h_moist 규약) ──
  m_dot_air = air_a.m_flow_da;
  air_a.m_flow_da + air_b.m_flow_da = 0;
  W_in = inStream(air_a.W_outflow);
  T_air_in = HPWDair.MoistAir.T_from_h(inStream(air_a.h_tilde_outflow), W_in);
  h_air_in = HXCorr.h_moist(T_air_in - 273.15, W_in);
  C_air = m_dot_air*HXCorr.cp_ha_moist(W_in);
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
    h_air_mid = h_air_in - Q2_air/m_dot_air;
    UA_air_2ph = alpha_air*A_o*eta_overall*zeta;
    if is_wet then
      T_surf_C = T_w1 - 273.15;
      h_app = HXCorr.h_air_sat(T_surf_C, 101325.0);
      Q1_air = m_dot_air*(1.0 - exp(-UA_air_2ph/C_air))*(h_air_mid - h_app);
      h_air_out = h_air_mid - Q1_air/m_dot_air;
      BF = max(0.0, min(1.0, (h_air_out - h_app)/max(h_air_mid - h_app, 1e-6)));
      W_sat_surf = HXCorr.W_sat(T_surf_C, 101325.0);
      W_air_out = min(W_in, max(W_sat_surf, BF*W_in + (1.0 - BF)*W_sat_surf));
      condensate = m_dot_air*(W_in - W_air_out);
      Q_latent = max(0.0, condensate*(2501e3 - 2.4*T_surf_C));
    else
      T_surf_C = T_w1 - 273.15;
      h_app = 0.0;
      Q1_air = (1.0 - exp(-UA_ser_2ph/C_air))*C_air*(T_air_mid - Tsat);
      h_air_out = h_air_mid - Q1_air/m_dot_air;
      BF = 1.0;
      W_sat_surf = W_in;
      W_air_out = W_in;
      condensate = 0.0;
      Q_latent = 0.0;
    end if;
    T_air_out = HXCorr.T_moist_from_h(h_air_out, W_air_out) + 273.15;
    // ── 벽: 공기측 직렬열 수신 − 냉매측 배출. 정상서 Q=Q_air=알고리즘 직렬열 → ζ 일치
    C_w1*der(T_w1) = Q1_air - Q1;
    C_w2*der(T_w2) = Q2_air - Q2;
    Q1 = UA_ref_2ph*(T_w1 - Tsat);
    Q2 = UA_ref_SH*(T_w2 - Tref2);
    // ── 관측
    Q_total = Q1 + Q2;
    SH_out = R290Tab.T_ph(P_ec, h_out) - Tsat;
    T_sat_C = Tsat - 273.15;
    x_in = (h_in - h_l)/(h_v - h_l);
  // ── 공기 출구 (제습 후 T/W → MoistAir h_tilde 변환) + ΔP ──
  h_out_air_tilde = HPWDair.MoistAir.h_da_fn(T_air_out, W_air_out);
  rho_da = HPWDair.MoistAir.rho_da_fn(T_air_in, W_in);
  u = m_dot_air/(rho_da*A_o_face);
  dp_air = K_air*u*abs(u);
  air_b.p = air_a.p - dp_air;
  air_a.W_outflow = W_air_out;
  air_b.W_outflow = W_air_out;
  air_a.h_tilde_outflow = h_out_air_tilde;
  air_b.h_tilde_outflow = h_out_air_tilde;
  algorithm
    P_ec := max(1.5e5, min(P_e, 35e5));
    // ── 포화 + 열역학 (FD 계수용; v1과 동일) ──
    Tsat := R290Tab.Tsat(P_ec);
    h_l := R290Tab.hl(P_ec);
    h_v := R290Tab.hv(P_ec);
    rho_l := R290Tab.rhol(P_ec);
    rho_v := R290Tab.rhov(P_ec);
    xm := 0.5*((h_in - h_l)/(h_v - h_l) + 1.0);
    gamma := 1.0/(1.0 + (1.0 - xm)/xm*rho_v/rho_l);
    rho1 := rho_l*(1.0 - gamma) + rho_v*gamma;
    hbar1 := 0.5*(h_in + h_v);
    hbar2 := 0.5*(h_v + h_out);
    rho2 := R290Tab.rho_ph(P_ec, hbar2);
    Tref2 := R290Tab.T_ph(P_ec, hbar2);
    h_lP := R290Tab.hl(P_ec + dP);
    h_vP := R290Tab.hv(P_ec + dP);
    rho_lP := R290Tab.rhol(P_ec + dP);
    rho_vP := R290Tab.rhov(P_ec + dP);
    xmP := 0.5*((h_in - h_lP)/(h_vP - h_lP) + 1.0);
    gammaP := 1.0/(1.0 + (1.0 - xmP)/xmP*rho_vP/rho_lP);
    rho1P := rho_lP*(1.0 - gammaP) + rho_vP*gammaP;
    hbar2P := 0.5*(h_vP + h_out);
    rho2P := R290Tab.rho_ph(P_ec + dP, hbar2P);
    hbar2h := 0.5*(h_v + (h_out + dh));
    rho2h := R290Tab.rho_ph(P_ec, hbar2h);
    dhv_dP := (h_vP - h_v)/dP;
    drho1_dP := (rho1P - rho1)/dP;
    drho2_dP := (rho2P - rho2)/dP;
    drho2_dh := (rho2h - rho2)/dh;
    ru1 := rho1*hbar1 - P_ec;
    ru2 := rho2*hbar2 - P_ec;
    CE1P := drho1_dP*hbar1 + rho1*(dhv_dP/2.0) - 1.0;
    CE2P := drho2_dP*hbar2 + rho2*(dhv_dP/2.0) - 1.0;
    CE2h := drho2_dh*hbar2 + rho2*0.5;
    // ── 전달물성 (알고리즘 EvapMB 레시피: 포화 ρ·μ, cp/k는 ±0.1K off-sat) ──
    mu_l := R290Tab.mul(P_ec);
    mu_v := R290Tab.muv(P_ec);
    k_l := R290Tab.kl(P_ec);
    cp_l := R290Tab.cpl(P_ec);
    Pr_l := cp_l*mu_l/k_l;
    mu10 := R290Tab.mu_ph(P_ec, h_v + R290Tab.cpv(P_ec)*10.0);
    k10 := R290Tab.k_ph(P_ec, h_v + R290Tab.cpv(P_ec)*10.0);
    cp10 := R290Tab.cp_ph(P_ec, h_v + R290Tab.cpv(P_ec)*10.0);
    cp_vs := R290Tab.cpv(P_ec);
    Pcrit := 42.512e5;
    Mmol := 44.096;
    // ── 냉매측 α ──
    x_avg_2ph := 0.5*((h_in - h_l)/(h_v - h_l) + 1.0);
    q_flux := mdot_in*(h_v - h_in)/A_i;
    G_2ph := (mdot_in/n_circuits)/A_cross;
    alpha_2ph := HXCorr.h_evap_chen1966(x_avg_2ph, G_2ph, D_i, q_flux, mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_ec/Pcrit, Mmol);
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

  end EvaporatorMBdyn_cpl;

model Cycle_SEMI_full
  "전체 SEMI 시스템: Comp_Winandy + CondenserSS_cpl + EEV_MB + EvaporatorMBdyn_cpl + Fan_L2 + Drum_L2 + 폐공기루프. 냉매·공기 전 컴포넌트 SEMI."
  HPWD.Comp_Winandy comp(N = 3000.0);
  CondenserSS_cpl cond(P_c(start = 15e5), K_air = 300);
  EevMB.EEV_MB eev "개도는 equation서 opening_pct 신호로 지정";
  EvaporatorMBdyn_cpl evap(is_wet = true, K_air = 300);
  parameter Real opening_pct = 12.0 "EEV 개도 [%]";
  // ── 공기 폐루프 (L2) ──
  HPWDair.Drum_L2 drum(
    m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
    A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 305.0,
    UA_amb = 100.0, T_amb = 298.15);
  HPWDair.Fan_L2 fan(
    D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
    eta_mech = 0.95, N = 3000);
  HPWDair.AirVolumeC volRef(
    V = 0.05, p_start = HPWDair.MoistAir.p_ref,
    T_start = 304.0, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volB(V = 0.05, T_start = 305.0, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volC(V = 0.05, T_start = 291.0, W_start = 0.012, fixedState = true);
  HPWDair.AirVolume volD(V = 0.05, T_start = 333.0, W_start = 0.012, fixedState = true);
equation
    eev.opening = opening_pct "RealInput 신호에 상수 개도 부여";
  // ── 냉매 루프 (직접연결, CycleDynL2 동일) ──
  connect(comp.port_b, cond.port_a);
  connect(cond.port_b, eev.port_a);
  connect(eev.port_b, evap.port_a);
  connect(evap.port_b, comp.port_a);
  // ── 공기 폐루프: drum→volRef→fan→volB→evap→volC→cond→volD→drum ──
  connect(drum.port_b,   volRef.port_a);
  connect(volRef.port_b, fan.port_a);
  connect(fan.port_b,    volB.port_a);
  connect(volB.port_b,   evap.air_a);
  connect(evap.air_b,    volC.port_a);
  connect(volC.port_b,   cond.air_a);
  connect(cond.air_b,    volD.port_a);
  connect(volD.port_b,   drum.port_a);
end Cycle_SEMI_full;

model Cycle_SEMI_open
  "L2 SEMI — 냉매루프 비교용 오픈 공기루프 (드럼/팬 제외).
   공기: 고정소스(20°C/RH80%, 2.42CMM) → 증발기 → 응축기 → 배출.
   압축기 N=1800 / V_disp=7.5cc 로 L1·L3와 스펙 통일."
  HPWD.Comp_Winandy comp(N = 1800.0);
  CondenserSS_cpl cond(P_c(start = 15e5), K_air = 300);
  EevMB.EEV_MB eev "개도는 equation서 opening_pct 신호로 지정";
  EvaporatorMBdyn_cpl evap(is_wet = true, K_air = 300);
  parameter Real opening_pct = 12.0 "EEV 개도 [%]";
  // ── 공기 오픈루프 경계 (L3와 동일 BC) ──
  parameter Modelica.Units.SI.MassFlowRate m_air_da = 0.047786
    "건공기 질량유량 [kg/s] = 2.42 CMM (L1·L3 통일)";
  parameter Modelica.Units.SI.Temperature T_air_in = 293.15 "증발기 입구 20°C";
  parameter Real W_air_in = 0.011674 "증발기 입구 절대습도 (20°C, RH80%)";
  HPWDair.BoundaryAir_mflow src(m_flow_da = -m_air_da, T = T_air_in, W = W_air_in);
  HPWDair.BoundaryAir_pTW snk(p = HPWDair.MoistAir.p_ref, T = T_air_in, W = W_air_in);
  HPWDair.AirVolume volC(V = 0.05, T_start = 288.0, W_start = 0.0100, fixedState = true);
equation
  eev.opening = opening_pct "RealInput 신호에 상수 개도 부여";
  // ── 냉매 루프 (Cycle_SEMI_full과 동일) ──
  connect(comp.port_b, cond.port_a);
  connect(cond.port_b, eev.port_a);
  connect(eev.port_b, evap.port_a);
  connect(evap.port_b, comp.port_a);
  // ── 공기 오픈루프: src → evap → volC → cond → snk ──
  connect(src.port,    evap.air_a);
  connect(evap.air_b,  volC.port_a);
  connect(volC.port_b, cond.air_a);
  connect(cond.air_b,  snk.port);
end Cycle_SEMI_open;

end CplSEMI;
