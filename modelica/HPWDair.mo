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
    // ── L2: 풍속 상관식으로 h_a 자동계산 (Nu~Re^m, 정격 앵커링) ──
    parameter Boolean h_corr = false
      "true: h_a를 드럼 풍속 상관식으로 (L2); false: 고정값 h_a (L1)";
    parameter Modelica.Units.SI.Velocity u_nom = 0.33
      "정격 드럼 풍속 (anchoring 기준점, m/s)";
    parameter Real m_Nu = 0.8 "Nu~Re^m 지수 (난류 강제대류 ≈0.8)";
    parameter Modelica.Units.SI.Area A_drum = 0.15
      "drum air-flow cross-section (m²)";
    parameter Real K_drum = 30 "cloth-bed resistance (Pa·s²/m²)";
    parameter Real X0 = 0.6 "initial moisture ratio (kg水/kg dry)";
    parameter Modelica.Units.SI.Temperature Tcl0 = 298.15
      "initial cloth temp (K)";
    parameter Real UA_amb = 0.0
      "cabinet 외기 열손실 UA (W/K); 0=단열(air 링 기본)";
    parameter Modelica.Units.SI.Temperature T_amb = 298.15 "외기온 (K)";

    // ── states ──
    Modelica.Units.SI.Mass m_w(
      start = X0 * m_cl_dry, fixed = true,
      stateSelect = StateSelect.prefer) "cloth moisture (state)";
    Modelica.Units.SI.Temperature T_cl(
      start = Tcl0, fixed = true,
      stateSelect = StateSelect.prefer) "cloth temp (state)";
    Real X "moisture ratio (dry basis)";

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
    Real h_a_act "유효 대류계수 (L1=h_a 고정, L2=Nu 상관식, W/m²·K)";
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
    W_s = MoistAir.W_sat(T_cl);
    h_m = h_a_act / MoistAir.cp_da;
    m_evap = h_m * A_eff * (W_s - W_out);

    // ── 공기 CV (quasi-steady, well-mixed: T_air=T_out) ──
    m_flow_da * (W_out - W_in) = m_evap;
    Q_amb = UA_amb * (T_out - T_amb);
    m_flow_da * (h_out - h_in)
        = -h_a_act * A_eff * (T_out - T_cl) + m_evap * MoistAir.h_g(T_cl) - Q_amb;
    T_out = MoistAir.T_from_h(h_out, W_out);

    // ── cloth 동특성 (states) ──
    X = m_w / m_cl_dry;
    der(m_w) = -m_evap;
    (m_cl_dry * c_p_cl + m_w * MoistAir.cp_w) * der(T_cl)
        = h_a_act * A_eff * (T_out - T_cl) - m_evap * MoistAir.h_fg(T_cl);

    // ── 공기측 압력강하 (의류 더미 저항, 단일 K) ──
    rho_da = MoistAir.rho_da_fn(T_in, W_in);
    u = m_flow_da / (rho_da * A_drum);
    // L2 상관식: Nu∝Re^m, Re∝u (고정 형상·물성) → h_a∝u^m, 정격점에서 h_a로 앵커링.
    // h_corr=false면 h_a_act=h_a (L1과 동일). max()로 기동 시 u→0 보호.
    h_a_act = if h_corr then h_a * (max(u, 1e-4) / u_nom) ^ m_Nu else h_a;
    dp_drum = K_drum * u * abs(u);
    port_b.p = port_a.p - dp_drum;

    // ── stream: well-mixed (양 포트 outflow = bulk) ──
    port_a.W_outflow = W_out;
    port_b.W_outflow = W_out;
    port_a.h_tilde_outflow = h_out;
    port_b.h_tilde_outflow = h_out;
  end Drum_L1;


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
