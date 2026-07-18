model TestEvapMBcpl "EvaporatorMB_cpl 커플 검증: 냉매 5.5bar + 공기 45°C/86%RH → 냉각·제습"
  EvapMB.EvaporatorMB_cpl evap(m_dot(start=0.004), P_evap(start=5.5e5));
  HPWDhx.FlowSource src(p = 5.5e5, h = 285990, m_flow_set = 0.004);
  HPWDhx.SinkOpen snk;
  HPWDair.BoundaryAir_pTW air_in(p = 101325, T = 318.15, W = 0.0552);
  HPWDair.BoundaryAir_mflow air_out(m_flow_da = -0.05, T = 300.15, W = 0.010);
equation
  connect(src.port, evap.port_a);
  connect(evap.port_b, snk.port);
  connect(air_in.port, evap.air_a);
  connect(evap.air_b, air_out.port);
end TestEvapMBcpl;
