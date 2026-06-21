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
    T_evap_K = R290Tab.Tsat(max(P_evap, 1e5));
    T_evap_C = T_evap_K - 273.15;
    (h_l, h_v, cp_dewd, cp_bubd) = HPWDhx.satProps(max(P_evap, 1e5));

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
    T_ref_out_C = R290Tab.T_ph(max(port_b.p, 1e5), h_out_ref) - 273.15;
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
    T_cond_K = R290Tab.Tsat(max(P_cond, 1e5));
    T_cond_C = T_cond_K - 273.15;
    (h_l, h_v, cp_dewd, cp_bubd) = HPWDhx.satProps(max(P_cond, 1e5));

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
    T_ref_out_C = R290Tab.T_ph(max(port_b.p, 1e5), h_out_ref) - 273.15;
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


  // =============================================================
  // Cycle_coupled_open: 냉매 사이클 + 공기(evap→cond, 유량 prescribed).
  // 드럼/팬 없는 open 경로 — 냉매-공기 커플링 코어 검증용 (Stage 2a).
  // init: 운전점 fixedState (HP 16bar / LP 6.4bar, 유량 6g/s, N 고정).
  //   rest init은 merged HX의 Q/m_dot가 m_dot=0에서 발산하므로 사용 불가.
  // =============================================================
  model Cycle_coupled_open
    "냉매 사이클 + 공기 evap→cond 커플 (유량 prescribed, open 경로)"
    parameter Real m_air = 0.04 "공기 유량 [kg_da/s] (드럼 출구 가정)";
    parameter Modelica.Units.SI.Temperature T_air_in = 304.15 "evap 입구 공기온도";
    parameter Real W_air_in = 0.018 "evap 입구 절대습도";

    HPWD.Comp_Theoretical comp(t_ramp = 0.0);
    HPWDcycle.Volume vol1(p_start = 16e5,  h_start = 665e3, fixedState = true);
    HPWDcpl.Cond_coupled cond(m_dot(start = 0.006));
    HPWDcycle.Volume vol2(p_start = 15.5e5, h_start = 345e3, fixedState = true);
    HPWDcycle.EEV_Orifice_ctrl eev(m_dot(start = 0.006));
    HPWDcycle.Volume vol3(p_start = 6.5e5, h_start = 345e3, fixedState = true);
    HPWDcpl.Evap_coupled evap(m_dot(start = 0.006));
    HPWDcycle.Volume vol4(p_start = 6.4e5, h_start = 595e3, fixedState = true);
    HPWDctrl.PI_Controller ctrl(I(fixed = true));

    HPWDair.BoundaryAir_mflow air_src(m_flow_da = -m_air, T = T_air_in, W = W_air_in);
    HPWDair.BoundaryAir_pTW air_snk(p = HPWDair.MoistAir.p_ref, T = T_air_in, W = W_air_in);
  equation
    // ── 냉매 루프 ──
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    // ── PI SH 제어 ──
    connect(evap.SH, ctrl.SH_meas);
    connect(ctrl.opening, eev.opening);
    // ── 공기 경로: 입구 → evap(냉각·제습) → cond(가열) → 출구 ──
    connect(air_src.port, evap.air_a);
    connect(evap.air_b, cond.air_a);
    connect(cond.air_b, air_snk.port);
  end Cycle_coupled_open;

  // =============================================================
  // Cycle_coupled_closed: 완전 커플 HPWD (Stage 2b).
  // 냉매 사이클 + 공기 폐루프(drum→fan→evap→cond→drum) + 드럼 건조 + 외기손실.
  // merged HX가 양 사이클 공유. 공기유량은 fan↔저항 balance로 자기결정
  //   (냉매용량 ~10g/s에 맞추려 merged HX K_air=1000 throttle).
  // init: 냉매 운전점 fixedState + 공기 fixedState (volRef=압력앵커).
  //
  // ★ 핵심 물리 발견: 닫힌 공기 루프는 압축기 일(W_comp)을 버릴 열 sink가 필수.
  //   에너지 균형 W_comp = 건조잠열 + 외기손실(Q_amb). sink 없으면 잉여열이
  //   공기 가열→T_evap↑→제습 정지→공기 포화→드럼 정지→양의피드백 폭주(초임계).
  //   → drum.UA_amb로 외기손실 모델 → 균형 닫힘(WBAL~0, EBAL~0), 아임계 유지.
  //
  // 현 상태(검증, K_air=300/UA_amb=100): 구조 완성·물/에너지 균형(WBAL~0.0002,
  //   EBAL~+0.7W)·Pc 안정 수렴·드럼 건조 진행. checkModel 249/249.
  //   운전점: Pc=24.3bar Pe=8.5bar, T_cond=67°C T_evap=21°C, W_comp=581W,
  //   SMER=2.47 kg/kWh (실 HPWD 우수 범위), 건조 X 0.6->0.05 ~1.1hr.
  //   공기유량 0.055kg/s (K_air=300 throttle), cond 공기 23->58°C 열풍.
  //   외기손실 Qamb~597W. 운전점 init이 파라미터 급변에 취약(K_air<200 등 큰
  //   변경시 t~0.06s 발산) — 추가 개선시 init 재튜닝 동반 필요.
  // =============================================================
  model Cycle_coupled_closed
    "커플 HPWD: 냉매 사이클 + 공기 폐루프 (drum 건조 + fan 순환)"
    // ── 냉매 사이클 (Cycle_coupled_open과 동일 init) ──
    HPWD.Comp_Theoretical comp(t_ramp = 0.0);
    HPWDcycle.Volume vol1(p_start = 16e5,  h_start = 665e3, fixedState = true);
    HPWDcpl.Cond_coupled cond(m_dot(start = 0.006), K_air = 300);
    HPWDcycle.Volume vol2(p_start = 15.5e5, h_start = 345e3, fixedState = true);
    HPWDcycle.EEV_Orifice_ctrl eev(m_dot(start = 0.006));
    HPWDcycle.Volume vol3(p_start = 6.5e5, h_start = 345e3, fixedState = true);
    HPWDcpl.Evap_coupled evap(m_dot(start = 0.006), K_air = 300);
    HPWDcycle.Volume vol4(p_start = 6.4e5, h_start = 595e3, fixedState = true);
    HPWDctrl.PI_Controller ctrl(I(fixed = true));
    // ── 공기 폐루프 (R: drum, fan / C: volRef 앵커 + volB,C,D) ──
    HPWDair.Drum_L1 drum(
      m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
      A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 305.0,
      UA_amb = 100.0, T_amb = 298.15);
    HPWDair.Fan_L1 fan(
      D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
      eta_h = 0.78, eta_mech = 0.95, N = 3000);
    HPWDair.AirVolumeC volRef(
      V = 0.05, p_start = HPWDair.MoistAir.p_ref,
      T_start = 304.0, W_start = 0.018, fixedState = true);
    HPWDair.AirVolume volB(V = 0.05, T_start = 305.0, W_start = 0.018, fixedState = true);
    HPWDair.AirVolume volC(V = 0.05, T_start = 291.0, W_start = 0.012, fixedState = true);
    HPWDair.AirVolume volD(V = 0.05, T_start = 333.0, W_start = 0.012, fixedState = true);
  equation
    // ── 냉매 루프 ──
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(evap.SH, ctrl.SH_meas);
    connect(ctrl.opening, eev.opening);
    // ── 공기 폐루프: drum→volRef→fan→volB→evap→volC→cond→volD→drum ──
    connect(drum.port_b,   volRef.port_a);
    connect(volRef.port_b, fan.port_a);
    connect(fan.port_b,    volB.port_a);
    connect(volB.port_b,   evap.air_a);
    connect(evap.air_b,    volC.port_a);
    connect(volC.port_b,   cond.air_a);
    connect(cond.air_b,    volD.port_a);
    connect(volD.port_b,   drum.port_a);
  end Cycle_coupled_closed;


  model Cycle_coupled_closed_L2air
    "커플 HPWD with L2 공기측 (Fan_L2 손실분해 + Drum_L2 감률/흡착). 냉매측·init은 Cycle_coupled_closed와 동일."
    // ── 냉매 사이클 (Cycle_coupled_closed와 동일 init) ──
    HPWD.Comp_Theoretical comp(t_ramp = 0.0);
    HPWDcycle.Volume vol1(p_start = 16e5,  h_start = 665e3, fixedState = true);
    HPWDcpl.Cond_coupled cond(m_dot(start = 0.006), K_air = 300);
    HPWDcycle.Volume vol2(p_start = 15.5e5, h_start = 345e3, fixedState = true);
    HPWDcycle.EEV_Orifice_ctrl eev(m_dot(start = 0.006));
    HPWDcycle.Volume vol3(p_start = 6.5e5, h_start = 345e3, fixedState = true);
    HPWDcpl.Evap_coupled evap(m_dot(start = 0.006), K_air = 300);
    HPWDcycle.Volume vol4(p_start = 6.4e5, h_start = 595e3, fixedState = true);
    HPWDctrl.PI_Controller ctrl(I(fixed = true));
    // ── 공기 폐루프 (L2: Drum_L2 감률+흡착, Fan_L2 손실분해) ──
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
    // ── 냉매 루프 ──
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(evap.SH, ctrl.SH_meas);
    connect(ctrl.opening, eev.opening);
    // ── 공기 폐루프: drum→volRef→fan→volB→evap→volC→cond→volD→drum ──
    connect(drum.port_b,   volRef.port_a);
    connect(volRef.port_b, fan.port_a);
    connect(fan.port_b,    volB.port_a);
    connect(volB.port_b,   evap.air_a);
    connect(evap.air_b,    volC.port_a);
    connect(volC.port_b,   cond.air_a);
    connect(cond.air_b,    volD.port_a);
    connect(volD.port_b,   drum.port_a);
  end Cycle_coupled_closed_L2air;

end HPWDcpl;
