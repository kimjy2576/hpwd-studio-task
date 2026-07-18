model TestCondMBcpl "CondenserMB_cpl 원본조건 대조: 17bar/m0.012 + 공기 V25.42CMM 대응"
  CondMB.CondenserMB_cpl cond(m_dot(start=0.012), P_cond(start=17e5));
  HPWDhx.FlowSource src(p = 17e5, h = 620e3, m_flow_set = 0.012);
  HPWDhx.SinkOpen snk;
  // 원본: T_air_in=35°C, RH=0.50, V=25.42 CMM → m_da≈0.483, W(35°C,50%)≈0.0178
  HPWDair.BoundaryAir_pTW air_in(p = 101325, T = 308.15, W = 0.0178);
  HPWDair.BoundaryAir_mflow air_out(m_flow_da = -0.483, T = 320.15, W = 0.0178);
equation
  connect(src.port, cond.port_a);
  connect(cond.port_b, snk.port);
  connect(air_in.port, cond.air_a);
  connect(cond.air_b, air_out.port);
end TestCondMBcpl;
