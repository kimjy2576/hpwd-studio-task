"""
EEV — Electronic Expansion Valve (L2 Semi-Empirical / Sami-Schnotale)
═══════════════════════════════════════════════════════════════════════
2-phase choked flow + subcooling correction을 포함하는 학계 표준 모델.

핵심 식 (Sami-Schnotale 1995, modified):
  
  Normal flow:
    ṁ_normal = Cd_eff × A_eff × √(2 × ρ_in × ΔP_eff)
  
  Choked flow (P_out/P_in < critical ratio):
    G_crit = √(ρ × P_in × Y_crit)         (Henry-Fauske 단순화)
    ṁ_choked = G_crit × A_eff
    ΔP_eff = P_in × (1 - Y_crit) 
  
  ṁ = min(ṁ_normal, ṁ_choked)
  
  Discharge coefficient correlation:
    Cd_eff = C_d0 × f_Re(Re) × f_sub(ΔT_sub) × f_op(op)
    
    f_Re(Re)  = 1 - exp(-Re/Re_c)        (low-Re correction)
    f_sub(ΔT) = 1 + k_sub × (ΔT_sub / 10)  (subcooling 효과)
    f_op(op)  = 1 - k_op × (1 - op)       (low opening 효과)
  
  A_eff = cf_A × A_orifice × op_frac     (선형 — L1과 동일, geometry는 L3)

Reference:
  • Sami, Schnotale (1995): "Modeling EEV with two-phase choked flow",
    International Journal of Refrigeration, 18(5):310-318
  • Buick et al. (1996): "Refrigerant Mass Flow Through Capillary Tubes"
  • Henry, Fauske (1971): "The two-phase critical flow of one-component mixtures"

L2 vs L1, L3:
  L1 (130): ARI curve, fitting 5 params, no choke
  L2 (131): + 2-phase choke + Re/subcooling correction, fitting 7 params  ← This
  L3 (132): + needle cone geometry, fitting 4 params

모드:
  • control: opening → m_dot
  • measure: m_dot → opening (bisection)
"""

import math
import CoolProp.CoolProp as CP


FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']
MODES = ['control', 'measure']


