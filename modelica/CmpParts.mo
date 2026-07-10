package CmpParts "부품 단독 충실도 비교 — 동일 BC에서 L1/L2/L3 압축기·EEV·응축기·증발기 대조"
  // ══════════════════════════════════════════════════════════════
  // 공통 BC (L3 사이클 Cycle_L3_coldstart_PI 정착점 t=200 기준)
  //   Pe = 5.000 bar,  Pc = 9.912 bar,  mdot = 2.27074 g/s,  N = 1800 rpm
  //   공기 오픈루프 2.42 CMM: 증발기 입구 20°C/RH0.8 → 응축기 입구 14.135°C/RH0.993
  //
  // [압축기] P_suc=5.000b, h_suc=587.309 kJ/kg (SH 6K), P_dis=9.912b, N=1800
  // [EEV]    P_in=9.912b, h_in=364.422 kJ/kg (응축기 출구), P_out=5.000b, 개도 25.63%
  // [응축기] P_in=9.912b, h_in=627.818 kJ/kg, mdot=2.27074 g/s, 공기 14.135°C/RH0.993
  // [증발기] P_in=5.000b, h_in=365.313 kJ/kg (2상), mdot=2.27074 g/s, 공기 20°C/RH0.8
  //
  // L3 기준출력: Cond Q=599.1W h_out=363.98 / Evap Q=513.3W h_out=591.35
  //              Comp mdot=2.271 g/s / EEV mdot=2.276 g/s
  // 방법 격리: L1 이론·ε-NTU / L2 반경험·이동경계 / L3 물리·유한체적
  // ══════════════════════════════════════════════════════════════

  constant Real P_e = 5.000e5;
  constant Real P_c = 9.912e5;
  constant Real m_ref = 0.00227074;
  constant Real h_suc = 587309.3;
  constant Real h_cond_in = 627.818e3;
  constant Real h_eev_in = 364.422e3;
  constant Real h_evap_in = 365.313e3;

  // ───────────────────── 압축기 (P_suc·h_suc·P_dis 고정) ─────────────────────
  model Comp_L1 "L1 이론 압축기 — Comp_Theoretical (eta_vol·eta_isen 상수)"
    EevMB.PBnd suc(p = P_e, h = h_suc);
    HPWD.Comp_Theoretical comp(V_disp = 7.5e-6, N = 1800.0, eta_vol = 0.88, eta_isen = 0.68);
    EevMB.PBnd dis(p = P_c, h = 0);
  equation
    connect(suc.port, comp.port_a);
    connect(comp.port_b, dis.port);
  end Comp_L1;

  model Comp_L2 "L2 반경험 압축기 — Comp_Winandy (흡입가열·ηv(rp)·over/under-comp)"
    EevMB.PBnd suc(p = P_e, h = h_suc);
    HPWD.Comp_Winandy comp(V_disp = 7.5e-6, N = 1800.0);
    EevMB.PBnd dis(p = P_c, h = 0);
  equation
    connect(suc.port, comp.port_a);
    connect(comp.port_b, dis.port);
  end Comp_L2;

  model Comp_L3 "L3 물리 압축기 — Comp_Chamber (chamber 1-cycle 평균, 밸브·누설·마찰)"
    EevMB.PBnd suc(p = P_e, h = h_suc);
    HPWDon.Comp_Chamber comp(V_disp_cm3 = 7.5);
    EevMB.PBnd dis(p = P_c, h = 0);
    Modelica.Blocks.Sources.Constant Nsig(k = 1800.0);
  equation
    connect(Nsig.y, comp.N);
    connect(suc.port, comp.port_a);
    connect(comp.port_b, dis.port);
  end Comp_L3;

  // ───────────────────── EEV (P_in·h_in·P_out 고정, 개도 25.63%) ─────────────────────
  model Eev_L1 "L1 오리피스 — EEV_Orifice_ctrl (개도→phi 매핑, momentum)"
    EevMB.PBnd inlet(p = P_c, h = h_eev_in);
    HPWDcycle.EEV_Orifice_ctrl eev;
    EevMB.PBnd outlet(p = P_e, h = 0);
    Modelica.Blocks.Sources.Constant openSig(k = 25.63);
  equation
    connect(openSig.y, eev.opening);
    connect(inlet.port, eev.port_a);
    connect(eev.port_b, outlet.port);
  end Eev_L1;

  model Eev_L2 "L2 MB — EEV_MB (Cd(Re)·서브쿨·choke)"
    EevMB.PBnd inlet(p = P_c, h = h_eev_in);
    EevMB.EEV_MB eev;
    EevMB.PBnd outlet(p = P_e, h = 0);
    Modelica.Blocks.Sources.Constant openSig(k = 25.63);
  equation
    connect(openSig.y, eev.opening);
    connect(inlet.port, eev.port_a);
    connect(eev.port_b, outlet.port);
  end Eev_L2;

  model Eev_L3 "L3 needle-cone — EEV_On (기하 A_throat·Re-Cd·2상 choke)"
    EevMB.PBnd inlet(p = P_c, h = h_eev_in);
    HPWDon.EEV_On eev(D_seat = 1.0e-3, stroke_max = 1.0e-3);
    EevMB.PBnd outlet(p = P_e, h = 0);
    Modelica.Blocks.Sources.Constant openSig(k = 25.63);
  equation
    connect(openSig.y, eev.opening);
    connect(inlet.port, eev.port_a);
    connect(eev.port_b, outlet.port);
  end Eev_L3;

  // ───────────────────── 응축기 (P_in·h_in·mdot·공기 고정) ─────────────────────
  model Cond_L1 "L1 ε-NTU 3존 — Cond_UA_eq"
    HPWDhx.FlowSource src(p = P_c, h = h_cond_in, m_flow_set = m_ref);
    HPWDhx.Cond_UA_eq cond(T_air_in_C = 14.135, RH_in = 0.993, V_air_CMM = 2.42);
    HPWDhx.SinkOpen snk(h = 340e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L1;

  model Cond_L2 "L2 이동경계 — CondenserSS (native 기하: 5.05 m², 2-row, FPI12)"
    HPWDhx.FlowSource src(p = P_c, h = h_cond_in, m_flow_set = m_ref);
    CondMBe.CondenserSS cond(T_air_in_C = 14.135, RH_in = 0.993);
    HPWDhx.SinkOpen snk;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L2;

  model Cond_L3 "L3 유한체적 — Cond_On (셀-march, 1.28 m², 6-row slit, FPI22)"
    HPWDevap.FlowSource src(m_dot = m_ref, h = h_cond_in, p = P_c);
    HPWDevap.Cond_On cond(T_air_in = 14.135, RH_in = 0.993);
    HPWDevap.OpenSink snk(h = 340e3);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end Cond_L3;

  // ───────────────────── 증발기 (P_in·h_in·mdot·공기 고정) ─────────────────────
  model Evap_L1 "L1 ε-NTU 2존 — Evap_UA_eq (습코일)"
    HPWDhx.FlowSource src(p = P_e, h = h_evap_in, m_flow_set = m_ref);
    HPWDhx.Evap_UA_eq evap(T_air_in = 20.0 + 273.15, RH_in = 0.8, V_air_CMM = 2.42);
    HPWDhx.SinkOpen snk(h = 600e3);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end Evap_L1;

  model Evap_L2 "L2 이동경계 동적 — EvaporatorMBdyn (FlowBC로 P_e 자기조절)"
    EvapMBe.EvaporatorMBdyn evap(T_air_in_C = 20.0, RH_in = 0.8, V_air_CMM = 2.42, is_wet = true);
    EvapMBe.FlowBC inlet(m_flow_set = -m_ref, k_p = 0.0, h_set = h_evap_in);
    EvapMBe.FlowBC outlet(m_flow_set = 0.0, k_p = m_ref/P_e, h_set = 0.0);
  equation
    connect(inlet.port, evap.port_a);
    connect(outlet.port, evap.port_b);
  end Evap_L2;

  model Evap_L3 "L3 유한체적 — Evap_On (셀-march, 습코일 제습)"
    HPWDevap.FlowSource src(m_dot = m_ref, h = h_evap_in, p = P_e);
    HPWDevap.Evap_On evap(T_air_in = 20.0, RH_in = 0.8);
    HPWDevap.OpenSink snk(h = 600e3);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end Evap_L3;
end CmpParts;
