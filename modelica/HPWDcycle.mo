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

  model Cycle_L3_guess "warm-start guess: 4컴포넌트를 healthy 경계로 독립 솔브 (각=검증된 standalone)"
    // 동일 인스턴스명(comp/cond/eev/evap) → .mat가 폐루프 Cycle에 -iif로 매핑됨
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    HPWD.Source src_c(p=6e5, h=623127.0);
    HPWD.Sink snk_c(p=19e5);
    Modelica.Blocks.Sources.Constant Nsig(k=1800.0);
    HPWDevap.Cond_On cond;
    HPWDevap.FlowSource src_cond(m_dot=0.005366, h=693465.0, p=19e5);
    HPWDevap.OpenSink snk_cond(h=312428.0);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    HPWD.Source src_e(p=19e5, h=312428.0);
    HPWD.Sink snk_e(p=6e5);
    Modelica.Blocks.Sources.Constant opsig(k=8.0);
    HPWDevap.Evap_On evap;
    HPWDevap.FlowSource src_evap(m_dot=0.005366, h=312428.0, p=6e5);
    HPWDevap.OpenSink snk_evap(h=623127.0);
  equation
    connect(src_c.port, comp.port_a);
    connect(comp.port_b, snk_c.port);
    connect(Nsig.y, comp.N);
    connect(src_cond.port, cond.port_a);
    connect(cond.port_b, snk_cond.port);
    connect(src_e.port, eev.port_a);
    connect(eev.port_b, snk_e.port);
    connect(opsig.y, eev.opening);
    connect(src_evap.port, evap.port_a);
    connect(evap.port_b, snk_evap.port);
  end Cycle_L3_guess;

  model Cycle_L3_steady "L3 정상상태 사이클 (N·opening 고정, 운전점 솔브)"
    parameter Real N_comp=1800.0 "압축기 회전수 [rpm]";
    parameter Real eev_opening=8.0 "EEV 개도 [%]";
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(p_start=19e5, h_start=693e3) "토출 (Pc, 과열증기)";
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=312e3) "응축출구 (Pc, 과냉액)";
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(p_start=6e5, h_start=312e3) "팽창후 (Pe, 2상)";
    HPWDevap.Evap_On evap;
    Volume_L3 vol4(p_start=6e5, h_start=623e3) "흡입 (Pe, 과열증기)";
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
    parameter Real N_comp=1800.0, eev_opening=40.0;
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(p_start=19e5, h_start=620e3, fixedState=true);
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=360e3, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
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
    parameter Real N_comp=1800.0 "압축기 회전수 [rpm]";
    parameter Real op_target=8.0 "목표 EEV 개도 [%] (고압점)";
    parameter Real op_easy=40.0 "homotopy 시작 개도 [%] (저압, 수렴쉬움)";
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(p_start=19e5, h_start=620e3);
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(p_start=19e5, h_start=360e3);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
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

  model Cycle_L3_coldstart "L3 on-design 콜드스타트 — rest 균일압서 staged N ramp으로 운전점 수렴 (Cycle_L1_ramp_PI의 L3판)"
    // 목표: warm-start 없이 콜드스타트. rest(균일압·N=0·무유량) init은 trivial →
    //   N을 계단식(0→500→1500→N_final)으로 천천히 올려 t≈0.5s 상변화 벽을 완만 통과.
    //   노드 체적 V_node를 크게 잡아 과도를 댐핑(수치 안정).
    parameter Real N_final = 1800.0 "최종 회전수 [rpm]";
    parameter Real eev_opening = 8.0 "EEV 개도 [%] (고정; 추후 PI)";
    parameter Modelica.Units.SI.Pressure p_rest = 9.0e5 "기동 전 균일 정지압 [Pa]";
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 590e3 "정지 엔탈피 [J/kg] (rest 과열증기)";
    parameter Modelica.Units.SI.Volume V_node = 2e-3 "노드 체적 [m3] (클수록 과도 완만·안정)";
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On cond;
    Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On evap;
    Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    // staged N ramp: 0 → 500 → 1500 → N_final (선형보간, 단계별 hold). t0=1s, 단계 10s.
    //   (반복변수 start 처방 후엔 t_stage를 줄여 가속 가능)
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,    0.0;
        1.0,    0.0;
        11.0,   500.0;
        21.0,   500.0;
        31.0,   1500.0;
        41.0,   1500.0;
        51.0,   N_final;
        500.0,  N_final]);
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
    Pc_bar=vol1.p/1e5;
    Pe_bar=vol3.p/1e5;
    mdot=comp.m_dot;
    SH=evap.SH;
    Q_evap=evap.Q_total;
    Q_cond=cond.Q_total;
    W_comp=comp.W_shaft;
  end Cycle_L3_coldstart;

  model Cycle_L3_coldstart_dyn "L3 동적 콜드스타트 — Cond_On_Dyn/Evap_On_Dyn(동적 유한체적) 폐루프. rest→staged N ramp."
    // ①동특성 재구성 적용: HX 내부 h_ref·T_w 상태화 → 폐루프 대수루프 소멸 → 컴파일.
    //   빌드 시 --generateDynamicJacobian=numeric 필수(증발기 습핀 dWsdT 2차도함수 회피).
    parameter Real N_final = 1800.0 "최종 회전수 [rpm]";
    parameter Real eev_opening = 8.0 "EEV 개도 [%] (고정; 추후 PI)";
    parameter Modelica.Units.SI.Pressure p_rest = 9.0e5 "기동 전 균일 정지압 [Pa]";
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 590e3 "정지 엔탈피 [J/kg]";
    parameter Modelica.Units.SI.Volume V_node = 2e-3 "노드 체적 [m3]";
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(h_ref_start=h_rest, T_w_start=25.0);
    Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(h_ref_start=h_rest, T_w_start=35.0);
    Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,    0.0;
        1.0,    0.0;
        11.0,   500.0;
        21.0,   500.0;
        31.0,   1500.0;
        41.0,   1500.0;
        51.0,   N_final;
        500.0,  N_final]);
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
    Pc_bar=vol1.p/1e5;
    Pe_bar=vol3.p/1e5;
    mdot=comp.m_dot;
    SH=evap.SH;
    Q_evap=evap.Q_total;
    Q_cond=cond.Q_total;
    W_comp=comp.W_shaft;
  end Cycle_L3_coldstart_dyn;

  model Cycle_L3_coldstart_PI "L3 동적 콜드스타트 + EEV PI(SH 제어) — starved 해소, 현실 운전점 수렴"
    parameter Real N_final = 1800.0 "최종 회전수 [rpm]";
    parameter Real SH_target = 6.0 "목표 과열도 [K]";
    parameter Modelica.Units.SI.Pressure p_rest = 12.5e5
      "정지 균압=충전 proxy. 9b→starved(SH 15K,개도 100% 포화). 12.5b에서 PI가 SH≈6K를 개도~60%로 추종(스윕 확정). step3서 L1/L2 충전 매칭 시 미세조정";
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 590e3;
    parameter Modelica.Units.SI.Volume V_node = 2e-3;
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(h_ref_start=h_rest, T_w_start=25.0);
    Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(h_ref_start=h_rest, T_w_start=35.0);
    Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDctrl.PI_Controller ctrl(SH_target=SH_target, Kp=1.0, Ki=0.3, opening_init=12.0, opening_min=3.0, I(fixed=true));
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,    0.0;
        1.0,    0.0;
        11.0,   500.0;
        21.0,   500.0;
        31.0,   1500.0;
        41.0,   1500.0;
        51.0,   N_final;
        500.0,  N_final]);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, opening;
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
    connect(ctrl.opening, eev.opening);
    ctrl.SH_meas = evap.SH;
    Pc_bar=vol1.p/1e5;
    Pe_bar=vol3.p/1e5;
    mdot=comp.m_dot;
    SH=evap.SH;
    Q_evap=evap.Q_total;
    Q_cond=cond.Q_total;
    W_comp=comp.W_shaft;
    opening=ctrl.opening;
  end Cycle_L3_coldstart_PI;

end HPWDcycle;
