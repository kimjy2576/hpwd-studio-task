within ;
package CmpAir "공기측 부품 충실도 비교 — 동일 BC에서 Fan(L1/L2)·Drum(L1/L2) 대조"
  // ══════════════════════════════════════════════════════════════
  // 공통 BC (HPWD 공기 오픈루프 운전 조건 기준):
  //   Fan: 입구 20°C/W=0.008, N=3000rpm, 유량 스윕(dp-Q 특성곡선 비교)
  //   Drum: 입구 공기 45°C/W=0.02 (증발기 후 가열된 건조공기), 유량 0.05 kg/s 고정
  //         → 정착 시 출구 T/W(증발량)·함수율 강하 비교
  //
  // 방법 격리:
  //   Fan  — L1(Euler+Stodola slip, η_h 상수 0.78) vs L2(+inlet각·incidence·diffusion 손실)
  //   Drum — L1(Lewis+항률건조) vs L2(감률건조 X_cr + 흡착평형 X_eq(RH))
  // ══════════════════════════════════════════════════════════════

  // ───────────────────── Fan (N=3000 고정, 유량 경계로 dp-Q 특성) ─────────────────────
  model Fan_L1_pt "L1 팬 @ 유량 경계 (dp 응답)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = 293.15, W = 0.008);
    HPWDair.Fan_L1 fan(N = 3000);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = -m_set, T = 293.15, W = 0.008);
    parameter Real m_set = 0.05 "질량유량 [kg_da/s]";
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L1_pt;

  model Fan_L2_pt "L2 팬 @ 유량 경계 (dp 응답)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = 293.15, W = 0.008);
    HPWDair.Fan_L2 fan(N = 3000);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = -m_set, T = 293.15, W = 0.008);
    parameter Real m_set = 0.05 "질량유량 [kg_da/s]";
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L2_pt;

  model Fan_L3_pt "L3 팬 @ 유량 경계 (Meanline+손실9종, fan_on.py 검증)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = 293.15, W = 0.008);
    HPWDair.Fan_L3 fan(N = 3000);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = m_set, T = 293.15, W = 0.008);
    parameter Real m_set = 0.05 "질량유량 [kg_da/s]";
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L3_pt;

  // ───────────────────── Drum (입구 공기·유량 고정, 정착 시 증발량 비교) ─────────────────────
  model Drum_L1_pt "L1 드럼 @ 고정 공기 BC (Lewis+항률)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -0.05, T = 328.15, W = 0.008);
    HPWDair.Drum_L1 drum;
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = 328.15, W = 0.008);
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L1_pt;

  model Drum_L2_pt "L2 드럼 @ 고정 공기 BC (감률+흡착)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -0.05, T = 328.15, W = 0.008);
    HPWDair.Drum_L2 drum;
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = 328.15, W = 0.008);
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L2_pt;

  model Drum_L3_pt "L3 드럼 @ 유량경계 (최소골격 동적검증)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -m_set, T = 333.15, W = 0.010);
    HPWDair.Drum_L3 drum(m_cl_dry = 3.0, X0 = 0.6);
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = 333.15, W = 0.010);
    parameter Real m_set = 0.035 "질량유량 [kg_da/s]";
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L3_pt;
end CmpAir;
