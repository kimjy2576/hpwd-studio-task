within ;
package HPWDcycle "L3 사이클 조립 (Comp_Chamber + Cond_On + EEV_On + Evap_On 폐루프)"

  model Volume_L3 "냉매 control volume (압력 노드, R290Tab 기반, 정상상태)"
    HPWD.RefPort port_a;
    HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Volume V=5e-4;
    parameter Modelica.Units.SI.Pressure p_start=10e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_start=360e3;
    parameter Boolean fixedState=false "true면 (p,h) start값 고정 init";
    Modelica.Units.SI.Pressure p(start=p_start, fixed=false, stateSelect=StateSelect.prefer);
    Modelica.Units.SI.SpecificEnthalpy h(start=h_start, fixed=false, stateSelect=StateSelect.prefer);
    Real rho, U;
  equation
    rho=R290Tab.rho_ph(p, h);
    U=rho*V*h - p*V;
    port_a.p=p; port_b.p=p;
    port_a.h_outflow=h; port_b.h_outflow=h;
    der(rho*V)=port_a.m_flow + port_b.m_flow;
    der(U)=port_a.m_flow*actualStream(port_a.h_outflow) + port_b.m_flow*actualStream(port_b.h_outflow);
  initial equation
    if fixedState then
      p=p_start;
      h=h_start;
    else
      der(p)=0;
      der(h)=0;
    end if;
  end Volume_L3;

  model Cycle_L3_steady "L3 정상상태 사이클 (N·opening 고정, 운전점 솔브)"
    parameter Real N_comp=3000.0 "압축기 회전수 [rpm]";
    parameter Real eev_opening=40.0 "EEV 개도 [%]";
    HPWDon.Comp_Chamber comp(V_disp_cm3=10.0);
    Volume_L3 vol1(p_start=19e5, h_start=620e3) "토출 (Pc, 과열증기)";
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=360e3) "응축출구 (Pc, 액)";
    HPWDon.EEV_On eev(D_seat=2.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(p_start=6e5, h_start=350e3) "팽창후 (Pe, 2상)";
    HPWDevap.Evap_On evap;
    Volume_L3 vol4(p_start=6e5, h_start=580e3) "흡입 (Pe, 과열증기)";
    Modelica.Blocks.Sources.Constant Nsig(k=N_comp);
    Modelica.Blocks.Sources.Constant opsig(k=eev_opening);
    Real Pc_bar, Pe_bar, mdot, SH, x_evap_in, Q_evap, Q_cond, W_comp;
  equation
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(Nsig.y, comp.N);
    connect(opsig.y, eev.opening);
    Pc_bar=vol1.p/1e5;
    Pe_bar=vol3.p/1e5;
    mdot=comp.m_dot;
    SH=evap.SH;
    x_evap_in=evap.x_in_q;
    Q_evap=evap.Q_total;
    Q_cond=cond.Q_total;
    W_comp=comp.W_shaft;
  end Cycle_L3_steady;

  model Cycle_L3_relax "L3 사이클 — 좋은 추정값서 fixedState init → transient 완화 (steady 근처)"
    parameter Real N_comp=3000.0, eev_opening=40.0;
    HPWDon.Comp_Chamber comp(V_disp_cm3=10.0);
    Volume_L3 vol1(p_start=19e5, h_start=620e3, fixedState=true);
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=360e3, fixedState=true);
    HPWDon.EEV_On eev(D_seat=2.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(p_start=6e5, h_start=350e3, fixedState=true);
    HPWDevap.Evap_On evap;
    Volume_L3 vol4(p_start=6e5, h_start=580e3, fixedState=true);
    Modelica.Blocks.Sources.Constant Nsig(k=N_comp);
    Modelica.Blocks.Sources.Constant opsig(k=eev_opening);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp;
  equation
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(Nsig.y, comp.N);
    connect(opsig.y, eev.opening);
    Pc_bar=vol1.p/1e5; Pe_bar=vol3.p/1e5; mdot=comp.m_dot;
    SH=evap.SH; Q_evap=evap.Q_total; Q_cond=cond.Q_total; W_comp=comp.W_shaft;
  end Cycle_L3_relax;

  model PNode "압력 고정 노드 (p=p_set, 질량·엔탈피 통과) — 저압 앵커용"
    HPWD.RefPort port_a;
    HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Pressure p_set=6e5;
    Real h;
  equation
    port_a.p=p_set;
    port_b.p=p_set;
    port_a.m_flow + port_b.m_flow=0;
    h=inStream(port_a.h_outflow);
    port_b.h_outflow=h;
    port_a.h_outflow=inStream(port_b.h_outflow);
  end PNode;

  model FreeNode "압력 노드 (p 자유변수, 질량·엔탈피 통과, der 없음)"
    HPWD.RefPort port_a;
    HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Pressure p_start=19e5;
    Modelica.Units.SI.Pressure p(start=p_start);
    Real h;
  equation
    port_a.p=p;
    port_b.p=p;
    port_a.m_flow + port_b.m_flow=0;
    h=inStream(port_a.h_outflow);
    port_b.h_outflow=h;
    port_a.h_outflow=inStream(port_b.h_outflow);
  end FreeNode;

  model Cycle_L3_homotopy "L3 사이클 — opening homotopy(40%→타깃)로 고압점 초기화 연속화"
    parameter Real N_comp=3000.0 "압축기 회전수 [rpm]";
    parameter Real op_target=8.0 "목표 EEV 개도 [%] (고압점)";
    parameter Real op_easy=40.0 "homotopy 시작 개도 [%] (저압, 수렴쉬움)";
    HPWDon.Comp_Chamber comp(V_disp_cm3=10.0);
    Volume_L3 vol1(p_start=19e5, h_start=620e3);
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=360e3);
    HPWDon.EEV_On eev(D_seat=2.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(p_start=6e5, h_start=350e3);
    HPWDevap.Evap_On evap;
    Volume_L3 vol4(p_start=6e5, h_start=580e3);
    Modelica.Blocks.Sources.Constant Nsig(k=N_comp);
    Modelica.Blocks.Sources.RealExpression opsig(y=homotopy(op_target, op_easy));
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, W_ind, COP;
  equation
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    connect(Nsig.y, comp.N);
    connect(opsig.y, eev.opening);
    Pc_bar=vol1.p/1e5; Pe_bar=vol3.p/1e5; mdot=comp.m_dot;
    SH=evap.SH; Q_evap=evap.Q_total; Q_cond=cond.Q_total;
    W_comp=comp.W_shaft; W_ind=comp.W_indicated; COP=Q_evap/max(W_comp, 1.0);
  end Cycle_L3_homotopy;

end HPWDcycle;
