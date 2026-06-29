within ;
package CycleMBe "방정식형 MB 사이클: EvaporatorSS + Comp_Winandy + CondenserSS + EEV → 폐루프 (정상상태 대수해)"
  import Modelica.Constants.pi;

  function propsEvap "P_e[Pa] -> 포화·과열 스칼라 물성 (R290Tab 테이블 미디어)"
    input Real p "[Pa]";
    output Real Tevap, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, mu_v, mu_sh, k_sh, cp_sh, Pcrit;
  protected
    Real h_sh;
  algorithm
    Tevap := R290Tab.Tsat(p);
    h_l := R290Tab.hl(p); h_v := R290Tab.hv(p);
    rho_l := R290Tab.rhol(p); rho_v := R290Tab.rhov(p);
    mu_l := R290Tab.mul(p); k_l := R290Tab.kl(p);
    Pr_l := R290Tab.cpl(p)*mu_l/k_l;
    mu_v := R290Tab.muv(p);
    h_sh := h_v + R290Tab.cpv(p)*5.0;
    mu_sh := R290Tab.mu_ph(p, h_sh);
    k_sh := R290Tab.k_ph(p, h_sh);
    cp_sh := R290Tab.cp_ph(p, h_sh);
    Pcrit := 42.512e5;
  end propsEvap;

  model EvaporatorSS "정상상태 방정식형 증발기 (2-zone: 2상+과열, RefPort TwoPort, 건조 sensible 공기)"
    HPWD.RefPort port_a "입구 (2상, EEV로부터)";
    HPWD.RefPort port_b "출구 (과열증기)";
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10.0, N_tubes = 24.0;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2.0, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12.0, k_fin = 200.0, A_o_face = 0.05;
    parameter Real dP_ref = 0.03;
    parameter Real T_air_in_C = 45.0, RH_in = 0.85, V_air_CMM = 2.54;
    parameter Real M_mol = 44.096 "propane molar mass [g/mol]";
    parameter Real zeta_2ph_nom = 0.7 "Chen q_flux용 공칭 2상 분율 (커플링 차단)";
    // ── 파생 (형상/공기) ──
    final parameter Real P_fin = 0.0254/FPI;
    final parameter Real A_tube_outer = pi*D_o*L_tube_total;
    final parameter Real n_fins_per_tube = L_tube_total/N_tubes/P_fin;
    final parameter Real A_per_fin = 2.0*(P_t*P_l - pi*D_o^2/4.0);
    final parameter Real A_fin_total = N_tubes*n_fins_per_tube*A_per_fin;
    final parameter Real A_o = A_tube_outer + A_fin_total;
    final parameter Real A_i = pi*D_i*L_tube_total;
    final parameter Real A_cross = pi*D_i^2/4.0;
    final parameter Real Dc = D_o + 2.0*t_fin;
    final parameter Real gap = P_fin - t_fin;
    final parameter Real sig_c = max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    final parameter Real A_c = sig_c*A_o_face;
    final parameter Real T_air_in = T_air_in_C + 273.15;
    final parameter Real W_in = HXCorr.W_humid(T_air_in_C, RH_in, 101325.0);
    final parameter Real m_dot_air = HXCorr.rho_humid_air(T_air_in_C, W_in, 101325.0)*(V_air_CMM/60.0);
    final parameter Real C_air = m_dot_air*HXCorr.cp_ha_moist(W_in);
    // ── 미지수 ──
    Real zeta_2ph(start = 0.7), zeta_SH;
    Real Q2ph, QSH, Q_total;
    Real Ta_SH, Ta_out;
    Real h_suc(start = 600e3), SH_out, T_ref_out_C, T_evap_C, x_in;
    Real mdot, P_e, h_in;
    Real UA_ref_2ph, UA_ref_SH, UA_ser_2ph, UA_ser_SH;
    Real Cmin_SH, Cr_SH, eps_SH, eps_2ph, NTU_2, NTU_sh;
    Real alpha_2ph, alpha_SH, alpha_air, eta_fin, eta_overall;
    Real q_flux_2ph;
    // ── 물성 (스칼라, propsEvap서) ──
    Real h_l, h_v, Tevap, rho_l, rho_v, mu_l, k_l, Pr_l, mu_v, mu_sh, k_sh, cp_sh, Pcrit;
    Real G_2ph, T_air_avg, mu_a, Pr_a, G_air, Re_Dc, j_air, x_avg;
  equation
    // ── 포트 (정상상태) ──
    P_e = port_a.p;
    port_b.p = P_e*(1.0 - dP_ref);
    h_in = inStream(port_a.h_outflow);
    mdot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_suc;
    port_a.h_outflow = h_l;
    zeta_SH = 1.0 - zeta_2ph;
    // ── 물성 (record 격리 함수) ──
    (Tevap, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, mu_v, mu_sh, k_sh, cp_sh, Pcrit) = propsEvap(P_e);
    // ── 냉매측 HTC ──
    G_2ph = (mdot/n_circuits)/A_cross;
    x_avg = 0.5*(max(0.05, (h_in - h_l)/(h_v - h_l)) + 1.0);
    q_flux_2ph = mdot*(h_v - h_in)/(A_i*zeta_2ph_nom);
    alpha_2ph = HXCorr.h_evap_chen1966(x_avg, G_2ph, D_i, q_flux_2ph, mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_e/Pcrit, M_mol);
    alpha_SH = HXCorr.dittus_boelter(mu_sh, k_sh, cp_sh, mdot/n_circuits, D_i, true);
    // ── 공기측 (Wang j-factor, dry sensible) ──
    T_air_avg = 0.5*(T_air_in + Tevap);
    mu_a = HXCorr.mu_air(T_air_avg);
    Pr_a = HXCorr.Pr_air(T_air_avg);
    G_air = m_dot_air/A_c;
    Re_Dc = G_air*Dc/mu_a;
    j_air = HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air = j_air*G_air*1006.0/Pr_a^(2.0/3.0);
    eta_fin = HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
    eta_overall = (A_tube_outer + A_fin_total*eta_fin)/A_o;
    // ── 냉매측 UA + 직렬 UA ──
    UA_ref_2ph = alpha_2ph*A_i*zeta_2ph;
    UA_ref_SH = alpha_SH*A_i*zeta_SH;
    UA_ser_2ph = (alpha_air*A_o*eta_overall*zeta_2ph)*UA_ref_2ph/(alpha_air*A_o*eta_overall*zeta_2ph + UA_ref_2ph + 1e-12);
    UA_ser_SH = (alpha_air*A_o*eta_overall*zeta_SH)*UA_ref_SH/(alpha_air*A_o*eta_overall*zeta_SH + UA_ref_SH + 1e-12);
    // ── 공기 누적 (counter: 공기입구=SH측 → 2상 → 공기출구) ──
    Cmin_SH = min(mdot*cp_sh, C_air);
    Cr_SH = Cmin_SH/max(mdot*cp_sh, C_air);
    NTU_sh = UA_ser_SH/max(Cmin_SH, 1e-9);
    eps_SH = (1.0 - exp(-NTU_sh*(1.0 - Cr_SH)))/(1.0 - Cr_SH*exp(-NTU_sh*(1.0 - Cr_SH)) + 1e-12);
    QSH = eps_SH*Cmin_SH*(T_air_in - Tevap);
    Ta_SH = T_air_in - QSH/C_air;
    NTU_2 = UA_ser_2ph/C_air;
    eps_2ph = 1.0 - exp(-NTU_2);
    Q2ph = eps_2ph*C_air*(Ta_SH - Tevap);
    Ta_out = Ta_SH - Q2ph/C_air;
    // ── demand 강제: 2상 zone이 입구 quality→x=1 → zeta_2ph 결정 ──
    Q2ph = mdot*(h_v - h_in);
    // ── SH: 잔여 zeta_SH가 과열 결정 ──
    h_suc = h_v + QSH/mdot;
    // ── 관측 ──
    Q_total = Q2ph + QSH;
    T_evap_C = Tevap - 273.15;
    SH_out = QSH/(mdot*cp_sh);
    T_ref_out_C = T_evap_C + SH_out;
    x_in = (h_in - h_l)/(h_v - h_l);
  end EvaporatorSS;

  model EvapSS_test "FlowSource(2상) → 증발기SS → 개방 싱크 (P_e=5.5bar, dry)"
    EvaporatorSS evap;
    HPWDhx.FlowSource src(p = 5.5e5, h = 287e3, m_flow_set = 0.005);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end EvapSS_test;

  model CycleFixedPc "MB 폐루프: Comp_Winandy->CondenserSS->EEV_L1->EvaporatorSS. P_c 고정 closure (조립·solvability 증명)"
    HPWD.Comp_Winandy comp(N = 3000.0);
    CondMBe.CondenserSS cond(P_c(start = 15e5));
    HPWD.EEV_L1 eev;
    EvaporatorSS evap(P_e(start = 5.5e5));
    parameter Real opening_pct = 50.0 "EEV 개도 [%]";
  equation
    connect(comp.port_b, cond.port_a);   // 토출 -> 응축기
    connect(cond.port_b, eev.port_a);    // 응축기 -> EEV
    connect(eev.port_b, evap.port_a);    // EEV -> 증발기
    connect(evap.port_b, comp.port_a);   // 증발기 -> 흡입 (폐루프)
    eev.opening = opening_pct;
  end CycleFixedPc;

  model CycleDyn "MB 사이클: Comp_Winandy + CondenserSS + EEV_L1 + 동적 증발기(P_e 상태로 압력레벨 핀). 시간적분 -> 정상상태"
    HPWD.Comp_Winandy comp(N = 3000.0);
    CondMBe.CondenserSS cond(P_c(start = 15e5));
    HPWD.EEV_L1 eev;
    EvapMBe.EvaporatorMBdyn evap(is_wet = false);
    parameter Real opening_pct = 12.0 "EEV 개도 [%]";
  equation
    connect(comp.port_b, cond.port_a);
    connect(cond.port_b, eev.port_a);
    connect(eev.port_b, evap.port_a);
    connect(evap.port_b, comp.port_a);
    eev.opening = opening_pct;
  end CycleDyn;

  model CycleDynL2 "순수 L2 MB 사이클: Comp_Winandy + CondenserSS + EEV_MB(L2 SEMI) + EvaporatorMBdyn. 전 컴포넌트 SEMI."
    HPWD.Comp_Winandy comp(N = 3000.0);
    CondMBe.CondenserSS cond(P_c(start = 15e5));
    EevMB.EEV_MB eev;
    EvapMBe.EvaporatorMBdyn evap(is_wet = false);
    Modelica.Blocks.Sources.Constant openSig(k = opening_pct);
    parameter Real opening_pct = 12.0 "EEV 개도 [%]";
    Real Pc_bar, Pe_bar, SH, mdot, opening;
  equation
    connect(comp.port_b, cond.port_a);
    connect(cond.port_b, eev.port_a);
    connect(eev.port_b, evap.port_a);
    connect(evap.port_b, comp.port_a);
    connect(openSig.y, eev.opening);
    Pc_bar = cond.P_c/1e5;
    Pe_bar = evap.P_e/1e5;
    SH = evap.SH_out;
    mdot = comp.m_dot;
    opening = openSig.y;
  end CycleDynL2;

  model CycleDynL2_PI "L2 MB 사이클 + EEV PI(SH 제어) — L1/L3와 동일 HPWDctrl.PI_Controller 공유. 고정SH 비교용."
    parameter Real SH_target = 6.0 "목표 과열도 [K]";
    parameter Real N = 3000.0 "압축기 회전수 [rpm]";
    HPWD.Comp_Winandy comp(N = N);
    CondMBe.CondenserSS cond(P_c(start = 15e5));
    EevMB.EEV_MB eev;
    EvapMBe.EvaporatorMBdyn evap(is_wet = false);
    HPWDctrl.PI_Controller ctrl(
      SH_target = SH_target, Kp = 0.5, Ki = 0.05,
      opening_init = 12.0, opening_min = 5.0, opening_max = 100.0, I(fixed = true));
    Real Pc_bar, Pe_bar, SH, mdot, opening;
  equation
    connect(comp.port_b, cond.port_a);
    connect(cond.port_b, eev.port_a);
    connect(eev.port_b, evap.port_a);
    connect(evap.port_b, comp.port_a);
    ctrl.SH_meas = evap.SH_out;          // SH 측정 → PI
    connect(ctrl.opening, eev.opening);  // PI 출력 → EEV 개도
    Pc_bar = cond.P_c/1e5;
    Pe_bar = evap.P_e/1e5;
    SH = evap.SH_out;
    mdot = comp.m_dot;
    opening = ctrl.opening;
  end CycleDynL2_PI;

  model CycleDynWet "습윤코일(제습) 사이클 — HPWD 건조모드. CycleDyn + evap 습표면"
    extends CycleDyn(evap(is_wet = true));
  end CycleDynWet;

  model CycleSH "전SS 정상상태 사이클: 과열제어 closure (개도 free, SH=SH_set). 절대제약으로 압력레벨 핀"
    HPWD.Comp_Winandy comp(N = 3000.0);
    CondMBe.CondenserSS cond(P_c(start = 16e5));
    HPWD.EEV_L1 eev;
    EvaporatorSS evap(P_e(start = 5.5e5));
    parameter Real SH_set = 20.0 "목표 과열 [K]";
  equation
    connect(comp.port_b, cond.port_a);
    connect(cond.port_b, eev.port_a);
    connect(eev.port_b, evap.port_a);
    connect(evap.port_b, comp.port_a);
    evap.SH_out = SH_set;   // closure: 과열 고정 (개도가 자유롭게 풀려 레벨 핀)
  end CycleSH;
end CycleMBe;
