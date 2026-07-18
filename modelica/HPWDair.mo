package HPWDair "HPWD air-side L1 (lumped, 비압축 + dry-air basis)"

  // =============================================================
  // MoistAir: 이상 습공기 정형식 (psychrometrics).
  //   규약: 비압축, ρ는 p_ref에서 평가, 유량은 m_dot_da (dry-air basis),
  //         stream 변수 = h_tilde (J/kg_da) + W (kg/kg_da).
  //   참고기준: dry-air 0°C, 액체수 0°C.
  // =============================================================
  package MoistAir "Ideal humid-air psychrometrics for air-side L1"

    // ── 물성 상수 ────────────────────────────────────────────
    constant Real cp_da  = 1005    "dry air specific heat (J/kg·K)";
    constant Real cp_v   = 1860    "water vapor specific heat (J/kg·K)";
    constant Real cp_w   = 4186    "liquid water specific heat (J/kg·K)";
    constant Real R_da   = 287.05  "dry air gas constant (J/kg·K)";
    constant Real eps    = 0.622   "M_v / M_da";
    constant Real T0     = 273.15  "reference temperature (K, 0°C)";
    constant Real hfg0   = 2.501e6 "h_fg at T0 (J/kg)";
    constant Real p_ref  = 101325  "reference pressure (Pa) for 비압축";

    // ── 함수들 (비미분 용도: 초기조건·후처리·Drum 등에서 호출) ───────
    function p_vs "Saturation vapor pressure (Magnus, 0~60°C 정확)"
      input Modelica.Units.SI.Temperature T;
      output Modelica.Units.SI.Pressure p;
    protected
      Real Tc = T - T0;
    algorithm
      p := 610.78 * exp(17.27 * Tc / (Tc + 237.3));
    end p_vs;

    function W_sat "Saturation humidity ratio at p_ref (kg/kg_da)"
      input Modelica.Units.SI.Temperature T;
      output Real W;
    protected
      Real pvs = p_vs(T);
    algorithm
      W := eps * pvs / (p_ref - pvs);
    end W_sat;

    function rho_da_fn "Dry-air partial density at p_ref (kg_da/m³)"
      input Modelica.Units.SI.Temperature T;
      input Real W "humidity ratio kg/kg_da";
      output Modelica.Units.SI.Density rho;
    algorithm
      rho := p_ref * eps / ((eps + W) * R_da * T);
    end rho_da_fn;

    function h_g "Vapor enthalpy at T (J/kg, ref: liquid water 0°C)"
      input Modelica.Units.SI.Temperature T;
      output Modelica.Units.SI.SpecificEnthalpy h;
    algorithm
      h := hfg0 + cp_v * (T - T0);
    end h_g;

    function h_fg "Latent heat of vaporization at T (J/kg)"
      input Modelica.Units.SI.Temperature T;
      output Modelica.Units.SI.SpecificEnthalpy h;
    algorithm
      h := hfg0 + (cp_v - cp_w) * (T - T0);
    end h_fg;

    function h_da_fn "Per-dry-air enthalpy h_tilde(T, W) (J/kg_da)"
      input Modelica.Units.SI.Temperature T;
      input Real W;
      output Modelica.Units.SI.SpecificEnthalpy h;
    algorithm
      h := cp_da * (T - T0) + W * (hfg0 + cp_v * (T - T0));
    end h_da_fn;

    function T_from_h "Inverse: T(h_tilde, W) — 선형이라 닫힌 형태"
      input Modelica.Units.SI.SpecificEnthalpy h;
      input Real W;
      output Modelica.Units.SI.Temperature T;
    algorithm
      T := T0 + (h - W * hfg0) / (cp_da + W * cp_v);
    end T_from_h;

  end MoistAir;


  // =============================================================
  // AirPort: 습공기 포트 (RefPort의 air 짝).
  //   규약: p = potential, m_flow_da = dry-air 질량유량(flow),
  //         h_tilde_outflow + W_outflow = stream variables.
  // =============================================================
  connector AirPort "Moist air port (dry-air basis, 비압축)"
    Modelica.Units.SI.Pressure p;
    flow Modelica.Units.SI.MassFlowRate m_flow_da
      "dry-air mass flow (kg_da/s)";
    stream Modelica.Units.SI.SpecificEnthalpy h_tilde_outflow
      "per-dry-air enthalpy at outflow (J/kg_da)";
    stream Real W_outflow(unit="kg/kg")
      "humidity ratio at outflow (kg_v/kg_da)";
  end AirPort;


  // =============================================================
  // AirVolume: air-side control volume (CRCR 패턴의 C 요소).
  //   상태: T, W. 압력 p는 potential(대수, R 컴포넌트가 결정).
  //   질량보존: der(m_da) = sum m_flow_da_k.  (m_da = ρ_da·V → T,W 변화로 변동)
  //   수분보존: m_da·der(W) = sum m_flow_da_k·(W_k^in - W).
  //   에너지보존: m_da·der(h_tilde) = sum m_flow_da_k·(h_tilde_k^in - h_tilde).
  //   ※ 분리한 형태 (chain rule)로 풀어쓰는 게 Modelica 미분 처리에 안전 →
  //     h_tilde·rho_da 식을 인라인으로 작성.
  // =============================================================
  model AirVolume "Air control volume (T, W states; CRCR의 C 요소)"
    AirPort port_a;
    AirPort port_b;
    parameter Modelica.Units.SI.Volume V = 0.05
      "default: 50 L (덕트 1구간 / 드럼 1/N 등)";
    parameter Modelica.Units.SI.Temperature T_start = 320
      "init temperature (K)";
    parameter Real W_start = 0.01 "init humidity ratio (kg/kg_da)";
    parameter Boolean fixedState = false
      "true면 (T,W)를 start값에 고정 초기화";
    parameter Boolean steadyInit = true
      "fixedState=false 일 때 steady (der=0) 초기화";

    Modelica.Units.SI.Pressure p(start = MoistAir.p_ref);
    Modelica.Units.SI.Temperature T(
      start = T_start, fixed = false,
      stateSelect = StateSelect.prefer);
    Real W(
      start = W_start, fixed = false, unit = "kg/kg",
      stateSelect = StateSelect.prefer);

    Modelica.Units.SI.Density rho_da;
    Modelica.Units.SI.Mass m_da;
    Modelica.Units.SI.SpecificEnthalpy h_tilde;

  equation
    // ── 매질 식 (미분 처리 안전하게 인라인) ──
    rho_da = MoistAir.p_ref * MoistAir.eps
             / ((MoistAir.eps + W) * MoistAir.R_da * T);
    m_da = rho_da * V;
    h_tilde = MoistAir.cp_da * (T - MoistAir.T0)
            + W * (MoistAir.hfg0 + MoistAir.cp_v * (T - MoistAir.T0));

    // ── 포트 식 (potential 균압 + outflow stream) ──
    port_a.p = p;
    port_b.p = p;
    port_a.h_tilde_outflow = h_tilde;
    port_b.h_tilde_outflow = h_tilde;
    port_a.W_outflow = W;
    port_b.W_outflow = W;

    // ── 보존식 ──
    der(m_da) = port_a.m_flow_da + port_b.m_flow_da;
    m_da * der(W) =
        port_a.m_flow_da * (actualStream(port_a.W_outflow) - W)
      + port_b.m_flow_da * (actualStream(port_b.W_outflow) - W);
    m_da * der(h_tilde) =
        port_a.m_flow_da * (actualStream(port_a.h_tilde_outflow) - h_tilde)
      + port_b.m_flow_da * (actualStream(port_b.h_tilde_outflow) - h_tilde);

  initial equation
    if fixedState then
      T = T_start;
      W = W_start;
    elseif steadyInit then
      der(T) = 0;
      der(W) = 0;
    end if;
  end AirVolume;


  // =============================================================
  // AirVolumeC: 압축성 공기 volume (T, W, p 상태) — 닫힌 루프 압력 앵커.
  //   AirVolume과 동일하되 ρ를 *실제 p*로 평가 → mass balance가 der(p)를
  //   품어 p가 상태가 됨. p 초기값(보통 대기압)이 루프 절대압 레벨을 고정.
  //   과도 시 net mass imbalance를 p 변동으로 흡수 (volume이 "숨쉼").
  //   비압축 AirVolume 3개 + 이거 1개로 링 구성 (압력 변동 ~0.1%, ρ 영향 무시).
  // =============================================================
  model AirVolumeC
    "Compressible air volume (T, W, p states) — 닫힌 루프 압력 앵커"
    AirPort port_a;
    AirPort port_b;
    parameter Modelica.Units.SI.Volume V = 0.05 "volume (m³)";
    parameter Modelica.Units.SI.Temperature T_start = 320 "init temperature (K)";
    parameter Real W_start = 0.01 "init humidity ratio (kg/kg_da)";
    parameter Modelica.Units.SI.Pressure p_start = MoistAir.p_ref
      "init pressure (절대압 레벨 앵커, 보통 대기압)";
    parameter Boolean fixedState = false "true면 (T,W) start값 고정 초기화";
    parameter Boolean steadyInit = true "fixedState=false면 steady (der=0) 초기화";

    Modelica.Units.SI.Pressure p(
      start = p_start, fixed = true,
      stateSelect = StateSelect.prefer);
    Modelica.Units.SI.Temperature T(
      start = T_start, fixed = false,
      stateSelect = StateSelect.prefer);
    Real W(
      start = W_start, fixed = false, unit = "kg/kg",
      stateSelect = StateSelect.prefer);

    Modelica.Units.SI.Density rho_da;
    Modelica.Units.SI.Mass m_da;
    Modelica.Units.SI.SpecificEnthalpy h_tilde;

  equation
    // ── 매질 식: ρ를 *실제 p*로 평가 (압축성 → p가 상태) ──
    rho_da = p * MoistAir.eps
             / ((MoistAir.eps + W) * MoistAir.R_da * T);
    m_da = rho_da * V;
    h_tilde = MoistAir.cp_da * (T - MoistAir.T0)
            + W * (MoistAir.hfg0 + MoistAir.cp_v * (T - MoistAir.T0));

    // ── 포트 식 ──
    port_a.p = p;
    port_b.p = p;
    port_a.h_tilde_outflow = h_tilde;
    port_b.h_tilde_outflow = h_tilde;
    port_a.W_outflow = W;
    port_b.W_outflow = W;

    // ── 보존식 (mass가 der(p) 포함 → p 상태) ──
    der(m_da) = port_a.m_flow_da + port_b.m_flow_da;
    m_da * der(W) =
        port_a.m_flow_da * (actualStream(port_a.W_outflow) - W)
      + port_b.m_flow_da * (actualStream(port_b.W_outflow) - W);
    m_da * der(h_tilde) =
        port_a.m_flow_da * (actualStream(port_a.h_tilde_outflow) - h_tilde)
      + port_b.m_flow_da * (actualStream(port_b.h_tilde_outflow) - h_tilde);

  initial equation
    if fixedState then
      T = T_start;
      W = W_start;
    elseif steadyInit then
      der(T) = 0;
      der(W) = 0;
    end if;
    // p는 fixed=true로 p_start 고정 (절대압 레벨 앵커)
  end AirVolumeC;


  // =============================================================
  // BoundaryAir_pTW: 테스트용 경계조건 (압력·온도·습도 지정).
  //   AirVolume·R 컴포넌트를 양쪽에서 끼워 단독 검증할 때 사용.
  // =============================================================
  model BoundaryAir_pTW "Air boundary: prescribed (p, T, W)"
    AirPort port;
    parameter Modelica.Units.SI.Pressure p = MoistAir.p_ref;
    parameter Modelica.Units.SI.Temperature T = 298.15
      "boundary 온도 (default 25°C)";
    parameter Real W = 0.01 "boundary humidity ratio (kg/kg_da)";
  equation
    port.p = p;
    port.h_tilde_outflow =
        MoistAir.cp_da * (T - MoistAir.T0)
      + W * (MoistAir.hfg0 + MoistAir.cp_v * (T - MoistAir.T0));
    port.W_outflow = W;
  end BoundaryAir_pTW;


  // =============================================================
  // Fan_L1: 원심 송풍기 L1 (Euler + Stodola slip, 전곡 시로코).
  //   R 요소 (압력상승 + dry-air 보존). 기하만으로 fan curve, fitting 없음.
  //   비압축 규약: ρ는 p_ref·입구상태서 평가, V̇ = ṁ_da(1+W)/ρ.
  //   L1 가정: 단열 (fan 자체발열 무시), 입구 선회 0.
  // =============================================================
  model Fan_L1 "Centrifugal fan L1 (Euler + Stodola slip, forward-curved)"
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Diameter D2 = 0.15
      "impeller outer diameter (m)";
    parameter Modelica.Units.SI.Length b2 = 0.04
      "outlet blade width (m)";
    parameter Integer Z = 40 "blade count";
    parameter Real beta2 = 150 "blade exit angle (deg, >90 = 전곡)";
    parameter Real eta_h = 0.78 "hydraulic efficiency (시로코 ≈0.78)";
    parameter Real eta_mech = 0.95 "mechanical efficiency";
    parameter Real N = 3000 "rotational speed (rpm)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05)
      "dry-air mass flow (a→b +)";
    Modelica.Units.SI.Velocity U2 "blade tip speed";
    Modelica.Units.SI.Velocity cm2 "outlet meridional velocity";
    Modelica.Units.SI.Velocity ctheta2 "outlet swirl velocity";
    Real sigma "Stodola slip factor";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Density rho "moist-air density (p_ref)";
    Modelica.Units.SI.Pressure dp_t "theoretical total pressure rise";
    Modelica.Units.SI.Pressure dp "static pressure rise";
    Modelica.Units.SI.Power W_sh "shaft power";

    Real W_op(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_op "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_op "inlet temperature (upstream)";

  protected
    parameter Real beta2_rad = beta2 * Modelica.Constants.pi / 180.0;

  equation
    // ── dry-air 질량보존 (저장 없음) ──
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    // ── 입구(상류) 상태 → 밀도 (정방향 a→b 가정) ──
    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);

    // ── 속도삼각형 + Euler + slip ──
    U2 = Modelica.Constants.pi * D2 * N / 60;
    V_dot = m_flow_da * (1 + W_op) / rho;
    cm2 = V_dot / (Modelica.Constants.pi * D2 * b2);
    sigma = 1 - Modelica.Constants.pi * sin(beta2_rad) / Z;
    ctheta2 = sigma * U2 - cm2 / tan(beta2_rad);
    dp_t = rho * U2 * ctheta2;
    dp = eta_h * dp_t;
    W_sh = rho * V_dot * U2 * ctheta2 / eta_mech;

    // ── 압력상승 (fan이 dp를 더함) ──
    port_b.p = port_a.p + dp;

    // ── stream: 단열 pass-through (L1: 자체발열 무시) ──
    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow);
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Fan_L1;

  model Fan_L2
    "Centrifugal fan L2 (SEMI: 손실분해 — Euler − Incidence − Friction). 상수효율 대신 유량의존 손실."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Diameter D2 = 0.15 "impeller outer diameter (m)";
    parameter Modelica.Units.SI.Length b2 = 0.04 "outlet blade width (m)";
    parameter Modelica.Units.SI.Diameter D1 = 0.075 "impeller eye(inlet) diameter (m)";
    parameter Modelica.Units.SI.Length b1 = 0.045 "inlet blade width (m)";
    parameter Integer Z = 40 "blade count";
    parameter Real beta2 = 150 "blade exit angle (deg, >90 = 전곡)";
    parameter Real beta1 = 35 "blade inlet angle (deg)";
    parameter Real f_inc = 0.6 "incidence loss coefficient";
    parameter Real f_fric = 0.8 "friction loss coefficient (C_f·L/D_h lumped)";
    parameter Real eta_mech = 0.95 "mechanical efficiency";
    parameter Real N = 3000 "rotational speed (rpm)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow (a→b +)";
    Modelica.Units.SI.Velocity U2 "blade tip speed";
    Modelica.Units.SI.Velocity U1 "inlet blade speed";
    Modelica.Units.SI.Velocity cm2 "outlet meridional velocity";
    Modelica.Units.SI.Velocity cm1 "inlet meridional velocity";
    Modelica.Units.SI.Velocity ctheta2 "outlet swirl velocity";
    Modelica.Units.SI.Velocity w2 "outlet relative velocity";
    Real sigma "Stodola slip factor";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Density rho "moist-air density (p_ref)";
    Modelica.Units.SI.Pressure dp_euler "Euler ideal total pressure rise";
    Modelica.Units.SI.Pressure dp_inc "incidence (shock) loss";
    Modelica.Units.SI.Pressure dp_fric "friction loss";
    Modelica.Units.SI.Pressure dp "net static pressure rise";
    Real eta_h "hydraulic efficiency (계산값 dp/dp_euler, 유량의존)";
    Modelica.Units.SI.Power W_sh "shaft power";

    Real W_op(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_op "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_op "inlet temperature (upstream)";

  protected
    parameter Real beta2_rad = beta2 * Modelica.Constants.pi / 180.0;
    parameter Real beta1_rad = beta1 * Modelica.Constants.pi / 180.0;

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);

    // ── 속도삼각형 (입구 station 1 + 출구 station 2) ──
    U2 = Modelica.Constants.pi * D2 * N / 60;
    U1 = Modelica.Constants.pi * D1 * N / 60;
    V_dot = m_flow_da * (1 + W_op) / rho;
    cm2 = V_dot / (Modelica.Constants.pi * D2 * b2);
    cm1 = V_dot / (Modelica.Constants.pi * D1 * b1);
    sigma = 1 - Modelica.Constants.pi * sin(beta2_rad) / Z;
    ctheta2 = sigma * U2 - cm2 / tan(beta2_rad);
    w2 = sqrt(cm2^2 + (U2 - ctheta2)^2);

    // ── 손실 분해: Euler − Incidence − Friction (상수효율 대체) ──
    dp_euler = rho * U2 * ctheta2;
    dp_inc = 0.5 * rho * f_inc * (U1 - cm1 / tan(beta1_rad))^2;   // 설계유량서 0
    dp_fric = 0.5 * rho * f_fric * w2^2;                          // 통로 마찰 ∝ w2²
    dp = dp_euler - dp_inc - dp_fric;
    eta_h = dp / dp_euler;
    W_sh = rho * V_dot * U2 * ctheta2 / eta_mech;

    port_b.p = port_a.p + dp;

    // ── stream: 손실열 자체발열 (forward a→b, Δh=손실/rho) ──
    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow) + (dp_inc + dp_fric) / rho;
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Fan_L2;

  model Fan_L3
    "Centrifugal fan L3 (ON: Meanline + 손실 9종 + scroll). fan_on.py(fan-sim 포팅) acausal화.
     문헌 6종 초과 — 시로코 전곡 특화(tongue·uncaptured·diffuser) 포함.
     ground truth: backend/components/fan_on.py (동일 물리, jet-wake 1회, recirc softplus)."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Length D1 = 0.120 "impeller eye diameter (m)";
    parameter Modelica.Units.SI.Length D2 = 0.175 "impeller outer diameter (m)";
    parameter Modelica.Units.SI.Length b1 = 0.060 "inlet blade width (m)";
    parameter Modelica.Units.SI.Length b2 = 0.050 "outlet blade width (m)";
    parameter Real beta1 = 30 "blade inlet angle (deg)";
    parameter Real beta2 = 145 "blade exit angle (deg, >90=전곡)";
    parameter Integer Z = 36 "blade count";
    parameter Real N = 1400 "rotational speed (rpm)";
    parameter Modelica.Units.SI.Length tBlade = 0.001 "blade thickness (m)";
    parameter Modelica.Units.SI.Length cutoffGap = 0.008 "tongue cutoff gap (m)";
    parameter Modelica.Units.SI.Length Rtongue = 0.005 "tongue radius (m)";
    parameter Real wrapAngle = 360 "scroll wrap angle (deg)";
    parameter Real scrollExpRate = 0.12 "scroll expansion rate";
    parameter Real diffAngle = 7 "diffuser half angle (deg)";
    parameter Modelica.Units.SI.Length diffLength = 0.040 "diffuser length (m)";

    parameter Real k_inc = 1.0;
    parameter Real k_fric = 1.0;
    parameter Real k_rec = 0.0085;
    parameter Real DR_crit = 0.5;
    parameter Real k_disk = 1.0;
    parameter Real k_jw = 1.0;
    parameter Real k_sc_mix = 0.20;
    parameter Real k_tongue_a = 0.82;
    parameter Real k_tongue_b = 0.7;
    parameter Real c_wake = 0.12;
    parameter Real r_scroll_w = 1.1;
    parameter Real c_scroll_v = 0.7;
    parameter Real c_tongue_loss = 0.3;
    parameter Real eps_leak_max = 0.25;
    parameter Real w_rec = 0.02 "recirc softplus 전이폭";
    parameter Real eta_mech = 0.95;

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow (a→b +)";
    Modelica.Units.SI.VolumeFlowRate V_dot;
    Modelica.Units.SI.Density rho;
    Real mu "dynamic viscosity (Pa·s)";
    Modelica.Units.SI.Velocity U1, U2, Cr1, Cr2, Ct2, C2, W1, W2, Wa;
    Real sigma;
    Modelica.Units.SI.Pressure Pt_e;
    Modelica.Units.SI.Pressure dP_inc, dP_fric, dP_rec, dP_disk, dP_jw;
    Modelica.Units.SI.Pressure dP_scroll, dP_tongue, dP_uncap;
    Modelica.Units.SI.Pressure Pt_imp, Pt_fan, Ps;
    Real DR, eps_leak, Q_delivered;
    Modelica.Units.SI.Power W_shaft;
    Real eta;

    Real W_op(unit="kg/kg");
    Modelica.Units.SI.SpecificEnthalpy h_op;
    Modelica.Units.SI.Temperature T_op;

    Real Re, f_darcy, Re_disk, Cm, Pdf;
    Real Pdyn_imp, Pdyn_cap, A_sc, D_h_sc, C_sc, Re_sc, f_sc, dP_sc_fric, dP_sc_mix;
    Real inc_A, sp_rec, A_exit;

  protected
    parameter Real b1R = beta1 * Modelica.Constants.pi / 180.0;
    parameter Real b2R = beta2 * Modelica.Constants.pi / 180.0;
    parameter Real omega_rot = 2 * Modelica.Constants.pi * N / 60;
    parameter Real r1 = D1 / 2;
    parameter Real r2 = D2 / 2;
    parameter Real pitch2 = Modelica.Constants.pi * D2 / Z;
    parameter Real Dh = 2 * pitch2 * b2 / (pitch2 + b2);
    parameter Real k_inc_base = 1 - (tBlade / (Modelica.Constants.pi * D1 / Z))^2;
    parameter Real wrapFrac = min(1.0, wrapAngle / 360);
    parameter Real gapRatio = cutoffGap / (2 * r2);
    parameter Real denom_tongue = 1 + Rtongue / cutoffGap;
    parameter Real eps_jw = c_wake + 0.5 * tBlade / pitch2;
    parameter Real bScrollM = b2 * r_scroll_w;
    parameter Real L_scroll = 2 * Modelica.Constants.pi * r2 * wrapFrac;
    parameter Real rExit = r2 + r2 * scrollExpRate * wrapFrac * 2 * Modelica.Constants.pi;
    parameter Real A_sc_exit = bScrollM * (rExit - r2);
    parameter Real Lb = blade_length(r1, r2, b1R, b2R);
    constant Real T_ref = 273.15;
    constant Real S_suth = 110.4;
    constant Real mu_ref = 1.716e-5;

  public
    function blade_length "Blade 경로장 적분 (형상만)"
      input Real r1_; input Real r2_; input Real b1R_; input Real b2R_;
      output Real Lb_;
    protected
      Real px, py, th, t, r, rP, rM, tM, bM, x, y;
      constant Integer n = 20;
    algorithm
      Lb_ := 0; px := r1_; py := 0; th := 0;
      for i in 1:n loop
        t := i / n;
        r := r1_ + t * (r2_ - r1_);
        rP := r1_ + (i - 1) / n * (r2_ - r1_);
        rM := (r + rP) / 2;
        tM := (t + (i - 1) / n) / 2;
        bM := b1R_ + tM * (b2R_ - b1R_);
        if abs(tan(bM)) > 0.001 then
          th := th + (-1 / (rM * tan(bM))) * (r - rP);
        end if;
        x := r * cos(th); y := r * sin(th);
        Lb_ := Lb_ + sqrt((x - px)^2 + (y - py)^2);
        px := x; py := y;
      end for;
    end blade_length;

    function softplus "(x)+ smooth. w→0이면 max(x,0)"
      input Real x; input Real w; output Real y;
    algorithm
      y := if x / w > 30 then x
           elseif x / w < -30 then 0.0
           else w * log(1 + exp(x / w));
    end softplus;

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);
    mu = mu_ref * (T_op / T_ref)^1.5 * (T_ref + S_suth) / (T_op + S_suth);

    V_dot = m_flow_da * (1 + W_op) / rho;

    U1 = omega_rot * r1;
    U2 = omega_rot * r2;
    Cr1 = V_dot / (Modelica.Constants.pi * D1 * b1);
    Cr2 = V_dot / (Modelica.Constants.pi * D2 * b2);
    sigma = 1 - Modelica.Constants.pi * sin(b2R) / Z;
    Ct2 = sigma * U2 - Cr2 / tan(b2R);
    C2 = sqrt(Cr2^2 + Ct2^2);
    W1 = sqrt(Cr1^2 + U1^2);
    W2 = sqrt(Cr2^2 + (Ct2 - U2)^2);
    Wa = (W1 + W2) / 2;
    Pt_e = rho * U2 * Ct2;

    inc_A = atan2(Cr1, U1) - b1R;
    dP_inc = k_inc_base * k_inc * 0.5 * rho * (W1 * sin(inc_A))^2;
    Re = rho * Wa * Dh / mu;
    f_darcy = if Re > 2300 then 1 / (-1.8 * log10(6.9 / Re + (5e-5 / Dh / 3.7)^1.11))^2
              else 64 / max(Re, 1);
    dP_fric = k_fric * f_darcy * (Lb / Dh) * 0.5 * rho * Wa^2;
    DR = 1 - W2 / W1 + abs(Ct2) / (2 * Z * W1 / Modelica.Constants.pi);
    sp_rec = softplus(DR - DR_crit, w_rec);
    dP_rec = k_rec * sp_rec^2 * rho * U2^2;
    Re_disk = rho * omega_rot * r2^2 / mu;
    Cm = 0.0622 / Re_disk^0.2;
    Pdf = k_disk * 2 * 0.5 * Cm * rho * omega_rot^3 * r2^5;
    dP_disk = min(Pdf / max(V_dot, 1e-6), Pt_e * 0.5);
    dP_jw = k_jw * 0.5 * rho * C2^2 * eps_jw^2;

    Pt_imp = max(0.0, Pt_e - dP_inc - dP_fric - dP_rec - dP_disk - dP_jw);
    Pdyn_imp = 0.5 * rho * C2^2;

    Pdyn_cap = Pdyn_imp * wrapFrac;
    A_sc = max(A_sc_exit, V_dot / max(1.0, C2 * 0.5));
    D_h_sc = 2 * A_sc / (sqrt(A_sc / bScrollM) + bScrollM);
    C_sc = V_dot / max(1e-4, A_sc) * c_scroll_v;
    Re_sc = rho * abs(C_sc) * max(0.005, D_h_sc) / mu;
    f_sc = if Re_sc > 2300 then 0.316 / Re_sc^0.25 else 64 / max(Re_sc, 1);
    dP_sc_fric = f_sc * (L_scroll / max(0.005, D_h_sc)) * 0.5 * rho * C_sc^2;
    dP_sc_mix = k_sc_mix * Pdyn_cap;
    dP_scroll = dP_sc_fric + dP_sc_mix;

    eps_leak = min(eps_leak_max, k_tongue_a * gapRatio^k_tongue_b / denom_tongue);
    Q_delivered = V_dot * (1 - eps_leak);
    dP_tongue = eps_leak * Pt_imp * c_tongue_loss;

    dP_uncap = 0.5 * rho * (C2 * sqrt(1 - wrapFrac))^2 * (1 - wrapFrac);

    Pt_fan = max(0.0, Pt_imp - dP_scroll - dP_tongue - dP_uncap);
    A_exit = max(0.001, A_sc * max(1.0,
             1 + 2 * diffLength * tan(abs(diffAngle) * Modelica.Constants.pi / 180) / max(0.01, sqrt(A_sc))));
    Ps = Pt_fan - 0.5 * rho * (Q_delivered / A_exit)^2;

    W_shaft = Pt_e * V_dot + Pdf;
    eta = if W_shaft > 0 then max(0.0, Ps * Q_delivered) / W_shaft else 0.0;

    port_b.p = port_a.p + Ps;

    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow)
                             + W_shaft * (1 - eta) / max(1e-6, rho * V_dot);
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Fan_L3;



  // =============================================================
  // Filter_L1: lint filter L1 (Darcy-Forchheimer, clean, 순수 R).
  //   면 기하(면적·주름·경사)→media velocity u, ΔP = K·u|u| (관성지배 단순화).
  //   clean 상태: 열·물질전달 무시 → 단열 pass-through. 압력 *강하*.
  //   ※ K는 면적무관 미디어 저항. lint loading K(m_lint)는 L2/SEMI.
  // =============================================================
  model Filter_L1 "Lint filter L1 (Darcy-Forchheimer, clean, pure R)"
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Area A_face = 0.05 "filter face area (m²)";
    parameter Real r_pleat = 1.0 "pleat area ratio (≥1, 1=flat)";
    parameter Real theta_face = 0 "face slope angle (deg)";
    parameter Real K = 20 "media resistance (Pa·s²/m²)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05)
      "dry-air mass flow (a→b +)";
    Modelica.Units.SI.Area A_media "effective media area";
    Modelica.Units.SI.Velocity u "media velocity (부호=유향)";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Density rho "moist-air density (p_ref)";
    Modelica.Units.SI.Pressure dp "pressure drop";

    Real W_op(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_op "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_op "inlet temperature (upstream)";

  protected
    parameter Real theta_rad = theta_face * Modelica.Constants.pi / 180.0;

  equation
    // ── dry-air 질량보존 (저장 없음) ──
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    // ── 입구(상류) 상태 → 밀도 ──
    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);

    // ── 면 기하 → media velocity → ΔP (관성지배, C¹) ──
    A_media = A_face * r_pleat / cos(theta_rad);
    V_dot = m_flow_da * (1 + W_op) / rho;
    u = V_dot / A_media;
    dp = K * u * abs(u);

    // ── 압력강하 (filter가 dp를 뺌) ──
    port_b.p = port_a.p - dp;

    // ── stream: 단열 pass-through (clean, 열·물질전달 무시) ──
    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow);
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Filter_L1;

  model Filter_L2
    "Lint filter L2 (SEMI: Darcy-Forchheimer 2항, a·b fit). filter_on.py L2 포팅.
     ΔP = a·μu + b·ρu·|u| — 점성(Darcy) + 관성(Forchheimer). L1의 K=b·ρ 특수형."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Area A_face = 0.05 "filter face area (m²)";
    parameter Real r_pleat = 1.0 "pleat area ratio (≥1, 1=flat)";
    parameter Real theta_face = 0 "face slope angle (deg)";
    parameter Real a_visc = 5.0e4 "점성(Darcy) 계수 (1/m²)";
    parameter Real b_inert = 17.0 "관성(Forchheimer) 계수 (1/m)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow (a→b +)";
    Modelica.Units.SI.Area A_media "effective media area";
    Modelica.Units.SI.Velocity u "media velocity (부호=유향)";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Density rho "moist-air density (p_ref)";
    Real mu "dynamic viscosity (Pa·s, Sutherland)";
    Modelica.Units.SI.Pressure dp "pressure drop";
    Modelica.Units.SI.Pressure dp_visc, dp_inert;

    Real W_op(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_op "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_op "inlet temperature (upstream)";

  protected
    parameter Real theta_rad = theta_face * Modelica.Constants.pi / 180.0;
    constant Real T_ref = 273.15;
    constant Real S_suth = 110.4;
    constant Real mu_ref = 1.716e-5;

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);
    mu = mu_ref * (T_op / T_ref)^1.5 * (T_ref + S_suth) / (T_op + S_suth);

    // 면 기하 → media velocity
    A_media = A_face * r_pleat / cos(theta_rad);
    V_dot = m_flow_da * (1 + W_op) / rho;
    u = V_dot / A_media;

    // ── DF 2항: 점성(Darcy) + 관성(Forchheimer), 역류 부호보존 ──
    dp_visc = a_visc * mu * u;
    dp_inert = b_inert * rho * u * abs(u);
    dp = dp_visc + dp_inert;

    port_b.p = port_a.p - dp;

    // stream: 단열 pass-through (clean, 열·물질전달 무시)
    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow);
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Filter_L2;

  model Filter_L3
    "Lint filter L3 (ON: 메쉬 기하 → Ergun, 다층). filter_on.py L3 포팅.
     ε,d_f를 MPI·wire경에서 도출 → Ergun a·b (fit 아닌 기하) → 두께적분 → 다층 합."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Area A_face = 0.05 "filter face area (m²)";
    parameter Real r_pleat = 1.0 "pleat area ratio (≥1, 1=flat)";
    parameter Real theta_face = 0 "face slope angle (deg)";
    parameter Real cf_ergun = 1.0 "재질 거칠기 보정";
    // 다층 메쉬 (기본 단일 린트메쉬). N_layer개 병렬 두께.
    parameter Integer N_layer = 1 "메쉬 층수 (pre+main)";
    parameter Real MPI[N_layer] = {15.0} "인치당 메쉬수 (1/inch)";
    parameter Modelica.Units.SI.Length d_w[N_layer] = {0.0004} "wire경 (m)";
    parameter Modelica.Units.SI.Length L_layer[N_layer] = {0.0006} "층 두께 (m)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow (a→b +)";
    Modelica.Units.SI.Area A_media "effective media area";
    Modelica.Units.SI.Velocity u "media velocity";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Density rho "moist-air density (p_ref)";
    Real mu "dynamic viscosity (Pa·s)";
    Modelica.Units.SI.Pressure dp "total pressure drop";
    Modelica.Units.SI.Pressure dp_layer[N_layer] "층별 ΔP";

    Real W_op(unit="kg/kg");
    Modelica.Units.SI.SpecificEnthalpy h_op;
    Modelica.Units.SI.Temperature T_op;

  protected
    parameter Real theta_rad = theta_face * Modelica.Constants.pi / 180.0;
    constant Real T_ref = 273.15;
    constant Real S_suth = 110.4;
    constant Real mu_ref = 1.716e-5;
    constant Real inch = 0.0254;
    // Ergun 계수 (형상만 — 사전계산)
    parameter Real MPI_per_m[N_layer] = {MPI[i] / inch for i in 1:N_layer};
    parameter Real eps_l[N_layer] = {
      max(min((1 - d_w[i] * MPI[i] / inch)^2, 0.999), 0.05) for i in 1:N_layer}
      "개구율 ε=(1-d_w·MPI)²";
    parameter Real a_erg[N_layer] = {
      150.0 * (1 - eps_l[i])^2 / (eps_l[i]^3 * d_w[i]^2) for i in 1:N_layer}
      "Ergun 점성계수";
    parameter Real b_erg[N_layer] = {
      1.75 * (1 - eps_l[i]) / (eps_l[i]^3 * d_w[i]) for i in 1:N_layer}
      "Ergun 관성계수";

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_op = inStream(port_a.W_outflow);
    h_op = inStream(port_a.h_tilde_outflow);
    T_op = MoistAir.T_from_h(h_op, W_op);
    rho  = MoistAir.rho_da_fn(T_op, W_op) * (1 + W_op);
    mu = mu_ref * (T_op / T_ref)^1.5 * (T_ref + S_suth) / (T_op + S_suth);

    A_media = A_face * r_pleat / cos(theta_rad);
    V_dot = m_flow_da * (1 + W_op) / rho;
    u = V_dot / A_media;

    // ── 층별 Ergun ΔP (두께적분 = 균질이라 ·L), 부호보존 ──
    for i in 1:N_layer loop
      dp_layer[i] = cf_ergun * (a_erg[i] * mu * u + b_erg[i] * rho * u * abs(u)) * L_layer[i];
    end for;
    dp = sum(dp_layer);

    port_b.p = port_a.p - dp;

    port_a.h_tilde_outflow = inStream(port_b.h_tilde_outflow);
    port_b.h_tilde_outflow = inStream(port_a.h_tilde_outflow);
    port_a.W_outflow = inStream(port_b.W_outflow);
    port_b.W_outflow = inStream(port_a.W_outflow);
  end Filter_L3;


  // =============================================================
  // Drum_L1: 드럼 L1 (Lewis analogy + constant-rate). 첫 동적 컴포넌트.
  //   상태 2개: 의류 수분 m_w, 의류 온도 T_cl.
  //   공기측 quasi-steady·well-mixed (T_air=T_out, W_air=W_out).
  //   air 네트워크에선 R: dry-air 보존 + ΔP_drum (CRCR 균일규칙).
  //   증발수는 W로 흡수 → dry-air(m_flow_da)는 보존.
  //   cloth 열용량은 wet 반영: C = m_cl_dry·c_p_cl + m_w·c_p_w.
  //   L1 한계: constant-rate only (표면 free water, falling-rate 무시).
  // =============================================================
  model Drum_L1
    "Drum L1 (Lewis + constant-rate; quasi-steady air + cloth dynamics)"
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Mass m_cl_dry = 3.0
      "dry cloth mass (load, kg)";
    parameter Real c_p_cl = 1500 "dry cloth specific heat (J/kg·K)";
    parameter Modelica.Units.SI.Area A_eff = 10
      "effective cloth area, heat/mass transfer (m²)";
    parameter Real h_a = 50 "air-cloth convective HTC (W/m²·K)";
    parameter Modelica.Units.SI.Area A_drum = 0.15
      "drum air-flow cross-section (m²)";
    parameter Real K_drum = 30 "cloth-bed resistance (Pa·s²/m²)";
    parameter Real X0 = 0.6 "initial moisture ratio (kg水/kg dry)";
    parameter Modelica.Units.SI.Temperature Tcl0 = 298.15
      "initial cloth temp (K)";
    parameter Real UA_amb = 0.0
      "cabinet 외기 열손실 UA (W/K); 0=단열(air 링 기본)";
    parameter Modelica.Units.SI.Temperature T_amb = 298.15 "외기온 (K)";
    parameter Modelica.Units.SI.Mass eps_dry = 1e-3
      "잔수 게이트 폭 (kg). →0이면 게이트 없음(원 거동), m_w<0 방지용";

    // ── states ──
    Modelica.Units.SI.Mass m_w(
      start = X0 * m_cl_dry, fixed = true,
      stateSelect = StateSelect.prefer) "cloth moisture (state)";
    Modelica.Units.SI.Temperature T_cl(
      start = Tcl0, fixed = true,
      stateSelect = StateSelect.prefer) "cloth temp (state)";
    Real X "moisture ratio (dry basis)";
    Real g_dry "잔수 게이트 (0~1, 물리 타당성 가드)";

    // ── air-side (quasi-steady, well-mixed bulk = outlet) ──
    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05)
      "dry-air mass flow (a→b +)";
    Real W_in(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_in "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_in "inlet air temp";
    Real W_out(unit="kg/kg", start = 0.02) "outlet/bulk humidity ratio";
    Modelica.Units.SI.SpecificEnthalpy h_out "outlet/bulk h_tilde";
    Modelica.Units.SI.Temperature T_out(start = 320)
      "outlet/bulk (well-mixed) air temp";
    Modelica.Units.SI.MassFlowRate m_evap(start = 5e-4) "evaporation rate";
    Real W_s(unit="kg/kg") "saturation humidity at cloth surface";
    Real h_m "mass transfer coeff (Lewis, kg/m²·s)";
    Modelica.Units.SI.Power Q_amb "외기 열손실 (air→ambient)";

    // ── ΔP ──
    Modelica.Units.SI.Density rho_da "dry-air density (p_ref, inlet)";
    Modelica.Units.SI.Velocity u "drum-pass air velocity";
    Modelica.Units.SI.Pressure dp_drum "air-side pressure drop";

  equation
    // ── dry-air 질량보존 (증발수는 W로; dry air 보존) ──
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    // ── 입구(상류) 상태 ──
    W_in = inStream(port_a.W_outflow);
    h_in = inStream(port_a.h_tilde_outflow);
    T_in = MoistAir.T_from_h(h_in, W_in);

    // ── Lewis analogy + 표면포화 증발 (W_air = W_out) ──
    //   g_dry: 잔수 게이트 (물 없으면 증발 정지). m_w<0 방지 = 물리 타당성 가드.
    //   ⚠️ fidelity 업그레이드 아님 — L1은 여전히 항률만(감률 없음), 건조점서
    //      멈출 뿐. Drum_L3 자유수 게이트와 동일 Michaelis-Menten 패턴(연속).
    //   m_evap을 게이트 → 공기CV·der(m_w) 양쪽 반영 = 질량보존 유지.
    W_s = MoistAir.W_sat(T_cl);
    h_m = h_a / MoistAir.cp_da;
    g_dry = m_w / (m_w + eps_dry);
    m_evap = h_m * A_eff * (W_s - W_out) * g_dry;

    // ── 공기 CV (quasi-steady, well-mixed: T_air=T_out) ──
    m_flow_da * (W_out - W_in) = m_evap;
    Q_amb = UA_amb * (T_out - T_amb);
    m_flow_da * (h_out - h_in)
        = -h_a * A_eff * (T_out - T_cl) + m_evap * MoistAir.h_g(T_cl) - Q_amb;
    T_out = MoistAir.T_from_h(h_out, W_out);

    // ── cloth 동특성 (states) ──
    X = m_w / m_cl_dry;
    der(m_w) = -m_evap;
    (m_cl_dry * c_p_cl + m_w * MoistAir.cp_w) * der(T_cl)
        = h_a * A_eff * (T_out - T_cl) - m_evap * MoistAir.h_fg(T_cl);

    // ── 공기측 압력강하 (의류 더미 저항, 단일 K) ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    u = m_flow_da / (rho_da * A_drum);
    dp_drum = K_drum * u * abs(u);
    port_b.p = port_a.p - dp_drum;

    // ── stream: well-mixed (양 포트 outflow = bulk) ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;
  end Drum_L1;

  model Drum_L2
    "Drum L2 (SEMI: Falling-rate + Sorption). Drum_L1 + 감률건조(임계함수율 X_cr) + 흡착평형 X_eq(RH)."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Mass m_cl_dry = 3.0 "dry cloth mass (load, kg)";
    parameter Real c_p_cl = 1500 "dry cloth specific heat (J/kg·K)";
    parameter Modelica.Units.SI.Area A_eff = 10 "effective cloth area (m²)";
    parameter Real h_a = 50 "air-cloth convective HTC (W/m²·K)";
    parameter Modelica.Units.SI.Area A_drum = 0.15 "drum air-flow cross-section (m²)";
    parameter Real K_drum = 30 "cloth-bed resistance (Pa·s²/m²)";
    parameter Real X0 = 0.6 "initial moisture ratio (kg水/kg dry)";
    parameter Modelica.Units.SI.Temperature Tcl0 = 298.15 "initial cloth temp (K)";
    parameter Real UA_amb = 0.0 "cabinet 외기 열손실 UA (W/K)";
    parameter Modelica.Units.SI.Temperature T_amb = 298.15 "외기온 (K)";
    // ── L2 추가 파라미터 (감률 + 흡착) ──
    parameter Real X_cr = 0.2 "critical moisture (항률→감률 전이, dry basis)";
    parameter Real a_sorp = 0.25 "sorption isotherm 계수 (X_eq = a·RH^n)";
    parameter Real n_sorp = 2.0 "sorption isotherm 지수 (cotton ~2)";

    Modelica.Units.SI.Mass m_w(
      start = X0 * m_cl_dry, fixed = true,
      stateSelect = StateSelect.prefer) "cloth moisture (state)";
    Modelica.Units.SI.Temperature T_cl(
      start = Tcl0, fixed = true,
      stateSelect = StateSelect.prefer) "cloth temp (state)";
    Real X "moisture ratio (dry basis)";
    Real X_eq "equilibrium moisture (sorption, 평형함수율)";
    Real RH_air "bulk air relative humidity";
    Real f_dry "drying-rate factor (1=항률, 0=평형도달)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow (a→b +)";
    Real W_in(unit="kg/kg") "inlet humidity ratio (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_in "inlet h_tilde (upstream)";
    Modelica.Units.SI.Temperature T_in "inlet air temp";
    Real W_out(unit="kg/kg", start = 0.02) "outlet/bulk humidity ratio";
    Modelica.Units.SI.SpecificEnthalpy h_out "outlet/bulk h_tilde";
    Modelica.Units.SI.Temperature T_out(start = 320) "outlet/bulk air temp";
    Modelica.Units.SI.MassFlowRate m_evap(start = 5e-4) "evaporation rate";
    Real W_s(unit="kg/kg") "saturation humidity at cloth surface";
    Real h_m "mass transfer coeff (Lewis)";
    Modelica.Units.SI.Power Q_amb "외기 열손실";

    Modelica.Units.SI.Density rho_da "dry-air density (inlet)";
    Modelica.Units.SI.Velocity u "drum-pass air velocity";
    Modelica.Units.SI.Pressure dp_drum "air-side pressure drop";

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_in = inStream(port_a.W_outflow);
    h_in = inStream(port_a.h_tilde_outflow);
    T_in = MoistAir.T_from_h(h_in, W_in);

    // ── 흡착 평형함수율 (cotton isotherm) + 감률 인자 ──
    RH_air = W_out / MoistAir.W_sat(T_out);
    X_eq = min(a_sorp * RH_air^n_sorp, 0.9 * X_cr);   // 평형함수율 (감률밴드 유효 보장)
    f_dry = max(0.0, min(1.0, (X - X_eq) / (X_cr - X_eq)));

    // ── Lewis analogy + 감률 보정 증발 (X<X_cr면 표면 부분습윤) ──
    W_s = MoistAir.W_sat(T_cl);
    h_m = h_a / MoistAir.cp_da;
    m_evap = f_dry * h_m * A_eff * (W_s - W_out);

    // ── 공기 CV (quasi-steady, well-mixed) ──
    m_flow_da * (W_out - W_in) = m_evap;
    Q_amb = UA_amb * (T_out - T_amb);
    m_flow_da * (h_out - h_in)
        = -h_a * A_eff * (T_out - T_cl) + m_evap * MoistAir.h_g(T_cl) - Q_amb;
    T_out = MoistAir.T_from_h(h_out, W_out);

    // ── cloth 동특성 ──
    X = m_w / m_cl_dry;
    der(m_w) = -m_evap;
    (m_cl_dry * c_p_cl + m_w * MoistAir.cp_w) * der(T_cl)
        = h_a * A_eff * (T_out - T_cl) - m_evap * MoistAir.h_fg(T_cl);

    // ── 공기측 압력강하 ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    u = m_flow_da / (rho_da * A_drum);
    dp_drum = K_drum * u * abs(u);
    port_b.p = port_a.p - dp_drum;

    // ── stream: well-mixed ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;
  end Drum_L2;

  model Drum_L3
    "Drum L3 (ON: 3-Zone 다층직물) — drum_on.py acausal 동적 포팅. [최소 골격 검증판]
     N-zone 함수율 + 직물온도 der 상태. 물리는 최소 (3스텝서 전체 이식)."
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Integer N = 3 "직물 두께방향 zone 수 (L3 기본 3)";
    parameter Modelica.Units.SI.Mass m_cl_dry = 3.0 "dry cloth mass (kg)";
    parameter Real c_p_cl = 1300 "dry cloth specific heat (J/kg·K)";
    parameter Modelica.Units.SI.Area A_eff = 10 "effective cloth area (m²)";
    parameter Real h_a = 50 "air-cloth HTC (W/m²·K) [3a서 rasti로 대체, 잔존 미사용]";
    parameter Modelica.Units.SI.Area A_drum = 0.15 "drum cross-section (m²)";
    parameter Real K_drum = 30 "cloth-bed resistance (Pa·s²/m²)";
    parameter Real X0 = 0.6 "initial moisture ratio (kg水/kg dry)";
    parameter Modelica.Units.SI.Temperature Tcl0 = 298.15 "initial cloth temp (K)";
    parameter Real absorption_ratio = 1.8 "최대 흡수량 (kg水/kg건, cotton)";
    parameter Real zf[N] = {0.25, 0.35, 0.40} "zone 두께 분율";
    // ── 3a: rasti hA 상관식 파라미터 (drum_on) ──
    parameter Modelica.Units.SI.Length drum_radius = 0.27 "드럼 반경 (m)";
    parameter Modelica.Units.SI.Length drum_length = 0.45 "드럼 길이 (m)";
    parameter Modelica.Units.SI.Length delta_fabric = 1.0e-3 "직물 두께 (m)";
    parameter Real RPM = 45.0 "드럼 회전수 (rpm)";
    parameter Real Fr_opt = 0.3 "최적 Froude";
    parameter Real Fr_sigma = 0.25 "Froude Gaussian 폭";
    parameter Real fill_optimal = 0.6 "최적 충전율";
    parameter Real f_conv_sliding = 0.7 "대류인자 (sliding)";
    parameter Real f_conv_peak = 1.7 "대류인자 (peak/cascading)";
    parameter Real f_conv_centrifuge = 0.3 "대류인자 (centrifuge)";
    parameter Real hA_multiplier = 1.0 "hA 보정계수";
    parameter Real rho_bulk = 300.0 "드럼내 벌크밀도 (kg/m³)";
    // ── 3b: Fick 확산 + Darcy-Leverett 모세관 파라미터 (drum_on) ──
    parameter Real D_ref = 5e-10 "확산계수 기준 (m²/s, cotton)";
    parameter Real E_a = 35000.0 "확산 활성화에너지 (J/mol)";
    parameter Real K_abs = 1e-12 "절대투과율 (m²)";
    parameter Real diffusion_S_exp = 0.5 "D∝S^n 지수 (토양값 차용)";
    parameter Real brooks_corey = 3.0 "모세관 K_r=S^n (토양값 차용)";
    parameter Real L_char_mult = 3.0 "특성 확산거리 배율";
    parameter Real R_GAS = 8.314 "기체상수 (J/mol·K)";
    // ── 3b: 텀블링 zone 교환 파라미터 (Fr 구간별) ──
    parameter Real k_exch_slide = 0.05 "텀블링 교환율 (sliding)";
    parameter Real k_exch_casc = 0.30 "텀블링 교환율 (cascading)";
    parameter Real k_exch_high = 0.02 "텀블링 교환율 (centrifuge)";
    // ── 3c: 4경로 저항 도면기하 (drum_on) ──
    parameter Modelica.Units.SI.Area A_rear_hole = 0.012 "후면 홀 면적 (m²)";
    parameter Modelica.Units.SI.Area A_side_hole = 0.006 "측면 홀 면적 (m²)";
    parameter Modelica.Units.SI.Length gap_width = 0.008 "간극 폭 (m)";
    parameter Modelica.Units.SI.Length L_side_hole = 0.15 "측면 홀 경로장 (m)";
    parameter Modelica.Units.SI.Length seal_depth = 0.03 "실 깊이 (m)";
    parameter Real C_d = 0.62 "오리피스 방출계수";
    parameter Real bypass_multiplier = 1.0 "바이패스 배율";
    parameter Real eps_free = 0.01 "자유수 smooth 게이트 폭 (약점C, →0이면 원본 if)";
    parameter Real eta_partial = min(0.15 / 0.45, 0.5) "부분경로 hA 배율 (L_side/drum_length)";
    parameter Real S_critical = 0.15 "임계 표면포화도 (감률전환)";
    parameter Real f_wet_exp = 0.5 "표면습윤 지수";

    // ── 상태변수: N-zone 함수율 + 직물온도 + 자유수 ──
    Modelica.Units.SI.Mass M_water_z[N](
      each fixed = false,
      each stateSelect = StateSelect.prefer) "zone별 수분질량 (state)";
    Modelica.Units.SI.Temperature T_fabric(
      start = Tcl0, fixed = true,
      stateSelect = StateSelect.prefer) "직물 온도 (state)";
    Modelica.Units.SI.Mass M_free(
      start = 0.0, fixed = false) "자유수 (state)";

    // zone별 최대 수분 (parameter)
    Real M_water_max_z[N] "zone별 최대 수분";
    Real S[N] "zone별 포화도";
    Real X "전체 함수율 (dry basis)";

    // 공기측
    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05) "dry-air mass flow";
    Real W_in(unit="kg/kg");
    Modelica.Units.SI.SpecificEnthalpy h_in;
    Modelica.Units.SI.Temperature T_in;
    Real W_out(unit="kg/kg", start = 0.02);
    Modelica.Units.SI.SpecificEnthalpy h_out;
    Modelica.Units.SI.Temperature T_out(start = 320);
    Modelica.Units.SI.MassFlowRate m_evap(start = 5e-4);
    Real W_s(unit="kg/kg") "표면 포화습도";
    Real h_m "물질전달계수 (Lewis)";
    // ── 3d: 자유수 smooth 게이트 ──
    Real g_free "자유수 존재도 게이트 (0~1)";
    Real f_wet_eff "표면 유효 습윤도 (자유수 blend)";
    // ── 4스텝: 공기CV 4경로 재구성 (drum_on 1:1) ──
    Real m_dot_partial "부분경로 유량 (kg/s)";
    Real eps_e "cloth 경로 ε";
    Real eps_p "partial 경로 ε";
    Real w1(unit="kg/kg") "cloth 경로 출구습도";
    Real w2(unit="kg/kg") "partial 경로 출구습도";
    Real T1 "cloth 경로 출구온도";
    Real T2 "partial 경로 출구온도";
    Real e1 "cloth 경로 증발 (kg/s)";
    Real e2 "partial 경로 증발 (kg/s)";
    Real e_air_demand "공기측 증발 수요";
    Real m_evap_supply "직물측 증발 공급";
    Real cap_ratio "공급/수요 제한비";
    Real ws_surf(unit="kg/kg") "표면 포화습도";
    // ── 3a: rasti hA 상관식 변수 ──
    Real Fr "Froude number";
    Real fill "충전율";
    Real hA "총 열전달계수 (W/K)";
    Real h_conv "대류 열전달계수 (W/m²K)";
    Real fc "접촉 인자";
    Real fv "대류 인자";
    // ── 3c: 4경로 저항 변수 ──
    Real R_eff "cloth 관통 경로 저항";
    Real R_partial "부분(측면홀) 경로 저항";
    Real R_rear_bypass "후면 바이패스 저항";
    Real R_gap_v "간극 누설 저항";
    Real f_eff "cloth 관통 유량분율";
    Real f_partial "부분 경로 유량분율";
    Real f_rbypass "후면 바이패스 유량분율";
    Real f_gap "간극 누설 유량분율";
    Real m_dot_eff "cloth 유효유량 (kg/s)";
    Real rear_covered "후면홀 덮임 비율";
    Real theta_fill "충전 각도";
    Real h_top "직물 상단 높이";

    // zone 간 확산 flux (최소: 단순 확산)
    Real J_zone[N-1] "zone 간 수분 flux (kg/s)";
    Real J_tumble[N-1] "zone 간 텀블링 flux (kg/s)";
    Real k_exch "텀블링 교환율 (Fr 구간별)";

    Modelica.Units.SI.Density rho_da;
    Modelica.Units.SI.Velocity u;
    Modelica.Units.SI.Pressure dp_drum;

  protected
    parameter Real D_simple = 1e-6 "최소골격 단순확산계수 (3b서 Fick으로 대체)";
    // 3a: rasti hA 공기 물성 상수 (drum_on)
    constant Real K_AIR = 0.028 "공기 열전도도 W/(m·K)";
    constant Real MU_AIR = 2.0e-5 "공기 점도 Pa·s";
    constant Real PR_AIR = 0.71 "Prandtl";
    constant Real RHO_AIR = 1.05 "공기 밀도 kg/m³";
    parameter Real d_char = delta_fabric * 2.0 "특성 길이";
    parameter Real A_drum_cross = Modelica.Constants.pi * drum_radius^2 "드럼 단면적";
    parameter Real omega_rot = 2 * Modelica.Constants.pi * RPM / 60 "각속도";
    parameter Real A_gap = 2 * Modelica.Constants.pi * drum_radius * gap_width "간극 면적";
    parameter Real rho_fiber = rho_fabric "섬유 밀도 (R_laundry용)";
    parameter Real rho_fabric = 1520.0 "섬유 밀도 (kg/m³, cotton)";
    parameter Real A_fabric = m_cl_dry / (rho_fabric * delta_fabric) * 2
      "직물 유효면적 (drum_on 공식, m²)";
    // 3b: L_char N정규화 (drum_on: delta·mult·2/(N-1))
    parameter Real L_char = delta_fabric * L_char_mult * (if N > 1 then 2.0 / (N - 1) else 1.0)
      "특성 확산거리 (N셀 정규화)";
    // 3b: w_cap 배열 — 각 쌍 diffusion↔capillary 가중 (i/(N-2))
    parameter Real w_cap[N-1] = {
      if N > 2 then max(0.0, min((i - 1) / (N - 2.0), 1.0))
      else (if i == 1 then 0.0 else 1.0)
      for i in 1:N-1} "쌍별 모세관 가중 (0=확산,1=모세관)";

  initial equation
    // 초기 함수율 분배 (drum_on init_state): X0>absorption면 초과분 자유수로
    //   M_water_max_total = Σ(m_dry_z·absorption). X0·m_dry 초과분 = M_free.
    //   각 zone은 S_init(=min(1, X0/absorption))까지 채움.
    for i in 1:N loop
      M_water_z[i] = m_cl_dry * zf[i] * absorption_ratio
                     * min(1.0, X0 / absorption_ratio);
    end for;
    M_free = max(X0 * m_cl_dry - m_cl_dry * absorption_ratio, 0.0);

  equation
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    W_in = inStream(port_a.W_outflow);
    h_in = inStream(port_a.h_tilde_outflow);
    T_in = MoistAir.T_from_h(h_in, W_in);

    // zone 최대수분·포화도
    for i in 1:N loop
      M_water_max_z[i] = m_cl_dry * zf[i] * absorption_ratio;
      S[i] = M_water_z[i] / M_water_max_z[i];
    end for;
    X = sum(M_water_z) / m_cl_dry;

    // ── 3a: Froude + fill + rasti hA 상관식 ──
    Fr = omega_rot^2 * drum_radius / 9.81;
    fill = min((m_cl_dry / rho_bulk + sum(M_water_z) * 0.3 / 1000.0)
               / (Modelica.Constants.pi * drum_radius^2 * drum_length), 1.0);

    // ── 3c: 4경로 저항 + 유량분배 ──
    theta_fill = segment_fill_angle(fill);
    // 직물 상단 높이 (Fr 리프트)
    h_top = (if Fr < 0.01 then -drum_radius * cos(theta_fill)
             elseif Fr < 0.1 then -drum_radius * cos(theta_fill) + drum_radius * (0.1 * Fr / 0.1)
             elseif Fr < 0.5 then min(-drum_radius * cos(theta_fill) + drum_radius * (0.1 + 0.6 * (Fr - 0.1) / 0.4), drum_radius * 0.9)
             elseif Fr < 1.0 then min(-drum_radius * cos(theta_fill) + drum_radius * (0.7 + 0.25 * (Fr - 0.5) / 0.5), drum_radius * 0.95)
             else drum_radius * 0.95);
    // 후면홀 덮임 = circle_area_below_h(h_top)
    rear_covered = (acos(-max(min(h_top / drum_radius, 0.999), -0.999))
                    - (-max(min(h_top / drum_radius, 0.999), -0.999))
                    * sqrt(1 - max(min(h_top / drum_radius, 0.999), -0.999)^2)) / Modelica.Constants.pi;
    // R_eff = R_orifice(A_rear·cover) + R_laundry
    R_eff = 1.0 / (2.0 * RHO_AIR * C_d^2 * max(A_rear_hole * rear_covered, 1e-8)^2)
            + laundry_R(fill, A_drum_cross, rho_bulk, rho_fiber, d_char, drum_radius, RHO_AIR);
    // R_partial = R_orifice(A_side·side_cover) + R_laundry·side_ratio
    R_partial = 1.0 / (2.0 * RHO_AIR * C_d^2 * max(A_side_hole * side_cover_fn(Fr, theta_fill), 1e-8)^2)
            + laundry_R(fill, A_drum_cross, rho_bulk, rho_fiber, d_char, drum_radius, RHO_AIR)
              * (L_side_hole / max(drum_length, 0.01));
    // R_rear_bypass = R_orifice(A_rear·(1-cover))
    R_rear_bypass = if A_rear_hole * (1 - rear_covered) > 1e-8
                    then 1.0 / (2.0 * RHO_AIR * C_d^2 * (A_rear_hole * (1 - rear_covered))^2)
                    else 1e8;
    // R_gap = fL/(2·rho·A_gap²)
    R_gap_v = (0.05 * seal_depth / (2 * gap_width) + 1.5) / (2.0 * RHO_AIR * A_gap^2);
    // 유량분배: G_i=1/√R_i, 분율=G_i/ΣG
    f_eff = (1/sqrt(max(R_eff,1.0)))
            / ((1/sqrt(max(R_eff,1.0))) + (1/sqrt(max(R_partial,1.0)))
             + (1/sqrt(max(R_rear_bypass,1.0)))*bypass_multiplier + (1/sqrt(max(R_gap_v,1.0)))*bypass_multiplier);
    f_partial = (1/sqrt(max(R_partial,1.0)))
            / ((1/sqrt(max(R_eff,1.0))) + (1/sqrt(max(R_partial,1.0)))
             + (1/sqrt(max(R_rear_bypass,1.0)))*bypass_multiplier + (1/sqrt(max(R_gap_v,1.0)))*bypass_multiplier);
    f_rbypass = (1/sqrt(max(R_rear_bypass,1.0)))*bypass_multiplier
            / ((1/sqrt(max(R_eff,1.0))) + (1/sqrt(max(R_partial,1.0)))
             + (1/sqrt(max(R_rear_bypass,1.0)))*bypass_multiplier + (1/sqrt(max(R_gap_v,1.0)))*bypass_multiplier);
    f_gap = (1/sqrt(max(R_gap_v,1.0)))*bypass_multiplier
            / ((1/sqrt(max(R_eff,1.0))) + (1/sqrt(max(R_partial,1.0)))
             + (1/sqrt(max(R_rear_bypass,1.0)))*bypass_multiplier + (1/sqrt(max(R_gap_v,1.0)))*bypass_multiplier);
    m_dot_eff = m_flow_da * f_eff;
    // 대류 h: Nu=2+1.1Re^0.6Pr^(1/3), Re는 유효유량(4경로 cloth 관통) 기준
    h_conv = (2.0 + 1.1 * (RHO_AIR * (m_dot_eff / max(RHO_AIR * A_drum_cross
             * max(0.85 - 0.4 * fill, 0.15), 1e-8)) * d_char / MU_AIR)^0.6
             * PR_AIR^(1.0/3.0)) * K_AIR / d_char;
    // f_contact: Fr Gaussian × fill 포물선
    fc = exp(-((Fr - Fr_opt)^2) / (2 * Fr_sigma^2))
         * max(1.0 - 0.5 * ((fill - fill_optimal) / fill_optimal)^2, 0.2);
    // f_conv: Fr 구간별 (smooth 근사 위해 noEvent)
    fv = if Fr < 0.1 then f_conv_sliding
         elseif Fr < 0.5 then f_conv_sliding + (f_conv_peak - f_conv_sliding) * (Fr - 0.1) / 0.4
         elseif Fr < 1.0 then f_conv_peak + (f_conv_centrifuge - f_conv_peak) * (Fr - 0.5) / 0.5
         else f_conv_centrifuge;
    hA = h_conv * A_fabric * fc * fv * hA_multiplier;

    // ── 3d: 자유수 게이트 + 표면 유효습윤도 ──
    //   f_wet_3zone = min((S[N]/S_crit)^0.5, 1): S[N]>S_crit면 완전습윤 (drum_on surface_evap_fwet).
    g_free = M_free / (M_free + eps_free);
    f_wet_eff = g_free * 1.0 + (1 - g_free) * min((max(S[N], 0.0) / S_critical)^f_wet_exp, 1.0);

    // ── 4스텝: 공기CV 4경로 재구성 (drum_on ntu_path 1:1) ──
    //   2경로 증발(cloth e1 + partial e2), bypass 2경로는 우회. 응축은 정상건조서
    //   미발생(w_out<w_sat)이라 생략(과포화 아님). f_wet_eff 게이트로 습윤도 반영.
    m_dot_partial = m_flow_da * f_partial;
    ws_surf = MoistAir.W_sat(T_fabric);
    // cloth 경로 (m_dot_eff, hA)
    eps_e = 1 - exp(-hA / max(m_dot_eff * MoistAir.cp_da, 1e-6));
    w1 = W_in + eps_e * (ws_surf - W_in) * f_wet_eff;
    T1 = T_in - eps_e * (T_in - T_fabric);
    e1 = m_dot_eff * max(w1 - W_in, 0.0);
    // partial 경로 (m_dot_partial, hA·eta_partial)
    eps_p = 1 - exp(-hA * eta_partial / max(m_dot_partial * MoistAir.cp_da, 1e-6));
    w2 = W_in + eps_p * (ws_surf - W_in) * f_wet_eff;
    T2 = T_in - eps_p * (T_in - T_fabric);
    e2 = m_dot_partial * max(w2 - W_in, 0.0);
    // supply 제한 (직물 공급 vs 공기 수요)
    e_air_demand = e1 + e2;
    m_evap_supply = M_water_z[N] / 1.0 + M_free / 1.0;  // 표면+자유수 (rate 근사)
    cap_ratio = min(e_air_demand / max(e_air_demand, 1e-12), 1.0);  // 정상건조선 공급충분
    m_evap = e_air_demand;   // actual_evap = e1+e2

    // W_s, h_m는 진단용 유지
    W_s = ws_surf;
    h_m = hA / (A_fabric * MoistAir.cp_da);

    // ── zone 간 확산 flux (최소: 인접 포화도 차) ──
    // ── 3b: N셀 Fick 확산 + Darcy-Leverett 모세관 blend flux ──
    //   w_cap(i)=i/(N-2): 내부(확산지배)→표면(모세관지배). N=3서 원본 재현.
    for i in 1:N-1 loop
      J_zone[i] = (
        // (1-w_cap)·diffusion: D_eff(T,S)·(ΔS)/L_char·rho_fabric
        (1 - w_cap[i]) * (
          D_ref * exp(-E_a / (R_GAS * T_fabric)) * max(S[i], 0.01)^diffusion_S_exp
          * (S[i] - S[i+1]) / L_char * rho_fabric
        )
        // w_cap·capillary: Darcy-Leverett
        + w_cap[i] * max(
          K_abs * (0.5 * (min(max(S[i],0.01),0.999)^brooks_corey
                        + min(max(S[i+1],0.01),0.999)^brooks_corey))
          / mu_water(T_fabric)
          * (sigma_water(T_fabric) / sqrt(K_abs))
          * ((0.364 * (1 - min(max(S[i],0.01),0.999))^0.5 - 0.221 * (1 - min(max(S[i],0.01),0.999)))
           - (0.364 * (1 - min(max(S[i+1],0.01),0.999))^0.5 - 0.221 * (1 - min(max(S[i+1],0.01),0.999))))
          / L_char * 1000.0, 0.0)
      ) * A_fabric;
    end for;

    // ── 3b: 텀블링 zone 교환 flux (der 연속: rate = k·RPM/60) ──
    k_exch = if Fr < 0.1 then k_exch_slide
             elseif Fr < 0.5 then k_exch_slide + (k_exch_casc - k_exch_slide) * (Fr - 0.1) / 0.4
             elseif Fr < 1.0 then k_exch_casc + (k_exch_high - k_exch_casc) * (Fr - 0.5) / 0.5
             else k_exch_high;
    for i in 1:N-1 loop
      J_tumble[i] = k_exch * RPM / 60.0 * (M_water_z[i] - M_water_z[i+1]) / 2.0;
    end for;

    // ── 공기 CV (well-mixed) ──
    // ── 4스텝: 출구 공기 4경로 질량가중 혼합 (drum_on 1:1) ──
    //   cloth(w1,T1)·partial(w2,T2) 증발경로 + rear_bypass·gap 우회(입구 0.98T).
    //   well-mixed 대신 경로별 혼합 → drum_on 정확 재현.
    W_out = (m_dot_eff * w1 + m_dot_partial * w2
             + m_flow_da * f_rbypass * W_in + m_flow_da * f_gap * W_in) / max(m_flow_da, 1e-8);
    T_out = (m_dot_eff * T1 + m_dot_partial * T2
             + m_flow_da * f_rbypass * (T_in * 0.98) + m_flow_da * f_gap * (T_in * 0.98)) / max(m_flow_da, 1e-8);
    h_out = MoistAir.h_da_fn(T_out, W_out);

    // ── zone 동특성 (der 상태) ──
    // ── zone 동특성 (der 상태): 확산+모세관(J_zone) + 텀블링(J_tumble) ──
    der(M_water_z[1]) = -J_zone[1] - J_tumble[1];
    for i in 2:N-1 loop
      der(M_water_z[i]) = J_zone[i-1] - J_zone[i] + J_tumble[i-1] - J_tumble[i];
    end for;
    der(M_water_z[N]) = J_zone[N-1] + J_tumble[N-1] - m_evap * (1 - g_free);

    // ── 3d: 자유수 der (증발이 자유수에서 g_free 비율로 소진) ──
    der(M_free) = -m_evap * g_free;

    // ── 직물 온도 (der 상태) ──
    // ── 직물 온도 (der): drum_on update_temperature 방식 ──
    //   Q_tot = m_flow_da·CP_A·eps·(T_in-T_fab), eps=1-exp(-hA/(m·CP_A)).
    //   ★ drum_on과 동일: 전체유량 NTU, 입구온도 T_in 기준 (well-mixed 아님).
    //   drum_on을 ground truth로 1:1 맞춤.
    (m_cl_dry * c_p_cl + sum(M_water_z) * MoistAir.cp_w) * der(T_fabric)
        = m_flow_da * MoistAir.cp_da * (1 - exp(-hA / max(m_flow_da * MoistAir.cp_da, 1e-6)))
          * (T_in - T_fabric) - m_evap * MoistAir.h_fg(T_fabric);

    // ── 공기측 압력강하 ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    u = m_flow_da / (rho_da * A_drum);
    dp_drum = K_drum * u * abs(u);
    port_b.p = port_a.p - dp_drum;

    // ── stream: well-mixed ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;

  public
    function sigma_water "물 표면장력 (N/m, drum_on)"
      input Modelica.Units.SI.Temperature T "K";
      output Real sigma;
    algorithm
      sigma := 0.0756 - 0.000139 * (T - 273.15);
    end sigma_water;

    function mu_water "물 점도 (Pa·s, drum_on)"
      input Modelica.Units.SI.Temperature T "K";
      output Real mu;
    algorithm
      mu := 0.001 * exp(-3.7188 + 578.919 / ((T - 273.15) + 137.546));
    end mu_water;

    function segment_fill_angle "충전각 bisection (fill=(θ-sinθcosθ)/π 역산)"
      input Real fill;
      output Real theta;
    protected
      Real lo, hi, mid, ratio;
    algorithm
      lo := 0.0; hi := Modelica.Constants.pi;
      for k in 1:60 loop
        mid := (lo + hi) / 2;
        ratio := (mid - sin(mid) * cos(mid)) / Modelica.Constants.pi;
        if ratio < fill then lo := mid; else hi := mid; end if;
      end for;
      theta := (lo + hi) / 2;
    end segment_fill_angle;

    function laundry_R "의류더미 Ergun 저항 (drum_on R_laundry)"
      input Real fill; input Real A_cross; input Real rb; input Real rf;
      input Real dc; input Real R_drum; input Real rho_a;
      output Real R;
    protected
      Real eps, L_bed, A_flow, coeff;
    algorithm
      eps := max(1.0 - rb / rf, 0.15);
      L_bed := 2.0 * R_drum * max(fill, 0.01)^0.5;
      A_flow := A_cross * eps;
      if A_flow < 1e-8 or dc < 1e-8 then
        R := 1e6;
      else
        coeff := 1.75 * L_bed * (1 - eps) / (dc * eps^3);
        R := coeff / (2.0 * rho_a * A_flow^2);
      end if;
    end laundry_R;

    function side_cover_fn "측면홀 덮임 (Fr 구간별)"
      input Real Fr_; input Real theta_fab;
      output Real cover;
    protected
      Real ang;
    algorithm
      if Fr_ < 0.01 then ang := theta_fab;
      elseif Fr_ < 0.5 then ang := min(theta_fab * (1.0 + 0.8 * Fr_ / 0.5), Modelica.Constants.pi * 0.85);
      elseif Fr_ < 1.0 then ang := min(theta_fab * (1.8 + 0.4 * (Fr_ - 0.5) / 0.5), Modelica.Constants.pi * 0.9);
      else ang := Modelica.Constants.pi * 0.95;
      end if;
      cover := min(ang / Modelica.Constants.pi, 0.95);
    end side_cover_fn;
  end Drum_L3;



  // =============================================================
  // EvapAir_L1: 증발기 공기측 L1 (냉각 + 제습, bypass-factor).
  //   air 네트워크에선 R: dry-air 보존 + ΔP_air (핀 마찰).
  //   코일 표면온도 = T_evap (파라미터, L1: 냉매측 막저항 무시 → 제습 다소 과대).
  //   표면포화 W_s(T_evap)로 bypass-factor 제습:
  //     T_out = BF·T_in + (1−BF)·T_evap
  //     W_out = min(W_in, BF·W_in + (1−BF)·W_s)   (응축 시 감소, dry면 W_in)
  //   응축수는 배수(stream 밖), Q는 냉매로 (추후 RefPort 커플링용 출력).
  // =============================================================
  model EvapAir_L1
    "Evaporator air-side L1 (cooling + dehumidification, bypass-factor)"
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Temperature T_evap = 283.15
      "evap surface temp (prescribed, L1)";
    parameter Real BF = 0.2 "bypass factor (0=ideal, ε=1−BF)";
    parameter Modelica.Units.SI.Area A_face = 0.05 "coil face area (m²)";
    parameter Real K_air = 50 "air-side fin resistance (Pa·s²/m²)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05)
      "dry-air mass flow (a→b +)";
    Real W_in(unit="kg/kg") "inlet humidity ratio (upstream)";
    Real W_out(unit="kg/kg") "outlet humidity ratio";
    Real W_sat_s(unit="kg/kg") "saturation humidity at coil surface";
    Modelica.Units.SI.SpecificEnthalpy h_in "inlet h_tilde (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_out "outlet h_tilde";
    Modelica.Units.SI.Temperature T_in "inlet air temp";
    Modelica.Units.SI.Temperature T_out "outlet air temp";
    Modelica.Units.SI.MassFlowRate m_cond "condensate rate (drained)";
    Modelica.Units.SI.Power Q_total "heat to refrigerant";
    Modelica.Units.SI.Power Q_sensible "sensible part";
    Modelica.Units.SI.Power Q_latent "latent part (condensation)";
    Real SHR "sensible heat ratio";

    Modelica.Units.SI.Density rho_da "dry-air density (p_ref, inlet)";
    Modelica.Units.SI.Velocity u "face velocity";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Pressure dp_air "air-side pressure drop";

  equation
    // ── dry-air 질량보존 (응축수는 배수; dry air 보존) ──
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    // ── 입구(상류) 상태 ──
    W_in = inStream(port_a.W_outflow);
    h_in = inStream(port_a.h_tilde_outflow);
    T_in = MoistAir.T_from_h(h_in, W_in);

    // ── 표면포화 + bypass-factor 출구상태 ──
    W_sat_s = MoistAir.W_sat(T_evap);
    T_out = BF * T_in + (1 - BF) * T_evap;
    W_out = min(W_in, BF * W_in + (1 - BF) * W_sat_s);
    h_out = MoistAir.h_da_fn(T_out, W_out);

    // ── 응축수 + 열 분해 (진단 + 추후 냉매 커플링) ──
    m_cond = m_flow_da * (W_in - W_out);
    Q_total = m_flow_da * (h_in - h_out)
              - m_cond * MoistAir.cp_w * (T_out - MoistAir.T0);
    Q_latent = m_cond * MoistAir.h_fg(T_out);
    Q_sensible = Q_total - Q_latent;
    SHR = Q_sensible / max(Q_total, 1e-9);

    // ── 공기측 압력강하 (핀 마찰) ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    V_dot = m_flow_da / rho_da;
    u = V_dot / A_face;
    dp_air = K_air * u * abs(u);
    port_b.p = port_a.p - dp_air;

    // ── stream: 출구 처리상태 (양 포트 outflow = outlet) ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;
  end EvapAir_L1;


  // =============================================================
  // CondAir_L1: 응축기 공기측 L1 (현열 가열, bypass-factor).
  //   air 네트워크에선 R: dry-air 보존 + ΔP_air (핀 마찰).
  //   코일 표면온도 = T_cond (파라미터, L1: 냉매측 막저항 무시).
  //   dry process — W 불변 (응축기는 공기 가열만, 제습 없음):
  //     T_out = BF·T_in + (1−BF)·T_cond   (T_cond > T_in → 가열)
  //     W_out = W_in
  //   Q는 냉매→공기 (추후 RefPort 커플링용 출력, evap과 부호 반대).
  // =============================================================
  model CondAir_L1
    "Condenser air-side L1 (sensible heating, bypass-factor)"
    AirPort port_a "inlet";
    AirPort port_b "outlet";

    parameter Modelica.Units.SI.Temperature T_cond = 333.15
      "cond surface temp (prescribed, L1)";
    parameter Real BF = 0.2 "bypass factor (0=ideal, ε=1−BF)";
    parameter Modelica.Units.SI.Area A_face = 0.05 "coil face area (m²)";
    parameter Real K_air = 50 "air-side fin resistance (Pa·s²/m²)";

    Modelica.Units.SI.MassFlowRate m_flow_da(start = 0.05)
      "dry-air mass flow (a→b +)";
    Real W_in(unit="kg/kg") "inlet humidity ratio (upstream)";
    Real W_out(unit="kg/kg") "outlet humidity ratio (= W_in, dry)";
    Modelica.Units.SI.SpecificEnthalpy h_in "inlet h_tilde (upstream)";
    Modelica.Units.SI.SpecificEnthalpy h_out "outlet h_tilde";
    Modelica.Units.SI.Temperature T_in "inlet air temp";
    Modelica.Units.SI.Temperature T_out "outlet air temp";
    Modelica.Units.SI.Power Q_total "heat from refrigerant to air";

    Modelica.Units.SI.Density rho_da "dry-air density (p_ref, inlet)";
    Modelica.Units.SI.Velocity u "face velocity";
    Modelica.Units.SI.VolumeFlowRate V_dot "volumetric flow";
    Modelica.Units.SI.Pressure dp_air "air-side pressure drop";

  equation
    // ── dry-air 질량보존 ──
    m_flow_da = port_a.m_flow_da;
    port_a.m_flow_da + port_b.m_flow_da = 0;

    // ── 입구(상류) 상태 ──
    W_in = inStream(port_a.W_outflow);
    h_in = inStream(port_a.h_tilde_outflow);
    T_in = MoistAir.T_from_h(h_in, W_in);

    // ── bypass-factor 가열 (dry process, W 불변) ──
    T_out = BF * T_in + (1 - BF) * T_cond;
    W_out = W_in;
    h_out = MoistAir.h_da_fn(T_out, W_out);

    // ── 열 (냉매→공기; 추후 커플링) ──
    Q_total = m_flow_da * (h_out - h_in);

    // ── 공기측 압력강하 (핀 마찰) ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    V_dot = m_flow_da / rho_da;
    u = V_dot / A_face;
    dp_air = K_air * u * abs(u);
    port_b.p = port_a.p - dp_air;

    // ── stream: 출구 처리상태 (양 포트 outflow = outlet) ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;
  end CondAir_L1;


  // =============================================================
  // BoundaryAir_mflow: 유량 지정 경계 (테스트용 flow source/sink).
  //   port.m_flow_da 직접 지정 (음수 = 유출/source, 양수 = 유입/sink).
  //   stream (T,W)는 역류 시 공급될 상류값.
  // =============================================================
  model BoundaryAir_mflow "Air boundary: prescribed dry-air mass flow + (T,W)"
    AirPort port;
    parameter Modelica.Units.SI.MassFlowRate m_flow_da = -0.05
      "prescribed dry-air mass flow (음수=유출)";
    parameter Modelica.Units.SI.Temperature T = 298.15;
    parameter Real W = 0.01 "humidity ratio (kg/kg_da)";
  equation
    port.m_flow_da = m_flow_da;
    port.h_tilde_outflow =
        MoistAir.cp_da * (T - MoistAir.T0)
      + W * (MoistAir.hfg0 + MoistAir.cp_v * (T - MoistAir.T0));
    port.W_outflow = W;
  end BoundaryAir_mflow;


end HPWDair;
