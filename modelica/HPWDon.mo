package HPWDon "HPWD 냉매 사이클 컴포넌트 (L3 On-Design) — needle-cone EEV / chamber 압축기 / tube-segment HX"

  // ════════════════════════════════════════════════════════════════════
  //  EEV_On — Electronic Expansion Valve (On-Design / Needle Cone)
  //  Python 기준: backend/components/eev_on_design.py
  //    A_throat = π·D_seat·stroke·sin(α)   [cone],  clamp π(D_seat/2)²,  ×cf_A
  //    dP_eff   = (P_out/P_in < choke_ratio) ? P_in·(1−choke_ratio) : (P_in−P_out)
  //    Cd_eff   = Cd_base·(0.5 + 0.5·Re/(Re+Re_trans)),  Re = m₁·D_h/(μ·A)
  //    m_dot    = Cd_eff·A·√(2ρ_in·dP_eff),  h_out = h_in (등엔탈피)
  //  물성: R290Tab(p,h) — CoolProp 없이 OM 심볼릭 미분.
  // ════════════════════════════════════════════════════════════════════
  model EEV_On "EEV On-design — needle-cone 기하 + 2상 choke + Re-Cd, acausal stream TwoPort"
    HPWD.RefPort port_a "inlet (상류, 응축기측 고압)";
    HPWD.RefPort port_b "outlet (하류, 증발기측 저압)";
    Modelica.Blocks.Interfaces.RealInput opening "개도 [%] (신호 입력)";

    // ─ 기하 (needle + seat) ─
    parameter Modelica.Units.SI.Length D_seat = 2.0e-3 "seat 직경";
    parameter Modelica.Units.SI.Length stroke_max = 1.0e-3 "최대 stroke";
    parameter Real needle_angle_deg = 30.0 "needle cone 반각 α/2 [deg]";
    parameter Real cf_A = 1.0 "throat 면적 보정계수";
    // ─ 유동 ─
    parameter Real Cd_base = 0.72 "기준 토출계수";
    parameter Real Re_transition = 1000.0 "Re 전이값";
    parameter Real choke_ratio = 0.5 "임계 압력비 (P_out/P_in)";
    parameter Real opening_min = 0.0 "최소 개도 [%]";
    // ─ 파생 상수 ─
    final parameter Real alpha = needle_angle_deg*Modelica.Constants.pi/180.0;
    final parameter Real A_max = Modelica.Constants.pi*(D_seat/2.0)^2 "full-open orifice 면적";

    // ─ 변수 ─
    Real op "개도 분율 (0~1)";
    Real stroke, A_cone, A_throat;
    Real h_in, rho_in, mu_in;
    Real dP, dP_eff, m1, D_h, Re, Cd_eff;
  equation
    h_in   = inStream(port_a.h_outflow);
    rho_in = R290Tab.rho_ph(port_a.p, h_in);
    mu_in  = R290Tab.mu_ph(port_a.p, h_in);

    // needle-cone 기하 → throat 면적
    op       = max(opening_min, min(100.0, opening))/100.0;
    stroke   = stroke_max*op;
    A_cone   = Modelica.Constants.pi*D_seat*stroke*sin(alpha);
    A_throat = min(A_cone, A_max)*cf_A;

    // 2상 choke (vena contracta 임계 압력비)
    dP     = port_a.p - port_b.p;
    dP_eff = if (port_b.p/port_a.p) < choke_ratio then port_a.p*(1.0 - choke_ratio) else dP;

    // Re 기반 Cd 보정 (1차 m_dot → Re → Cd_eff)
    m1     = Cd_base*A_throat*sqrt(max(1e-9, 2.0*rho_in*dP_eff));
    D_h    = sqrt(4.0*A_throat/Modelica.Constants.pi + 1e-30);
    Re     = m1*D_h/max(1e-12, mu_in*A_throat);
    Cd_eff = Cd_base*(0.5 + 0.5*Re/(Re + Re_transition));

    // 유량 + 등엔탈피 팽창
    port_a.m_flow = Cd_eff*A_throat*sqrt(max(1e-9, 2.0*rho_in*dP_eff));
    port_a.m_flow + port_b.m_flow = 0;
    port_b.h_outflow = h_in;
    port_a.h_outflow = port_b.h_outflow;
  end EEV_On;

  // ── 단품 검증: Source(P_in,h_in) → EEV_On(opening) → Sink(P_out) ──
  model TestEevOn "EEV_On 단품 검증 (control 모드 등가)"
    HPWD.Source src(p = 17.13e5, h = 280.0e3);
    HPWDon.EEV_On eev(
      D_seat = 2.0e-3, stroke_max = 1.0e-3, needle_angle_deg = 30.0, cf_A = 1.0,
      Cd_base = 0.72, Re_transition = 1000.0, choke_ratio = 0.5);
    HPWD.Sink snk(p = 5.675e5, h = 280.0e3);
    Modelica.Blocks.Sources.Constant openSig(k = 50.0);
  equation
    connect(openSig.y, eev.opening);
    connect(src.port, eev.port_a);
    connect(eev.port_b, snk.port);
  end TestEevOn;

  // ════════════════════════════════════════════════════════════════════
  //  Comp_Chamber — 압축기 (Chamber 1-Cycle 평균물리) On-Design
  //  Python 기준: backend/components/compressor_chamber.py
  //    재팽창 V_re=V_clear·π^(1/n) → 실효 흡입체적 V_eff
  //    누설 m_leak=Cd·A·√(2ρ̄ΔP)·(N/N_rated)^(-n_leak)
  //    swept ṁ=V_eff·ω·ρ_su,  실효 ṁ=ṁ_swept−m_leak,  η_v=ṁ/(V_max·ω·ρ_su)
  //    polytropic P_int=P_su·rv_in^n,  등엔트로피 w_is=h(P_dis,s_su)−h_su
  //    over/under-comp 보정 + 밸브손실 + 마찰/모터
  //    n_poly=cp/cv=R290Tab.gamma_ph,  h_dis_is=R290Tab.h_ps (등엔트로피 역산)
  //  물성 전부 R290Tab(p,h) — CoolProp 없이 OM 심볼릭.
  // ════════════════════════════════════════════════════════════════════
  model Comp_Chamber "압축기 On-design (chamber 1-cycle 평균물리) — acausal stream TwoPort"
    HPWD.RefPort port_a "흡입 (저압)";
    HPWD.RefPort port_b "토출 (고압)";
    Modelica.Blocks.Interfaces.RealInput N "회전수 [rpm] (신호 입력)";

    // ─ 기하 ─
    parameter Real V_disp_cm3 = 10.0 "행정체적 [cm³]";
    parameter Real clearance_ratio = 0.04 "clearance 체적/V_disp";
    parameter Real rv_in = 2.5 "built-in 체적비";
    parameter Real A_valve_in_mm2 = 8.0;
    parameter Real A_valve_out_mm2 = 6.0;
    // ─ 손실/누설 ─
    parameter Real zeta_valve = 1.5;
    parameter Real A_leak_mm2 = 0.02;
    parameter Real Cd_leak = 0.6;
    parameter Real n_leak_rpm = 0.5;
    parameter Real N_rated = 3000.0;
    parameter Real over_comp_factor = 0.3;
    // ─ 마찰/모터 ─
    parameter Real W_f_const = 20.0;
    parameter Real alpha_f_rpm = 8e-6;
    parameter Real eta_motor = 0.92;
    parameter Real eta_inv = 0.95;
    // ─ 파생 상수 ─
    final parameter Real V_clear = V_disp_cm3*clearance_ratio*1e-6;
    final parameter Real V_max = V_disp_cm3*(1.0 + clearance_ratio)*1e-6;
    final parameter Real A_in = A_valve_in_mm2*1e-6;
    final parameter Real A_out = A_valve_out_mm2*1e-6;
    final parameter Real A_leak = A_leak_mm2*1e-6;

    // ─ 변수 ─
    Real p_su, p_dis, h_su, s_su, rho_su, n_poly, omega, pi_ratio;
    Real V_re, V_eff, rpm_factor, dP_chamber, rho_avg, m_leak;
    Real m_dot_swept, m_dot, m_dot_ideal, eta_v;
    Real P_int, h_dis_is, w_is, v_internal, w_overunder;
    Real dP_in, W_valve_in, rho_dis_est, dP_out, W_valve_out;
    Real w_chamber, W_indicated, h_dis, eta_is, W_friction, W_shaft, W_elec, T_dis;
  equation
    p_su   = port_a.p;
    p_dis  = port_b.p;
    h_su   = inStream(port_a.h_outflow);
    rho_su = R290Tab.rho_ph(p_su, h_su);
    s_su   = R290Tab.s_ph(p_su, h_su);
    n_poly = R290Tab.gamma_ph(p_su, h_su);
    omega    = N/60.0;
    pi_ratio = p_dis/p_su;

    // 재팽창 → 실효 흡입체적
    V_re  = V_clear*(pi_ratio^(1.0/n_poly));
    V_eff = max(V_max - V_re, 0.01*V_max);
    // 누설
    rpm_factor = (N/N_rated)^(-n_leak_rpm);
    dP_chamber = p_dis - p_su;
    rho_avg    = rho_su*1.5;
    m_leak     = Cd_leak*A_leak*sqrt(max(0.0, 2.0*rho_avg*dP_chamber))*rpm_factor;
    // swept + 실효 + 체적효율
    m_dot_swept = V_eff*omega*rho_su;
    m_dot       = max(m_dot_swept - m_leak, 1e-6);
    m_dot_ideal = V_max*omega*rho_su;
    eta_v       = max(0.05, m_dot/m_dot_ideal);
    // polytropic 내부압력
    P_int = p_su*(rv_in^n_poly);
    // 등엔트로피 토출 (R290Tab 역산)
    h_dis_is = R290Tab.h_ps(p_dis, s_su);
    w_is     = h_dis_is - h_su;
    // over/under-compression 보정
    v_internal  = (1.0/rho_su)/rv_in;
    w_overunder = if P_int < p_dis then v_internal*(p_dis - P_int)
                  else over_comp_factor*v_internal*(P_int - p_dis);
    // 밸브 손실 (흡입 ρ_su, 토출 ρ_dis_est)
    dP_in       = zeta_valve*m_dot^2/(rho_su*A_in^2);
    W_valve_in  = m_dot*dP_in/rho_su;
    rho_dis_est = R290Tab.rho_ph(p_dis, h_dis_is);
    dP_out      = zeta_valve*m_dot^2/(rho_dis_est*A_out^2);
    W_valve_out = m_dot*dP_out/rho_dis_est;
    // indicated 일 + 실제 토출엔탈피
    w_chamber   = w_is + w_overunder;
    W_indicated = m_dot*w_chamber + W_valve_in + W_valve_out;
    h_dis       = h_su + w_chamber + (W_valve_in + W_valve_out)/m_dot;
    T_dis       = R290Tab.T_ph(p_dis, h_dis);
    // 등엔트로피 효율
    eta_is = max(0.05, min(0.99, w_is/w_chamber));
    // 마찰 + 모터
    W_friction = W_f_const + alpha_f_rpm*N^2;
    W_shaft    = W_indicated + W_friction;
    W_elec     = W_shaft/(eta_motor*eta_inv);

    // 포트 (흡입 유입, 토출 유출, 토출엔탈피 부여)
    port_a.m_flow = m_dot;
    port_b.m_flow = -m_dot;
    port_b.h_outflow = h_dis;
    port_a.h_outflow = inStream(port_b.h_outflow);
  end Comp_Chamber;

  // ── 단품 검증: Source(P_su,h_su) → Comp(N) → Sink(P_dis) ──
  model TestCompChamber "Comp_Chamber 단품 검증 (P_su=6,T_su=12℃,P_dis=18bar,N=3000)"
    HPWD.Source src(p = 6.0e5, h = 590863.41);   // 6 bar, 12℃ R290 (CoolProp h)
    HPWDon.Comp_Chamber comp(
      V_disp_cm3 = 10.0, clearance_ratio = 0.04, rv_in = 2.5,
      A_valve_in_mm2 = 8.0, A_valve_out_mm2 = 6.0, zeta_valve = 1.5,
      A_leak_mm2 = 0.02, Cd_leak = 0.6, n_leak_rpm = 0.5, N_rated = 3000.0,
      over_comp_factor = 0.3, W_f_const = 20.0, alpha_f_rpm = 8e-6,
      eta_motor = 0.92, eta_inv = 0.95);
    HPWD.Sink snk(p = 18.0e5, h = 650.0e3);
    Modelica.Blocks.Sources.Constant Nsig(k = 3000.0);
  equation
    connect(Nsig.y, comp.N);
    connect(src.port, comp.port_a);
    connect(comp.port_b, snk.port);
  end TestCompChamber;

end HPWDon;
