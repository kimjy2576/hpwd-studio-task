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

    Modelica.Units.SI.MassFlowRate m_flow_da "dry-air mass flow (a→b +)";
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
