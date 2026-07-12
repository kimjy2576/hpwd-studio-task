within ;
package CmpCycle "혼합 충실도 사이클 비교 — HX는 L3(Cond_On_Dyn/Evap_On_Dyn) 고정, 압축기·EEV만 L1/L2/L3 교체"
  // ══════════════════════════════════════════════════════════════
  // 목적: HX 충실도 차이(상수 UA vs 상관식 vs 셀별)를 제거하고,
  //       압축기·EEV 충실도가 사이클 운전점에 미치는 영향만 격리 비교.
  //
  // 공통 (Cycle_L3_coldstart_PI와 동일):
  //   - HX: Cond_On_Dyn + Evap_On_Dyn (L3 유한체적, 공기 폐루프)
  //   - 제어: PI(SH_target=6K), N staged ramp(0→1800rpm), 콜드스타트 균압
  //   - 볼륨 4개(vol1~4), p_rest=12.5b, h_rest=575e3
  //
  // 변경점 (압축기·EEV만):
  //   L1comp: Comp_Theoretical(상수 ηv) + EEV_Orifice_ctrl(오리피스 momentum)
  //   L2comp: Comp_Winandy(흡입가열·ηv(rp)) + EEV_MB(Cd(Re)·cf_A)
  //   L3comp: Comp_Chamber(chamber 물리) + EEV_On(needle-cone) = 기준(원 L3 사이클)
  // ══════════════════════════════════════════════════════════════

  // ── L1 EEV 로컬 복제 (Cycle.mo와 HPWDcycle.mo가 같은 패키지명 HPWDcycle이라
  //    L1 EEV와 L3 Volume을 동시 로드 불가 → 여기 복제해 충돌 회피) ──
  model EEV_Orifice_L1 "EEV momentum + 개도 입력 (Cycle.mo EEV_Orifice_ctrl 복제)"
    HPWD.RefPort port_a; HPWD.RefPort port_b;
    Modelica.Blocks.Interfaces.RealInput opening "개도 [%]";
    parameter Real A_orifice=7.854e-7, Cv=0.7, L_inertia=1e6;
    parameter Real D_seat=1.0e-3, stroke_max=1.0e-3, needle_angle_deg=30.0;
    parameter Real opening_floor=1.0;
    Real op, phi, phi_raw, h_in, rho_in, m_dot(start=1e-5, fixed=true), dP_orifice;
  equation
    op = max(opening_floor, min(100.0, opening))/100.0;
    phi_raw = Modelica.Constants.pi*D_seat*(stroke_max*op)*sin(needle_angle_deg*Modelica.Constants.pi/180.0)/A_orifice;
    phi = 0.5*(phi_raw + 1.0 - sqrt((phi_raw - 1.0)^2 + 1e-6));
    h_in = inStream(port_a.h_outflow);
    rho_in = R290Tab.rho_ph(port_a.p, h_in);
    dP_orifice = (m_dot/(Cv*A_orifice*phi))^2/(2.0*rho_in);
    der(m_dot) = (port_a.p - port_b.p - dP_orifice)/L_inertia;
    port_a.m_flow = m_dot;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_in;
    port_a.h_outflow = port_b.h_outflow;
  end EEV_Orifice_L1;

  model Cycle_MixHX_L1comp "L3 HX + L1 압축기(Theoretical) + L1 EEV(Orifice)"
    parameter Real N_final = 1800.0;
    parameter Real SH_target = 6.0;
    parameter Modelica.Units.SI.Pressure p_rest = 12.5e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 575e3;
    parameter Modelica.Units.SI.Volume V_node = 2e-3;
    // 압축기: L1
    HPWD.Comp_Theoretical comp(V_disp=7.5e-6, N=N_final, eta_vol=0.88, eta_isen=0.68);
    HPWDcycle.Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(h_ref_start=h_rest, T_w_start=25.0);
    HPWDcycle.Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    // EEV: L1 (momentum + opening 입력)
    CmpCycle.EEV_Orifice_L1 eev;
    HPWDcycle.Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(h_ref_start=h_rest, T_w_start=35.0);
    HPWDcycle.Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDctrl.PI_Controller ctrl(SH_target=SH_target, Kp=1.0, Ki=0.3, opening_init=12.0, opening_min=3.0, I(fixed=true));
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,0.0; 1.0,300.0; 11.0,500.0; 21.0,500.0; 31.0,1500.0; 41.0,1500.0; 51.0,N_final; 500.0,N_final]);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, opening;
  equation
    cond.T_air_in = evap.T_air_out;
    cond.Wi       = evap.W_air_out;
    // L1 압축기는 N이 파라미터 → Nsig 미사용(ramp 없이 정속). 콜드스타트 대신 정속기동.
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(ctrl.opening, eev.opening);
    ctrl.SH_meas = evap.SH;
    Pc_bar=vol1.p/1e5; Pe_bar=vol3.p/1e5; mdot=comp.m_dot; SH=evap.SH;
    Q_evap=evap.Q_total; Q_cond=cond.Q_total; W_comp=0.0; opening=ctrl.opening;
  end Cycle_MixHX_L1comp;

  model Cycle_MixHX_L2comp "L3 HX + L2 압축기(Winandy) + L2 EEV(MB)"
    parameter Real N_final = 1800.0;
    parameter Real SH_target = 6.0;
    parameter Modelica.Units.SI.Pressure p_rest = 12.5e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 575e3;
    parameter Modelica.Units.SI.Volume V_node = 2e-3;
    // 압축기: L2
    HPWD.Comp_Winandy comp(V_disp=7.5e-6, N=N_final);
    HPWDcycle.Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(h_ref_start=h_rest, T_w_start=25.0);
    HPWDcycle.Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    // EEV: L2
    EevMB.EEV_MB eev;
    HPWDcycle.Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(h_ref_start=h_rest, T_w_start=35.0);
    HPWDcycle.Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDctrl.PI_Controller ctrl(SH_target=SH_target, Kp=1.0, Ki=0.3, opening_init=12.0, opening_min=3.0, I(fixed=true));
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,0.0; 1.0,300.0; 11.0,500.0; 21.0,500.0; 31.0,1500.0; 41.0,1500.0; 51.0,N_final; 500.0,N_final]);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, opening;
  equation
    cond.T_air_in = evap.T_air_out;
    cond.Wi       = evap.W_air_out;
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(ctrl.opening, eev.opening);
    ctrl.SH_meas = evap.SH;
    Pc_bar=vol1.p/1e5; Pe_bar=vol3.p/1e5; mdot=comp.m_dot; SH=evap.SH;
    Q_evap=evap.Q_total; Q_cond=cond.Q_total; W_comp=0.0; opening=ctrl.opening;
  end Cycle_MixHX_L2comp;

  model Cycle_MixHX_L3comp "L3 HX + L3 압축기(Chamber) + L3 EEV(On) = 기준(원 L3 사이클과 동일)"
    parameter Real N_final = 1800.0;
    parameter Real SH_target = 6.0;
    parameter Modelica.Units.SI.Pressure p_rest = 12.5e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 575e3;
    parameter Modelica.Units.SI.Volume V_node = 2e-3;
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    HPWDcycle.Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(h_ref_start=h_rest, T_w_start=25.0);
    HPWDcycle.Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    HPWDcycle.Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(h_ref_start=h_rest, T_w_start=35.0);
    HPWDcycle.Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDctrl.PI_Controller ctrl(SH_target=SH_target, Kp=1.0, Ki=0.3, opening_init=12.0, opening_min=3.0, I(fixed=true));
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,0.0; 1.0,300.0; 11.0,500.0; 21.0,500.0; 31.0,1500.0; 41.0,1500.0; 51.0,N_final; 500.0,N_final]);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, opening;
  equation
    cond.T_air_in = evap.T_air_out;
    cond.Wi       = evap.W_air_out;
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(Nsig.y, comp.N);
    connect(ctrl.opening, eev.opening);
    ctrl.SH_meas = evap.SH;
    Pc_bar=vol1.p/1e5; Pe_bar=vol3.p/1e5; mdot=comp.m_dot; SH=evap.SH;
    Q_evap=evap.Q_total; Q_cond=cond.Q_total; W_comp=comp.W_shaft; opening=ctrl.opening;
  end Cycle_MixHX_L3comp;
end CmpCycle;
