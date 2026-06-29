within ;
package EevMB
  "EEV Moving-Boundary (model-docs SEMI) 조립. eev_moving_boundary.py step() 충실 포팅.
   오리피스 유량: ṁ = Cd_eff·A_eff·√(2ρ·ΔP_eff). Cd 보정(f_Re·f_sub·f_op) + choke. 등엔탈피.
   신규 상관식 없음(대수식). 냉매물성은 model이 R290Tab으로 전달."

  function eev_Cd_corr "방출계수 보정 Cd_eff = Cd_0·f_Re·f_sub·f_op. eev_moving_boundary.py _Cd_corrections."
    input Real Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op;
    output Real Cd_eff;
  protected
    Real f_Re, f_sub, f_op;
  algorithm
    f_Re := if Re > 0 then 1.0 - exp(-max(0.0, Re)/max(1.0, Re_c)) else 0.0;
    f_sub := 1.0 + k_sub*(T_sub_K/10.0);
    f_op := 1.0 - k_op*(1.0 - max(0.0, min(1.0, op_frac)));
    Cd_eff := Cd_0*max(0.05, f_Re)*max(0.5, f_sub)*max(0.3, f_op);
  end eev_Cd_corr;

  function eevMB
    "EEV 1 step. control: opening→ṁ. measure: ṁ_meas→opening(bisect). 등엔탈피라 h_out=h_in."
    input Real A_orifice_mm2, opening_min, Cd_0, Re_c, k_sub, k_op, Y_crit, cf_A;
    input Boolean use_choke = true, mode_control = true;
    input Real P_in_bar, h_in_kjkg, P_out_bar, opening_pct, m_dot_meas;
    input Real rho_in, mu_in, T_sub_K "냉매물성 (model이 R290Tab으로 전달)";
    output Real m_dot_ref, opening_calc, Cd_eff, Re, dP_eff_bar, is_choked;
  protected
    Real A_orifice, P_in_Pa, P_out_Pa, dP_actual, pr, dP_eff;
    Real op_frac, A_eff, m_first, D_h;
    Real lo, hi, mid, op_t, A_t, m_first_t, Dh_t, Re_t, Cd_t, m_t;
  algorithm
    if P_out_bar >= P_in_bar then
      // 역압 — 유량 0
      m_dot_ref := 0.0;
      opening_calc := if mode_control then opening_pct else 0.0;
      Cd_eff := 0.0; Re := 0.0; dP_eff_bar := 0.0; is_choked := 0.0;
    else
      A_orifice := A_orifice_mm2*1e-6;
      P_in_Pa := P_in_bar*1e5;
      P_out_Pa := P_out_bar*1e5;
      dP_actual := P_in_Pa - P_out_Pa;
      pr := P_out_Pa/P_in_Pa;
      // choke (임계유동)
      if use_choke and pr < Y_crit then
        dP_eff := P_in_Pa*(1.0 - Y_crit);
        is_choked := 1.0;
      else
        dP_eff := dP_actual;
        is_choked := 0.0;
      end if;
      dP_eff_bar := dP_eff/1e5;
      if mode_control then
        op_frac := max(opening_min, min(100.0, opening_pct))/100.0;
        A_eff := cf_A*A_orifice*op_frac;
        m_first := Cd_0*A_eff*sqrt(2.0*rho_in*dP_eff);
        D_h := if A_eff > 0 then sqrt(4.0*A_eff/3.141592653589793) else 0.0;
        Re := if (mu_in*A_eff) > 0 then m_first*D_h/(mu_in*A_eff) else 0.0;
        Cd_eff := eev_Cd_corr(Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op);
        m_dot_ref := Cd_eff*A_eff*sqrt(2.0*rho_in*dP_eff);
        opening_calc := max(opening_min, min(100.0, opening_pct));
      else
        // measure: opening bisection으로 ṁ_meas 맞춤
        if m_dot_meas <= 0 or rho_in <= 0 then
          opening_calc := 0.0; A_eff := 0.0; Cd_eff := 0.0; Re := 0.0; m_dot_ref := 0.0;
        else
          lo := opening_min; hi := 100.0;
          for it in 1:40 loop
            mid := 0.5*(lo + hi);
            op_t := mid/100.0;
            A_t := cf_A*A_orifice*op_t;
            m_first_t := Cd_0*A_t*sqrt(2.0*rho_in*dP_eff);
            Dh_t := if A_t > 0 then sqrt(4.0*A_t/3.141592653589793) else 0.0;
            Re_t := if (mu_in*A_t) > 0 then m_first_t*Dh_t/(mu_in*A_t) else 0.0;
            Cd_t := eev_Cd_corr(Cd_0, Re_t, T_sub_K, op_t, Re_c, k_sub, k_op);
            m_t := Cd_t*A_t*sqrt(2.0*rho_in*dP_eff);
            if m_t < m_dot_meas then lo := mid; else hi := mid; end if;
            if abs(hi - lo) < 0.001 then break; end if;
          end for;
          opening_calc := 0.5*(lo + hi);
          op_frac := opening_calc/100.0;
          A_eff := cf_A*A_orifice*op_frac;
          m_first := Cd_0*A_eff*sqrt(2.0*rho_in*dP_eff);
          D_h := if A_eff > 0 then sqrt(4.0*A_eff/3.141592653589793) else 0.0;
          Re := if (mu_in*A_eff) > 0 then m_first*D_h/(mu_in*A_eff) else 0.0;
          Cd_eff := eev_Cd_corr(Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op);
          m_dot_ref := m_dot_meas;
        end if;
      end if;
    end if;
  end eevMB;

  // ════════════════════ Acausal TwoPort 모델 ════════════════════
  model EEV_MB "EEV MB (L2 SEMI). RefPort TwoPort. 등엔탈피 팽창. 냉매물성 R290Tab."
    HPWD.RefPort port_a "입구 (고압 과냉액)";
    HPWD.RefPort port_b "출구 (저압 2상)";
    parameter Real A_orifice_mm2 = 0.785, opening_min = 0.0, Cd_0 = 0.70;
    parameter Real Re_c = 5000.0, k_sub = 0.05, k_op = 0.15, Y_crit = 0.55, cf_A = 1.0;
    parameter Boolean use_choke = true;
    Modelica.Blocks.Interfaces.RealInput opening "개도 [%] (신호: PI 또는 Constant)";
    Real m_dot_ref, opening_calc, Cd_eff, Re, dP_eff_bar, is_choked;
    Real T_sub, x_out, T_out_C;
    Real m_dot, P_in, P_out, h_in;
  protected
    Real rho_in, mu_in, Tsat_in_K, h_l_in, T_in_K, h_l_out, h_v_out;
    Real mdr, opc, cde, re_l, dpe, isc;
  equation
    P_in = port_a.p;
    P_out = port_b.p;
    h_in = inStream(port_a.h_outflow);
    port_a.m_flow + port_b.m_flow = 0;
    m_dot = port_a.m_flow;
    m_dot = m_dot_ref;
    port_b.h_outflow = h_in;
    port_a.h_outflow = inStream(port_b.h_outflow);
  algorithm
    // 입구 냉매물성 (R290Tab)
    rho_in := R290Tab.rho_ph(P_in, h_in);
    mu_in := R290Tab.mu_ph(P_in, h_in);
    Tsat_in_K := R290Tab.Tsat(P_in);
    h_l_in := R290Tab.hl(P_in);
    T_in_K := R290Tab.T_ph(P_in, h_in);
    T_sub := if h_in < h_l_in then Tsat_in_K - T_in_K else 0.0;
    // EEV 계산 (control mode)
    (mdr, opc, cde, re_l, dpe, isc) := eevMB(
      A_orifice_mm2, opening_min, Cd_0, Re_c, k_sub, k_op, Y_crit, cf_A,
      use_choke, true, P_in/1e5, h_in/1000.0, P_out/1e5, opening, 0.0,
      rho_in, mu_in, T_sub);
    m_dot_ref := mdr; opening_calc := opc; Cd_eff := cde; Re := re_l; dP_eff_bar := dpe; is_choked := isc;
    // 출구상태 (등엔탈피, h_out=h_in @ P_out)
    h_l_out := R290Tab.hl(P_out);
    h_v_out := R290Tab.hv(P_out);
    T_out_C := R290Tab.T_ph(P_out, h_in) - 273.15;
    if h_in <= h_l_out then
      x_out := 0.0;
    elseif h_in >= h_v_out then
      x_out := 1.0;
    else
      x_out := (h_in - h_l_out)/(h_v_out - h_l_out);
    end if;
  end EEV_MB;

  // 압력 고정 경계 (유량 자유) — EEV가 ΔP로 유량 결정
  model PBnd "압력 경계"
    HPWD.RefPort port;
    parameter Modelica.Units.SI.AbsolutePressure p = 17e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h = 0;
  equation
    port.p = p;
    port.h_outflow = h;
  end PBnd;

  model EEV_MB_test "압력경계(고압 과냉액) → EEV → 압력경계(저압)"
    EevMB.EEV_MB eev;
    Modelica.Blocks.Sources.Constant openSig(k = 50.0);
    PBnd inlet(p = 16.49e5, h = 271000);
    PBnd outlet(p = 5.5e5, h = 0);
  equation
    connect(openSig.y, eev.opening);
    connect(inlet.port, eev.port_a);
    connect(eev.port_b, outlet.port);
  end EEV_MB_test;
end EevMB;
