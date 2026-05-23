package HPWDcycle "L1 사이클 — volume 2개(고압/저압) + 컴포넌트 등압"
  model EEV_Orifice
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a; HPWD.RefPort port_b;
    parameter Real A_orifice=5.5e-7, Cv=0.7, phi_fixed=0.35, L_inertia=1e6;
    Real h_in, rho_in, m_dot(start=0.005, fixed=true), dP_orifice;
  equation
    h_in = inStream(port_a.h_outflow);
    rho_in = M.density(M.setState_ph(port_a.p, h_in));
    dP_orifice = (m_dot/(Cv*A_orifice*phi_fixed))^2/(2.0*rho_in);
    der(m_dot) = (port_a.p - port_b.p - dP_orifice)/L_inertia;
    port_a.m_flow = m_dot;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_in;
    port_a.h_outflow = port_b.h_outflow;
  end EEV_Orifice;

  model Volume "냉매 control volume (압력 노드)"
    package Med = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.RefPort port_a; HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Volume V = 1e-5;
    parameter Modelica.Units.SI.Pressure p_start = 1e6;
    parameter Modelica.Units.SI.SpecificEnthalpy h_start = 5e5;
    parameter Boolean steadyP = true "false면 압력 앵커(charge가 결정)";
    Modelica.Units.SI.Pressure p(start=p_start, fixed=false, stateSelect=StateSelect.prefer);
    Modelica.Units.SI.SpecificEnthalpy h(start=h_start, fixed=false, stateSelect=StateSelect.prefer);
    Real rho, U;
  equation
    rho = Med.density(Med.setState_ph(p, h));
    U = rho*V*h - p*V;
    port_a.p = p; port_b.p = p;
    port_a.h_outflow = h; port_b.h_outflow = h;
    der(rho*V) = port_a.m_flow + port_b.m_flow;
    der(U) = port_a.m_flow*actualStream(port_a.h_outflow)
           + port_b.m_flow*actualStream(port_b.h_outflow);
  initial equation
    if steadyP then der(p) = 0; end if;
    der(h) = 0;
  end Volume;

  model Cycle_L1_dyn
    parameter Real M_total = 0.1 "총 냉매 충전량 [kg]";
    HPWD.Comp_Theoretical comp(V_disp=10e-6,N=3000.0,eta_vol=0.85,eta_isen=0.65);
    Volume vol1(V=5e-4, p_start=19e5, h_start=700e3, steadyP=false);
    HPWDhx.Cond_UA_eq cond(T_air_in_C=35.0,RH_in=0.5,V_air_CMM=25.42,UA_deSH=8.0,UA_2ph=50.0,UA_SC=5.0,R_fric=1e7);
    Volume vol2(V=5e-4, p_start=18.5e5, h_start=440e3);
    EEV_Orifice eev(A_orifice=5.5e-7,Cv=0.7,phi_fixed=0.35);
    Volume vol3(V=5e-4, p_start=5.5e5, h_start=440e3);
    HPWDhx.Evap_UA_eq evap(T_air_in=50.0+273.15,RH_in=0.9,V_air_CMM=2.54,UA_2ph=25.0,UA_SH=4.0,R_fric=2e6);
    Volume vol4(V=5e-4, p_start=5.3e5, h_start=590e3);
  equation
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
  initial equation
    vol1.rho*vol1.V + vol2.rho*vol2.V + vol3.rho*vol3.V + vol4.rho*vol4.V = M_total;
  end Cycle_L1_dyn;
end HPWDcycle;
