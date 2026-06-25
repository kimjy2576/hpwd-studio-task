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

  // ── FinTube 기하 계산 검증 (spec → 면적), Python FinTubeGeo 대조 ──
  model TestGeoFT "FinTube 파생 기하 (Dc/A_total/A_i/A_c/...) — spec에서 계산"
    // ─ spec (물리 치수) ─
    parameter Modelica.Units.SI.Length Do = 0.00952 "튜브 외경";
    parameter Modelica.Units.SI.Length Di = 0.00822 "튜브 내경";
    parameter Modelica.Units.SI.Length Pt = 0.0254 "transverse pitch";
    parameter Modelica.Units.SI.Length Pl = 0.022 "longitudinal pitch";
    parameter Integer Nr = 4 "row 수 (공기방향)";
    parameter Integer Nt = 12 "row당 튜브 수";
    parameter Real FPI = 14.0 "fins per inch";
    parameter Modelica.Units.SI.Length fin_thickness = 0.00012;
    parameter Modelica.Units.SI.Length W = 0.5 "폭 (튜브길이방향)";
    parameter Modelica.Units.SI.Length H = 0.3 "높이 (전면)";
    parameter Modelica.Units.SI.Length D = 0.08 "깊이 (공기방향)";
    parameter Integer N_seg = 10;
    parameter Boolean staggered = true;
    constant Real pi = Modelica.Constants.pi;
    // ─ 파생 기하 (FinTubeGeo.from_spec 이식) ─
    final parameter Real Dc = Do + 2.0*fin_thickness "collar 직경";
    final parameter Real fin_pitch = 0.0254/FPI;
    final parameter Integer N_fins = integer(floor(W/fin_pitch + 0.5));
    final parameter Real gap = fin_pitch - fin_thickness;
    final parameter Real A_fr = H*W "전면적";
    final parameter Real Xm = Pt/2.0;
    final parameter Real XL = if staggered then sqrt((Pt/2.0)^2 + Pl^2)/2.0 else Pl/2.0;
    final parameter Real A_plate = H*D;
    final parameter Real tube_hole = Nr*Nt*pi*Dc^2/4.0;
    final parameter Real A_one_fin = 2.0*(A_plate - tube_hole);
    final parameter Real A_fin = N_fins*A_one_fin "핀 면적";
    final parameter Real A_tube_ext = Nr*Nt*pi*Dc*N_fins*gap "핀사이 튜브외면";
    final parameter Real A_total = A_fin + A_tube_ext "공기측 전열면적";
    final parameter Real A_i = pi*Di*W*Nr*Nt "냉매측 내면적";
    final parameter Real sigma = max((Pt - Dc)*gap/(Pt*fin_pitch), 0.1) "자유유동비";
    final parameter Real A_c = sigma*A_fr "최소 자유유동면적";
    final parameter Real Dh = 4.0*A_c*D/A_total "공기측 수력직경";
    final parameter Real L_seg = W/N_seg "세그먼트당 튜브길이";
    final parameter Real A_i_seg = pi*Di*L_seg "세그먼트당 내면적";
    Real probe;  // 시뮬용 더미 (파라미터 평가 강제)
  equation
    probe = A_total + A_i_seg;
  end TestGeoFT;

  // ── 공기측 h_o (Wang j → Colburn) + 핀효율(Schmidt) 검증 ──
  model TestAirHo "공기측 HTC h_o + 핀효율 eta_o — Python _compute_h_o/fin_efficiency_schmidt 대조"
    // 기하 spec
    parameter Real Do = 0.00952, Di = 0.00822, Pt = 0.0254, Pl = 0.022;
    parameter Integer Nr = 4, Nt = 12;
    parameter Real FPI = 14.0, fin_thickness = 0.00012;
    parameter Real W = 0.5, H = 0.3, D = 0.08, k_fin = 200.0;
    parameter Boolean staggered = true;
    // 공기 조건
    parameter Real T_air_C = 35.0, RH = 0.60, V_air = 2.0, P_atm = 101325.0;
    constant Real pi = Modelica.Constants.pi;
    // 파생 기하 (FinTubeGeo)
    final parameter Real Dc = Do + 2.0*fin_thickness;
    final parameter Real fin_pitch = 0.0254/FPI;
    final parameter Integer N_fins = integer(floor(W/fin_pitch + 0.5));
    final parameter Real gap = fin_pitch - fin_thickness;
    final parameter Real A_fr = H*W;
    final parameter Real Xm = Pt/2.0;
    final parameter Real XL = if staggered then sqrt((Pt/2.0)^2 + Pl^2)/2.0 else Pl/2.0;
    final parameter Real A_one_fin = 2.0*(H*D - Nr*Nt*pi*Dc^2/4.0);
    final parameter Real A_fin = N_fins*A_one_fin;
    final parameter Real A_tube_ext = Nr*Nt*pi*Dc*N_fins*gap;
    final parameter Real A_total = A_fin + A_tube_ext;
    final parameter Real sigma = max((Pt - Dc)*gap/(Pt*fin_pitch), 0.1);
    final parameter Real A_c = sigma*A_fr;
    // 공기물성 + h_o 체인
    Real T_K, W_in, rho_air, mu, Pr, cp, m_air, G_air, Re_Dc, j, h_o;
    // 핀효율 (Schmidt)
    Real r_i, r_eq_ratio, phi, m_fin, mr_phi, eta_fin, eta_o;
  equation
    T_K     = T_air_C + 273.15;
    W_in    = HXCorr.W_humid(T_air_C, RH, P_atm);
    rho_air = P_atm/(287.055*T_K)*(1.0 + W_in)/(1.0 + 1.6078*W_in);
    mu      = HXCorr.mu_air(T_K);
    Pr      = HXCorr.Pr_air(T_K);
    cp      = HXCorr.cp_air_moist(0.0);
    m_air   = rho_air*V_air*A_fr;
    G_air   = m_air/A_c;
    Re_Dc   = G_air*Dc/mu;
    j       = HXCorr.j_wang2000_plain(Re_Dc, Nr, Dc, Pt, Pl, FPI, fin_thickness);
    h_o     = j*G_air*cp/Pr^(2.0/3.0);
    // Schmidt 핀효율
    r_i        = Dc/2.0;
    r_eq_ratio = max(1.27*(Xm/r_i)*sqrt(XL/Xm - 0.3), 1.0);
    phi        = (r_eq_ratio - 1.0)*(1.0 + 0.35*log(max(r_eq_ratio, 1.001)));
    m_fin      = sqrt(2.0*h_o/(k_fin*fin_thickness));
    mr_phi     = m_fin*r_i*phi;
    eta_fin    = tanh(mr_phi)/mr_phi;
    eta_o      = 1.0 - (A_fin/A_total)*(1.0 - eta_fin);
  end TestAirHo;

  // ── 냉매측 h_i: 2상 Chen + 단상 Gnielinski 검증 ──
  model TestHi "냉매 HTC h_i — Chen(2상)/Gnielinski(단상), Python h_with_transition 대조"
    parameter Real P = 5.8e5 "압력 [Pa]";
    parameter Real x = 0.5 "quality";
    parameter Real G = 200.0 "질량유속 [kg/m2.s]";
    parameter Real Di = 8.22e-3 "내경 [m]";
    parameter Real q_flux = 5000.0 "열유속 [W/m2]";
    parameter Real Pcrit = 4.2512e6 "R290 임계압 [Pa]";
    parameter Real M_mol = 44.0956 "R290 몰질량 [g/mol]";
    // 포화물성 (Chen 입력) — R290Tab
    Real mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, P_r;
    Real h_chen "2상 Chen HTC";
    Real h_gni "단상 Gnielinski HTC (Re=50000,Pr=0.85,k=0.018)";
  equation
    mu_l  = R290Tab.mul(P);
    k_l   = R290Tab.kl(P);
    cp_l  = R290Tab.cpl(P);
    rho_l = R290Tab.rhol(P);
    rho_v = R290Tab.rhov(P);
    mu_v  = R290Tab.muv(P);
    Pr_l  = cp_l*mu_l/k_l;
    P_r   = P/Pcrit;
    h_chen = HXCorr.h_evap_chen1966(x, G, Di, q_flux, mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_r, M_mol);
    h_gni  = HXCorr.gnielinski(50000.0, 0.85, 0.018, Di);
  end TestHi;

  // ── 냉매 N-세그먼트 all-2상 dry march 검증 ──
  model TestMarchDry "냉매 FV march (all-2상, dry, 고정P) — Python 레퍼런스 march 대조"
    parameter Integer N = 10;
    parameter Real P = 5.8e5, x_in = 0.2, G_ref = 200.0;
    parameter Real T_air_C = 20.0, V_air = 2.0, P_atm = 101325.0;
    // 기하 spec
    parameter Real Do=0.00952, Di=0.00822, Pt=0.0254, Pl=0.022;
    parameter Integer Nr=4, Nt=12;
    parameter Real FPI=14.0, fin_thickness=0.00012, W=0.5, H=0.3, D=0.08, k_fin=200.0;
    parameter Boolean staggered=true;
    parameter Real Pcrit=4.2512e6, M_mol=44.0956;
    constant Real pi=Modelica.Constants.pi;
    // 파생 기하 (FinTubeGeo)
    final parameter Real Dc=Do+2.0*fin_thickness;
    final parameter Real fin_pitch=0.0254/FPI;
    final parameter Integer N_fins=integer(floor(W/fin_pitch+0.5));
    final parameter Real gap=fin_pitch-fin_thickness;
    final parameter Real A_fr=H*W;
    final parameter Real Xm=Pt/2.0;
    final parameter Real XL=if staggered then sqrt((Pt/2.0)^2+Pl^2)/2.0 else Pl/2.0;
    final parameter Real A_fin=N_fins*2.0*(H*D-Nr*Nt*pi*Dc^2/4.0);
    final parameter Real A_tube_ext=Nr*Nt*pi*Dc*N_fins*gap;
    final parameter Real A_total=A_fin+A_tube_ext;
    final parameter Real sigma=max((Pt-Dc)*gap/(Pt*fin_pitch),0.1);
    final parameter Real A_c=sigma*A_fr;
    final parameter Real L_seg=W/N;
    final parameter Real A_i_seg=pi*Di*L_seg;
    final parameter Real A_o_seg=A_total/(Nr*Nt*N);
    final parameter Real A_cs=pi*Di^2/4.0;
    final parameter Real m_dot=G_ref*A_cs;
    // 공기측 h_o, eta_o (dry)
    Real T_K, rho_air, mu_a, Pr_a, cp_a, m_air, G_air, Re_Dc, j, h_o;
    Real r_i, r_eq_ratio, phi_f, m_fin, mr_phi, eta_fin, eta_o;
    // 냉매 포화물성 @P
    Real T_sat, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, P_r;
    // march
    Real x[N+1], h_i[N], UA[N], Q[N], q_flux[N];
    Real Q_total, x_out;
  equation
    // 공기측 (dry: W=0)
    T_K=T_air_C+273.15;
    rho_air=P_atm/(287.055*T_K);
    mu_a=HXCorr.mu_air(T_K); Pr_a=HXCorr.Pr_air(T_K); cp_a=HXCorr.cp_air_moist(0.0);
    m_air=rho_air*V_air*A_fr; G_air=m_air/A_c; Re_Dc=G_air*Dc/mu_a;
    j=HXCorr.j_wang2000_plain(Re_Dc,Nr,Dc,Pt,Pl,FPI,fin_thickness);
    h_o=j*G_air*cp_a/Pr_a^(2.0/3.0);
    r_i=Dc/2.0; r_eq_ratio=max(1.27*(Xm/r_i)*sqrt(XL/Xm-0.3),1.0);
    phi_f=(r_eq_ratio-1.0)*(1.0+0.35*log(max(r_eq_ratio,1.001)));
    m_fin=sqrt(2.0*h_o/(k_fin*fin_thickness)); mr_phi=m_fin*r_i*phi_f;
    eta_fin=tanh(mr_phi)/mr_phi; eta_o=1.0-(A_fin/A_total)*(1.0-eta_fin);
    // 냉매 포화물성
    T_sat=R290Tab.Tsat(P); h_fg=R290Tab.hv(P)-R290Tab.hl(P);
    mu_l=R290Tab.mul(P); k_l=R290Tab.kl(P); cp_l=R290Tab.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=R290Tab.rhol(P); rho_v=R290Tab.rhov(P); mu_v=R290Tab.muv(P); P_r=P/Pcrit;
    // FV march (각 세그먼트: q_flux↔h_i↔Q 비선형, OM이 풂)
    x[1]=x_in;
    for i in 1:N loop
      h_i[i]=HXCorr.h_evap_chen1966(x[i],G_ref,Di,q_flux[i],mu_l,k_l,Pr_l,rho_l,rho_v,mu_v,P_r,M_mol);
      UA[i]=1.0/(1.0/(eta_o*h_o*A_o_seg)+1.0/(h_i[i]*A_i_seg));
      Q[i]=UA[i]*(T_K-T_sat);
      q_flux[i]=Q[i]/A_i_seg;
      x[i+1]=x[i]+Q[i]/(m_dot*h_fg);
    end for;
    Q_total=sum(Q);
    x_out=x[N+1];
  end TestMarchDry;

end HPWDon;
