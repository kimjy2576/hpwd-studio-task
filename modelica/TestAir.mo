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


model TestDrumL1
  "Drum_L1 단독: 60°C 건조공기 → 젖은 드럼(X0=0.6) → sink (건조 트랜지언트)"
  // flow source: 60°C, W=0.01, 0.05 kg_da/s 공급 (음수=유출)
  HPWDair.BoundaryAir_mflow src(
    m_flow_da = -0.05, T = 333.15, W = 0.01);
  HPWDair.Drum_L1 drum(
    m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
    A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 298.15);
  HPWDair.BoundaryAir_pTW snk(
    p = HPWDair.MoistAir.p_ref, T = 333.15, W = 0.01);
equation
  connect(src.port, drum.port_a);
  connect(drum.port_b, snk.port);
end TestDrumL1;


model TestEvapAirL1
  "EvapAir_L1 단독: 습한 더운 공기(30°C,W=0.022) → 증발기(T_evap=10°C) → sink"
  HPWDair.BoundaryAir_mflow src(
    m_flow_da = -0.05, T = 303.15, W = 0.022);
  HPWDair.EvapAir_L1 evap(
    T_evap = 283.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.BoundaryAir_pTW snk(
    p = HPWDair.MoistAir.p_ref, T = 303.15, W = 0.022);
equation
  connect(src.port, evap.port_a);
  connect(evap.port_b, snk.port);
end TestEvapAirL1;


model TestCondAirL1
  "CondAir_L1 단독: 식은 건조공기(14°C,W=0.0105) → 응축기(T_cond=60°C) → sink"
  HPWDair.BoundaryAir_mflow src(
    m_flow_da = -0.05, T = 287.15, W = 0.0105);
  HPWDair.CondAir_L1 cond(
    T_cond = 333.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.BoundaryAir_pTW snk(
    p = HPWDair.MoistAir.p_ref, T = 287.15, W = 0.0105);
equation
  connect(src.port, cond.port_a);
  connect(cond.port_b, snk.port);
end TestCondAirL1;


model TestAirRingL1
  "Air 링 L1: drum→fan→evap→cond→drum (CRCR, volRef만 압축성=압력앵커)"
  // ── R 컴포넌트 4개 ──
  HPWDair.Drum_L1 drum(
    m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
    A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 298.15);
  HPWDair.Fan_L1 fan(
    D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
    eta_h = 0.78, eta_mech = 0.95, N = 3000);
  HPWDair.EvapAir_L1 evap(
    T_evap = 283.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.CondAir_L1 cond(
    T_cond = 333.15, BF = 0.2, A_face = 0.05, K_air = 50);
  // ── C 요소 4개 (volRef = 압축성 압력앵커, 나머지 비압축) ──
  HPWDair.AirVolumeC volRef(
    V = 0.05, p_start = HPWDair.MoistAir.p_ref,
    T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volB(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volC(
    V = 0.05, T_start = 288.15, W_start = 0.010, fixedState = true);
  HPWDair.AirVolume volD(
    V = 0.05, T_start = 328.15, W_start = 0.011, fixedState = true);
equation
  connect(drum.port_b,  volRef.port_a);
  connect(volRef.port_b, fan.port_a);
  connect(fan.port_b,   volB.port_a);
  connect(volB.port_b,  evap.port_a);
  connect(evap.port_b,  volC.port_a);
  connect(volC.port_b,  cond.port_a);
  connect(cond.port_b,  volD.port_a);
  connect(volD.port_b,  drum.port_a);
end TestAirRingL1;





