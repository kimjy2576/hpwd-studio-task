package CmpAirParts "공기측 부품 단독 충실도 비교 — 동일 BC에서 L1/L2/L3 팬·드럼·필터 대조"
  // ══════════════════════════════════════════════════════════════
  // 냉매측 CmpParts.mo와 대칭. 각 공기 컴포넌트를 동일 BC에서 L1/L2/L3 나란히.
  // 방법론 격리: 같은 입력 → fidelity만 다른 출력 → 3급 차이 정량 관찰.
  //
  // [팬 Fan]    RPM=3000, m_dot_da=0.05 kg/s, 20°C, W=0.008
  //   L1 Euler+Stodola(η_h 상수) / L2 +incidence·friction / L3 Meanline 9손실
  //   비교출력: dp [Pa]. (fan_on.py 검증: L3 Ps≈662.6 @ m=0.05)
  //   ⚠️ 팬 출력 정의가 급별로 다름 — 직접 dp 비교 주의:
  //      L1 dp=η_h·dp_t (전압), L2 dp=dp_euler-손실 (전압),
  //      L3 Ps=Pt_fan-동압 (정압). L1/L2는 전압상승, L3는 정압상승을
  //      port에 실음 → port 압력차 L1 413/L2 407/L3 154는 total vs static
  //      차이(동압 ~수백 Pa)라 물리적으로 다른 양. 공정 비교는 같은 기준
  //      (전압 or 정압) 통일 필요. L3에 동압 더하면 전압 기준 일치 가능.
  //
  // [드럼 Drum]  60°C, W=0.010, m_dot_da=0.035 kg/s, 면3kg, X0=0.6 (동적)
  //   L1 Lewis+항률 / L2 감률+흡착(동적) / L3 3-Zone 4경로(동적)
  //   비교출력: 초기 증발률 m_evap, T_fabric 궤적. (동적이라 정착·궤적 관찰)
  //
  // [필터 Filter] m_dot_da=0.05 kg/s, 50°C, W=0.010
  //   L1 K·u|u| / L2 DF 2항(a·μu+b·ρu²) / L3 메쉬 Ergun 다층
  //   비교출력: dp [Pa]. (filter_on.py 검증: L2 16.88 / L3 14.11 @ m=0.05)
  // ══════════════════════════════════════════════════════════════

  // ───────────── 공통 BC 상수 ─────────────
  constant Real T_fan = 293.15 "팬 공기온도 (K)";
  constant Real W_fan = 0.008 "팬 습도비";
  constant Real m_fan = 0.05 "팬 유량 (kg_da/s)";
  constant Real N_fan = 3000 "팬 회전수 (rpm)";

  constant Real T_drum = 333.15 "드럼 공기온도 (K)";
  constant Real W_drum = 0.010 "드럼 습도비";
  constant Real m_drum = 0.035 "드럼 유량 (kg_da/s)";

  constant Real T_filt = 323.15 "필터 공기온도 (K)";
  constant Real W_filt = 0.010 "필터 습도비";
  constant Real m_filt = 0.05 "필터 유량 (kg_da/s)";

  // ═══════════════════ 팬 (RPM=3000, m=0.05 고정) ═══════════════════
  model Fan_L1 "L1 팬 — Euler+Stodola slip (η_h 상수, 전곡)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_fan, W = W_fan);
    HPWDair.Fan_L1 fan(N = N_fan);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = -m_fan, T = T_fan, W = W_fan);
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L1;

  model Fan_L2 "L2 팬 — +incidence·skin-friction 손실"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_fan, W = W_fan);
    HPWDair.Fan_L2 fan(N = N_fan);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = -m_fan, T = T_fan, W = W_fan);
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L2;

  model Fan_L3 "L3 팬 — Meanline 9손실 (fan_on.py 검증)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_fan, W = W_fan);
    HPWDair.Fan_L3 fan(N = N_fan);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = -m_fan, T = T_fan, W = W_fan);
  equation
    connect(inlet.port, fan.port_a);
    connect(fan.port_b, outlet.port);
  end Fan_L3;

  // ═══════════════════ 드럼 (60°C, m=0.035, 면3kg, X0=0.6, 동적) ═══════════════════
  model Drum_L1 "L1 드럼 — Lewis+항률 (동적)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -m_drum, T = T_drum, W = W_drum);
    HPWDair.Drum_L1 drum(m_cl_dry = 3.0, X0 = 0.6);
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = T_drum, W = W_drum);
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L1;

  model Drum_L2 "L2 드럼 — 감률+흡착 (동적)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -m_drum, T = T_drum, W = W_drum);
    HPWDair.Drum_L2 drum(m_cl_dry = 3.0, X0 = 0.6);
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = T_drum, W = W_drum);
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L2;

  model Drum_L3 "L3 드럼 — 3-Zone 4경로 (drum_on.py 검증, 동적)"
    HPWDair.BoundaryAir_mflow inlet(m_flow_da = -m_drum, T = T_drum, W = W_drum);
    HPWDair.Drum_L3 drum(m_cl_dry = 3.0, X0 = 0.6);
    HPWDair.BoundaryAir_pTW outlet(p = 101325.0, T = T_drum, W = W_drum);
  equation
    connect(inlet.port, drum.port_a);
    connect(drum.port_b, outlet.port);
  end Drum_L3;

  // ═══════════════════ 필터 (m=0.05, 50°C 고정) ═══════════════════
  model Filter_L1 "L1 필터 — K·u|u| (관성지배 단순화)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_filt, W = W_filt);
    HPWDair.Filter_L1 filt(A_face = 0.05, K = 20);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = m_filt, T = T_filt, W = W_filt);
  equation
    connect(inlet.port, filt.port_a);
    connect(filt.port_b, outlet.port);
  end Filter_L1;

  model Filter_L2 "L2 필터 — DF 2항 (점성+관성)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_filt, W = W_filt);
    HPWDair.Filter_L2 filt(A_face = 0.05, a_visc = 5.0e4, b_inert = 17.0);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = m_filt, T = T_filt, W = W_filt);
  equation
    connect(inlet.port, filt.port_a);
    connect(filt.port_b, outlet.port);
  end Filter_L2;

  model Filter_L3 "L3 필터 — 메쉬 Ergun 다층 (filter_on.py 검증)"
    HPWDair.BoundaryAir_pTW inlet(p = 101325.0, T = T_filt, W = W_filt);
    HPWDair.Filter_L3 filt(A_face = 0.05);
    HPWDair.BoundaryAir_mflow outlet(m_flow_da = m_filt, T = T_filt, W = W_filt);
  equation
    connect(inlet.port, filt.port_a);
    connect(filt.port_b, outlet.port);
  end Filter_L3;
end CmpAirParts;
