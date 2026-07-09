package HPWDhx "UA 모델 HX connector"

  function epsC0 "Cr=0 ε-NTU"
    input Real NTU; output Real eps;
  algorithm
    eps := if NTU <= 0 then 0.0 elseif NTU > 50 then 1.0 else 1.0 - exp(-NTU);
  end epsC0;

  function epsCounter "Counter-flow ε-NTU"
    input Real NTU; input Real Cr; output Real eps;
  algorithm
    if NTU <= 0 then eps := 0.0;
    elseif Cr <= 1e-6 then eps := if NTU > 50 then 1.0 else 1.0 - exp(-NTU);
    elseif Cr >= 1.0 - 1e-6 then eps := NTU/(1.0 + NTU);
    else eps := (1.0 - exp(-NTU*(1.0 - Cr)))/(1.0 - Cr*exp(-NTU*(1.0 - Cr)));
    end if;
  end epsCounter;

  function pSatWater "물 포화압 (Antoine, Pa)"
    input Real T_C; output Real P_Pa;
  protected
    constant Real A = 8.07131, B = 1730.63, C = 233.426;
  algorithm
    P_Pa := 10.0^(A - B/(T_C + C)) * 133.322;
  end pSatWater;

  function satProps "포화 물성 (R290Tab)"
    input Real P;
    output Real hl, hv, cp_dew, cp_bub;
  algorithm
    hl := R290Tab.hl(P);
    hv := R290Tab.hv(P);
    cp_dew := R290Tab.cpv(P);
    cp_bub := R290Tab.cpl(P);
  end satProps;

  function airProps "습공기 물성 추출 (ThermodynamicState record를 scalar로)"
    input Real P, T, RH;
    output Real cp, rho, x_w, Xw_out;
  protected
    package A = Modelica.Media.Air.MoistAir;
    A.ThermodynamicState st;
    Real Xw;
  algorithm
    Xw := A.massFraction_pTphi(P, T, RH);
    st := A.setState_pTX(P, T, {Xw, 1.0 - Xw});
    cp := A.specificHeatCapacityCp(st);
    rho := A.density(st);
    x_w := Xw/(1.0 - Xw);
    Xw_out := Xw;
  end airProps;

  model FlowSource "냉매 flow 소스 (ṁ 지정)"
    HPWD.RefPort port;
    parameter Modelica.Units.SI.AbsolutePressure p = 5.51e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h = 336.563e3;
    parameter Real m_flow_set = 0.00458812;
  equation
    port.p = p;
    port.h_outflow = h;
    port.m_flow = -m_flow_set;   // 포트로 나가는 방향 (-)
  end FlowSource;

  model SinkOpen "압력 미지정 종단 (압력은 상류 컴포넌트가 결정)"
    HPWD.RefPort port;
    parameter Modelica.Units.SI.SpecificEnthalpy h = 250e3;
  equation
    port.h_outflow = h;   // 역류 시 (단방향이라 안 씀)
  end SinkOpen;

  model Evap_UA "증발기 UA 2-zone ε-NTU — RefPort TwoPort + SH 출력"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    package Air = Modelica.Media.Air.MoistAir;
    HPWD.RefPort port_a "입구 (2상)";
    HPWD.RefPort port_b "출구 (과열)";
    Modelica.Blocks.Interfaces.RealOutput SH "출구 과열도 [K]";
    parameter Modelica.Units.SI.Temperature T_air_in = 50.0 + 273.15;
    parameter Real RH_in = 0.90;
    parameter Real V_air_CMM = 2.54;
    parameter Real UA_2ph = 25.0, UA_SH = 4.0, dP_ref = 0.02, R_fric = 2e6, L_inertia = 1e5;
    parameter Modelica.Units.SI.Pressure P_atm = 101325.0;
    // port 연동
    Real m_dot, h_in, P_evap;
    // 중간/출력
    Real T_evap_K, T_evap, h_l, h_v, h_fg;
    Real Xw_in, x_w_in, cp_air, rho_air, m_dot_air, C_air;
    Real p_w_in, p_ws_surf, is_wet;
    Real Q_max_2ph_ref, NTU_2ph, eps_2ph, Q_sensible_2ph;
    Real Xw_sat, x_w_sat, dW, condensate_rate, h_fg_water, Q_latent;
    Real Q_2ph_total, ratio, T_air_after_2ph_K, h_after_2ph, x_after_2ph;
    Real Q_SH, h_out, T_air_out_K;
    Real cp_ref_SH, C_ref, Cmin_SH, Cmax_SH, Cr, NTU_SH, eps_SH;
    Real P_ref_out, T_ref_out, SH_calc;
    Boolean ref_fully_evap;
    Ref.SaturationProperties satP;
    Air.ThermodynamicState stAir;
  equation
    m_dot = (port_a.p - port_b.p)/R_fric;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    P_evap = port_a.p;
    port_b.h_outflow = h_out;
    port_a.h_outflow = port_b.h_outflow;
    SH = SH_calc;
  algorithm
    T_evap_K := Ref.saturationTemperature(P_evap);
    T_evap := T_evap_K - 273.15;
    satP := Ref.setSat_p(P_evap);
    h_l := Ref.bubbleEnthalpy(satP);
    h_v := Ref.dewEnthalpy(satP);
    h_fg := h_v - h_l;
    Xw_in := Air.massFraction_pTphi(P_atm, T_air_in, RH_in);
    x_w_in := Xw_in/(1.0 - Xw_in);
    stAir := Air.setState_pTX(P_atm, T_air_in, {Xw_in, 1.0 - Xw_in});
    cp_air := Air.specificHeatCapacityCp(stAir);
    rho_air := Air.density(stAir);
    m_dot_air := rho_air*V_air_CMM/60.0;
    C_air := m_dot_air*cp_air;
    p_w_in := x_w_in*P_atm/(0.621945 + x_w_in);
    p_ws_surf := Air.saturationPressure(T_evap_K);
    is_wet := if p_w_in > p_ws_surf then 1.0 else 0.0;
    Q_max_2ph_ref := m_dot*(h_v - h_in);
    NTU_2ph := UA_2ph/C_air;
    eps_2ph := if NTU_2ph < 50.0 then 1.0 - exp(-NTU_2ph) else 1.0;
    Q_sensible_2ph := max(0.0, eps_2ph*C_air*(T_air_in - T_evap_K));
    condensate_rate := 0.0; Q_latent := 0.0;
    if is_wet > 0.5 then
      Xw_sat := Air.massFraction_pTphi(P_atm, T_evap_K, 0.999);
      x_w_sat := Xw_sat/(1.0 - Xw_sat);
      if x_w_in > x_w_sat then
        dW := eps_2ph*(x_w_in - x_w_sat);
        condensate_rate := m_dot_air*dW;
        h_fg_water := 2501e3 - 2.4*T_evap;
        Q_latent := condensate_rate*h_fg_water;
      end if;
    end if;
    Q_2ph_total := Q_sensible_2ph + Q_latent;
    if Q_2ph_total > Q_max_2ph_ref then
      Q_2ph_total := Q_max_2ph_ref;
      if (Q_sensible_2ph + Q_latent) > 0.0 then
        ratio := Q_max_2ph_ref/(Q_sensible_2ph + Q_latent);
        Q_sensible_2ph := Q_sensible_2ph*ratio;
        Q_latent := Q_latent*ratio;
        condensate_rate := condensate_rate*ratio;
      end if;
      ref_fully_evap := true;
    else
      ref_fully_evap := (Q_2ph_total >= Q_max_2ph_ref - 1e-6);
    end if;
    T_air_after_2ph_K := T_air_in - Q_sensible_2ph/C_air;
    h_after_2ph := h_in + Q_2ph_total/m_dot;
    x_after_2ph := if h_after_2ph >= h_v - 1e-3 then 1.0 else (h_after_2ph - h_l)/h_fg;
    Q_SH := 0.0; h_out := h_after_2ph; T_air_out_K := T_air_after_2ph_K;
    if ref_fully_evap and x_after_2ph >= 0.999 then
      cp_ref_SH := Ref.specificHeatCapacityCp(Ref.setDewState(satP));
      C_ref := m_dot*cp_ref_SH;
      Cmin_SH := min(C_ref, C_air); Cmax_SH := max(C_ref, C_air); Cr := Cmin_SH/Cmax_SH;
      NTU_SH := UA_SH/Cmin_SH;
      if abs(Cr - 1.0) < 1e-6 then eps_SH := NTU_SH/(1.0 + NTU_SH);
      elseif Cr < 1e-9 then eps_SH := 1.0 - exp(-NTU_SH);
      else eps_SH := (1.0 - exp(-NTU_SH*(1.0 - Cr)))/(1.0 - Cr*exp(-NTU_SH*(1.0 - Cr)));
      end if;
      Q_SH := max(0.0, eps_SH*Cmin_SH*(T_air_after_2ph_K - T_evap_K));
      h_out := h_after_2ph + Q_SH/m_dot;
      T_air_out_K := T_air_after_2ph_K - Q_SH/C_air;
    end if;
    P_ref_out := P_evap*(1.0 - dP_ref);
    T_ref_out := Ref.temperature(Ref.setState_ph(P_ref_out, h_out)) - 273.15;
    if h_out >= h_v then
      SH_calc := max(0.0, T_ref_out - T_evap);
    else
      SH_calc := 0.0;
    end if;
  end Evap_UA;

  model EvapUA_test "flow source → 증발기 → sink (정합 검증)"
    FlowSource src(p=5.51e5, h=336.563e3, m_flow_set=0.00458812);
    Evap_UA evap(T_air_in=50.0+273.15, RH_in=0.9, V_air_CMM=2.54, UA_2ph=25.0, UA_SH=4.0, dP_ref=0.02);
    SinkOpen snk;
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end EvapUA_test;

  model Cond_UA "응축기 UA 3-zone cascade — RefPort TwoPort + SC 출력"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    package Air = Modelica.Media.Air.MoistAir;
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    Modelica.Blocks.Interfaces.RealOutput SC "출구 과냉도 [K]";
    parameter Real T_air_in_C = 35.0, RH_in = 0.50, V_air_CMM = 25.42;
    parameter Real UA_deSH = 8.0, UA_2ph = 50.0, UA_SC = 5.0, dP_ref = 0.03, R_fric = 1e7, L_inertia = 1e5;
    parameter Modelica.Units.SI.Pressure P_atm = 101325.0;
    Real m_dot, h_in, P_cond;
    Real T_cond_K, T_cond_C, h_l_sat, h_v_sat, h_fg, T_ref_in_K, T_ref_in_C;
    Real Xw_in, x_w_in, cp_air, rho_air, m_dot_air, C_air;
    Real T_air_curr, h_ref_curr, Q_deSH, Q_2ph, Q_SC;
    Real cp_v, C_ref_v, cp_l, C_ref_l, Cmin, Cmax, Cr, NTU, eps;
    Real Q_max_deSH_ref, Q_max_2ph_ref, Q_total;
    Real h_out, T_ref_out, quality_out, SC_calc;
    Real T_air_out, RH_air_out, P_ws_out, P_w_out;
    Ref.SaturationProperties satP;
    Air.ThermodynamicState stAir;
  equation
    m_dot = (port_a.p - port_b.p)/R_fric;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    P_cond = port_a.p;
    port_b.h_outflow = h_out;
    port_a.h_outflow = port_b.h_outflow;
    SC = SC_calc;
  algorithm
    satP := Ref.setSat_p(P_cond);
    T_cond_K := Ref.saturationTemperature(P_cond);
    T_cond_C := T_cond_K - 273.15;
    h_l_sat := Ref.bubbleEnthalpy(satP);
    h_v_sat := Ref.dewEnthalpy(satP);
    h_fg := h_v_sat - h_l_sat;
    T_ref_in_K := Ref.temperature(Ref.setState_ph(P_cond, h_in));
    T_ref_in_C := T_ref_in_K - 273.15;
    Xw_in := Air.massFraction_pTphi(P_atm, T_air_in_C + 273.15, RH_in);
    x_w_in := Xw_in/(1.0 - Xw_in);
    stAir := Air.setState_pTX(P_atm, T_air_in_C + 273.15, {Xw_in, 1.0 - Xw_in});
    cp_air := Air.specificHeatCapacityCp(stAir);
    rho_air := Air.density(stAir);
    m_dot_air := rho_air*V_air_CMM/60.0;
    C_air := m_dot_air*cp_air;
    T_air_curr := T_air_in_C;
    h_ref_curr := h_in;
    Q_deSH := 0.0; Q_2ph := 0.0; Q_SC := 0.0;
    // Zone 1: De-SH
    if h_ref_curr > h_v_sat and T_air_curr < T_ref_in_C then
      cp_v := Ref.specificHeatCapacityCp(Ref.setState_pT(P_cond, T_ref_in_K));
      C_ref_v := m_dot*cp_v;
      Cmin := min(C_ref_v, C_air); Cmax := max(C_ref_v, C_air); Cr := Cmin/Cmax;
      NTU := UA_deSH/Cmin;
      eps := epsCounter(NTU, Cr);
      Q_max_deSH_ref := m_dot*(h_ref_curr - h_v_sat);
      Q_deSH := max(0.0, min(eps*Cmin*(T_ref_in_C - T_air_curr), Q_max_deSH_ref));
      T_air_curr := T_air_curr + Q_deSH/C_air;
      h_ref_curr := h_ref_curr - Q_deSH/m_dot;
    end if;
    // Zone 2: 2-phase
    if h_ref_curr > h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05 then
      NTU := UA_2ph/C_air;
      eps := epsC0(NTU);
      Q_max_2ph_ref := m_dot*(h_ref_curr - h_l_sat);
      Q_2ph := max(0.0, min(eps*C_air*(T_cond_C - T_air_curr), Q_max_2ph_ref));
      T_air_curr := T_air_curr + Q_2ph/C_air;
      h_ref_curr := h_ref_curr - Q_2ph/m_dot;
    end if;
    // Zone 3: SC
    if h_ref_curr <= h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05 then
      cp_l := Ref.specificHeatCapacityCp(Ref.setBubbleState(satP));
      C_ref_l := m_dot*cp_l;
      Cmin := min(C_ref_l, C_air); Cmax := max(C_ref_l, C_air); Cr := Cmin/Cmax;
      NTU := UA_SC/Cmin;
      eps := epsCounter(NTU, Cr);
      Q_SC := max(0.0, eps*Cmin*(T_cond_C - T_air_curr));
      T_air_curr := T_air_curr + Q_SC/C_air;
      h_ref_curr := h_ref_curr - Q_SC/m_dot;
    end if;
    Q_total := Q_deSH + Q_2ph + Q_SC;
    h_out := h_ref_curr;
    if h_out >= h_v_sat then
      T_ref_out := Ref.temperature(Ref.setState_ph(P_cond, h_out)) - 273.15;
      quality_out := 1.0 + max(0.0, (h_out - h_v_sat)/max(h_fg, 1.0));
      SC_calc := 0.0;
    elseif h_out >= h_l_sat then
      quality_out := max(0.0, min(1.0, (h_out - h_l_sat)/h_fg));
      T_ref_out := T_cond_C;
      SC_calc := 0.0;
    else
      T_ref_out := Ref.temperature(Ref.setState_ph(P_cond, h_out)) - 273.15;
      quality_out := -max(0.0, (h_l_sat - h_out)/max(h_fg, 1.0));
      SC_calc := max(0.0, T_cond_C - T_ref_out);
    end if;
    T_air_out := T_air_curr;
    P_ws_out := pSatWater(T_air_curr);
    P_w_out := x_w_in/(x_w_in + 0.622)*P_atm;
    RH_air_out := max(0.0, min(100.0, P_w_out/P_ws_out*100.0));
  end Cond_UA;

  model CondUA_test "flow source → 응축기 → open sink (정합 검증)"
    FlowSource src(p=19.07e5, h=702.725e3, m_flow_set=0.00458812);
    Cond_UA cond(T_air_in_C=35.0, RH_in=0.5, V_air_CMM=25.42, UA_deSH=8.0, UA_2ph=50.0, UA_SC=5.0, dP_ref=0.03);
    SinkOpen snk(h=437e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end CondUA_test;

  model Evap_UA_eq "증발기 UA — equation 버전 (acausal, 사이클용). 물성 R290Tab(테이블)."
    package Air = Modelica.Media.Air.MoistAir;
    HPWD.RefPort port_a "입구 (2상)";
    HPWD.RefPort port_b "출구 (과열)";
    Modelica.Blocks.Interfaces.RealOutput SH "출구 과열도 [K]";
    parameter Modelica.Units.SI.Temperature T_air_in = 20.0 + 273.15 "L3 통일: 드럼 출구 공기";
    parameter Real RH_in = 0.80, V_air_CMM = 2.42 "L3 통일: RH0.8, 2.42 CMM";
    parameter Real UA_2ph = 15.9, UA_SH = 1.0, dP_ref = 0.02, R_fric = 2e6, L_inertia = 1e5 "L3 실효 UA 캘리브레이션 (2.42CMM, 20C/RH0.8)";
    parameter Modelica.Units.SI.Pressure P_atm = 101325.0;
    Real m_dot(start=0.005, fixed=true), h_in(start=440e3), P_evap;
    Real T_evap_K(start=278.0), T_evap(start=5.0), h_l(start=212e3), h_v(start=580e3), h_fg(start=368e3);
    Real Xw_in, x_w_in, cp_air, rho_air, m_dot_air, C_air;
    Real p_w_in, p_ws_surf;
    Real NTU_2ph, eps_2ph, Q_sens_raw;
    Real Xw_sat, x_w_sat, dW_raw, cond_raw, h_fg_water, Q_lat_raw;
    Real Q_2ph_uncapped, Q_max_2ph_ref, ratio;
    Real Q_sensible_2ph, Q_latent, condensate_rate, Q_2ph_total;
    Real T_air_after_2ph_K, h_after_2ph(start=580e3), x_after_2ph;
    Real cp_ref_SH, dummy_cpbub, C_ref, Cmin_SH, Cmax_SH, Cr_SH, NTU_SH, eps_SH, Q_SH;
    Real h_out(start=607e3), T_air_out_K, P_ref_out, T_ref_out(start=293.0), SH_calc;
    Boolean is_wet, has_latent, ref_fully_evap, in_SH;
  equation
    // ── port 연동 (momentum) ──
    der(m_dot) = (port_a.p - port_b.p - R_fric*m_dot)/L_inertia;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    P_evap = port_a.p;
    port_b.h_outflow = h_out;
    port_a.h_outflow = port_b.h_outflow;
    SH = SH_calc;
    // ── 포화 ──
    T_evap_K = R290Tab.Tsat(P_evap);
    T_evap = T_evap_K - 273.15;
    (h_l, h_v, cp_ref_SH, dummy_cpbub) = satProps(P_evap);
    h_fg = h_v - h_l;
    // ── 공기 ──
    (cp_air, rho_air, x_w_in, Xw_in) = airProps(P_atm, T_air_in, RH_in);
    m_dot_air = rho_air*V_air_CMM/60.0;
    C_air = m_dot_air*cp_air;
    // ── wet 판단 ──
    p_w_in = x_w_in*P_atm/(0.621945 + x_w_in);
    p_ws_surf = Air.saturationPressure(T_evap_K);
    is_wet = p_w_in > p_ws_surf;
    // ── 2상 sensible ──
    NTU_2ph = UA_2ph/C_air;
    eps_2ph = if NTU_2ph < 50.0 then 1.0 - exp(-NTU_2ph) else 1.0;
    Q_sens_raw = max(0.0, eps_2ph*C_air*(T_air_in - T_evap_K));
    // ── latent (항상 평가, 비활성 시 0) ──
    Xw_sat = Air.massFraction_pTphi(P_atm, T_evap_K, 0.999);
    x_w_sat = Xw_sat/(1.0 - Xw_sat);
    has_latent = is_wet and (x_w_in > x_w_sat);
    dW_raw = if has_latent then eps_2ph*(x_w_in - x_w_sat) else 0.0;
    cond_raw = m_dot_air*dW_raw;
    h_fg_water = 2501e3 - 2.4*T_evap;
    Q_lat_raw = cond_raw*h_fg_water;
    // ── 냉매 한계 clamp (ratio로 비례 축소) ──
    Q_2ph_uncapped = Q_sens_raw + Q_lat_raw;
    Q_max_2ph_ref = m_dot*(h_v - h_in);
    ratio = if (Q_2ph_uncapped > Q_max_2ph_ref) and (Q_2ph_uncapped > 1e-9)
            then Q_max_2ph_ref/Q_2ph_uncapped else 1.0;
    Q_sensible_2ph = Q_sens_raw*ratio;
    Q_latent = Q_lat_raw*ratio;
    condensate_rate = cond_raw*ratio;
    Q_2ph_total = Q_sensible_2ph + Q_latent;
    ref_fully_evap = Q_2ph_uncapped >= Q_max_2ph_ref - 1e-6;
    // ── 2상 후 상태 ──
    T_air_after_2ph_K = T_air_in - Q_sensible_2ph/C_air;
    h_after_2ph = h_in + Q_2ph_total/m_dot;
    x_after_2ph = if h_after_2ph >= h_v - 1e-3 then 1.0 else (h_after_2ph - h_l)/h_fg;
    // ── SH zone (항상 평가, 비활성 시 Q_SH=0) ──
    in_SH = ref_fully_evap and (x_after_2ph >= 0.999);
    C_ref = m_dot*cp_ref_SH;
    Cmin_SH = min(C_ref, C_air);
    Cmax_SH = max(C_ref, C_air);
    Cr_SH = Cmin_SH/Cmax_SH;
    NTU_SH = UA_SH/Cmin_SH;
    eps_SH = if abs(Cr_SH - 1.0) < 1e-6 then NTU_SH/(1.0 + NTU_SH)
             elseif Cr_SH < 1e-9 then 1.0 - exp(-NTU_SH)
             else (1.0 - exp(-NTU_SH*(1.0 - Cr_SH)))/(1.0 - Cr_SH*exp(-NTU_SH*(1.0 - Cr_SH)));
    Q_SH = if in_SH then max(0.0, eps_SH*Cmin_SH*(T_air_after_2ph_K - T_evap_K)) else 0.0;
    // ── 출구 ──
    h_out = h_after_2ph + Q_SH/m_dot;
    T_air_out_K = T_air_after_2ph_K - Q_SH/C_air;
    P_ref_out = port_b.p;
    T_ref_out = R290Tab.T_ph(P_ref_out, h_out) - 273.15;
    SH_calc = if h_out >= h_v then max(0.0, T_ref_out - T_evap) else 0.0;
  end Evap_UA_eq;

  model EvapEq_test "equation 버전 단독 검증 (algorithm과 대조)"
    FlowSource src(p=5.51e5, h=336.563e3, m_flow_set=0.00458812);
    Evap_UA_eq evap(T_air_in=50.0+273.15, RH_in=0.9, V_air_CMM=2.54, UA_2ph=25.0, UA_SH=4.0, dP_ref=0.02);
    SinkOpen snk;
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end EvapEq_test;

  model Cond_UA_eq "응축기 UA 3-zone cascade — equation 버전 (acausal, 사이클용). 물성 R290Tab(테이블)."
    package Air = Modelica.Media.Air.MoistAir;
    HPWD.RefPort port_a "입구 (과열증기)";
    HPWD.RefPort port_b "출구 (과냉액)";
    Modelica.Blocks.Interfaces.RealOutput SC "출구 과냉도 [K]";
    parameter Real T_air_in_C = 14.1, RH_in = 0.70, V_air_CMM = 2.42 "L3 통일: 증발기 출구 공기(근사), 2.42 CMM (직렬 건공기 보존)";
    parameter Real UA_deSH = 15.5, UA_2ph = 90.9, UA_SC = 0.5, dP_ref = 0.03, R_fric = 1e7, L_inertia = 1e5 "L3 실효 UA 캘리브레이션 (SC존≈0: L3는 x_out>0)";
    parameter Modelica.Units.SI.Pressure P_atm = 101325.0;
    Real m_dot(start=0.005, fixed=true), h_in(start=700e3), P_cond;
    Real T_cond_K(start=328.0), T_cond_C(start=55.0), h_l_sat(start=352e3), h_v_sat(start=625e3), dummy_dew, h_fg(start=273e3), T_ref_in_K(start=360.0), T_ref_in_C(start=87.0);
    Real cp_air, rho_air, x_w_in, Xw_in, m_dot_air, C_air;
    Real cp_v, C_ref_v, Cmin_dS, Cmax_dS, Cr_dS, NTU_dS, eps_dS, Q_max_deSH, Q_deSH;
    Real T_air_1, h_ref_1;
    Real NTU_2ph, eps_2ph, Q_max_2ph, Q_2ph, T_air_2, h_ref_2;
    Real cp_l, C_ref_l, Cmin_SC, Cmax_SC, Cr_SC, NTU_SC, eps_SC, Q_SC;
    Real T_air_3, h_ref_3;
    Real h_out(start=440e3), Q_total, T_ref_out(start=323.0), quality_out, SC_calc;
    Boolean c1, c2, c3;
  equation
    // ── port 연동 (momentum) ──
    der(m_dot) = (port_a.p - port_b.p - R_fric*m_dot)/L_inertia;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    P_cond = port_a.p;
    port_b.h_outflow = h_out;
    port_a.h_outflow = port_b.h_outflow;
    SC = SC_calc;
    // ── 포화 + 입구 ──
    T_cond_K = R290Tab.Tsat(P_cond);
    T_cond_C = T_cond_K - 273.15;
    (h_l_sat, h_v_sat, dummy_dew, cp_l) = satProps(P_cond);
    h_fg = h_v_sat - h_l_sat;
    T_ref_in_K = R290Tab.T_ph(P_cond, h_in);
    T_ref_in_C = T_ref_in_K - 273.15;
    // ── 공기 ──
    (cp_air, rho_air, x_w_in, Xw_in) = airProps(P_atm, T_air_in_C + 273.15, RH_in);
    m_dot_air = rho_air*V_air_CMM/60.0;
    C_air = m_dot_air*cp_air;
    // ── Zone 1: De-SH ──
    c1 = (h_in > h_v_sat) and (T_air_in_C < T_ref_in_C);
    cp_v = dummy_dew;  // de-SH 증기 cp ≈ sat 증기 cp(cpv) — satProps서 이미 계산. Helmholtz cp_pT 대체(표준 1D 근사)
    C_ref_v = m_dot*cp_v;
    Cmin_dS = min(C_ref_v, C_air); Cmax_dS = max(C_ref_v, C_air); Cr_dS = Cmin_dS/Cmax_dS;
    NTU_dS = UA_deSH/Cmin_dS;
    eps_dS = epsCounter(NTU_dS, Cr_dS);
    Q_max_deSH = m_dot*(h_in - h_v_sat);
    Q_deSH = if c1 then max(0.0, min(eps_dS*Cmin_dS*(T_ref_in_C - T_air_in_C), Q_max_deSH)) else 0.0;
    T_air_1 = T_air_in_C + Q_deSH/C_air;
    h_ref_1 = h_in - Q_deSH/m_dot;
    // ── Zone 2: 2-phase ──
    c2 = (h_ref_1 > h_l_sat + 1e-3) and (T_air_1 < T_cond_C - 0.05);
    NTU_2ph = UA_2ph/C_air;
    eps_2ph = epsC0(NTU_2ph);
    Q_max_2ph = m_dot*(h_ref_1 - h_l_sat);
    Q_2ph = if c2 then max(0.0, min(eps_2ph*C_air*(T_cond_C - T_air_1), Q_max_2ph)) else 0.0;
    T_air_2 = T_air_1 + Q_2ph/C_air;
    h_ref_2 = h_ref_1 - Q_2ph/m_dot;
    // ── Zone 3: SC ──
    c3 = (h_ref_2 <= h_l_sat + 1e-3) and (T_air_2 < T_cond_C - 0.05);
    C_ref_l = m_dot*cp_l;
    Cmin_SC = min(C_ref_l, C_air); Cmax_SC = max(C_ref_l, C_air); Cr_SC = Cmin_SC/Cmax_SC;
    NTU_SC = UA_SC/Cmin_SC;
    eps_SC = epsCounter(NTU_SC, Cr_SC);
    Q_SC = if c3 then max(0.0, eps_SC*Cmin_SC*(T_cond_C - T_air_2)) else 0.0;
    T_air_3 = T_air_2 + Q_SC/C_air;
    h_ref_3 = h_ref_2 - Q_SC/m_dot;
    // ── 출구 ──
    Q_total = Q_deSH + Q_2ph + Q_SC;
    h_out = h_ref_3;
    T_ref_out = if h_out >= h_v_sat then R290Tab.T_ph(P_cond, h_out) - 273.15
                elseif h_out >= h_l_sat then T_cond_C
                else R290Tab.T_ph(P_cond, h_out) - 273.15;
    quality_out = if h_out >= h_v_sat then 1.0 + max(0.0, (h_out - h_v_sat)/max(h_fg, 1.0))
                  elseif h_out >= h_l_sat then max(0.0, min(1.0, (h_out - h_l_sat)/h_fg))
                  else -max(0.0, (h_l_sat - h_out)/max(h_fg, 1.0));
    SC_calc = if h_out < h_l_sat then max(0.0, T_cond_C - T_ref_out) else 0.0;
  end Cond_UA_eq;

  model CondEq_test "equation 버전 단독 검증 (algorithm과 대조)"
    FlowSource src(p=19.07e5, h=702.725e3, m_flow_set=0.00458812);
    Cond_UA_eq cond(T_air_in_C=35.0, RH_in=0.5, V_air_CMM=25.42, UA_deSH=8.0, UA_2ph=50.0, UA_SC=5.0, dP_ref=0.03);
    SinkOpen snk(h=437e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end CondEq_test;

end HPWDhx;
