package HPWDcpl "냉매-공기 커플드 HX (L1) — RefPort + AirPort 양쪽 포트"
  // 한 물리적 열교환기에 냉매(안쪽)·공기(바깥쪽)를 동시 모델.
  // 냉매측: momentum flow + 포화온도(T_sat(P))가 코일 표면, Q 흡수/방출.
  // 공기측: bypass-factor (표면 = T_sat), HPWDair.MoistAir 사용 (air 링과 일관).
  // Q는 공기측에서 한 번 계산 → 냉매가 흡수(evap)/방출(cond). 양측 자동 일관.
  // L1 가정: 코일 전체 표면 = T_sat (냉매측 막저항·SH/SC zone 표면온도차 무시).

  // =============================================================
  // Evap_coupled: 증발기 — 냉매 흡열 + 공기 냉각·제습.
  // =============================================================
  model Evap_coupled
    "증발기 L1 커플드 (냉매 RefPort 흡열 + 공기 AirPort 냉각·제습)"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a "냉매 입구 (2상)";
    HPWD.RefPort port_b "냉매 출구 (과열)";
    HPWDair.AirPort air_a "공기 입구";
    HPWDair.AirPort air_b "공기 출구";
    Modelica.Blocks.Interfaces.RealOutput SH "냉매 과열도 [K]";

    // ── 냉매측 (momentum) ──
    parameter Real R_fric = 2e6 "냉매 마찰계수";
    parameter Real L_inertia = 1e5 "냉매 관성";
    // ── 공기측 (bypass-factor + ΔP) ──
    parameter Real BF = 0.2 "bypass factor (ε=1−BF)";
    parameter Modelica.Units.SI.Area A_face = 0.05 "코일 정면적";
    parameter Real K_air = 50 "공기측 핀 저항 (Pa·s²/m²)";

    // 냉매 변수
    Real m_dot(start = 0.005, fixed = true) "냉매 유량";
    Modelica.Units.SI.SpecificEnthalpy h_in_ref(start = 440e3);
    Modelica.Units.SI.SpecificEnthalpy h_out_ref(start = 580e3);
    Modelica.Units.SI.Pressure P_evap;
    Modelica.Units.SI.Temperature T_evap_K(start = 283);
    Real T_evap_C;
    Modelica.Units.SI.SpecificEnthalpy h_l(start = 270e3), h_v(start = 580e3);
    Real T_ref_out_C(start = 12);
    Real cp_dewd, cp_bubd "satProps 더미 (cp, 미사용)";

    // 공기 변수 (bypass-factor)
    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05);
    Real W_in(unit = "kg/kg"), W_out(unit = "kg/kg"), W_sat_s(unit = "kg/kg");
    Modelica.Units.SI.SpecificEnthalpy h_in_air, h_out_air;
    Modelica.Units.SI.Temperature T_air_in, T_air_out;
    Modelica.Units.SI.MassFlowRate m_cond "응축수 (배수)";
    Modelica.Units.SI.Power Q "공기→냉매 흡열";
    Modelica.Units.SI.Density rho_da;
    Modelica.Units.SI.Velocity u;
    Modelica.Units.SI.Pressure dp_air;

  equation
    // ── 냉매 momentum + 포트 ──
    der(m_dot) = (port_a.p - port_b.p - R_fric*m_dot)/L_inertia;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in_ref = inStream(port_a.h_outflow);
    P_evap = port_a.p;
    port_b.h_outflow = h_out_ref;
    port_a.h_outflow = port_b.h_outflow;

    // ── 냉매 포화 (코일 표면온도) — satProps로 scalar 추출 (record 변수 회피) ──
    T_evap_K = Ref.saturationTemperature(P_evap);
    T_evap_C = T_evap_K - 273.15;
    (h_l, h_v, cp_dewd, cp_bubd) = HPWDhx.satProps(P_evap);

    // ── 공기 bypass-factor (표면 = T_evap) ──
    m_flow_da = air_a.m_flow_da;
    air_a.m_flow_da + air_b.m_flow_da = 0;
    W_in = inStream(air_a.W_outflow);
    h_in_air = inStream(air_a.h_tilde_outflow);
    T_air_in = HPWDair.MoistAir.T_from_h(h_in_air, W_in);
    W_sat_s = HPWDair.MoistAir.W_sat(T_evap_K);
    T_air_out = BF*T_air_in + (1 - BF)*T_evap_K;
    W_out = min(W_in, BF*W_in + (1 - BF)*W_sat_s);
    h_out_air = HPWDair.MoistAir.h_da_fn(T_air_out, W_out);
    m_cond = m_flow_da*(W_in - W_out);
    Q = m_flow_da*(h_in_air - h_out_air)
        - m_cond*HPWDair.MoistAir.cp_w*(T_air_out - HPWDair.MoistAir.T0);

    // ── 냉매가 Q 흡수 ──
    h_out_ref = h_in_ref + Q/m_dot;
    T_ref_out_C = Ref.temperature(Ref.setState_ph(port_b.p, h_out_ref)) - 273.15;
    SH = if h_out_ref >= h_v then max(0.0, T_ref_out_C - T_evap_C) else 0.0;

    // ── 공기측 ΔP + stream (출구 처리상태, 양 포트) ──
    rho_da = HPWDair.MoistAir.rho_da_fn(T_air_in, W_in);
    u = m_flow_da/(rho_da*A_face);
    dp_air = K_air*u*abs(u);
    air_b.p = air_a.p - dp_air;
    air_a.W_outflow = W_out;
    air_b.W_outflow = W_out;
    air_a.h_tilde_outflow = h_out_air;
    air_b.h_tilde_outflow = h_out_air;
  end Evap_coupled;


  // =============================================================
  // Cond_coupled: 응축기 — 냉매 방열 + 공기 현열 가열 (dry).
  // =============================================================
  model Cond_coupled
    "응축기 L1 커플드 (냉매 RefPort 방열 + 공기 AirPort 가열)"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a "냉매 입구 (과열증기)";
    HPWD.RefPort port_b "냉매 출구 (과냉액)";
    HPWDair.AirPort air_a "공기 입구";
    HPWDair.AirPort air_b "공기 출구";
    Modelica.Blocks.Interfaces.RealOutput SC "냉매 과냉도 [K]";

    parameter Real R_fric = 1e7 "냉매 마찰계수";
    parameter Real L_inertia = 1e5 "냉매 관성";
    parameter Real BF = 0.2 "bypass factor";
    parameter Modelica.Units.SI.Area A_face = 0.05 "코일 정면적";
    parameter Real K_air = 50 "공기측 핀 저항";

    Real m_dot(start = 0.005, fixed = true) "냉매 유량";
    Modelica.Units.SI.SpecificEnthalpy h_in_ref(start = 700e3);
    Modelica.Units.SI.SpecificEnthalpy h_out_ref(start = 440e3);
    Modelica.Units.SI.Pressure P_cond;
    Modelica.Units.SI.Temperature T_cond_K(start = 328);
    Real T_cond_C;
    Modelica.Units.SI.SpecificEnthalpy h_l(start = 350e3), h_v(start = 620e3);
    Real T_ref_out_C(start = 50);
    Real cp_dewd, cp_bubd "satProps 더미 (cp, 미사용)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05);
    Real W_in(unit = "kg/kg"), W_out(unit = "kg/kg");
    Modelica.Units.SI.SpecificEnthalpy h_in_air, h_out_air;
    Modelica.Units.SI.Temperature T_air_in, T_air_out;
    Modelica.Units.SI.Power Q "냉매→공기 방열";
    Modelica.Units.SI.Density rho_da;
    Modelica.Units.SI.Velocity u;
    Modelica.Units.SI.Pressure dp_air;

  equation
    // ── 냉매 momentum + 포트 ──
    der(m_dot) = (port_a.p - port_b.p - R_fric*m_dot)/L_inertia;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in_ref = inStream(port_a.h_outflow);
    P_cond = port_a.p;
    port_b.h_outflow = h_out_ref;
    port_a.h_outflow = port_b.h_outflow;

    // ── 냉매 포화 (코일 표면온도) — satProps로 scalar 추출 ──
    T_cond_K = Ref.saturationTemperature(P_cond);
    T_cond_C = T_cond_K - 273.15;
    (h_l, h_v, cp_dewd, cp_bubd) = HPWDhx.satProps(P_cond);

    // ── 공기 bypass-factor 가열 (표면 = T_cond, dry) ──
    m_flow_da = air_a.m_flow_da;
    air_a.m_flow_da + air_b.m_flow_da = 0;
    W_in = inStream(air_a.W_outflow);
    h_in_air = inStream(air_a.h_tilde_outflow);
    T_air_in = HPWDair.MoistAir.T_from_h(h_in_air, W_in);
    T_air_out = BF*T_air_in + (1 - BF)*T_cond_K;
    W_out = W_in;
    h_out_air = HPWDair.MoistAir.h_da_fn(T_air_out, W_out);
    Q = m_flow_da*(h_out_air - h_in_air);

    // ── 냉매가 Q 방출 ──
    h_out_ref = h_in_ref - Q/m_dot;
    T_ref_out_C = Ref.temperature(Ref.setState_ph(port_b.p, h_out_ref)) - 273.15;
    SC = if h_out_ref < h_l then max(0.0, T_cond_C - T_ref_out_C) else 0.0;

    // ── 공기측 ΔP + stream ──
    rho_da = HPWDair.MoistAir.rho_da_fn(T_air_in, W_in);
    u = m_flow_da/(rho_da*A_face);
    dp_air = K_air*u*abs(u);
    air_b.p = air_a.p - dp_air;
    air_a.W_outflow = W_out;
    air_b.W_outflow = W_out;
    air_a.h_tilde_outflow = h_out_air;
    air_b.h_tilde_outflow = h_out_air;
  end Cond_coupled;

end HPWDcpl;
