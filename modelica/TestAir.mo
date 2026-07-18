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
  "Air 링 L1: drum→filter→fan→evap→cond→drum (CRCR, volRef만 압축성=압력앵커)"
  // ── R 컴포넌트 5개 ──
  HPWDair.Drum_L1 drum(
    m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
    A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 305.0,
    UA_amb = 0.0, T_amb = 298.15);
    // BC 통일: Tcl0=305.0, UA_amb=0 (3급 링 공정비교용).
    // UA_amb=0인 이유: Drum_L3엔 외기손실 파라미터 자체가 없음.
  HPWDair.Filter_L1 filt(
    A_face = 0.05, r_pleat = 1.0, theta_face = 0, K = 10.2698);
    // K는 L3 메쉬(MPI15/d_w0.4mm/L0.6mm)를 링 운전점(u=2.28)서 fit
    // → 3급이 같은 물리필터. L1은 운전점만 정확(고유속 정상운전용).
  HPWDair.Fan_L1 fan(
    D2 = 0.15, b2 = 0.04, Z = 40, beta2 = 150,
    eta_h = 0.78, eta_mech = 0.95, N = 3000);
  HPWDair.EvapAir_L1 evap(
    T_evap = 283.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.CondAir_L1 cond(
    T_cond = 333.15, BF = 0.2, A_face = 0.05, K_air = 50);
  // ── C 요소 5개 (volRef = 압축성 압력앵커, 나머지 비압축) ──
  HPWDair.AirVolumeC volRef(
    V = 0.05, p_start = HPWDair.MoistAir.p_ref,
    T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volF(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volB(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volC(
    V = 0.05, T_start = 288.15, W_start = 0.010, fixedState = true);
  HPWDair.AirVolume volD(
    V = 0.05, T_start = 328.15, W_start = 0.011, fixedState = true);
equation
  connect(drum.port_b,  volRef.port_a);
  connect(volRef.port_b, filt.port_a);
  connect(filt.port_b,  volF.port_a);
  connect(volF.port_b,  fan.port_a);
  connect(fan.port_b,   volB.port_a);
  connect(volB.port_b,  evap.port_a);
  connect(evap.port_b,  volC.port_a);
  connect(volC.port_b,  cond.port_a);
  connect(cond.port_b,  volD.port_a);
  connect(volD.port_b,  drum.port_a);
end TestAirRingL1;


model AirRingL2
  "Air 링 L2: drum→filter→fan→evap→cond→drum. Drum_L2(감률/흡착)+Filter_L2(DF 2항)
   +Fan_L2(손실분해), 공기코일 고정온도(피델리티 무관 재사용). volRef=압축성 압력앵커"
  // ── R 컴포넌트 5개 (L2 drum/filter/fan) ──
  HPWDair.Drum_L2 drum(
    m_cl_dry = 3.0, c_p_cl = 1500, A_eff = 10, h_a = 50,
    A_drum = 0.15, K_drum = 30, X0 = 0.6, Tcl0 = 305.0,
    UA_amb = 0.0, T_amb = 298.15);
    // BC 통일: UA_amb 100→0 (3급 링 공정비교용). 기존 100은 L2 링
    // 단독 설정이었으나 L1/L3와 달라 fidelity 차이를 가림.
  HPWDair.Filter_L2 filt(
    A_face = 0.05, r_pleat = 1.0, theta_face = 0,
    a_visc = 4.9186e5, b_inert = 5.5091);
    // a·b는 L3 메쉬(MPI15/d_w0.4mm/L0.6mm) 곡선에 최소자승 fit
    // → 3급이 같은 물리필터. L2는 전영역 L3 완벽재현(2항=Ergun 동형).
  HPWDair.Fan_L2 fan(
    D2 = 0.15, b2 = 0.04, D1 = 0.120, b1 = 0.060, Z = 40,
    beta2 = 150, beta1 = 30, eta_mech = 0.95, N = 3000);
    // D1/b1/beta1 명시: 미설정 시 L2 기본(0.075/0.045/35) vs L3 기본
    // (0.120/0.060/30)이 달라 입사손실이 다른 팬 비교가 됨 → 통일.
  HPWDair.EvapAir_L1 evap(
    T_evap = 283.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.CondAir_L1 cond(
    T_cond = 333.15, BF = 0.2, A_face = 0.05, K_air = 50);
  // ── C 요소 5개 (volRef = 압축성 압력앵커) ──
  HPWDair.AirVolumeC volRef(
    V = 0.05, p_start = HPWDair.MoistAir.p_ref,
    T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volF(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volB(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volC(
    V = 0.05, T_start = 288.15, W_start = 0.010, fixedState = true);
  HPWDair.AirVolume volD(
    V = 0.05, T_start = 328.15, W_start = 0.011, fixedState = true);
equation
  connect(drum.port_b,  volRef.port_a);
  connect(volRef.port_b, filt.port_a);
  connect(filt.port_b,  volF.port_a);
  connect(volF.port_b,  fan.port_a);
  connect(fan.port_b,   volB.port_a);
  connect(volB.port_b,  evap.port_a);
  connect(evap.port_b,  volC.port_a);
  connect(volC.port_b,  cond.port_a);
  connect(cond.port_b,  volD.port_a);
  connect(volD.port_b,  drum.port_a);
end AirRingL2;


model AirRingL3
  "Air 링 L3: drum→filter→fan→evap→cond→drum. Drum_L3(3-Zone 4경로 동적)
   +Filter_L3(메쉬 Ergun)+Fan_L3(Meanline 9손실), 공기코일 고정온도(L1 재사용).
   volRef=압축성 압력앵커. drum_on/filter_on/fan_on 검증 L3로 구성한
   최고충실도 공기 폐루프. 필터는 드럼 직후(린트 포집) = 실제 건조기 구조."
  // ── R 컴포넌트 (L3 drum/filter/fan, 공기코일 L1) ──
  HPWDair.Drum_L3 drum(
    m_cl_dry = 3.0, X0 = 0.6, Tcl0 = 305.0,
    drum_radius = 0.27, drum_length = 0.45, RPM = 45.0);
  HPWDair.Filter_L3 filt(
    A_face = 0.05, r_pleat = 1.0, theta_face = 0);
  HPWDair.Fan_L3 fan(
    D2 = 0.15, b2 = 0.04, D1 = 0.120, b1 = 0.060, Z = 40,
    beta2 = 150, beta1 = 30, N = 3000);   // D1/b1/beta1 통일 (L2와 동일)
  HPWDair.EvapAir_L1 evap(
    T_evap = 283.15, BF = 0.2, A_face = 0.05, K_air = 50);
  HPWDair.CondAir_L1 cond(
    T_cond = 333.15, BF = 0.2, A_face = 0.05, K_air = 50);
  // ── C 요소 5개 (volRef = 압축성 압력앵커, 나머지 비압축) ──
  HPWDair.AirVolumeC volRef(
    V = 0.05, p_start = HPWDair.MoistAir.p_ref,
    T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volF(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volB(
    V = 0.05, T_start = 308.15, W_start = 0.018, fixedState = true);
  HPWDair.AirVolume volC(
    V = 0.05, T_start = 288.15, W_start = 0.010, fixedState = true);
  HPWDair.AirVolume volD(
    V = 0.05, T_start = 328.15, W_start = 0.011, fixedState = true);
equation
  connect(drum.port_b,  volRef.port_a);
  connect(volRef.port_b, filt.port_a);
  connect(filt.port_b,  volF.port_a);
  connect(volF.port_b,  fan.port_a);
  connect(fan.port_b,   volB.port_a);
  connect(volB.port_b,  evap.port_a);
  connect(evap.port_b,  volC.port_a);
  connect(volC.port_b,  cond.port_a);
  connect(cond.port_b,  volD.port_a);
  connect(volD.port_b,  drum.port_a);
end AirRingL3;





