package HXCmp "HX 단품 충실도 비교 — 동일 냉매입구·공기조건서 L1/L2/L3 Cond·Evap 대조"
  // 응축기 공통 BC: m=0.008 kg/s, P_in=17bar, h_in=660 kJ/kg, 공기 35°C/RH0.5
  // 증발기 공통 BC: m=0.005 kg/s, P_in=5.5bar, h_in=287 kJ/kg(2상), 공기 45°C/RH0.85
  // 방법 격리: L1 ε-NTU 평균ΔT / L2 MB 이동경계+Shah / L3 FV 셀-march 입구ΔT.

  // ───────────────────── 응축기 ─────────────────────
  model Cond_L1 "L1 UA 집중 — Cond_UA_eq"
    HPWDhx.FlowSource src(p = 17e5, h = 660e3, m_flow_set = 0.008);
    HPWDhx.Cond_UA_eq cond(T_air_in_C = 35.0, RH_in = 0.5, V_air_CMM = 25.42);
    HPWDhx.SinkOpen snk(h = 440e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L1;

  model Cond_L2 "L2 MB 이동경계 — CondenserSS (native 기하)"
    HPWDhx.FlowSource src(p = 17e5, h = 660e3, m_flow_set = 0.008);
    CondMBe.CondenserSS cond(T_air_in_C = 35.0, RH_in = 0.5);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L2;

  model Cond_L2m "L2 MB — UA 매칭(L_tube 10→7.8, 공기 19.1CMM)해 L1/L3와 conductance 근사"
    HPWDhx.FlowSource src(p = 17e5, h = 660e3, m_flow_set = 0.008);
    CondMBe.CondenserSS cond(T_air_in_C = 35.0, RH_in = 0.5, L_tube_total = 7.8, V_air_CMM = 19.1);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L2m;

  model Cond_L3 "L3 유한체적 — Cond_On (셀-march)"
    HPWDevap.FlowSource src(m_dot = 0.008, h = 660e3, p = 17e5);
    HPWDevap.Cond_On cond(T_air_in = 35.0, RH_in = 0.5);
    HPWDevap.OpenSink snk(h = 440e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L3;

  // ───────────────────── 증발기 (공통 ṁ=5g/s, h_in=287kJ/kg 2상, 공기45°C/RH0.85, P~5.5bar) ─────────────────────
  model Evap_L1 "L1 UA 집중 — Evap_UA_eq (UA를 L3 유효UA≈80에 매칭: 2ph=64,SH=16)"
    HPWDhx.FlowSource src(p = 5.5e5, h = 287e3, m_flow_set = 0.005);
    HPWDhx.Evap_UA_eq evap(T_air_in = 45.0 + 273.15, RH_in = 0.85, V_air_CMM = 2.54, UA_2ph = 64.0, UA_SH = 16.0);
    HPWDhx.SinkOpen snk(h = 580e3);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end Evap_L1;

  model Evap_L1n "L1 native 사이징 (참고 — 기본 UA 8.75/1.4)"
    HPWDhx.FlowSource src(p = 5.5e5, h = 287e3, m_flow_set = 0.005);
    HPWDhx.Evap_UA_eq evap(T_air_in = 45.0 + 273.15, RH_in = 0.85, V_air_CMM = 2.54);
    HPWDhx.SinkOpen snk(h = 580e3);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end Evap_L1n;

  model Evap_L2 "L2 MB 동적 — EvaporatorMBdyn (FlowBC P_e 자기조절, 5g/s 안정점)"
    EvapMBe.EvaporatorMBdyn evap(T_air_in_C = 45.0, RH_in = 0.85, V_air_CMM = 2.54, is_wet = false);
    EvapMBe.FlowBC inlet(m_flow_set = -0.005, k_p = 0.0, h_set = 287e3);
    EvapMBe.FlowBC outlet(m_flow_set = 0.0, k_p = 0.005/5.5e5, h_set = 0.0);
  equation
    connect(inlet.port, evap.port_a);
    connect(outlet.port, evap.port_b);
  end Evap_L2;

  model Evap_L3 "L3 유한체적 동적 — Evap_On (셀-march)"
    HPWDevap.FlowSource src(m_dot = 0.005, h = 287e3, p = 5.5e5);
    HPWDevap.Evap_On evap(T_air_in = 45.0, RH_in = 0.85);
    HPWDevap.OpenSink snk(h = 580e3);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end Evap_L3;
end HXCmp;
