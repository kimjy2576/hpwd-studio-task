within ;
package CondMB
  "응축기 Moving-Boundary (model-docs SEMI) 조립. condenser_moving_boundary.py step() 충실 포팅.
   3-zone(deSH/2상/SC) cascade. 응축 Shah1979, 단상 Gnielinski(HXCorr), 공기 Wang j + Schmidt.
   공기측 dry(제습 없음), ΔP는 고정율(dP_ref). 냉매물성은 model이 HelmholtzMedia로 전달."

  // ════════════ ε-NTU (condenser_moving_boundary.py와 동일) ════════════
  function eps_NTU_C0
    input Real NTU;
    output Real eps;
  algorithm
    eps := if NTU <= 0 then 0.0 elseif NTU > 50 then 1.0 else 1.0 - exp(-NTU);
  end eps_NTU_C0;

  function eps_NTU_counter
    input Real NTU, Cr;
    output Real eps;
  protected
    Real arg, e;
  algorithm
    if NTU <= 0 then
      eps := 0.0;
    elseif Cr <= 1e-6 then
      eps := eps_NTU_C0(NTU);
    elseif Cr >= 1.0 - 1e-6 then
      eps := NTU/(1.0 + NTU);
    else
      arg := -NTU*(1.0 - Cr);
      if arg < -50 then
        eps := if Cr < 1 then 1.0/Cr else 1.0;
      else
        e := exp(arg);
        eps := (1.0 - e)/(1.0 - Cr*e);
      end if;
    end if;
  end eps_NTU_counter;

  function eps_NTU_parallel
    input Real NTU, Cr;
    output Real eps;
  protected
    Real denom, arg;
  algorithm
    if NTU <= 0 then
      eps := 0.0;
    elseif Cr <= 1e-6 then
      eps := eps_NTU_C0(NTU);
    else
      denom := 1.0 + Cr;
      arg := -NTU*denom;
      eps := if arg < -50 then 1.0/denom else (1.0 - exp(arg))/denom;
    end if;
  end eps_NTU_parallel;

  function eps_NTU
    input Real NTU, Cr;
    input Boolean counter = true;
    output Real eps;
  algorithm
    eps := if counter then eps_NTU_counter(NTU, Cr) else eps_NTU_parallel(NTU, Cr);
  end eps_NTU;

  // ════════════ zone별 Q (z=zone 길이비, T_air=zone 공기 입구) ════════════
  function qDeSH
    input Real z, T_air, UA_deSH_full, C_ref_v, C_air, T_ref_in_C;
    input Boolean counter;
    output Real Q;
  protected
    Real Cmin, Cmax, Cr, NTU;
  algorithm
    if z <= 1e-9 then
      Q := 0.0;
    else
      Cmin := min(C_ref_v, C_air);
      Cmax := max(C_ref_v, C_air);
      Cr := if Cmax > 0 then Cmin/Cmax else 0.0;
      NTU := if Cmin > 0 then UA_deSH_full*z/Cmin else 0.0;
      Q := eps_NTU(NTU, Cr, counter)*Cmin*(T_ref_in_C - T_air);
    end if;
  end qDeSH;

  function q2ph
    input Real z, T_air, UA_2ph_full, C_air, T_cond_C;
    output Real Q;
  protected
    Real NTU;
  algorithm
    if z <= 1e-9 then
      Q := 0.0;
    else
      NTU := if C_air > 0 then UA_2ph_full*z/C_air else 0.0;
      Q := eps_NTU_C0(NTU)*C_air*(T_cond_C - T_air);
    end if;
  end q2ph;

  function qSC
    input Real z, T_air, UA_SC_full, C_ref_l, C_air, T_cond_C;
    input Boolean counter;
    output Real Q;
  protected
    Real Cmin, Cmax, Cr, NTU;
  algorithm
    if z <= 1e-9 then
      Q := 0.0;
    else
      Cmin := min(C_ref_l, C_air);
      Cmax := max(C_ref_l, C_air);
      Cr := if Cmax > 0 then Cmin/Cmax else 0.0;
      NTU := if Cmin > 0 then UA_SC_full*z/Cmin else 0.0;
      Q := eps_NTU(NTU, Cr, counter)*Cmin*(T_cond_C - T_air);
    end if;
  end qSC;

  // ════════════════════ 메인: 응축기 MB ════════════════════
  function condenserMB
    "응축기 Moving-Boundary 1 step. T_ref_out·SC_out·M_deSH·M_SC는 model이 파생."
    input Real D_o, D_i, L_tube_total, N_tubes;
    input Integer N_rows;
    input Real n_circuits, P_t, P_l, t_fin, FPI, k_fin, A_o_face;
    input Real htc_corr_cond = 1.0, htc_corr_SP = 1.0, htc_corr_air = 1.0;
    input Real dP_ref = 0.03;
    input Boolean flow_counter = true;
    input Real P_cond_bar, h_in_kjkg, m_dot_ref, T_air_in_C, RH_air_in_pct, V_air_CMM;
    // 냉매물성 (model이 HelmholtzMedia로 계산해 전달)
    input Real T_cond_K, h_l_J, h_v_J, T_ref_in_K;
    input Real rho_l, rho_v, mu_l, k_l, Pr_l, sigma, P_crit;
    input Real cp_v_mean "C_ref_v용 (deSH 평균온도)";
    input Real cp_l_sat "C_ref_l용 (포화액)";
    input Real mu_v5, k_v5, Pr_v5 "deSH Gnielinski @ T_cond+5";
    input Real mu_l5, k_l5, Pr_l5 "SC Gnielinski @ T_cond-5";
    output Real Q_total, Q_deSH, Q_2ph, Q_SC;
    output Real h_ref_out_J, P_ref_out_bar, quality_out;
    output Real zeta_deSH, zeta_2ph, zeta_SC;
    output Real T_air_out_C, RH_out_pct;
    output Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin;
    output Real M_2ph;
  protected
    Real P_cond_Pa, h_in_J, P_fin, h_fg, T_cond_C, T_ref_in_C;
    Real W_in, cp_air, C_air, C_air_safe, m_dot_air;
    Real A_tube_outer, n_fins_per_tube, A_per_fin, A_fin_total, A_o, A_i;
    Real T_air_avg_K, mu_a, Pr_a, cp_a, Dc, gap, sig_c, A_c, G_air, Re_Dc, j_air, eta_overall;
    Real A_cross, G_2ph, Re_deSH, Re_SC, P_r;
    Real UA_deSH_full, UA_2ph_full, UA_SC_full;
    Real C_ref_v, C_ref_l;
    Real Q_deSH_demand, Q_2ph_demand;
    Boolean has_deSH;
    Real Ta_deSH, Ta_2ph, Ta_SC, Qd, Q2, Qs;
    Real z2_new, zd_new, zs_new, zmax_d, lo, hi, mid;
    Real T_air_exit_C, h_out_J, x_out, P_ws_out, P_w_out, Tcl;
    Real V_internal, m_per_circuit, x_out_2ph, rho_sum, xv, av, rho_2ph;
    Integer Nint;
  algorithm
    P_cond_Pa := P_cond_bar*1e5;
    h_in_J := h_in_kjkg*1000.0;
    P_fin := 0.0254/FPI;
    h_fg := h_v_J - h_l_J;
    T_cond_C := T_cond_K - 273.15;
    T_ref_in_C := T_ref_in_K - 273.15;
    P_r := P_cond_Pa/P_crit;

    // 공기 입구 (dry — 제습 없음)
    W_in := HXCorr.W_humid(T_air_in_C, RH_air_in_pct/100.0, 101325.0);
    cp_air := HXCorr.cp_ha_moist(W_in);
    m_dot_air := HXCorr.rho_humid_air(T_air_in_C, W_in, 101325.0)*(V_air_CMM/60.0);
    C_air := m_dot_air*cp_air;
    C_air_safe := max(C_air, 1e-9);

    // 면적
    A_tube_outer := 3.141592653589793*D_o*L_tube_total;
    n_fins_per_tube := if P_fin > 0 then L_tube_total/N_tubes/P_fin else 0.0;
    A_per_fin := 2.0*(P_t*P_l - 3.141592653589793*D_o^2/4.0);
    A_fin_total := N_tubes*n_fins_per_tube*A_per_fin;
    A_o := A_tube_outer + A_fin_total;
    A_i := 3.141592653589793*D_i*L_tube_total;

    // 공기측 α (Wang j)
    T_air_avg_K := (T_air_in_C + 273.15 + T_cond_K)/2.0;
    mu_a := HXCorr.mu_air(T_air_avg_K);
    Pr_a := HXCorr.Pr_air(T_air_avg_K);
    cp_a := 1006.0;
    Dc := D_o + 2.0*t_fin;
    gap := P_fin - t_fin;
    sig_c := max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    A_c := sig_c*A_o_face;
    G_air := m_dot_air/max(A_c, 1e-9);
    Re_Dc := G_air*Dc/max(mu_a, 1e-9);
    j_air := HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air := j_air*G_air*cp_a/Pr_a^(2.0/3.0)*htc_corr_air;
    eta_fin := HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
    eta_overall := if A_o > 0 then (A_tube_outer + A_fin_total*eta_fin)/A_o else eta_fin;

    // 냉매측 α (2상 Shah, 단상 Gnielinski)
    A_cross := 3.141592653589793*D_i^2/4.0;
    G_2ph := (m_dot_ref/max(n_circuits, 1.0))/max(A_cross, 1e-12);
    alpha_2ph := HXCorr.h_cond_shah1979(0.5, G_2ph, D_i, mu_l, k_l, Pr_l, P_r)*htc_corr_cond;
    Re_deSH := G_2ph*D_i/max(mu_v5, 1e-9);
    alpha_deSH := HXCorr.gnielinski(Re_deSH, Pr_v5, k_v5, D_i)*htc_corr_SP;
    Re_SC := G_2ph*D_i/max(mu_l5, 1e-9);
    alpha_SC := HXCorr.gnielinski(Re_SC, Pr_l5, k_l5, D_i)*htc_corr_SP;

    // zone UA (cascade)
    UA_deSH_full := 1.0/(1.0/(alpha_deSH*A_i) + 1.0/(alpha_air*A_o*eta_overall));
    UA_2ph_full := 1.0/(1.0/(alpha_2ph*A_i) + 1.0/(alpha_air*A_o*eta_overall));
    UA_SC_full := 1.0/(1.0/(alpha_SC*A_i) + 1.0/(alpha_air*A_o*eta_overall));

    C_ref_v := m_dot_ref*cp_v_mean;
    C_ref_l := m_dot_ref*cp_l_sat;
    Q_deSH_demand := m_dot_ref*max(0.0, h_in_J - h_v_J);
    Q_2ph_demand := m_dot_ref*(h_v_J - h_l_J);
    has_deSH := (Q_deSH_demand > 1e-6) and (T_ref_in_C > T_cond_C);

    // 3-zone ζ 풀이 (40-iter, 각 zone bisection 60-iter)
    zeta_deSH := if has_deSH then 0.15 else 0.0;
    zeta_2ph := 0.6;
    zeta_SC := max(0.0, 1.0 - zeta_deSH - zeta_2ph);
    for it in 1:40 loop
      // zone 공기 입구온도 (flow 누적)
      if not flow_counter then
        Ta_deSH := T_air_in_C;
        Qd := if has_deSH then min(qDeSH(zeta_deSH, Ta_deSH, UA_deSH_full, C_ref_v, C_air, T_ref_in_C, flow_counter), Q_deSH_demand) else 0.0;
        Ta_2ph := Ta_deSH + Qd/C_air_safe;
        Q2 := min(q2ph(zeta_2ph, Ta_2ph, UA_2ph_full, C_air, T_cond_C), Q_2ph_demand);
        Ta_SC := Ta_2ph + Q2/C_air_safe;
      else
        Ta_SC := T_air_in_C;
        Qs := qSC(zeta_SC, Ta_SC, UA_SC_full, C_ref_l, C_air, T_cond_C, flow_counter);
        Qs := max(0.0, min(Qs, C_ref_l*(T_cond_C - Ta_SC)));
        Ta_2ph := Ta_SC + Qs/C_air_safe;
        Q2 := min(q2ph(zeta_2ph, Ta_2ph, UA_2ph_full, C_air, T_cond_C), Q_2ph_demand);
        Ta_deSH := Ta_2ph + Q2/C_air_safe;
      end if;
      // bisect zeta_2ph (z_max=1.0)
      if Q_2ph_demand <= 1e-9 then
        z2_new := 0.0;
      elseif q2ph(1.0, Ta_2ph, UA_2ph_full, C_air, T_cond_C) <= Q_2ph_demand then
        z2_new := 1.0;
      else
        lo := 0.0; hi := 1.0;
        for b in 1:60 loop
          mid := 0.5*(lo + hi);
          if q2ph(mid, Ta_2ph, UA_2ph_full, C_air, T_cond_C) < Q_2ph_demand then
            lo := mid;
          else
            hi := mid;
          end if;
          if hi - lo < 1e-6 then break; end if;
        end for;
        z2_new := 0.5*(lo + hi);
      end if;
      // bisect zeta_deSH (z_max=1-z2_new)
      zmax_d := max(0.0, 1.0 - z2_new);
      if (not has_deSH) or Q_deSH_demand <= 1e-9 or zmax_d <= 1e-9 then
        zd_new := 0.0;
      elseif qDeSH(zmax_d, Ta_deSH, UA_deSH_full, C_ref_v, C_air, T_ref_in_C, flow_counter) <= Q_deSH_demand then
        zd_new := zmax_d;
      else
        lo := 0.0; hi := zmax_d;
        for b in 1:60 loop
          mid := 0.5*(lo + hi);
          if qDeSH(mid, Ta_deSH, UA_deSH_full, C_ref_v, C_air, T_ref_in_C, flow_counter) < Q_deSH_demand then
            lo := mid;
          else
            hi := mid;
          end if;
          if hi - lo < 1e-6 then break; end if;
        end for;
        zd_new := 0.5*(lo + hi);
      end if;
      zs_new := max(0.0, 1.0 - zd_new - z2_new);
      if (abs(zd_new - zeta_deSH) + abs(z2_new - zeta_2ph) + abs(zs_new - zeta_SC)) < 1e-5 then
        zeta_deSH := zd_new; zeta_2ph := z2_new; zeta_SC := zs_new;
        break;
      end if;
      zeta_deSH := 0.5*zd_new + 0.5*zeta_deSH;
      zeta_2ph := 0.5*z2_new + 0.5*zeta_2ph;
      zeta_SC := max(0.0, 1.0 - zeta_deSH - zeta_2ph);
    end for;

    // 수렴 ζ로 최종 Q
    if not flow_counter then
      Ta_deSH := T_air_in_C;
      Qd := if has_deSH then min(qDeSH(zeta_deSH, Ta_deSH, UA_deSH_full, C_ref_v, C_air, T_ref_in_C, flow_counter), Q_deSH_demand) else 0.0;
      Ta_2ph := Ta_deSH + Qd/C_air_safe;
      Q2 := min(q2ph(zeta_2ph, Ta_2ph, UA_2ph_full, C_air, T_cond_C), Q_2ph_demand);
      Ta_SC := Ta_2ph + Q2/C_air_safe;
    else
      Ta_SC := T_air_in_C;
      Qs := qSC(zeta_SC, Ta_SC, UA_SC_full, C_ref_l, C_air, T_cond_C, flow_counter);
      Qs := max(0.0, min(Qs, C_ref_l*(T_cond_C - Ta_SC)));
      Ta_2ph := Ta_SC + Qs/C_air_safe;
      Q2 := min(q2ph(zeta_2ph, Ta_2ph, UA_2ph_full, C_air, T_cond_C), Q_2ph_demand);
      Ta_deSH := Ta_2ph + Q2/C_air_safe;
    end if;
    Q_SC := qSC(zeta_SC, Ta_SC, UA_SC_full, C_ref_l, C_air, T_cond_C, flow_counter);
    Q_SC := max(0.0, min(Q_SC, C_ref_l*(T_cond_C - Ta_SC)));
    Q_2ph := min(q2ph(zeta_2ph, Ta_2ph, UA_2ph_full, C_air, T_cond_C), Q_2ph_demand);
    Q_deSH := if has_deSH then min(qDeSH(zeta_deSH, Ta_deSH, UA_deSH_full, C_ref_v, C_air, T_ref_in_C, flow_counter), Q_deSH_demand) else 0.0;
    T_air_exit_C := if not flow_counter then Ta_SC + Q_SC/C_air_safe else Ta_deSH + Q_deSH/C_air_safe;

    Q_total := Q_deSH + Q_2ph + Q_SC;
    h_out_J := if m_dot_ref > 0 then h_in_J - Q_total/m_dot_ref else h_in_J;
    h_ref_out_J := h_out_J;
    if h_out_J >= h_v_J then
      quality_out := 1.0 + max(0.0, (h_out_J - h_v_J)/max(h_fg, 1.0));
    elseif h_out_J >= h_l_J then
      quality_out := max(0.0, min(1.0, (h_out_J - h_l_J)/h_fg));
    else
      quality_out := -max(0.0, (h_l_J - h_out_J)/max(h_fg, 1.0));
    end if;
    T_air_out_C := T_air_exit_C;

    // 공기 출구 RH (Antoine 물 포화압)
    Tcl := max(-50.0, min(200.0, T_air_out_C));
    P_ws_out := 133.322*10.0^(8.07131 - 1730.63/(Tcl + 233.426));
    P_w_out := W_in/(W_in + 0.622)*101325.0;
    RH_out_pct := if P_ws_out > 0 then max(0.0, min(100.0, P_w_out/P_ws_out*100.0)) else 0.0;

    P_ref_out_bar := P_cond_bar*(1.0 - dP_ref);

    // charge holdup 2상 (void Premoli 10점, 응축은 [x_out_2ph,1])
    V_internal := A_cross*L_tube_total;
    m_per_circuit := m_dot_ref/max(n_circuits, 1.0);
    x_out_2ph := max(0.0, min(1.0, quality_out));
    Nint := 10;
    rho_sum := 0.0;
    for i in 1:Nint loop
      xv := x_out_2ph + (1.0 - x_out_2ph)*(i - 0.5)/Nint;
      av := HXCorr.void_premoli(xv, rho_l, rho_v, mu_l, sigma, m_per_circuit, D_i);
      rho_sum := rho_sum + HXCorr.void_mean_density(av, rho_l, rho_v);
    end for;
    rho_2ph := rho_sum/Nint;
    M_2ph := rho_2ph*(zeta_2ph*V_internal);
  end condenserMB;

  // ════════════════════ Acausal TwoPort 모델 ════════════════════
  model CondenserMB "응축기 MB (L2 SEMI). RefPort TwoPort. 냉매물성 HelmholtzMedia."
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10, N_tubes = 24;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12, k_fin = 200, A_o_face = 0.05;
    parameter Real htc_corr_cond = 1, htc_corr_SP = 1, htc_corr_air = 1, dP_ref = 0.03;
    parameter Boolean flow_counter = true;
    parameter Modelica.Units.SI.Temperature T_air_in = 35 + 273.15;
    parameter Real RH_in = 0.50;
    parameter Real V_air_CMM = 25.42;
    Real Q_total, Q_deSH, Q_2ph, Q_SC "[W]";
    Real T_ref_out_C, SC_out, quality_out, T_cond_C;
    Real T_air_out_C, RH_air_out;
    Real zeta_deSH, zeta_2ph, zeta_SC;
    Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin;
    Real M_holdup "[kg]";
    Real m_dot, P_cond, h_in, h_ref_out;
  protected
    M.ThermodynamicState st_l, st_v, st_in, st_lq, st_v5, st_l5, st_out, st_deSHavg, st_SCavg, st_cpv;
    Real Tcond_K, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, sig, Pcrit;
    Real Trefin_K, cpv_mean, cpl_sat, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5;
    Real Tcpv_K;
    Real Qt_l, Qd_l, Q2_l, Qs_l, href_l, Pout_l, qual_l, zd_l, z2_l, zs_l, Taout_l, RHout_l;
    Real a2_l, adeSH_l, aSC_l, aair_l, etaf_l, M2_l;
    Real rho_deSH, rho_SC, M_deSH, M_SC, V_internal;
  equation
    m_dot = port_a.m_flow;
    P_cond = port_a.p;
    h_in = inStream(port_a.h_outflow);
    port_a.m_flow + port_b.m_flow = 0;
    port_b.p = P_cond*(1.0 - dP_ref);
    port_b.h_outflow = h_ref_out;
    port_a.h_outflow = inStream(port_b.h_outflow);
  algorithm
    Tcond_K := M.saturationTemperature(P_cond);
    h_l := M.bubbleEnthalpy(M.setSat_p(P_cond));
    h_v := M.dewEnthalpy(M.setSat_p(P_cond));
    st_l := M.setState_px(P_cond, 0);
    st_v := M.setState_px(P_cond, 1);
    rho_l := st_l.d; rho_v := st_v.d;
    mu_l := M.dynamicViscosity(st_l);
    st_lq := M.setState_pT(P_cond, Tcond_K - 0.1);
    k_l := M.thermalConductivity(st_lq);
    Pr_l := M.specificHeatCapacityCp(st_lq)*mu_l/k_l;
    sig := M.surfaceTension(M.setSat_p(P_cond));
    Pcrit := M.fluidConstants[1].criticalPressure;
    cpl_sat := M.specificHeatCapacityCp(st_lq);
    // 입구 냉매온도 (과열이면 SH온도)
    st_in := M.setState_ph(P_cond, h_in);
    Trefin_K := M.temperature(st_in);
    // deSH 평균온도 cp_v (no deSH면 T_cond+0.5로 특이점 회피)
    Tcpv_K := if Trefin_K > Tcond_K + 0.2 then 0.5*(Trefin_K + Tcond_K) else Tcond_K + 0.5;
    st_cpv := M.setState_pT(P_cond, Tcpv_K);
    cpv_mean := M.specificHeatCapacityCp(st_cpv);
    // deSH Gnielinski 물성 @ T_cond+5
    st_v5 := M.setState_pT(P_cond, Tcond_K + 5);
    mu_v5 := M.dynamicViscosity(st_v5); k_v5 := M.thermalConductivity(st_v5);
    Pr_v5 := M.specificHeatCapacityCp(st_v5)*mu_v5/k_v5;
    // SC Gnielinski 물성 @ T_cond-5
    st_l5 := M.setState_pT(P_cond, Tcond_K - 5);
    mu_l5 := M.dynamicViscosity(st_l5); k_l5 := M.thermalConductivity(st_l5);
    Pr_l5 := M.specificHeatCapacityCp(st_l5)*mu_l5/k_l5;
    // MB 계산
    (Qt_l, Qd_l, Q2_l, Qs_l, href_l, Pout_l, qual_l, zd_l, z2_l, zs_l, Taout_l, RHout_l,
     a2_l, adeSH_l, aSC_l, aair_l, etaf_l, M2_l)
     := condenserMB(
        D_o, D_i, L_tube_total, N_tubes, N_rows, n_circuits, P_t, P_l, t_fin, FPI, k_fin, A_o_face,
        htc_corr_cond, htc_corr_SP, htc_corr_air, dP_ref, flow_counter,
        P_cond/1e5, h_in/1000.0, m_dot, T_air_in - 273.15, RH_in*100.0, V_air_CMM,
        Tcond_K, h_l, h_v, Trefin_K, rho_l, rho_v, mu_l, k_l, Pr_l, sig, Pcrit,
        cpv_mean, cpl_sat, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5);
    Q_total := Qt_l; Q_deSH := Qd_l; Q_2ph := Q2_l; Q_SC := Qs_l;
    h_ref_out := href_l; quality_out := qual_l;
    zeta_deSH := zd_l; zeta_2ph := z2_l; zeta_SC := zs_l;
    T_air_out_C := Taout_l; RH_air_out := RHout_l;
    alpha_2ph := a2_l; alpha_deSH := adeSH_l; alpha_SC := aSC_l; alpha_air := aair_l; eta_fin := etaf_l;
    T_cond_C := Tcond_K - 273.15;
    // 출구상태·SC·holdup (결과의존 → model 파생; T_ref_out는 Python처럼 P_cond서 평가)
    st_out := M.setState_ph(P_cond, h_ref_out);
    T_ref_out_C := M.temperature(st_out) - 273.15;
    SC_out := max(0.0, T_cond_C - T_ref_out_C);
    V_internal := 3.141592653589793*D_i^2/4.0*L_tube_total;
    // M_deSH (과열 vapor @ 0.5(T_ref_in+T_cond))
    if zeta_deSH > 1e-6 then
      st_deSHavg := M.setState_pT(P_cond, 0.5*(Trefin_K + Tcond_K));
      rho_deSH := st_deSHavg.d;
      M_deSH := rho_deSH*(zeta_deSH*V_internal);
    else
      M_deSH := 0.0;
    end if;
    // M_SC (과냉 liquid @ 0.5(T_cond+T_ref_out))
    if zeta_SC > 1e-6 then
      st_SCavg := M.setState_pT(P_cond, 0.5*(Tcond_K + (T_ref_out_C + 273.15)));
      rho_SC := st_SCavg.d;
      M_SC := rho_SC*(zeta_SC*V_internal);
    else
      M_SC := 0.0;
    end if;
    M_holdup := M_deSH + M2_l + M_SC;
  end CondenserMB;

  model CondenserMB_cpl
    "응축기 MB L2 커플드 — CondenserMB(냉매 단독 검증용)의 공기 포트 개조판.
     원본은 공기조건이 파라미터였으나 AirPort air_a/air_b로 받아 공기 폐루프와 결합.
     냉매측 MB 물리는 원본과 동일(condenserMB 함수 그대로). 응축기는 가열·제습없음
     → 출구 W = 입구 W (응축기서 수분 응축 안 함, RH만 하강). L2 커플드용."
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    HPWDair.AirPort air_a "공기 입구 (응축기 상류)";
    HPWDair.AirPort air_b "공기 출구 (가열 후)";
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10, N_tubes = 24;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12, k_fin = 200, A_o_face = 0.05;
    parameter Real htc_corr_cond = 1, htc_corr_SP = 1, htc_corr_air = 1, dP_ref = 0.03;
    parameter Boolean flow_counter = true;
    // ── 공기 조건 (AirPort 유래; 개조판) ──
    Modelica.Units.SI.Temperature T_air_in(start = 308.15) "포트서 역산한 공기 입구온도";
    Real RH_in(start = 0.50) "포트 W서 역산한 상대습도 (0~1)";
    Real V_air_CMM(start = 2.5) "포트 유량서 산정한 체적유량 (m³/min)";
    Real W_air_in(start = 0.018) "공기 입구 습도비 (포트)";
    Real h_air_in(start = 9.0e4) "공기 입구 엔탈피 (포트)";
    Real m_flow_da_air(start = 0.05) "건공기 질량유량 (포트, kg/s)";
    Real rho_da_air(start = 1.1) "건공기 밀도";
    Real Q_total, Q_deSH, Q_2ph, Q_SC "[W]";
    Real T_ref_out_C, SC_out, quality_out, T_cond_C;
    Real T_air_out_C, RH_air_out;
    Real zeta_deSH, zeta_2ph, zeta_SC;
    Real alpha_2ph, alpha_deSH, alpha_SC, alpha_air, eta_fin;
    Real M_holdup "[kg]";
    Real m_dot, P_cond, h_in, h_ref_out;
  protected
    M.ThermodynamicState st_l, st_v, st_in, st_lq, st_v5, st_l5, st_out, st_deSHavg, st_SCavg, st_cpv;
    Real Tcond_K, h_l, h_v, rho_l, rho_v, mu_l, k_l, Pr_l, sig, Pcrit;
    Real Trefin_K, cpv_mean, cpl_sat, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5;
    Real Tcpv_K;
    Real Qt_l, Qd_l, Q2_l, Qs_l, href_l, Pout_l, qual_l, zd_l, z2_l, zs_l, Taout_l, RHout_l;
    Real a2_l, adeSH_l, aSC_l, aair_l, etaf_l, M2_l;
    Real rho_deSH, rho_SC, M_deSH, M_SC, V_internal;
  equation
    // ══ 공기 포트 → 내부 (개조 핵심, EvaporatorMB_cpl과 동형) ══
    m_flow_da_air = air_a.m_flow_da;
    air_a.m_flow_da + air_b.m_flow_da = 0;
    W_air_in = inStream(air_a.W_outflow);
    h_air_in = inStream(air_a.h_tilde_outflow);
    T_air_in = HPWDair.MoistAir.T_from_h(h_air_in, W_air_in);
    RH_in = min(1.0, max(0.0,
      (W_air_in*HPWDair.MoistAir.p_ref/(HPWDair.MoistAir.eps + W_air_in))
      / HPWDair.MoistAir.p_vs(T_air_in)));
    rho_da_air = HPWDair.MoistAir.rho_da_fn(T_air_in, W_air_in);
    V_air_CMM = abs(m_flow_da_air)/rho_da_air*60.0;   // 역류 보호(sqrt 음수 방지)
    m_dot = port_a.m_flow;
    P_cond = port_a.p;
    h_in = inStream(port_a.h_outflow);
    port_a.m_flow + port_b.m_flow = 0;
    port_b.p = P_cond*(1.0 - dP_ref);
    port_b.h_outflow = h_ref_out;
    port_a.h_outflow = inStream(port_b.h_outflow);
  algorithm
    Tcond_K := M.saturationTemperature(P_cond);
    h_l := M.bubbleEnthalpy(M.setSat_p(P_cond));
    h_v := M.dewEnthalpy(M.setSat_p(P_cond));
    st_l := M.setState_px(P_cond, 0);
    st_v := M.setState_px(P_cond, 1);
    rho_l := st_l.d; rho_v := st_v.d;
    mu_l := M.dynamicViscosity(st_l);
    st_lq := M.setState_pT(P_cond, Tcond_K - 0.1);
    k_l := M.thermalConductivity(st_lq);
    Pr_l := M.specificHeatCapacityCp(st_lq)*mu_l/k_l;
    sig := M.surfaceTension(M.setSat_p(P_cond));
    Pcrit := M.fluidConstants[1].criticalPressure;
    cpl_sat := M.specificHeatCapacityCp(st_lq);
    // 입구 냉매온도 (과열이면 SH온도)
    st_in := M.setState_ph(P_cond, h_in);
    Trefin_K := M.temperature(st_in);
    // deSH 평균온도 cp_v (no deSH면 T_cond+0.5로 특이점 회피)
    Tcpv_K := if Trefin_K > Tcond_K + 0.2 then 0.5*(Trefin_K + Tcond_K) else Tcond_K + 0.5;
    st_cpv := M.setState_pT(P_cond, Tcpv_K);
    cpv_mean := M.specificHeatCapacityCp(st_cpv);
    // deSH Gnielinski 물성 @ T_cond+5
    st_v5 := M.setState_pT(P_cond, Tcond_K + 5);
    mu_v5 := M.dynamicViscosity(st_v5); k_v5 := M.thermalConductivity(st_v5);
    Pr_v5 := M.specificHeatCapacityCp(st_v5)*mu_v5/k_v5;
    // SC Gnielinski 물성 @ T_cond-5
    st_l5 := M.setState_pT(P_cond, Tcond_K - 5);
    mu_l5 := M.dynamicViscosity(st_l5); k_l5 := M.thermalConductivity(st_l5);
    Pr_l5 := M.specificHeatCapacityCp(st_l5)*mu_l5/k_l5;
    // MB 계산
    (Qt_l, Qd_l, Q2_l, Qs_l, href_l, Pout_l, qual_l, zd_l, z2_l, zs_l, Taout_l, RHout_l,
     a2_l, adeSH_l, aSC_l, aair_l, etaf_l, M2_l)
     := condenserMB(
        D_o, D_i, L_tube_total, N_tubes, N_rows, n_circuits, P_t, P_l, t_fin, FPI, k_fin, A_o_face,
        htc_corr_cond, htc_corr_SP, htc_corr_air, dP_ref, flow_counter,
        P_cond/1e5, h_in/1000.0, m_dot, T_air_in - 273.15, RH_in*100.0, V_air_CMM,
        Tcond_K, h_l, h_v, Trefin_K, rho_l, rho_v, mu_l, k_l, Pr_l, sig, Pcrit,
        cpv_mean, cpl_sat, mu_v5, k_v5, Pr_v5, mu_l5, k_l5, Pr_l5);
    Q_total := Qt_l; Q_deSH := Qd_l; Q_2ph := Q2_l; Q_SC := Qs_l;
    h_ref_out := href_l; quality_out := qual_l;
    zeta_deSH := zd_l; zeta_2ph := z2_l; zeta_SC := zs_l;
    T_air_out_C := Taout_l; RH_air_out := RHout_l;
    alpha_2ph := a2_l; alpha_deSH := adeSH_l; alpha_SC := aSC_l; alpha_air := aair_l; eta_fin := etaf_l;
    T_cond_C := Tcond_K - 273.15;
    // 출구상태·SC·holdup (결과의존 → model 파생; T_ref_out는 Python처럼 P_cond서 평가)
    st_out := M.setState_ph(P_cond, h_ref_out);
    T_ref_out_C := M.temperature(st_out) - 273.15;
    SC_out := max(0.0, T_cond_C - T_ref_out_C);
    V_internal := 3.141592653589793*D_i^2/4.0*L_tube_total;
    // M_deSH (과열 vapor @ 0.5(T_ref_in+T_cond))
    if zeta_deSH > 1e-6 then
      st_deSHavg := M.setState_pT(P_cond, 0.5*(Trefin_K + Tcond_K));
      rho_deSH := st_deSHavg.d;
      M_deSH := rho_deSH*(zeta_deSH*V_internal);
    else
      M_deSH := 0.0;
    end if;
    // M_SC (과냉 liquid @ 0.5(T_cond+T_ref_out))
    if zeta_SC > 1e-6 then
      st_SCavg := M.setState_pT(P_cond, 0.5*(Tcond_K + (T_ref_out_C + 273.15)));
      rho_SC := st_SCavg.d;
      M_SC := rho_SC*(zeta_SC*V_internal);
    else
      M_SC := 0.0;
    end if;
    M_holdup := M_deSH + M2_l + M_SC;
  equation
    // ══ 내부 → 공기 포트 (개조 핵심) ══
    //   응축기는 가열·제습없음 → 출구 W = 입구 W (수분 응축 안 함).
    //   함수 출력 Taout_l(°C)만 온도로, W는 입구값 유지.
    air_a.h_tilde_outflow = HPWDair.MoistAir.h_da_fn(Taout_l + 273.15, W_air_in);
    air_b.h_tilde_outflow = HPWDair.MoistAir.h_da_fn(Taout_l + 273.15, W_air_in);
    air_a.W_outflow = W_air_in;
    air_b.W_outflow = W_air_in;
    air_b.p = air_a.p;   // 응축기 공기측 ΔP 무시(원본 함수가 별도 산출 안 함)
  end CondenserMB_cpl;

  model CondenserMB_test "FlowSource → 응축기MB → Sink"
    CondMB.CondenserMB cond;
    HPWDhx.FlowSource src(p = 17e5, h = 620e3, m_flow_set = 0.012);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end CondenserMB_test;
end CondMB;
