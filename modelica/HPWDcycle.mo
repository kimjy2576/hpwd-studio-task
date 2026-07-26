within ;
package HPWDcycle "L3 사이클 조립 (Comp_Chamber + Cond_On + EEV_On + Evap_On 폐루프)"

  model OilSump "압축기 오일 섬프 — 냉매 용해 저장소 (2026-07-25)

    사이클 충전량의 상당분이 압축기 오일에 용해되어 순환하지 않는다.
    Python 정방향(충전량 구속) 해에서 100g 중 84g 이 오일에 용해.
    이 항이 없으면 순환 냉매가 실제의 5배가 되어 어큐 범람 -> 응축기
    액범람 -> Pc 26bar / SH=0 의 잘못된 운전점으로 수렴한다.

    고압쉘 압축기이므로 섬프는 토출압에 노출된다.
    T_sump 는 압축기 쉘 에너지수지에서 나온 벽온도 T_w 를 그대로 쓴다 (고압쉘).
    양(Pc, Pe, SH, T_dis, 소비전력)으로 역보정할 것.
    용해량이 여기에 극도로 민감함: dT 5~20K 에서 용해 43~81g.
  "
    parameter Real V_oil_cc = 160.0 "오일 주입체적 [cc]";
    parameter Real dT_offset = 0.0 "섬프 보정 오프셋 [K]. T_sump = T_shell - dT_offset" annotation(Evaluate=false);
    parameter Real tau = 300.0 "용해/탈리 시상수 [s].
      2026-07-26 문헌 근거로 30 -> 300 변경.
      기존 30s 는 근거 없이 넣은 값이며 쉘 압력과 강성 되먹임을 만들어
      콜드스타트가 t=24 에서 정지했음 (tau>=120s 면 완주).
      문헌:
      - 흡수는 정지 상태에서 확산 지배이며(Barbosa 계열), 자연대류 개시와
        운전 중 교반(모터 로터·베인·토출류)이 속도를 크게 높인다.
      - Purdue ICEC 2016: 운전 압축기에서 측정한 '동적 용해도'는 PVT 선도의
        '정적 용해도'와 다르다. 우리 모델은 정적 상관식 + 1차 지연 구조이므로
        tau 가 그 차이를 대신 흡수하는 파라미터임.
      - US5211542: 섬프 압력을 흡입압까지 낮추는 데 통상 2~10분 —
        섬프 탈기 시간 규모가 120~600s 임을 시사.
      검증: tau 120/300/600/1000s 전부 완주하고 SH 를 목표 6.0K 로 제어.
      t=300s 는 아직 오일 평형 도중이라 tau 에 따라 M_dis 78/71/61/55g 로
      갈리나 모두 같은 정상해로 수렴하는 경로임 (tau=120 에서 Pc 10.45 로
      ssinit 정상해 10.46 에 근접).
      ★실측으로 확정할 것★";
    parameter Real M_dis_start = 0.084 "초기 용해량 [kg]" annotation(Evaluate=false);
    parameter Real M_eq_max = 0.09 "평형 용해량 상한 [kg].
      유효범위 밖에서 dissolved 가 발산하는 것을 막는 물리적 상한.
      2026-07-26: 기존 0.15 는 총 충전량 100g 보다 커서 무의미했음 —
      콜드스타트 중 code=2 구간에서 M_dis 가 149.9g 까지 올라 충전량을
      초과했음. 상위 모델에서 충전량에 연동해 넘길 것 (0.9*M_charge 권장).";
    input Real P_dis "섬프 압력 (고압쉘 = 토출압) [Pa]";
    input Real T_shell "쉘(섬프) 온도 [K] — 압축기 벽 에너지수지에서";
    Real M_oil "오일 질량 [kg]";
    Real M_eq "평형 용해량 [kg] (상한 매끄럽게 반영)";
    Real M_eq_raw "상관식 원값 [kg] — 유효범위 밖에서 발산함";
    parameter Boolean steadyInit = false "true: der(M_dis)=0";
    parameter Integer initOpt = 0 "0=legacy 1=noInit 2=fixedState 3=steadyState";
    Real M_dis(start=M_dis_start, fixed=false) "현재 용해량 [kg]";
    Real m_flow "냉매 -> 오일 흡수율 [kg/s]. 양수면 회로에서 빠져나감";
    Integer code "R290Oil.validity: 0=ok 1=외삽 2=파탄";
  initial equation
    if initOpt == 1 then
      // noInit
    elseif initOpt == 3 or (initOpt == 0 and steadyInit) then
      der(M_dis)=0;
    else
      M_dis=M_dis_start;
    end if;
  equation
    M_oil = R290Oil.oil_mass(V_oil_cc);
    M_eq_raw = R290Oil.dissolved(M_oil, P_dis, T_shell - dT_offset);
    // 매끄러운 min. 경성 min() 은 미분 불연속을 만들어 사이클을 강성으로 만든다.
    //   실측(T_shell 305K): P=12bar 에서 dM_eq/dP = 44.6 g/bar,
    //   P=15bar 에서 651 g/bar 로 발산(P>Psat 라 x1 이 0.99 클램프에 붙음),
    //   그 위는 min() 에 걸려 0 g/bar. 651 -> 0 의 꺾임이 콜드스타트를 막았음.
    //   콜드스타트는 8.365 -> 25bar 로 이 절벽을 정면 통과한다.
    // smooth min: 0.5*(a+b-sqrt((a-b)^2+eps^2)),  eps = 5% of M_eq_max
    M_eq  = 0.5*(M_eq_raw + M_eq_max
                 - sqrt((M_eq_raw - M_eq_max)^2 + (0.05*M_eq_max)^2))
      "상한 클램프: 유효범위 밖에서 dissolved 가 발산함 (실측 26bar/32C 에서 2114g)";
    code  = R290Oil.validity(P_dis, T_shell - dT_offset);
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
    // ThermoPower Water.mo:735 패턴. steadyStateNoP 같은 별도 모드 대신
    // 컴포넌트별 플래그로 중복 초기방정식을 하나만 제거한다.
    parameter Boolean noInitialPressure = false "정상초기화에서 der(p)=0 을 제거";
    parameter Boolean noInitialEnthalpy = false "정상초기화에서 der(h)=0 을 제거";
    parameter Integer initOpt = 0 "0=legacy 1=noInit 2=fixedState 3=steadyState";
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
    // initOpt: 0=legacy(fixedState 플래그 따름) 1=noInit 2=fixedState 3=steadyState
    // noInit 은 초기방정식을 전혀 두지 않아 -iif 로 준 상태를 그대로 받는다
    // (ThermoPower Choices.Init.Options.noInit 대응).
    // ※ 앞서 '중첩 if 가 원인'이라 적었던 주석은 오진이었음. 실제 원인은
    //   분기 우선순위(fixedState 가 플래그를 이김)였고 vol4(fixedState=false)
    //   를 명시해 해결했음.
    if initOpt == 1 then
      // 초기방정식 없음
    elseif initOpt == 2 or (initOpt == 0 and fixedState) then
      p=p_start;
      h=h_start;
    elseif noInitialPressure and noInitialEnthalpy then
      p=p_start;
      h=h_start;
    elseif noInitialPressure then
      der(h)=0;
    elseif noInitialEnthalpy then
      der(p)=0;
    else
      der(p)=0;
      der(h)=0;
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
    // ThermoPower Water.mo:735 패턴. steadyStateNoP 같은 별도 모드 대신
    // 컴포넌트별 플래그로 중복 초기방정식을 하나만 제거한다.
    parameter Boolean noInitialPressure = false "정상초기화에서 der(p)=0 을 제거";
    parameter Boolean noInitialEnthalpy = false "정상초기화에서 der(h)=0 을 제거";
    parameter Integer initOpt = 0 "0=legacy 1=noInit 2=fixedState 3=steadyState";
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
    // initOpt: 0=legacy(fixedState 플래그 따름) 1=noInit 2=fixedState 3=steadyState
    // noInit 은 초기방정식을 전혀 두지 않아 -iif 로 준 상태를 그대로 받는다
    // (ThermoPower Choices.Init.Options.noInit 대응).
    // ※ 앞서 '중첩 if 가 원인'이라 적었던 주석은 오진이었음. 실제 원인은
    //   분기 우선순위(fixedState 가 플래그를 이김)였고 vol4(fixedState=false)
    //   를 명시해 해결했음.
    if initOpt == 1 then
      // 초기방정식 없음
    elseif initOpt == 2 or (initOpt == 0 and fixedState) then
      p=p_start;
      h=h_start;
    elseif noInitialPressure and noInitialEnthalpy then
      p=p_start;
      h=h_start;
    elseif noInitialPressure then
      der(h)=0;
    elseif noInitialEnthalpy then
      der(p)=0;
    else
      der(p)=0;
      der(h)=0;
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
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
    // ── 압축기 쉘 가스 체적 (2026-07-26 신설) ──
    // 고압쉘이므로 쉘 내부는 토출압 가스로 채워지고, 오일 섬프도 그 안에 있다.
    // 기존에는 이 체적이 인벤토리에 아예 없었고(체크리스트 414.1cc = HX+배관+어큐),
    // 오일 질량 싱크를 18.3cc 토출배관(vol1, 냉매 0.366g)에 붙여놨었다.
    // 그 결과 vol1.p -> M_eq -> m_ext -> vol1 질량 -> vol1.p 되먹임의 시상수가
    //   dM_eq/dP = 33.7 g/bar,  dM1/dp = 0.035 g/bar,  tau_oil = 30s
    //   -> tau_loop = 0.035/(33.7/30) ~ 0.031 s
    // 로 다른 시상수(볼륨 ~s, HX벽 ~수십s)보다 1000배 빨라 사이클이 강성으로 정지했다.
    // 실측: V_n1 18cc -> t=3 정체 / 100cc -> 완주.
    // ★V_shell 은 실물 압축기 사양에서 확인할 것★ (행정체적 7.5cm3 와 무관한 값)
    parameter Real V_shell = 4.0e-4 "압축기 쉘 가스 체적 [m3] ★실물 확인 필요★" annotation(Evaluate=false);
    Volume_L3 vshell(V=V_shell, p_start=p1_0, h_start=h1_0, fixedState=true,
                     m_ext=if use_oil then oil.m_flow else 0);
    Volume_L3 vol1(V=V_n1, p_start=p1_0, h_start=h1_0, fixedState=true);
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
    parameter Real dT_offset = 0.0 "섬프 보정 오프셋 [K] (기본 0 — 쉘 벽온도를 그대로 사용)" annotation(Evaluate=false);
    parameter Real M_charge = 0.100 "총 냉매 충전량 [kg]. 오일 용해 상한 연동용" annotation(Evaluate=false);
    parameter Real M_dis_start = 0.084 "초기 오일 용해량 [kg]" annotation(Evaluate=false);
    // ── 노드별 초기상태 (기본=정지조건. Python 정상해 주입용) ──
    parameter Real p1_0 = p_rest; parameter Real h1_0 = h_rest annotation(Evaluate=false);
    parameter Real p2_0 = p_rest; parameter Real h2_0 = h_rest annotation(Evaluate=false);
    parameter Real p3_0 = p_rest; parameter Real h3_0 = h_rest annotation(Evaluate=false);
    parameter Real p4_0 = p_rest; parameter Real h4_0 = h_rest annotation(Evaluate=false);
    OilSump oil(V_oil_cc=160.0, dT_offset=dT_offset, M_dis_start=M_dis_start, M_eq_max=0.9*M_charge);
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
    oil.P_dis = vshell.p "고압쉘 — 오일 섬프는 쉘 안";
    oil.T_shell = comp.T_w "쉘 벽온도 = 섬프 온도 (고압쉘)";
    cond.T_air_in = if air_series then evap.T_air_out else T_air_cond;
    cond.Wi       = if air_series then evap.W_air_out else W_air_cond;
    connect(comp.port_b, vshell.port_a);
    connect(vshell.port_b, vol1.port_a);
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
      cond(steadyInit=true, h_ref_start=362350, T_w_start=27.0),
      evap(steadyInit=true, h_ref_start=334610, T_w_start=10.0),
      oil(steadyInit=true),
      vshell(fixedState=false), vol1(fixedState=false), vol2(fixedState=false), vol3(fixedState=false),
      vol4(fixedState=false, noInitialPressure=true),
      // 가지 B(superheated) 근처 초기추정. 정상초기화에서 p_start/h_start 는
      // 고정값이 아니라 뉴턴 초기추정이므로 어느 정상해로 수렴할지에 영향.
      // 기본값(정지조건 8.365bar/265.5kJ/kg)은 두 가지 모두에서 멀다.
      p1_0=1041100, h1_0=642369,
      p2_0=1021000, h2_0=330734,
      p3_0= 604500, h3_0=330734,
      p4_0= 604500, h4_0=583705);

    Real M_total "시스템 총 냉매량 [kg]";
  equation
    M_total = vshell.rho*vshell.V + vol1.rho*vol1.V + vol2.rho*vol2.V
              + vol3.rho*vol3.V + vol4.rho*vol4.V
              + cond.M_tot + evap.M_tot + oil.M_dis;
  initial equation
    M_total = M_charge "폐루프 특이성 해소 — 충전량이 어큐 압력을 결정";
  end Cycle_L3_ssinit;

  model Cycle_L3_branchtest "가지 B 상태에서 출발하는 과도 — 다중해 판정용 (2026-07-26)

    질문: dT_sump=15 에서 가지 A(SH=0) 와 가지 B(SH=5.5) 가 둘 다 안정한가,
          아니면 A 만 안정하고 B 는 초기화 경로의 산물인가.
    방법: 가지 B(dT_sump=20 정상해)의 상태를 fixedState 로 고정 초기화하고
          dT_sump=15 로 과도해석. B 에 머물면 진짜 다중해, A 로 흘러가면 아님.
    초기 충전량은 100g 이 되도록 HX 엔탈피를 역산해 맞췄음
    (노드 4.258 + 오일 90.093 + 응축기 4.193 + 증발기 1.455 = 99.999 g).
  "
    extends Cycle_L3_coldstart_PI(
      use_oil=true, N_const=1800.0, Kp_c=0.0, Ki_c=0.0,
      open_init=23.586, air_series=true, M_dis_start=0.0900933,
      p1_0=1041060, h1_0=649646,
      p2_0=1024050, h2_0=331815,
      p3_0= 604497, h3_0=331815,
      p4_0= 582345, h4_0=594178,
      cond(h_ref_start=448846, T_w_start=27.0),
      evap(h_ref_start=439579, T_w_start=10.0));
    Real M_total "시스템 총 냉매량 [kg] (구속 아님 — 초기값이 결정)";
  equation
    M_total = vshell.rho*vshell.V + vol1.rho*vol1.V + vol2.rho*vol2.V
              + vol3.rho*vol3.V + vol4.rho*vol4.V
              + cond.M_tot + evap.M_tot + oil.M_dis;
  end Cycle_L3_branchtest;

  model Cycle_L3_noinit "초기방정식 없음 — -iif 로 상태를 받아 과도 (2026-07-26)

    다중해 판정용. ssinit 이 낸 가지 B 의 전체 상태(셀 120개 포함)를 mat 으로
    받아 그 지점에서 출발시킨다. fixedState 로는 h_ref_start 가 스칼라라
    셀 프로파일을 줄 수 없고, -iif 값도 초기방정식에 덮여 실패했음.
    initOpt=1 (noInit) 이면 초기방정식이 없어 -iif 상태가 그대로 유지된다.
  "
    extends Cycle_L3_coldstart_PI(
      use_oil=true, N_const=1800.0, Kp_c=0.0, Ki_c=0.0,
      open_init=23.586, air_series=true,
      cond(initOpt=1), evap(initOpt=1), oil(initOpt=1),
      vshell(initOpt=1), vol1(initOpt=1), vol2(initOpt=1), vol3(initOpt=1), vol4(initOpt=1));
    Real M_total "시스템 총 냉매량 [kg] (구속 아님)";
  equation
    M_total = vshell.rho*vshell.V + vol1.rho*vol1.V + vol2.rho*vol2.V
              + vol3.rho*vol3.V + vol4.rho*vol4.V
              + cond.M_tot + evap.M_tot + oil.M_dis;
  end Cycle_L3_noinit;

  model Cycle_L3_coldstart_charge "정지조건을 충전량에서 유도하는 콜드스타트 (2026-07-26)

    문제: 기존 콜드스타트는 h_rest / M_dis_start 를 손으로 넣는 구조라
    구성(쉘 체적, 오일 ON/OFF)이 바뀔 때마다 조용히 과충전됐다.
      h_rest=265.5kJ/kg 은 '414.1cc 가 정확히 100g' 이 되도록 역산된 값이라
      쉘 400cc 를 더하면 정지 충전량이 196g 이 된다(목표의 2배).
      M_dis_start 도 회로에서 빠지지 않고 더해져 오일 ON 이면 +84% 과충전.

    해결: ssinit 과 같은 방식으로 초기화에 충전량 구속을 건다.
      정지상태는 전 시스템이 주위온도·포화압에서 균일하다고 보고
      엔탈피를 단일 미지수 h0 로 두면, M_total = M_charge 가 h0 를 결정한다.
      오일은 정지 평형(der(M_dis)=0 과 동치인 M_dis = M_eq)으로 둔다.
      -> 구성이 바뀌어도 충전량이 자동으로 맞는다.
  "
    extends Cycle_L3_coldstart_PI(
      use_oil=true, air_series=true,
      vshell(initOpt=1), vol1(initOpt=1), vol2(initOpt=1),
      vol3(initOpt=1), vol4(initOpt=1),
      cond(initOpt=1), evap(initOpt=1), oil(initOpt=1));
    // parameter + fixed=false: 초기화에서 풀리고 이후 상수로 유지되는 미지수.
    // Real 로 두면 t>0 에 방정식이 없어 시뮬레이션계가 1개 부족해진다.
    parameter Real h0(fixed=false, start=3.0e5) "정지 균일 엔탈피 [J/kg] — 충전량 구속이 결정";
    Real M_total "시스템 총 냉매량 [kg]";
  equation
    M_total = vshell.rho*vshell.V + vol1.rho*vol1.V + vol2.rho*vol2.V
              + vol3.rho*vol3.V + vol4.rho*vol4.V
              + cond.M_tot + evap.M_tot + oil.M_dis;
  initial equation
    // 압력: 주위온도 포화압으로 균일
    vshell.p = p_rest; vol1.p = p_rest; vol2.p = p_rest;
    vol3.p = p_rest;   vol4.p = p_rest;
    // 엔탈피: 단일 미지수 h0 로 균일 (충전량이 결정)
    vshell.h = h0; vol1.h = h0; vol2.h = h0; vol3.h = h0; vol4.h = h0;
    for k in 1:cond.M loop
      cond.h_ref[k] = h0;
      cond.T_w[k] = T_air_cond;
    end for;
    for k in 1:evap.M loop
      evap.h_ref[k] = h0;
      evap.T_w[k] = evap.T_air_in;
    end for;
    cond.m_ref_col = 0.0;
    evap.m_ref_col = 0.0;
    cond.dp_lag = 0.0;
    // 오일: 정지 평형 (der(M_dis)=0 과 동치)
    oil.M_dis = oil.M_eq;
    // PI 적분기 (자체 초기방정식이 없어 명시 필요)
    ctrl.I = open_init;
    // 충전량 구속 — h0 를 결정
    M_total = M_charge;
  end Cycle_L3_coldstart_charge;

end HPWDcycle;
