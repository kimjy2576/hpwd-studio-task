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

end HPWDon;
