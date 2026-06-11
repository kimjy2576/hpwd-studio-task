within ;
package EvapMB
  "증발기 Moving-Boundary (model-docs SEMI) 조립. evaporator_moving_boundary.py step() 충실 포팅.
   상관식은 HXCorr 호출, 냉매물성은 model이 HelmholtzMedia로 계산해 인자로 전달.
   공기물성·습공기는 HXCorr 다항식/Magnus(내부 계산). 적용범위: x_in<0.80(증발기 입구 정상영역)."

  // ════════════════════ ε-NTU (단상 zone용) ════════════════════
  function eps_counterflow
    input Real NTU, Cr;
    output Real eps;
  protected
    Real N, num, den;
  algorithm
    if NTU <= 0 then
      eps := 0.0;
    elseif abs(Cr - 1.0) < 1e-6 then
      eps := NTU/(1.0 + NTU);
    elseif Cr < 1e-9 then
      eps := if NTU < 50 then 1.0 - exp(-NTU) else 1.0;
    else
      N := min(NTU, 50.0);
      num := 1.0 - exp(-N*(1.0 - Cr));
      den := 1.0 - Cr*exp(-N*(1.0 - Cr));
      eps := num/den;
    end if;
  end eps_counterflow;

  function eps_parallel
    input Real NTU, Cr;
    output Real eps;
  protected
    Real denom;
  algorithm
    if NTU <= 0 then
      eps := 0.0;
    elseif Cr < 1e-9 then
      eps := if NTU < 50 then 1.0 - exp(-NTU) else 1.0;
    else
      denom := 1.0 + Cr;
      eps := (1.0 - exp(-min(NTU*denom, 50.0)))/denom;
    end if;
  end eps_parallel;

  function eps_evap "flow arrangement별 ε-NTU. counter=true면 대향류."
    input Real NTU, Cr;
    input Boolean counter = true;
    output Real eps;
  algorithm
    eps := if counter then eps_counterflow(NTU, Cr) else eps_parallel(NTU, Cr);
  end eps_evap;

  // ════════════════════ _compute_2ph (2상 zone 공급열·표면온도) ════════════════════
  function compute2ph
    "주어진 ζ에서 2상 zone 공급열 Q_sup[W], 표면온도 Ts[°C], eps, 포화엔탈피 h_app.
     wet은 N_sub=12 sub-zone march(각 20-iter Ts 균형). evaporator_moving_boundary.py _compute_2ph."
    input Real zeta_val;
    input Real Ta2 "2상 zone 공기 입구온도 [°C]";
    input Real ha2 "2상 zone 공기 입구엔탈피 [J/kg dry air]";
    input Boolean is_wet;
    input Real alpha_2ph, A_i;
    input Real alpha_air, A_o, eta_overall;
    input Real C_air, m_dot_air, T_evap_C;
    input Real UA_2ph_full;
    output Real Q_sup;
    output Real Ts_avg;
    output Real eps_out;
    output Real h_app;
  protected
    Integer N_sub;
    Real UA_o_sub, UA_i_sub, NTU_sub, eps_sub, h_air_local, Ts, Ts_new, Q_b, Q_s, Ts_sum;
    Real UA_2ph, NTU, eps;
  algorithm
    if is_wet then
      N_sub := 12;
      UA_o_sub := alpha_air*A_o*zeta_val*eta_overall/N_sub;
      UA_i_sub := (alpha_2ph*A_i*zeta_val)/N_sub;
      NTU_sub := if C_air > 0 then UA_o_sub/C_air else 0.0;
      eps_sub := if NTU_sub < 50 then 1.0 - exp(-NTU_sub) else 1.0;
      h_air_local := ha2;
      Q_sup := 0.0;
      Ts_sum := 0.0;
      Ts := 0.5*(T_evap_C + Ta2);
      for s in 1:N_sub loop
        for it in 1:20 loop
          Q_b := m_dot_air*eps_sub*(h_air_local - HXCorr.h_air_sat(Ts));
          Ts_new := if UA_i_sub > 0 then T_evap_C + Q_b/UA_i_sub else T_evap_C;
          Ts_new := max(T_evap_C, min(Ts_new, Ta2));
          if abs(Ts_new - Ts) < 0.02 then
            Ts := Ts_new;
            break;
          end if;
          Ts := 0.5*(Ts_new + Ts);
        end for;
        Q_s := max(0.0, m_dot_air*eps_sub*(h_air_local - HXCorr.h_air_sat(Ts)));
        Q_sup := Q_sup + Q_s;
        h_air_local := h_air_local - Q_s/m_dot_air;
        Ts_sum := Ts_sum + Ts;
      end for;
      Ts_avg := Ts_sum/N_sub;
      eps_out := eps_sub;
      h_app := HXCorr.h_air_sat(Ts_avg);
    else
      UA_2ph := UA_2ph_full*zeta_val;
      NTU := if C_air > 0 then UA_2ph/C_air else 0.0;
      eps := if NTU < 50 then 1.0 - exp(-NTU) else 1.0;
      Q_sup := eps*C_air*(Ta2 - T_evap_C);
      Ts_avg := T_evap_C;
      eps_out := eps;
      h_app := 0.0;
    end if;
  end compute2ph;

  // ════════════════════ 메인: 증발기 MB ════════════════════
  function evaporatorMB
    "증발기 Moving-Boundary 1 step. 출력은 Q/ΔP/공기출구/holdup 등. T_ref_out·SH_out·RH는 model이 파생."
    // ── 기하 ──
    input Real D_o, D_i, L_tube_total, N_tubes;
    input Integer N_rows;
    input Real n_circuits, P_t, P_l, t_fin, FPI, k_fin, A_o_face, eps_over_D;
    // ── 보정계수 ──
    input Real htc_corr_2ph = 1.0, htc_corr_SH = 1.0, htc_corr_air = 1.0;
    input Real dp_corr_2ph = 1.0, dp_corr_SH = 1.0;
    input Boolean flow_counter = true;
    input Boolean wet_auto = true;
    // ── 운전 입력 ──
    input Real P_evap_bar, h_in_kjkg, m_dot_ref, T_air_in_C, RH_air_in_pct, V_air_CMM;
    // ── 냉매물성 (model이 HelmholtzMedia로 계산해 전달) ──
    input Real T_evap_K, h_l_J, h_v_J;
    input Real rho_l, rho_v, mu_l, mu_v, k_l, Pr_l, sigma, cp_v_sat, P_crit, M_mol;
    input Real mu_v_sh10, k_v_sh10, cp_v_sh10 "과열증기 @ T_evap+10 (alpha_SH/DB용)";
    input Real rho_v_sh5, mu_v_sh5 "과열증기 @ T_evap+5 (단상 ΔP용)";
    // ── 출력 ──
    output Real Q_total, Q_2ph, Q_SH, Q_latent;
    output Real h_ref_out_J, P_ref_out_bar, quality_out;
    output Real T_air_out_C, W_air_out, condensate_rate;
    output Real zeta, BF;
    output Real alpha_2ph, alpha_SH, alpha_air, eta_fin;
    output Real UA_2ph_actual, UA_SH_actual;
    output Real dP_2ph, dP_SH, dP_accel, dP_total_Pa;
    output Real M_2ph;
    output Real is_wet_out;
  protected
    Real P_evap_Pa, h_in_J, P_fin, h_fg, T_evap_C, x_in;
    Real W_in, h_air_in, T_dp_in_C, cp_air, C_air, m_dot_air;
    Real A_tube_outer, n_fins_per_tube, A_per_fin, A_fin_total, A_o, A_i;
    Real T_air_avg_K, mu_a, Pr_a, cp_a, Dc, gap, sig_c, A_c, G_air, Re_Dc, j_air;
    Real eta_overall, UA_air_total;
    Real x_avg_2ph, Q_2ph_demand, q_flux_2ph_est, A_cross, G_2ph;
    Real UA_2ph_full, UA_SH_full;
    Boolean is_wet, ref_fully_evap;
    Real T_air_2ph_in, h_air_2ph_in, Q_2ph_sup, T_surf_C, eps_2ph_w, h_app_2ph;
    Real Q_at_full, lo, hi, Qs, dum1, dum2, dum3;
    Real h_air_after_2ph, W_sat_surf, h_fg_water, T_air_after_2ph_C;
    Real cp_ref_SH, C_ref, Cmin_SH, Cmax_SH, Cr, NTU_SH, eps_SH, T_air_SH_in;
    Real h_ref_out_local, T_air_2ph_new, h_air_2ph_new;
    Real L_2ph_zone, L_SH_zone, m_dot_per_tube, x_at_2ph_end;
    Real P_ref_out_Pa, h_ref_out_final_J;
    Real V_internal, m_per_tube, x_in_2ph, rho_sum, xv, av, rho_2ph;
    Integer Nint;
  algorithm
    // ── 0. 단위 ──
    P_evap_Pa := P_evap_bar*1e5;
    h_in_J := h_in_kjkg*1000.0;
    P_fin := 0.0254/FPI;
    h_fg := h_v_J - h_l_J;
    T_evap_C := T_evap_K - 273.15;

    // ── 1. 냉매 입구 quality ──
    x_in := if h_fg > 0 then (h_in_J - h_l_J)/h_fg else 0.0;
    x_in := max(0.0, min(1.0 + 1e-6, x_in));

    // ── 2. 공기 입구 (Magnus, HAPropsSI 규약 매칭) ──
    W_in := HXCorr.W_humid(T_air_in_C, RH_air_in_pct/100.0, 101325.0);
    h_air_in := HXCorr.h_moist(T_air_in_C, W_in);
    T_dp_in_C := HXCorr.Tdew(T_air_in_C, RH_air_in_pct/100.0, 101325.0);
    cp_air := HXCorr.cp_ha_moist(W_in);
    m_dot_air := HXCorr.rho_humid_air(T_air_in_C, W_in, 101325.0)*(V_air_CMM/60.0);
    C_air := m_dot_air*cp_air;

    // ── 3. 면적 ──
    A_tube_outer := 3.141592653589793*D_o*L_tube_total;
    n_fins_per_tube := if P_fin > 0 then L_tube_total/N_tubes/P_fin else 0.0;
    A_per_fin := 2.0*(P_t*P_l - 3.141592653589793*D_o^2/4.0);
    A_fin_total := N_tubes*n_fins_per_tube*A_per_fin;
    A_o := A_tube_outer + A_fin_total;
    A_i := 3.141592653589793*D_i*L_tube_total;

    // ── 4. 공기측 α (Wang j-factor) ──
    T_air_avg_K := (T_air_in_C + 273.15 + T_evap_K)/2.0;
    mu_a := HXCorr.mu_air(T_air_avg_K);
    Pr_a := HXCorr.Pr_air(T_air_avg_K);
    cp_a := 1006.0 "dry air cp (W=0, vendor cp_air(T,0))";
    Dc := D_o + 2.0*t_fin;
    gap := P_fin - t_fin;
    sig_c := max((P_t - Dc)*gap/(P_t*P_fin), 0.1);
    A_c := sig_c*A_o_face;
    G_air := m_dot_air/max(A_c, 1e-9);
    Re_Dc := G_air*Dc/max(mu_a, 1e-9);
    j_air := HXCorr.j_wang2000_plain(Re_Dc, N_rows, Dc, P_t, P_l, FPI, t_fin);
    alpha_air := j_air*G_air*cp_a/Pr_a^(2.0/3.0)*htc_corr_air;

    // ── 5. 핀 효율 (Schmidt) ──
    eta_fin := HXCorr.schmidt_fin(D_o, P_t, P_l, t_fin, k_fin, alpha_air, "staggered");
    eta_overall := if A_o > 0 then (A_tube_outer + A_fin_total*eta_fin)/A_o else eta_fin;
    UA_air_total := alpha_air*A_o*eta_overall;

    // ── 6. 냉매측 α ──
    x_avg_2ph := (x_in + 1.0)/2.0;
    Q_2ph_demand := m_dot_ref*(h_v_J - h_in_J);
    q_flux_2ph_est := Q_2ph_demand/max(A_i, 1e-6);
    A_cross := 3.141592653589793*D_i^2/4.0;
    G_2ph := (m_dot_ref/max(n_circuits, 1.0))/max(A_cross, 1e-12);
    // 2상 비등: x_avg<0.90 → 순수 Chen (h_with_transition 순수경로)
    alpha_2ph := HXCorr.h_evap_chen1966(x_avg_2ph, G_2ph, D_i, q_flux_2ph_est,
      mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_evap_Pa/P_crit, M_mol)*htc_corr_2ph;
    // SH 단상: Dittus-Boelter @ T_evap+10
    alpha_SH := HXCorr.dittus_boelter(mu_v_sh10, k_v_sh10, cp_v_sh10,
      m_dot_ref/max(n_circuits, 1.0), D_i, true)*htc_corr_SH;

    // ── 7. zone별 UA (직렬저항) ──
    UA_2ph_full := 1.0/(1.0/(alpha_2ph*A_i) + 1.0/(alpha_air*A_o*eta_overall));
    UA_SH_full := 1.0/(1.0/(alpha_SH*A_i) + 1.0/(alpha_air*A_o*eta_overall));

    // ── 8. wet 판정 ──
    is_wet := wet_auto and (T_dp_in_C > T_evap_C);

    // ── 8~10. flow 결합 iteration ──
    T_air_2ph_in := T_air_in_C;
    h_air_2ph_in := h_air_in;
    zeta := 0.5;
    ref_fully_evap := false;
    Q_2ph := 0.0; Q_SH := 0.0; Q_latent := 0.0;
    T_surf_C := T_evap_C; eps_2ph_w := 0.0; h_app_2ph := 0.0;
    BF := 1.0; W_air_out := W_in; condensate_rate := 0.0;
    h_air_after_2ph := h_air_in; T_air_after_2ph_C := T_air_in_C;
    for ctr in 1:15 loop
      // ζ bisection (Q_2ph_supply(ζ) 단조증가, demand 고정)
      (Q_at_full, dum1, dum2, dum3) := compute2ph(0.999, T_air_2ph_in, h_air_2ph_in,
        is_wet, alpha_2ph, A_i, alpha_air, A_o, eta_overall, C_air, m_dot_air, T_evap_C, UA_2ph_full);
      if Q_at_full <= Q_2ph_demand then
        zeta := 1.0;
        ref_fully_evap := false;
      else
        lo := 0.01; hi := 0.999;
        for bi in 1:50 loop
          zeta := 0.5*(lo + hi);
          (Qs, dum1, dum2, dum3) := compute2ph(zeta, T_air_2ph_in, h_air_2ph_in,
            is_wet, alpha_2ph, A_i, alpha_air, A_o, eta_overall, C_air, m_dot_air, T_evap_C, UA_2ph_full);
          if Qs < Q_2ph_demand then
            lo := zeta;
          else
            hi := zeta;
          end if;
          if hi - lo < 1e-4 then
            break;
          end if;
        end for;
        zeta := 0.5*(lo + hi);
        ref_fully_evap := (zeta < 0.99);
      end if;
      zeta := max(0.01, min(1.0, zeta));

      // 최종 2상 zone
      (Q_2ph_sup, T_surf_C, eps_2ph_w, h_app_2ph) := compute2ph(zeta, T_air_2ph_in, h_air_2ph_in,
        is_wet, alpha_2ph, A_i, alpha_air, A_o, eta_overall, C_air, m_dot_air, T_evap_C, UA_2ph_full);
      Q_2ph := if ref_fully_evap then Q_2ph_demand else Q_2ph_sup;
      UA_SH_actual := if zeta < 1.0 then UA_SH_full*(1.0 - zeta) else 0.0;

      // 2상 공기 출구 + 제습
      h_air_after_2ph := h_air_2ph_in - Q_2ph/m_dot_air;
      if is_wet then
        BF := (h_air_after_2ph - h_app_2ph)/max(h_air_2ph_in - h_app_2ph, 1e-6);
        BF := max(0.0, min(1.0, BF));
        W_sat_surf := HXCorr.W_sat(T_surf_C, 101325.0);
        W_air_out := BF*W_in + (1.0 - BF)*W_sat_surf;
        W_air_out := min(W_in, max(W_sat_surf, W_air_out));
        condensate_rate := m_dot_air*(W_in - W_air_out);
        h_fg_water := 2501e3 - 2.4*T_surf_C;
        Q_latent := max(0.0, condensate_rate*h_fg_water);
      else
        BF := 1.0;
        W_air_out := W_in;
        condensate_rate := 0.0;
        Q_latent := 0.0;
      end if;
      T_air_after_2ph_C := HXCorr.T_moist_from_h(h_air_after_2ph, W_air_out);

      // SH zone (dry sensible)
      Q_SH := 0.0;
      if ref_fully_evap and UA_SH_actual > 0 then
        cp_ref_SH := cp_v_sat;
        C_ref := m_dot_ref*cp_ref_SH;
        Cmin_SH := min(C_ref, C_air);
        Cmax_SH := max(C_ref, C_air);
        Cr := if Cmax_SH > 0 then Cmin_SH/Cmax_SH else 0.0;
        NTU_SH := if Cmin_SH > 0 then UA_SH_actual/Cmin_SH else 0.0;
        eps_SH := eps_evap(NTU_SH, Cr, flow_counter);
        T_air_SH_in := if flow_counter then T_air_in_C else T_air_after_2ph_C;
        Q_SH := max(0.0, eps_SH*Cmin_SH*(T_air_SH_in - T_evap_C));
      end if;

      // 2상 공기 입구 업데이트
      if flow_counter then
        T_air_2ph_new := if C_air > 0 then T_air_in_C - Q_SH/C_air else T_air_in_C;
        h_air_2ph_new := h_air_in - Q_SH/m_dot_air;
      else
        T_air_2ph_new := T_air_in_C;
        h_air_2ph_new := h_air_in;
      end if;

      if abs(T_air_2ph_new - T_air_2ph_in) < 0.03 then
        T_air_2ph_in := T_air_2ph_new;
        h_air_2ph_in := h_air_2ph_new;
        break;
      end if;
      T_air_2ph_in := T_air_2ph_new;
      h_air_2ph_in := h_air_2ph_new;
    end for;

    UA_2ph_actual := UA_2ph_full*zeta;

    // ── 공기 최종 출구온도 ──
    if flow_counter then
      T_air_out_C := T_air_after_2ph_C;
    else
      T_air_out_C := if C_air > 0 then T_air_after_2ph_C - Q_SH/C_air else T_air_after_2ph_C;
    end if;

    // ── 11. Q_total ──
    Q_total := Q_2ph + Q_SH;

    // ── 12. ΔP ──
    L_2ph_zone := L_tube_total*zeta;
    L_SH_zone := if zeta < 0.99 then L_tube_total*(1.0 - zeta) else 0.0;
    m_dot_per_tube := m_dot_ref;
    x_at_2ph_end := if (m_dot_ref > 0 and h_fg > 0) then max(0.0, min(1.0, x_in + Q_2ph/(m_dot_ref*h_fg))) else x_in;
    dP_2ph := if L_2ph_zone > 0 then HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, x_in, x_at_2ph_end, m_dot_per_tube, D_i, L_2ph_zone, 10)*dp_corr_2ph else 0.0;
    dP_SH := if (L_SH_zone > 0 and ref_fully_evap) then HXCorr.single_phase_dp(rho_v_sh5, mu_v_sh5, m_dot_per_tube, D_i, L_SH_zone, eps_over_D)*dp_corr_SH else 0.0;
    dP_accel := HXCorr.acceleration_dp(rho_l, rho_v, x_in, x_at_2ph_end, m_dot_per_tube, D_i);
    dP_total_Pa := dP_2ph + dP_SH + dP_accel;
    P_ref_out_Pa := max(P_evap_Pa - dP_total_Pa, 1e3);
    P_ref_out_bar := P_ref_out_Pa/1e5;

    // ── 13. 출구 ──
    h_ref_out_final_J := h_in_J + Q_total/m_dot_ref;
    h_ref_out_J := h_ref_out_final_J;
    if h_ref_out_final_J >= h_v_J then
      quality_out := 1.0 + (h_ref_out_final_J - h_v_J)/max(h_fg, 1.0);
    else
      quality_out := if h_fg > 0 then (h_ref_out_final_J - h_l_J)/h_fg else 0.0;
    end if;

    // ── charge holdup 2상 (void Premoli 10점 적분) ──
    V_internal := A_cross*L_tube_total;
    m_per_tube := m_dot_ref/max(n_circuits, 1.0);
    x_in_2ph := max(0.0, min(1.0, (h_in_J - h_l_J)/max(h_fg, 1.0)));
    Nint := 10;
    rho_sum := 0.0;
    for i in 1:Nint loop
      xv := x_in_2ph + (1.0 - x_in_2ph)*(i - 0.5)/Nint;
      av := HXCorr.void_premoli(xv, rho_l, rho_v, mu_l, sigma, m_per_tube, D_i);
      rho_sum := rho_sum + HXCorr.void_mean_density(av, rho_l, rho_v);
    end for;
    rho_2ph := rho_sum/Nint;
    M_2ph := rho_2ph*(zeta*V_internal);

    is_wet_out := if is_wet then 1.0 else 0.0;
  end evaporatorMB;

  // ════════════════════ Acausal TwoPort 모델 ════════════════════
  model EvaporatorMB "증발기 MB (L2 SEMI). RefPort TwoPort + 공기조건 파라미터. 냉매물성 HelmholtzMedia."
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a "입구 (2상)";
    HPWD.RefPort port_b "출구 (과열/2상)";
    // ── 기하 (Python step() default) ──
    parameter Real D_o = 7e-3, D_i = 6.5e-3, L_tube_total = 10, N_tubes = 24;
    parameter Integer N_rows = 2;
    parameter Real n_circuits = 2, P_t = 25e-3, P_l = 22e-3, t_fin = 0.12e-3;
    parameter Real FPI = 12, k_fin = 200, A_o_face = 0.05, eps_over_D = 0;
    parameter Real htc_corr_2ph = 1, htc_corr_SH = 1, htc_corr_air = 1, dp_corr_2ph = 1, dp_corr_SH = 1;
    parameter Boolean flow_counter = true, wet_auto = true;
    // ── 공기 조건 (파라미터; 향후 air loop 결합 시 입력화) ──
    parameter Modelica.Units.SI.Temperature T_air_in = 45 + 273.15;
    parameter Real RH_in = 0.85 "0~1";
    parameter Real V_air_CMM = 2.54;
    // ── 노출 출력 ──
    Real Q_total, Q_2ph, Q_SH, Q_latent "[W]";
    Real T_ref_out_C, SH_out, quality_out, T_evap_C;
    Real T_air_out_C, W_air_out, condensate_rate;
    Real zeta, alpha_2ph, alpha_SH, alpha_air, eta_fin;
    Real dP_total "[Pa]";
    Real M_holdup "[kg]";
    Real is_wet;
    // ── 포트 결합용 ──
    Real m_dot, P_evap, h_in, h_ref_out;
  protected
    M.SaturationProperties satP;
    M.ThermodynamicState st_l, st_v, st_lq, st_vq, st10, st5, st_out, st_SHavg;
    Real Tev_K, h_l, h_v, rho_l, rho_v, mu_l, mu_v, k_l, cp_l, Pr_l, sig, cp_vs;
    Real mu10, k10, cp10, rho5, mu5, Pcrit, Mmol;
    Real Q_2ph_l, Q_SH_l, Q_lat_l, href_l, Pout_l, qual_l, Taout_l, Waout_l, cond_l;
    Real zeta_l, BF_l, a2_l, aSH_l, aair_l, etaf_l, UA2_l, UASH_l, dp2_l, dpSH_l, dpacc_l, dptot_l, M2_l, iswet_l;
    Real T_SHavg_K, rho_SH, M_SH, V_internal;
  equation
    m_dot = port_a.m_flow;
    P_evap = port_a.p;
    h_in = inStream(port_a.h_outflow);
    port_a.m_flow + port_b.m_flow = 0;
    port_b.p = P_evap - dP_total;
    port_b.h_outflow = h_ref_out;
    port_a.h_outflow = inStream(port_b.h_outflow);
  algorithm
    // ── 냉매물성 (HelmholtzMedia; cp/k는 포화경계 특이 → ±0.1K 단상 평가) ──
    Tev_K := M.saturationTemperature(P_evap);
    satP := M.setSat_p(P_evap);
    h_l := M.bubbleEnthalpy(satP);
    h_v := M.dewEnthalpy(satP);
    st_l := M.setState_px(P_evap, 0);
    st_v := M.setState_px(P_evap, 1);
    rho_l := st_l.d; rho_v := st_v.d;
    mu_l := M.dynamicViscosity(st_l);
    mu_v := M.dynamicViscosity(st_v);
    st_lq := M.setState_pT(P_evap, Tev_K - 0.1);
    st_vq := M.setState_pT(P_evap, Tev_K + 0.1);
    k_l := M.thermalConductivity(st_lq);
    cp_l := M.specificHeatCapacityCp(st_lq);
    Pr_l := cp_l*mu_l/k_l;
    cp_vs := M.specificHeatCapacityCp(st_vq);
    sig := M.surfaceTension(satP);
    st10 := M.setState_pT(P_evap, Tev_K + 10);
    mu10 := M.dynamicViscosity(st10); k10 := M.thermalConductivity(st10); cp10 := M.specificHeatCapacityCp(st10);
    st5 := M.setState_pT(P_evap, Tev_K + 5);
    rho5 := st5.d; mu5 := M.dynamicViscosity(st5);
    Pcrit := M.fluidConstants[1].criticalPressure;
    Mmol := M.fluidConstants[1].molarMass*1000.0;
    // ── MB 계산 ──
    (Q_total, Q_2ph_l, Q_SH_l, Q_lat_l, href_l, Pout_l, qual_l, Taout_l, Waout_l, cond_l,
     zeta_l, BF_l, a2_l, aSH_l, aair_l, etaf_l, UA2_l, UASH_l, dp2_l, dpSH_l, dpacc_l, dptot_l, M2_l, iswet_l)
     := evaporatorMB(
        D_o, D_i, L_tube_total, N_tubes, N_rows, n_circuits, P_t, P_l, t_fin, FPI, k_fin, A_o_face, eps_over_D,
        htc_corr_2ph, htc_corr_SH, htc_corr_air, dp_corr_2ph, dp_corr_SH, flow_counter, wet_auto,
        P_evap/1e5, h_in/1000.0, m_dot, T_air_in - 273.15, RH_in*100.0, V_air_CMM,
        Tev_K, h_l, h_v, rho_l, rho_v, mu_l, mu_v, k_l, Pr_l, sig, cp_vs, Pcrit, Mmol,
        mu10, k10, cp10, rho5, mu5);
    dP_total := dptot_l;
    h_ref_out := href_l;
    Q_2ph := Q_2ph_l; Q_SH := Q_SH_l; Q_latent := Q_lat_l;
    quality_out := qual_l; T_air_out_C := Taout_l; W_air_out := Waout_l; condensate_rate := cond_l;
    zeta := zeta_l; alpha_2ph := a2_l; alpha_SH := aSH_l; alpha_air := aair_l; eta_fin := etaf_l;
    is_wet := iswet_l;
    T_evap_C := Tev_K - 273.15;
    // ── 출구상태·SH·holdup (결과의존 → model에서 파생) ──
    st_out := M.setState_ph(port_b.p, h_ref_out);
    T_ref_out_C := M.temperature(st_out) - 273.15;
    SH_out := max(0.0, T_ref_out_C - T_evap_C);
    V_internal := 3.141592653589793*D_i^2/4.0*L_tube_total;
    if zeta < 0.999 then
      T_SHavg_K := 0.5*(Tev_K + (T_ref_out_C + 273.15));
      st_SHavg := M.setState_pT(P_evap, T_SHavg_K);
      rho_SH := st_SHavg.d;
      M_SH := rho_SH*((1.0 - zeta)*V_internal);
    else
      M_SH := 0.0;
    end if;
    M_holdup := M2_l + M_SH;
  end EvaporatorMB;

  model EvaporatorMB_test "FlowSource → 증발기MB → Sink (정합 검증)"
    EvapMB.EvaporatorMB evap;
    HPWDhx.FlowSource src(p = 5.5e5, h = 285990, m_flow_set = 0.004);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end EvaporatorMB_test;
end EvapMB;