modelDescription = {
    'typeNo': 131,
    'name': 'EEV (Semi-Empirical / Sami-Schnotale)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.8,
    'description': 'Sami-Schnotale: 2-phase choke + subcooling/Re correction',
    'backend': 'python',
    'variables': [
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'control', 'unit': '-', 'options': MODES,
         'description': 'control: opening→ṁ / measure: ṁ→opening'},
        {'name': 'use_choke', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'on', 'unit': '-', 'options': ['on', 'off'],
         'description': '2-phase choke 활성화'},
        {'name': 'A_orifice', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 3.14e-6, 'unit': 'm²',
         'description': 'Maximum orifice 면적 (D=2mm → 3.14e-6 m²)'},
        {'name': 'opening_min', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.0, 'unit': '%',
         'description': 'Minimum opening %'},
        {'name': 'Cd_0', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.72, 'unit': '-',
         'description': 'Base Cd at high Re, full opening, no subcooling'},
        {'name': 'Re_c', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 5000.0, 'unit': '-',
         'description': 'Critical Re for low-Re correction'},
        {'name': 'k_sub', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.05, 'unit': '-',
         'description': 'Subcooling sensitivity (per 10K subcool)'},
        {'name': 'k_op', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.15, 'unit': '-',
         'description': 'Low-opening Cd reduction factor'},
        {'name': 'Y_crit', 'causality': 'parameter', 'type': 'Real',
         'group': 'Choke', 'start': 0.55, 'unit': '-',
         'description': 'Critical pressure ratio for choke (R290 typical: 0.5~0.6)'},
        {'name': 'cf_A', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'A_eff 보정 factor'},
        {'name': 'P_in', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '입구 압력 (subcool liquid)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '입구 비엔탈피'},
        {'name': 'P_out', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '출구 압력 (2-phase)'},
        {'name': 'opening', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '(control) Opening 0~100%'},
        {'name': 'm_dot_meas', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '(measure) 측정 ṁ'},
        {'name': 'm_dot_ref', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 mass flow'},
        {'name': 'opening_calc', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': 'opening (measure 시 역산)'},
        {'name': 'h_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '출구 비엔탈피'},
        {'name': 'T_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '출구 온도'},
        {'name': 'x_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '출구 quality'},
        {'name': 'Cd_eff', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '실제 적용된 Cd (correction 적용 후)'},
        {'name': 'Re', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Throat Reynolds number'},
        {'name': 'T_sub', 'causality': 'output', 'type': 'Real',
         'unit': 'K', 'description': '입구 subcooling'},
        {'name': 'rho_in', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '입구 밀도'},
        {'name': 'dP', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'P_in - P_out (실제)'},
        {'name': 'dP_eff', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '실제 효과 ΔP (choke cap)'},
        {'name': 'is_choked', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '2-phase choke 발생 여부 (1/0)'},
    ],
    'capabilities': {'canDoStep': True, 'canGetDerivatives': False},
}


def init_state(params):
    return {}


def _compute_subcooling(P_in_Pa, h_in_J, fluid):
    """입구 subcooling 계산 (K). subcooled면 양수, 2-phase면 0."""
    try:
        T_sat = CP.PropsSI('T', 'P', P_in_Pa, 'Q', 0, fluid)
        h_sat_l = CP.PropsSI('H', 'P', P_in_Pa, 'Q', 0, fluid)
        if h_in_J >= h_sat_l:
            return 0.0  # already 2-phase or superheated → no subcooling
        T_in = CP.PropsSI('T', 'P', P_in_Pa, 'H', h_in_J, fluid)
        return T_sat - T_in
    except Exception:
        return 5.0  # fallback


def _Cd_corrections(Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op):
    """
    Cd_eff = Cd_0 × f_Re × f_sub × f_op
    
    f_Re(Re)  = 1 - exp(-Re/Re_c)    [→ 1 as Re→∞, → 0 as Re→0]
    f_sub(ΔT) = 1 + k_sub × (ΔT_sub / 10)
    f_op(op)  = 1 - k_op × (1 - op)  [reduces at low opening]
    """
    f_Re = 1.0 - math.exp(-max(0, Re) / max(1, Re_c)) if Re > 0 else 0.0
    f_sub = 1.0 + k_sub * (T_sub_K / 10.0)
    f_op = 1.0 - k_op * (1.0 - max(0, min(1, op_frac)))
    return Cd_0 * max(0.05, f_Re) * max(0.5, f_sub) * max(0.3, f_op)


def step(input, params, state, dt):
    fluid = params.get('fluid', 'R290')
    mode = params.get('mode', 'control')
    use_choke = params.get('use_choke', 'on')

    A_orifice = float(params.get('A_orifice', 3.14e-6))
    opening_min = float(params.get('opening_min', 0.0))
    Cd_0 = float(params.get('Cd_0', 0.72))
    Re_c = float(params.get('Re_c', 5000.0))
    k_sub = float(params.get('k_sub', 0.05))
    k_op = float(params.get('k_op', 0.15))
    Y_crit = float(params.get('Y_crit', 0.55))
    cf_A = float(params.get('cf_A', 1.0))

    P_in_bar = float(input.get('P_in', 17.0))
    h_in_kjkg = float(input.get('h_in', 280.0))
    P_out_bar = float(input.get('P_out', 5.84))
    opening_pct = float(input.get('opening', 50.0))
    m_dot_meas = float(input.get('m_dot_meas', 0.012))

    if P_in_bar <= 0 or P_out_bar <= 0:
        raise ValueError(f"압력 0 이하: P_in={P_in_bar}, P_out={P_out_bar}")
    if P_out_bar >= P_in_bar:
        return _zero_output(P_in_bar, P_out_bar, h_in_kjkg, mode, opening_pct)

    P_in_Pa = P_in_bar * 1e5
    P_out_Pa = P_out_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0

    try:
        rho_in = CP.PropsSI('D', 'P', P_in_Pa, 'H', h_in_J, fluid)
        mu_in = CP.PropsSI('V', 'P', P_in_Pa, 'H', h_in_J, fluid)
    except Exception:
        rho_in = 480.0 if fluid == 'R290' else 1100.0
        mu_in = 1.5e-4

    T_sub_K = _compute_subcooling(P_in_Pa, h_in_J, fluid)

    # ═══ Choke check ═══
    is_choked = 0
    dP_actual_Pa = P_in_Pa - P_out_Pa
    dP_eff_Pa = dP_actual_Pa
    pressure_ratio = P_out_Pa / P_in_Pa

    if use_choke == 'on' and pressure_ratio < Y_crit:
        dP_eff_Pa = P_in_Pa * (1.0 - Y_crit)
        is_choked = 1

    dP_eff_bar = dP_eff_Pa / 1e5

    # ═══ Mode-specific 계산 ═══
    if mode == 'control':
        opening_clamped = max(opening_min, min(100.0, opening_pct))
        op_frac = opening_clamped / 100.0
        A_eff = cf_A * A_orifice * op_frac

        # First-pass: estimate Re with high-Re Cd
        m_dot_first = Cd_0 * A_eff * math.sqrt(2 * rho_in * dP_eff_Pa)
        D_h = math.sqrt(4 * A_eff / math.pi) if A_eff > 0 else 0
        Re = m_dot_first * D_h / (mu_in * A_eff) if (mu_in * A_eff) > 0 else 0

        # Cd with all corrections
        Cd_eff = _Cd_corrections(Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op)

        m_dot_ref = Cd_eff * A_eff * math.sqrt(2 * rho_in * dP_eff_Pa)
        opening_calc = opening_clamped
    else:
        # measure mode: bisection
        if m_dot_meas <= 0 or rho_in <= 0:
            opening_calc = 0.0
            A_eff = 0.0
            Cd_eff = 0.0
            Re = 0.0
            m_dot_ref = 0.0
        else:
            lo, hi = opening_min, 100.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                op_frac_t = mid / 100.0
                A_t = cf_A * A_orifice * op_frac_t
                m_first = Cd_0 * A_t * math.sqrt(2 * rho_in * dP_eff_Pa)
                D_h = math.sqrt(4 * A_t / math.pi) if A_t > 0 else 0
                Re_t = m_first * D_h / (mu_in * A_t) if (mu_in * A_t) > 0 else 0
                Cd_t = _Cd_corrections(Cd_0, Re_t, T_sub_K, op_frac_t, Re_c, k_sub, k_op)
                m_t = Cd_t * A_t * math.sqrt(2 * rho_in * dP_eff_Pa)
                if m_t < m_dot_meas:
                    lo = mid
                else:
                    hi = mid
                if abs(hi - lo) < 0.001:
                    break
            opening_calc = (lo + hi) / 2.0
            op_frac = opening_calc / 100.0
            A_eff = cf_A * A_orifice * op_frac
            m_dot_first = Cd_0 * A_eff * math.sqrt(2 * rho_in * dP_eff_Pa)
            D_h = math.sqrt(4 * A_eff / math.pi) if A_eff > 0 else 0
            Re = m_dot_first * D_h / (mu_in * A_eff) if (mu_in * A_eff) > 0 else 0
            Cd_eff = _Cd_corrections(Cd_0, Re, T_sub_K, op_frac, Re_c, k_sub, k_op)
            m_dot_ref = m_dot_meas

    # ═══ 출구 상태 (isenthalpic) ═══
    h_out_J = h_in_J
    try:
        h_l_out = CP.PropsSI('H', 'P', P_out_Pa, 'Q', 0, fluid)
        h_v_out = CP.PropsSI('H', 'P', P_out_Pa, 'Q', 1, fluid)
        if h_out_J <= h_l_out:
            x_out = 0.0
            T_out_K = CP.PropsSI('T', 'P', P_out_Pa, 'H', h_out_J, fluid)
        elif h_out_J >= h_v_out:
            x_out = 1.0
            T_out_K = CP.PropsSI('T', 'P', P_out_Pa, 'H', h_out_J, fluid)
        else:
            x_out = (h_out_J - h_l_out) / (h_v_out - h_l_out)
            T_out_K = CP.PropsSI('T', 'P', P_out_Pa, 'Q', x_out, fluid)
    except Exception:
        x_out = 0.2
        T_out_K = 280.0

    return {
        'outputs': {
            'm_dot_ref': m_dot_ref,
            'opening_calc': opening_calc,
            'h_out': h_out_J / 1000.0,
            'T_out': T_out_K - 273.15,
            'x_out': x_out,
            'Cd_eff': Cd_eff,
            'Re': Re,
            'T_sub': T_sub_K,
            'rho_in': rho_in,
            'dP': P_in_bar - P_out_bar,
            'dP_eff': dP_eff_bar,
            'is_choked': float(is_choked),
        },
        'newState': {},
    }


def _zero_output(P_in_bar, P_out_bar, h_in_kjkg, mode, opening_pct):
    return {
        'outputs': {
            'm_dot_ref': 0.0,
            'opening_calc': opening_pct if mode == 'control' else 0.0,
            'h_out': h_in_kjkg,
            'T_out': float('nan'),
            'x_out': 0.0,
            'Cd_eff': 0.0,
            'Re': 0.0,
            'T_sub': 0.0,
            'rho_in': 0.0,
            'dP': P_in_bar - P_out_bar,
            'dP_eff': 0.0,
            'is_choked': 0.0,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    A_orifice = float(params.get('A_orifice', 3.14e-6))
    if A_orifice <= 0 or A_orifice > 1e-4:
        issues.append({'key': 'A_orifice',
                       'msg': f'A_orifice={A_orifice*1e6:.2f}mm² — 보통 1~30 mm²'})
    Cd_0 = float(params.get('Cd_0', 0.72))
    if Cd_0 < 0.4 or Cd_0 > 0.95:
        issues.append({'key': 'Cd_0', 'msg': f'Cd_0={Cd_0} — 0.6~0.8 권장'})
    Y_crit = float(params.get('Y_crit', 0.55))
    if Y_crit < 0.3 or Y_crit > 0.8:
        issues.append({'key': 'Y_crit', 'msg': f'Y_crit={Y_crit} — 0.4~0.6 권장 (R290)'})
    return issues
