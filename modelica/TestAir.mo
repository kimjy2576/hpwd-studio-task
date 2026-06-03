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


model TestFanFilterL1
  "Fan → AirVolume(C) → Filter (R-C-R): 작동점 = fan곡선 ∩ filter곡선"
  // 양단 p_ref 고정 → 정상상태에서 dp_fan = dp_filter (유량 결정)
  HPWDair.BoundaryAir_pTW src(
    p = HPWDair.MoistAir.p_ref, T = 323.15, W = 0.05);
  HPWDair.Fan_L1 fan(
    D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
    eta_h = 0.78, eta_mech = 0.95, N = 3000);
  HPWDair.AirVolume vol(
    V = 0.05, T_start = 323.15, W_start = 0.05);
  // K=500: 시스템 저항 대표값 (clean lint 단독은 더 약함).
  // 작동점이 standalone fan(V̇≈0.052) 근처에 맺히게 잡아 교차검증.
  HPWDair.Filter_L1 filt(A_face = 0.05, r_pleat = 1.0, K = 500);
  HPWDair.BoundaryAir_pTW snk(
    p = HPWDair.MoistAir.p_ref, T = 323.15, W = 0.05);
equation
  connect(src.port, fan.port_a);
  connect(fan.port_b, vol.port_a);
  connect(vol.port_b, filt.port_a);
  connect(filt.port_b, snk.port);
end TestFanFilterL1;

