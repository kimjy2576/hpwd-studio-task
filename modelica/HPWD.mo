package HPWD "HPWD 냉매 사이클 컴포넌트 (L1)"

  connector RefPort "냉매 포트 (stream connector)"
    Modelica.Units.SI.AbsolutePressure p;
    flow Modelica.Units.SI.MassFlowRate m_flow;
    stream Modelica.Units.SI.SpecificEnthalpy h_outflow;
  end RefPort;

  function ahriPoly "AHRI 540 10-coefficient 다항식"
    input Real C[10]; input Real Te; input Real Tc; output Real Y;
  algorithm
    Y := C[1] + C[2]*Te + C[3]*Tc + C[4]*Te^2 + C[5]*Te*Tc + C[6]*Tc^2
       + C[7]*Te^3 + C[8]*Tc*Te^2 + C[9]*Te*Tc^2 + C[10]*Tc^3;
  end ahriPoly;

  model Source "boundary 소스"
    RefPort port;
    parameter Modelica.Units.SI.AbsolutePressure p = 5.51e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h = 589.2518e3;
  equation
    port.p = p;
    port.h_outflow = h;
  end Source;

  model Sink "boundary 싱크"
    RefPort port;
    parameter Modelica.Units.SI.AbsolutePressure p = 19.07e5;
    parameter Modelica.Units.SI.SpecificEnthalpy h = 250e3;
  equation
    port.p = p;
    port.h_outflow = h;
  end Sink;

  model EEV_L1 "EEV Off-design — acausal stream TwoPort"
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "inlet (상류)";
    RefPort port_b "outlet (하류)";
    Modelica.Blocks.Interfaces.RealInput opening "개도 [%] (신호 입력)";
    parameter Real A_orifice=3.14e-6, Cv_rated=0.7;
    parameter Real c0=0.0, c1=0.5, c2=0.3, c3=0.2;
    parameter Real opening_min=0.0;
    Real op, phi, h_in, rho_in;
  equation
    op = max(opening_min, min(100.0, opening))/100.0;
    phi = c0 + c1*op + c2*op^2 + c3*op^3;
    h_in = inStream(port_a.h_outflow);
    rho_in = M.density(M.setState_ph(port_a.p, h_in));
    port_a.m_flow = Cv_rated*A_orifice*phi*sqrt(max(1.0, 2.0*rho_in*(port_a.p - port_b.p)));
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_in;
    port_a.h_outflow = port_b.h_outflow;
  end EEV_L1;

  model Comp_AHRI "압축기 AHRI — acausal stream TwoPort (흡입 a → 토출 b)"
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "흡입 (저압)";
    RefPort port_b "토출 (고압)";
    parameter Real N=3000.0, N_rated=3000.0, eta_motor=0.92, alpha_W=1.0;
    parameter Real Mc[10] = {1.584115e+01, 4.950100e-01, -2.289228e-02,
       5.213752e-03, 5.696390e-04, -1.838950e-04, 2.544573e-05,
       1.200546e-05, -5.465480e-06, -1.224724e-06};
    parameter Real Wc[10] = {2.207072e+02, 5.981247e+01, -3.230793e+00,
       2.018269e+00, -2.429011e+00, 1.463795e-01, 1.191119e-02,
       -3.784984e-02, 1.995116e-02, 8.855172e-04};
    Real T_e, T_c, m_dot_kgh, W_ref, rpm_ratio, m_dot, W_elec, W_shaft;
    Real h_suc, h_dis;
  equation
    T_e = M.saturationTemperature(port_a.p) - 273.15;
    T_c = M.saturationTemperature(port_b.p) - 273.15;
    m_dot_kgh = ahriPoly(Mc, T_e, T_c);
    W_ref     = ahriPoly(Wc, T_e, T_c);
    rpm_ratio = N/N_rated;
    m_dot   = (m_dot_kgh/3600.0)*rpm_ratio;
    W_elec  = W_ref*rpm_ratio^alpha_W;
    W_shaft = W_elec*eta_motor;
    h_suc = inStream(port_a.h_outflow);
    h_dis = h_suc + W_shaft/m_dot;
    port_a.m_flow = m_dot;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_dis;
    port_a.h_outflow = port_b.h_outflow;
  end Comp_AHRI;

  model Comp_Theoretical "이론적 압축기 — 체적효율 + 등엔트로피효율 (L1)"
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "흡입 (저압)";
    RefPort port_b "토출 (고압)";
    parameter Real V_disp = 10e-6 "행정체적 [m³/rev]";
    parameter Real N = 3000.0 "회전수 [rpm] (목표/정격)";
    parameter Real eta_vol = 0.85 "체적효율";
    parameter Real eta_isen = 0.65 "등엔트로피효율";
    parameter Real t_ramp = 0.0 "기동 ramp 시간 [s]. 0이면 N 고정(단독검증), >0이면 0→N로 선형 상승";
    Real N_eff "유효 회전수 (ramp 적용)";
    Real h_suc(start=590e3), s_suc(start=2450), rho_suc(start=11), h_dis_s(start=648e3), h_dis(start=680e3), m_dot(start=0.005), W(start=450);
  equation
    N_eff = if t_ramp > 0.0 then N*min(1.0, time/t_ramp) else N;    // 정지(N=0)에서 운전점으로 단계 기동
    h_suc = inStream(port_a.h_outflow);
    rho_suc = M.density(M.setState_ph(port_a.p, h_suc));
    s_suc = M.specificEntropy(M.setState_ph(port_a.p, h_suc));
    h_dis_s = M.specificEnthalpy(M.setState_ps(port_b.p, s_suc));   // 등엔트로피 토출
    m_dot = eta_vol*V_disp*(N_eff/60.0)*rho_suc;                    // ṁ = ηv·Vd·(N_eff/60)·ρ_suc
    W = m_dot*(h_dis_s - h_suc)/eta_isen;                           // 소요 동력
    h_dis = h_suc + (h_dis_s - h_suc)/eta_isen;                     // 실제 토출 엔탈피
    port_a.m_flow = m_dot;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_dis;
    port_a.h_outflow = port_b.h_outflow;
  end Comp_Theoretical;

  model Comp_Winandy "압축기 Winandy 반경험 (L2) — 흡입가열·ηv(rp)·over/under-comp·열손실"
    // Winandy E., Saavedra C., Lebrun J. (2002), Int. J. Thermal Sciences 41(2).
    // Python 원본 backend/components/compressor_winandy.py와 동일 식. T_wall fixed-point
    // iteration → Modelica 비인과 방정식(벽 에너지 균형) 1개로, 솔버가 동시해.
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "흡입 (저압)";
    RefPort port_b "토출 (고압)";
    // ── 기하/운전 ──
    parameter Real V_disp = 10e-6 "행정체적 [m³/rev]";
    parameter Real N = 3000.0 "회전수 [rpm]";
    parameter Real V_se = 0.95 "swept volume 효율 (ηv 식 절편)";
    parameter Real rv_in = 2.5 "built-in 체적비 (over/under-comp)";
    parameter Real clearance_factor = 0.05 "ηv clearance 항 가중";
    parameter Real over_comp_factor = 0.5 "over-comp 손실 계수";
    // ── 열/손실 (semi-empirical fit, R290 ~10cc) ──
    parameter Real AU_su = 3.0 "흡입 가열 UA [W/K]";
    parameter Real AU_loss = 5.0 "외부 열손실 UA [W/K]";
    parameter Real dP_su = 0.05 "흡입 압력손실 비율 [-]";
    parameter Real W_loss0 = 30.0 "정수 기계손실 [W]";
    parameter Real alpha_loss = 0.1 "비례 기계손실 [-]";
    parameter Real eta_motor = 0.92 "모터 효율";
    parameter Modelica.Units.SI.Temperature T_amb = 308.15 "shell 주위 온도 [K]";
    parameter Real t_ramp = 0.0 "기동 ramp [s] (0=N 고정 단독검증)";
    // ── 변수 ──
    Real N_eff;
    Modelica.Units.SI.AbsolutePressure P_su2;
    Real h_su1, cp_su1;
    Modelica.Units.SI.Temperature T_su1, T_su2, T_w(start = 333.15) "외벽 온도";
    Real eps_su, h_su2, s_su2, rho_su2, v_su2, gamma, rp, clearance_term, eta_v;
    Real m_dot(start = 0.005), h_dis_is, w_is, P_internal, w_extra_raw, w_extra, w_actual, h_dis;
    Real W_shaft(start = 450), W_loss_mech, W_elec, Q_loss;
    Modelica.Units.SI.Temperature T_dis "토출 온도 [K]";
    M.ThermodynamicState st_su2;
  equation
    N_eff = if t_ramp > 0.0 then N*min(1.0, time/t_ramp) else N;
    // 1. 흡입 압력손실
    P_su2 = port_a.p*(1.0 - dP_su);
    // 2. 흡입 shell 입구 (inStream → T_su1)
    h_su1 = inStream(port_a.h_outflow);
    T_su1 = M.temperature(M.setState_ph(port_a.p, h_su1));
    cp_su1 = M.specificHeatCapacityCp(M.setState_ph(port_a.p, h_su1));
    // 3a. 흡입 가열 (ε-NTU: 뜨거운 벽 → 가스)
    eps_su = 1.0 - exp(-AU_su/max(m_dot*cp_su1, 1e-6));
    T_su2 = T_su1 + eps_su*(T_w - T_su1);
    st_su2 = M.setState_pT(P_su2, T_su2);
    h_su2 = M.specificEnthalpy(st_su2);
    s_su2 = M.specificEntropy(st_su2);
    rho_su2 = M.density(st_su2);
    v_su2 = 1.0/rho_su2;
    // 3b. 체적효율 (clearance 재팽창, ηv = V_se - c·(rp^(1/γ)-1))
    gamma = M.specificHeatCapacityCp(st_su2)/M.specificHeatCapacityCv(st_su2);
    rp = port_b.p/port_a.p;
    clearance_term = max(0.0, rp^(1.0/gamma) - 1.0);
    eta_v = max(0.05, V_se - clearance_factor*clearance_term);
    // 3c. 질량유량
    m_dot = eta_v*V_disp*(N_eff/60.0)*rho_su2;
    // 3d. 등엔트로피 토출 + over/under-compression (built-in rv)
    h_dis_is = M.specificEnthalpy(M.setState_ps(port_b.p, s_su2));
    w_is = h_dis_is - h_su2;
    P_internal = P_su2*(rv_in^gamma);
    w_extra_raw = v_su2*(port_b.p - P_internal);
    w_extra = if w_extra_raw < 0.0 then over_comp_factor*(-w_extra_raw) else w_extra_raw;
    w_actual = w_is + w_extra;
    h_dis = h_su2 + w_actual;
    // 3e. shaft work → 기계손실 → 벽 에너지 균형(정상상태)으로 T_w 해
    W_shaft = m_dot*w_actual;
    W_loss_mech = W_loss0 + alpha_loss*W_shaft;
    AU_loss*(T_w - T_amb) + AU_su*(T_w - T_su1) = W_loss_mech;
    // 4-5. 전기입력 + 외부 열손실
    W_elec = (W_shaft + W_loss_mech)/eta_motor;
    Q_loss = AU_loss*(T_w - T_amb);
    T_dis = M.temperature(M.setState_ph(port_b.p, h_dis));
    // 포트 balance (acausal stream)
    port_a.m_flow = m_dot;
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_dis;
    port_a.h_outflow = port_b.h_outflow;
  end Comp_Winandy;

  model CompWinandyCircuit "흡입 → Winandy 압축기 → 토출 (단독 검증)"
    Source src(p = 5.51e5, h = 589.2518e3);
    Comp_Winandy comp;
    Sink snk(p = 19.07e5);
  equation
    connect(src.port, comp.port_a);
    connect(comp.port_b, snk.port);
  end CompWinandyCircuit;

  model CompCircuit "흡입 → 압축기 → 토출 (검증)"
    Source src(p=5.51e5, h=589.2518e3);
    Comp_AHRI comp;
    Sink snk(p=19.07e5);
  equation
    connect(src.port, comp.port_a);
    connect(comp.port_b, snk.port);
  end CompCircuit;

  model Evap_SH "증발기 — SH 고정 모드 (사이클 닫기용)"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "입구 (2상)";
    RefPort port_b "출구 (과열)";
    parameter Real SH_set = 5.0 "출구 과열도 [K]";
    Real m_dot, h_in, h_out, T_sat;
  equation
    port_a.p = port_b.p;                 // 등압 (dP 무시)
    m_dot = port_a.m_flow;               // ṁ 통과
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    T_sat = Ref.saturationTemperature(port_b.p);
    h_out = Ref.specificEnthalpy(Ref.setState_pT(port_b.p, T_sat + SH_set));
    port_b.h_outflow = h_out;            // 출구 SH 고정
    port_a.h_outflow = port_b.h_outflow;
  end Evap_SH;

  model Cond_SC "응축기 — SC 고정 모드 (사이클 닫기용)"
    package Ref = HelmholtzMedia.HelmholtzFluids.Propane;
    RefPort port_a "입구 (과열증기)";
    RefPort port_b "출구 (과냉액)";
    parameter Real SC_set = 5.0 "출구 과냉도 [K]";
    Real m_dot, h_in, h_out, T_sat;
  equation
    port_a.p = port_b.p;
    m_dot = port_a.m_flow;
    port_a.m_flow + port_b.m_flow = 0;
    h_in = inStream(port_a.h_outflow);
    T_sat = Ref.saturationTemperature(port_b.p);
    h_out = Ref.specificEnthalpy(Ref.setState_pT(port_b.p, T_sat - SC_set));
    port_b.h_outflow = h_out;            // 출구 SC 고정
    port_a.h_outflow = port_b.h_outflow;
  end Cond_SC;

  model Cycle_L1 "L1 사이클 폐루프: 압축기→응축기→EEV→증발기→압축기"
    Comp_AHRI comp(N=3000.0);
    Cond_SC cond(SC_set=5.0);
    EEV_L1 eev(opening_pct=50.0);
    Evap_SH evap(SH_set=5.0);
  equation
    connect(comp.port_b, cond.port_a);   // 토출 → 응축기
    connect(cond.port_b, eev.port_a);    // 응축기 → EEV
    connect(eev.port_b, evap.port_a);    // EEV → 증발기
    connect(evap.port_b, comp.port_a);   // 증발기 → 흡입 (폐루프)
  end Cycle_L1;

end HPWD;
