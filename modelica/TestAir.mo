// =============================================================
// TestAir.mo — air-side L1 컴포넌트 단독 검증 모델 모음.
//   HPWDair.mo 를 먼저 load 한 뒤 사용.
// =============================================================

model TestFanL1 "Fan_L1 단독: flow source → fan → pressure sink (정방향 a→b)"
  // 50°C, W=0.05 공기를 0.0525 kg_da/s 공급 (음수=유출)
  HPWDair.BoundaryAir_mflow src(
    m_flow_da = -0.0525, T = 323.15, W = 0.05);
  HPWDair.Fan_L1 fan(
    D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
    eta_h = 0.78, eta_mech = 0.95, N = 3000);
  HPWDair.BoundaryAir_pTW snk(
    p = HPWDair.MoistAir.p_ref, T = 323.15, W = 0.05);
equation
  connect(src.port, fan.port_a);
  connect(fan.port_b, snk.port);
end TestFanL1;
