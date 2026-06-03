within ;
// 커플드 HX 단독 검증 — 냉매 경계(Source/Sink) + 공기 경계(BoundaryAir).
// 검증 포인트: T_sat(P)가 코일 표면 / 공기 냉각·제습(evap)·가열(cond) /
//   냉매 흡열·방열 Q = 공기측 Q (m_dot·Δh = Q) 정확 일치.
// 로드 순서: Modelica, HelmholtzMedia, HPWD.mo, EvapUA.mo, HPWDair.mo, Coupled.mo

model TestEvapCoupled "Evap_coupled 단독 — 6.4bar(T_evap≈10°C), 공기 31°C/W0.018 → 냉각·제습"
  HPWD.Source ref_src(p = 6.4e5, h = 440e3) "냉매 2상 입구";
  HPWDcpl.Evap_coupled evap(R_fric = 2e6, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWD.Sink ref_snk(p = 6.3e5, h = 250e3);
  HPWDair.BoundaryAir_mflow air_src(m_flow_da = -0.02, T = 304.15, W = 0.018);
  HPWDair.BoundaryAir_pTW air_snk(p = HPWDair.MoistAir.p_ref, T = 304.15, W = 0.018);
equation
  connect(ref_src.port, evap.port_a);
  connect(evap.port_b, ref_snk.port);
  connect(air_src.port, evap.air_a);
  connect(evap.air_b, air_snk.port);
  // 검증값(t=5): T_evap=10.19°C, 공기 31→14.35°C, W 0.018→0.00978,
  //   m_cond=0.164g/s, Q=751.3W, m_dot·(h_out−h_in)=751.3W ✓, SH=2.17K
end TestEvapCoupled;

model TestCondCoupled "Cond_coupled 단독 — 16bar(T_cond≈47°C), 공기 14°C/W0.010 → 가열"
  HPWD.Source ref_src(p = 16e5, h = 700e3) "냉매 과열증기 입구";
  HPWDcpl.Cond_coupled cond(R_fric = 1e7, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWD.Sink ref_snk(p = 15.85e5, h = 440e3);
  HPWDair.BoundaryAir_mflow air_src(m_flow_da = -0.02, T = 287.15, W = 0.010);
  HPWDair.BoundaryAir_pTW air_snk(p = HPWDair.MoistAir.p_ref, T = 287.15, W = 0.010);
equation
  connect(ref_src.port, cond.port_a);
  connect(cond.port_b, ref_snk.port);
  connect(air_src.port, cond.air_a);
  connect(cond.air_b, air_snk.port);
  // 검증값(t=5): T_cond=46.88°C, 공기 14→40.31°C, W 불변,
  //   Q=538.5W, m_dot·(h_in−h_out)=538.5W ✓, SC=0(2상 출구 근접)
end TestCondCoupled;
