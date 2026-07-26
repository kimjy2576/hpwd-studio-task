within ;
package HPWDcycle "L3 사이클 조립 (Comp_Chamber + Cond_On + EEV_On + Evap_On 폐루프)"

  model OilSump "압축기 오일 섬프 — 냉매 용해 저장소 (2026-07-25)

    사이클 충전량의 상당분이 압축기 오일에 용해되어 순환하지 않는다.
    Python 정방향(충전량 구속) 해에서 100g 중 84g 이 오일에 용해.
    이 항이 없으면 순환 냉매가 실제의 5배가 되어 어큐 범람 -> 응축기
    액범람 -> Pc 26bar / SH=0 의 잘못된 운전점으로 수렴한다.

    고압쉘 압축기이므로 섬프는 토출압에 노출된다.
    T_sump 는 측정 불가 -> dT_sump 를 보정계수로 노출하고 추후 측정 가능한
    양(Pc, Pe, SH, T_dis, 소비전력)으로 역보정할 것.
    용해량이 여기에 극도로 민감함: dT 5~20K 에서 용해 43~81g.
  "
    parameter Real V_oil_cc = 160.0 "오일 주입체적 [cc]";
    parameter Real dT_sump = 15.0 "T_sump = T_dis - dT_sump [K]. ★보정계수★" annotation(Evaluate=false);
    parameter Real tau = 30.0 "용해/탈리 시상수 [s]";
    parameter Real M_dis_start = 0.084 "초기 용해량 [kg]" annotation(Evaluate=false);
    parameter Real M_eq_max = 0.15 "평형 용해량 상한 [kg] (발산 차단)";
    input Real P_dis "섬프 압력 (고압쉘 = 토출압) [Pa]";
    input Real T_dis "토출 온도 [K]";
    Real M_oil "오일 질량 [kg]";
    Real M_eq "평형 용해량 [kg]";
    parameter Boolean steadyInit = false "true: der(M_dis)=0";
    Real M_dis(start=M_dis_start, fixed=false) "현재 용해량 [kg]";
    Real m_flow "냉매 -> 오일 흡수율 [kg/s]. 양수면 회로에서 빠져나감";
    Integer code "R290Oil.validity: 0=ok 1=외삽 2=파탄";
  initial equation
    if steadyInit then der(M_dis)=0; else M_dis=M_dis_start; end if;
  equation
    M_oil = R290Oil.oil_mass(V_oil_cc);
    M_eq  = min(M_eq_max, R290Oil.dissolved(M_oil, P_dis, T_dis - dT_sump))
      "상한 클램프: 유효범위 밖에서 dissolved 가 발산함 (실측 26bar/32C 에서 2114g)";
    code  = R290Oil.validity(P_dis, T_dis - dT_sump);
    tau*der(M_dis) = M_eq - M_dis;
    m_flow = der(M_dis);
  end OilSump;

  model Volume_L3 "냉매 control volume (압력 노드, R290Tab 기반, 정상상태)"
    HPWD.RefPort port_a;
    HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Volume V=5e-4;
    parameter Modelica.Units.SI.Pressure p_start=10e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_start=360e3;
    parameter Boolean fixedState=false "true면 (p,h) start값 고정 init";
    input Real m_ext = 0 "외부 질량추출 [kg/s]. 기본 0 이라 기존 모델 하위호환. 오일 섬프 연결 시 vol(m_ext=oil.m_flow) 로 결속";
    // ThermoPower 패턴 (Water.mo:735). steadyStateNoP 같은 별도 모드 대신
    // 컴포넌트별 플래그로 중복 초기방정식을 하나만 제거한다.
    // 폐루프에서는 정확히 하나의 컴포넌트에만 noInitialPressure=true.
    parameter Boolean noInitialPressure = false "정상초기화에서 der(p)=0 을 제거";
    parameter Boolean noInitialEnthalpy = false "정상초기화에서 der(h)=0 을 제거";
    Modelica.Units.SI.Pressure p(start=p_start, fixed=false, stateSelect=StateSelect.prefer);
    Modelica.Units.SI.SpecificEnthalpy h(start=h_start, fixed=false, stateSelect=StateSelect.prefer);
    Real rho, U;
  equation
    rho=R290Tab.rho_ph(p, h);
    U=rho*V*h - p*V;
    port_a.p=p; port_b.p=p;
    port_a.h_outflow=h; port_b.h_outflow=h;
    der(rho*V)=port_a.m_flow + port_b.m_flow - m_ext "m_ext: 외부 질량추출 [kg/s]. 오일 용해가 회로에서 냉매를 빼감 (2026-07-25)";
    der(U)=port_a.m_flow*actualStream(port_a.h_outflow) + port_b.m_flow*actualStream(port_b.h_outflow) - m_ext*h;
  initial equation
    if fixedState then
      p=p_start;
      h=h_start;
    else
      // 정상초기화. 폐루프 중복 방정식은 컴포넌트별 플래그로 하나만 제거.
      if not noInitialPressure then der(p)=0; end if;
      if not noInitialEnthalpy then der(h)=0; end if;
    end if;
  end Volume_L3;

  model Accumulator_L3 "흡입측 어큐뮬레이터 — 액 저장, 포화증기 토출 (상분리)"
    // 2026-07-24: 단순 체적(Volume_L3)은 상분리를 하지 않아 정지 상태(x≈0.04, 거의 액)
    // 에서 액이 그대로 압축기로 유입됨 -> 흡입밀도 30배 -> ṁ 이 설계의 3배(0.0067)로
    // 튀고 SH=0 에 고착. 실물은 어큐가 액을 잡아두고 증기만 보낸다.
    HPWD.RefPort port_a;
    HPWD.RefPort port_b;
    parameter Modelica.Units.SI.Volume V=2.226e-4 "배관 + 어큐 200cc + 증발기 밴드";
    parameter Modelica.Units.SI.Pressure p_start=8.365e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h_start=265.5e3;
    parameter Boolean fixedState=false;
    parameter Real dx_sep=0.02 "상분리 전이대 [quality] (이벤트 없는 tanh 전이)";
    input Real m_ext = 0 "외부 질량추출 [kg/s]. 기본 0 이라 기존 모델 하위호환. 오일 섬프 연결 시 vol(m_ext=oil.m_flow) 로 결속";
    // ThermoPower 패턴 (Water.mo:735). steadyStateNoP 같은 별도 모드 대신
    // 컴포넌트별 플래그로 중복 초기방정식을 하나만 제거한다.
    // 폐루프에서는 정확히 하나의 컴포넌트에만 noInitialPressure=true.
    parameter Boolean noInitialPressure = false "정상초기화에서 der(p)=0 을 제거";
    parameter Boolean noInitialEnthalpy = false "정상초기화에서 der(h)=0 을 제거";
    Modelica.Units.SI.Pressure p(start=p_start, fixed=false, stateSelect=StateSelect.prefer);
    Modelica.Units.SI.SpecificEnthalpy h(start=h_start, fixed=false, stateSelect=StateSelect.prefer);
    Real rho, U, hL, hV, xq, w_sep, h_out;
  equation
    rho=R290Tab.rho_ph(p, h);
    U=rho*V*h - p*V;
    hL=R290Tab.hl(p);
    hV=R290Tab.hv(p);
    xq=(h - hL)/max(hV - hL, 1.0);
    // 2상 구간에서만 포화증기 토출. 과냉/과열에서는 벌크 엔탈피 그대로.
    w_sep=0.25*(1.0 + tanh(xq/dx_sep))*(1.0 + tanh((1.0 - xq)/dx_sep));
    h_out=w_sep*hV + (1.0 - w_sep)*h "토출 엔탈피 — 액은 남기고 증기만";
    port_a.p=p; port_b.p=p;
    port_a.h_outflow=h "역류 시 벌크";
    port_b.h_outflow=h_out;
    der(rho*V)=port_a.m_flow + port_b.m_flow - m_ext "m_ext: 외부 질량추출 [kg/s]. 오일 용해가 회로에서 냉매를 빼감 (2026-07-25)";
    der(U)=port_a.m_flow*actualStream(port_a.h_outflow) + port_b.m_flow*actualStream(port_b.h_outflow) - m_ext*h;
  initial equation
    if fixedState then
      p=p_start;
      h=h_start;
    else
      // 정상초기화. 폐루프 중복 방정식은 컴포넌트별 플래그로 하나만 제거.
      if not noInitialPressure then der(p)=0; end if;
      if not noInitialEnthalpy then der(h)=0; end if;
    end if;
  end Accumulator_L3;

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
        1.0,    300.0;
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
    parameter Real eev_opening = 40.1
      "EEV 개도 [%] (고정). coldstart_PI가 SH=6K로 정착시킨 개도와 동일 → 두 변이가 같은 평형해 재현(교차검증). 구값 8.0은 옛 HX 기준으로 starved(SH 60K, Pe 1.9b)";
    parameter Modelica.Units.SI.Pressure p_rest = 12.5e5 "기동 전 균일 정지압 [Pa] (coldstart_PI와 일치)";
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 575e3 "정지 엔탈피 [J/kg] = 충전 proxy (coldstart_PI와 일치)";
    parameter Modelica.Units.SI.Volume V_node = 2e-3 "노드 체적 [m3]";
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Cond_On_Dyn cond(Nseg=3, h_ref_start=h_rest, T_w_start=25.0);
    Volume_L3 vol2(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(Nseg=3, h_ref_start=h_rest, T_w_start=35.0);
    Volume_L3 vol4(V=V_node, p_start=p_rest, h_start=h_rest, fixedState=true);
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,    0.0;
        1.0,    300.0;
        11.0,   500.0;
        21.0,   500.0;
        31.0,   1500.0;
        41.0,   1500.0;
        51.0,   N_final;
        500.0,  N_final]);
    Modelica.Blocks.Sources.Constant opsig(k=eev_opening);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp;
  equation
    // ── 공기 폐루프: 증발기 출구 → 응축기 입구 (온도·습도) ──
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
    parameter Modelica.Units.SI.Pressure p_rest = 8.365e5
      "20°C 포화압. 충전 100g / 시스템 총체적 414.1cc -> rho=241.5 kg/m3, x=0.040 (2026-07-24 실물 대조).
       구값 12.5e5 는 T_sat 36.1°C 로 공기(20°C)보다 뜨거워 Q_evap 음수·x_out 1.0 고착을 유발했음";
    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = 265.5e3
      "정지 엔탈피 = hl + x*hfg @8.365bar, x=0.040 (hl 251.6 / hv 595.9 kJ/kg).
       구값 575e3 은 x=0.886 로 거의 증기 — 충전 100g 과 불일치";
    // 노드 체적 = 실제 배관 + 부속 (2026-07-24 실물). 구값 2e-3 x4 = 8L 는 시스템의 98% 로 20배 과대.
    parameter Modelica.Units.SI.Volume V_n1 = 1.832e-5 "압축기→응축기 1.0m (1/4\" 동관)";
    parameter Modelica.Units.SI.Volume V_n2 = 9.99e-6  "응축기→EEV 0.2m + 응축기 리턴밴드 6.33cc";
    parameter Modelica.Units.SI.Volume V_n3 = 3.66e-6  "EEV→증발기 0.2m";
    parameter Modelica.Units.SI.Volume V_n4 = 2.226e-4 "증발기→압축기 1.0m + 어큐 200cc + 증발기 밴드 4.24cc";
    // ── 공기 경계 모드 (2026-07-25) ──
    // air_series=false : 응축기 공기 BC 독립 = 로드맵 2단계 '냉매 사이클(공기BC 고정)'.
    //   증발기 출구를 응축기에 물리면 응축기 공기가 11.8C 까지 식어 냉매를 12.8C 로 과냉
    //   -> 증발기 입구 x=0.044 -> 전잠열 증발에 823W 필요한데 공급 786W (4.5% 부족)
    //   -> SH=0 -> 개도 최소 -> Pc 25bar 폭주. 드럼이 없어 응축기가 데운 34C 공기가
    //   버려지고 증발기엔 계속 20C 가 들어가는 열린 경계가 원인.
    // air_series=true  : 증발기 출구 -> 응축기 (직렬 덕트). 드럼 연결 후 커플드에서 사용.
    parameter Boolean air_series = false "true: 증발기 출구 공기를 응축기 입구로";
    parameter Real T_air_cond = 20.0 "응축기 공기 입구온도 [degC] (air_series=false)";
    parameter Real RH_air_cond = 0.8 "응축기 공기 입구 상대습도 (air_series=false)";
    final parameter Real W_air_cond = HXCorr.W_humid(T_air_cond, RH_air_cond, 101325.0);
    HPWDon.Comp_Chamber comp(V_disp_cm3=7.5);
    Volume_L3 vol1(V=V_n1, p_start=p1_0, h_start=h1_0, fixedState=true, m_ext=if use_oil then oil.m_flow else 0);
    HPWDevap.Cond_On_Dyn cond(Nseg=3, h_ref_start=h_rest, T_w_start=20.0, T_air_in_start=T_air_cond);
    Volume_L3 vol2(V=V_n2, p_start=p2_0, h_start=h2_0, fixedState=true);
    HPWDon.EEV_On eev(D_seat=1.0e-3, stroke_max=1.0e-3);
    Volume_L3 vol3(V=V_n3, p_start=p3_0, h_start=h3_0, fixedState=true);
    HPWDevap.Evap_On_Dyn evap(Nseg=3, h_ref_start=h_rest, T_w_start=20.0);
    Accumulator_L3 vol4(V=V_n4, p_start=p4_0, h_start=h4_0, fixedState=true);
    parameter Real open_init = 30.0 "적분기 초기값 [%]. Kp=1,err=-6 이므로 초기개도=open_init-6.
      12 이면 초기개도가 곧바로 최소 6%% 라 콜드스타트 트랩. 설계개도 23.586%% 근처를 주려면 30.";
    // ── 오일 용해 (2026-07-25) ──
    parameter Boolean use_oil = false "true: 압축기 오일 섬프를 충전량 싱크로 연결" annotation(Evaluate=false);
    parameter Real dT_sump = 15.0 "섬프 온도차 [K] ★측정불가 보정계수★" annotation(Evaluate=false);
    parameter Real M_dis_start = 0.084 "초기 오일 용해량 [kg]" annotation(Evaluate=false);
    // ── 노드별 초기상태 (기본=정지조건. Python 정상해 주입용) ──
    parameter Real p1_0 = p_rest; parameter Real h1_0 = h_rest annotation(Evaluate=false);
    parameter Real p2_0 = p_rest; parameter Real h2_0 = h_rest annotation(Evaluate=false);
    parameter Real p3_0 = p_rest; parameter Real h3_0 = h_rest annotation(Evaluate=false);
    parameter Real p4_0 = p_rest; parameter Real h4_0 = h_rest annotation(Evaluate=false);
    OilSump oil(V_oil_cc=160.0, dT_sump=dT_sump, M_dis_start=M_dis_start);
    parameter Real N_scale = 1.0 "압축기 속도 배율 (1.0 = 표 그대로, 최종 1800rpm)";
    parameter Real N_const = 0.0 "0 이면 램프표 사용. >0 이면 그 값으로 고정 [rpm]" annotation(Evaluate=false);
    parameter Real Kp_c = 1.0 "PI 비례게인. Kp_c=Ki_c=0 이면 개도가 open_init 로 고정 (개도고정 시험용)";
    parameter Real Ki_c = 0.3 "PI 적분게인";
    HPWDctrl.PI_Controller ctrl(SH_target=SH_target, Kp=Kp_c, Ki=Ki_c, opening_init=open_init, opening_min=6.0, I(fixed=true));
    Modelica.Blocks.Sources.TimeTable Nsig(table=[
        0.0,    0.0;
        1.0,    300.0;
        11.0,   500.0;
        21.0,   500.0;
        31.0,   1500.0;
        41.0,   1500.0;
        51.0,   N_final;
        500.0,  N_final]);
    Real Pc_bar, Pe_bar, mdot, SH, Q_evap, Q_cond, W_comp, opening;
  equation
    // ── 공기 폐루프: 증발기 출구 → 응축기 입구 (온도·습도) ──
    // 오일 섬프 입력 — 고압쉘이므로 섬프 압력 = 토출압
    oil.P_dis = vol1.p;
    oil.T_dis = comp.T_dis;
    cond.T_air_in = if air_series then evap.T_air_out else T_air_cond;
    cond.Wi       = if air_series then evap.W_air_out else W_air_cond;
    connect(comp.port_b, vol1.port_a);
    connect(vol1.port_b, cond.port_a);
    connect(cond.port_b, vol2.port_a);
    connect(vol2.port_b, eev.port_a);
    connect(eev.port_b, vol3.port_a);
    connect(vol3.port_b, evap.port_a);
    connect(evap.port_b, vol4.port_a);
    connect(vol4.port_b, comp.port_a);
    comp.N = if N_const > 0 then N_const else N_scale*Nsig.y
      "N_const>0 이면 램프표 무시하고 고정속도 (정상해 검증용)";
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

  model Cycle_L3_ssinit "정상상태 초기화 사이클 (2026-07-26)

    콜드스타트로 정상점까지 걸어가는 대신, 초기화 단계에서 der(x)=0 을 직접
    풀어 정상해에서 출발한다. Schulze 2019 (VCC homotopy 초기화),
    Casella 2012 (폐루프 정상초기화의 구조적 특이성) 이 말하는 표준 방식.

    특이성 처리: 모든 상태에 der=0 을 걸면 총 냉매량이 결정되지 않아 계가
    특이해진다. 어큐 압력만 der(p)=0 대신 충전량 구속이 정하도록 뺐다
    (vol4.noInitialPressure=true).
  "
    extends Cycle_L3_coldstart_PI(
      use_oil=true, N_const=1800.0, Kp_c=0.0, Ki_c=0.0,
      open_init=23.586, air_series=true,
      cond(steadyInit=true), evap(steadyInit=true), oil(steadyInit=true),
      vol1(fixedState=false), vol2(fixedState=false), vol3(fixedState=false),
      vol4(noInitialPressure=true));
    parameter Real M_charge = 0.100 "총 냉매 충전량 [kg]" annotation(Evaluate=false);
    Real M_total "시스템 총 냉매량 [kg]";
  equation
    M_total = vol1.rho*vol1.V + vol2.rho*vol2.V + vol3.rho*vol3.V
              + vol4.rho*vol4.V + cond.M_tot + evap.M_tot + oil.M_dis;
  initial equation
    M_total = M_charge "폐루프 특이성 해소 — 충전량이 어큐 압력을 결정";
  end Cycle_L3_ssinit;

end HPWDcycle;
