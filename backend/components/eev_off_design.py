"""
EEV — Electronic Expansion Valve (L1 Off-design / ARI Flow Coefficient Curve)
═══════════════════════════════════════════════════════════════════════
제조사 카탈로그 데이터를 직접 사용하는 단순 모델.
HPWD 시스템 레벨 시뮬레이션에 가장 적합.

핵심 식 (ARI-style):
  ṁ = Cv_rated × A_orifice × Φ(opening) × √(2 × ρ_in × ΔP)
  
  Φ(op) = c0 + c1·op + c2·op² + c3·op³   (제조사 normalized curve)
        — opening 0~1에서 normalized 0~1
        — c0=0 (closed: ṁ=0)
        — c3 가까이서 c0+c1+c2+c3 ≈ 1 (fully open: Φ=1)

Reference:
  • ARI Standard 750-94: "Thermostatic Refrigerant Expansion Valves"
  • Park, Cho, Kim (2007): "Empirical correlations for EEV"
  • Saginomiya STF/Danfoss CCM 카탈로그 → 직접 Φ(op) curve fit 가능

L1 vs L2 vs L3:
  L1 (130): Cv × Φ(op) × √(ρ·ΔP)        — manufacturer curve, fast
  L2 (131): + 2-phase choke + subcooling — semi-empirical (Sami-Schnotale)
  L3 (132): + needle cone geometry       — physics-based

모드:
  • control: opening → m_dot
  • measure: m_dot → opening (역산, calibration용)
"""

import math
import CoolProp.CoolProp as CP


FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']
MODES = ['control', 'measure']


modelDescription = {
    'typeNo': 130,
    'name': 'EEV (Off-Design / ARI Curve)',
    'category': 'refrigerant',
    'modelType': 'off-design',
    'fidelity': 0.6,
    'description': 'ARI flow coefficient curve — manufacturer 카탈로그 직접 사용',
    'backend': 'python',
    'variables': [
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'control', 'unit': '-', 'options': MODES,
         'description': 'control: opening→ṁ / measure: ṁ→opening'},
        {'name': 'A_orifice', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 3.14, 'unit': 'mm²',
         'description': 'Maximum orifice 면적 [mm²] (D=2mm → 3.14 mm²). 내부에서 ×1e-6로 m² 변환'},
        {'name': 'opening_min', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.0, 'unit': '%',
         'description': 'Minimum opening % (leakage)'},
        {'name': 'Cv_rated', 'causality': 'parameter', 'type': 'Real',
         'group': 'Curve', 'start': 0.7, 'unit': '-',
         'description': 'Cv at fully open (R290 EEV typical: 0.65~0.75)'},
        {'name': 'c0', 'causality': 'parameter', 'type': 'Real',
         'group': 'Curve', 'start': 0.0, 'unit': '-',
         'description': 'Φ(op) = c0 + c1·op + c2·op² + c3·op³ (op in [0,1])'},
        {'name': 'c1', 'causality': 'parameter', 'type': 'Real',
         'group': 'Curve', 'start': 0.5, 'unit': '-',
         'description': '선형 항 계수'},
        {'name': 'c2', 'causality': 'parameter', 'type': 'Real',
         'group': 'Curve', 'start': 0.3, 'unit': '-',
         'description': '2차 항 계수 (typical: opening curve 약간 위로 볼록)'},
        {'name': 'c3', 'causality': 'parameter', 'type': 'Real',
         'group': 'Curve', 'start': 0.2, 'unit': '-',
         'description': '3차 항 계수'},
        {'name': 'P_in', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '입구 압력 (subcool liquid)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '입구 비엔탈피'},
        {'name': 'P_out', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '출구 압력 (2-phase)'},
        {'name': 'opening', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '(control mode) Opening 0~100%'},
        {'name': 'm_dot_meas', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '(measure mode) 측정 ṁ → opening 역산'},
        {'name': 'm_dot_ref', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 mass flow'},
        {'name': 'opening_calc', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': 'opening (measure 시 역산)'},
        {'name': 'h_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '출구 비엔탈피 (= h_in)'},
        {'name': 'T_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '출구 온도'},
        {'name': 'x_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '출구 quality'},
        {'name': 'phi_op', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Φ(opening) — normalized flow coefficient'},
        {'name': 'rho_in', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '입구 밀도'},
        {'name': 'dP', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'P_in - P_out'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _phi(op_frac, c0, c1, c2, c3):
    """Φ(op) — normalized flow coefficient curve (manufacturer-fitted polynomial)"""
    op = max(0.0, min(1.0, op_frac))
    return c0 + c1 * op + c2 * op ** 2 + c3 * op ** 3


def step(input, params, state, dt):
    fluid = params.get('fluid', 'R290')
    mode = params.get('mode', 'control')
    A_orifice = float(params.get('A_orifice', 3.14)) * 1e-6   # mm² → m² (UI=mm², 물리=SI)
    opening_min = float(params.get('opening_min', 0.0))
    Cv_rated = float(params.get('Cv_rated', 0.7))
    c0 = float(params.get('c0', 0.0))
    c1 = float(params.get('c1', 0.5))
    c2 = float(params.get('c2', 0.3))
    c3 = float(params.get('c3', 0.2))

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
    dP_Pa = P_in_Pa - P_out_Pa

    try:
        rho_in = CP.PropsSI('D', 'P', P_in_Pa, 'H', h_in_J, fluid)
    except Exception:
        rho_in = 480.0 if fluid == 'R290' else 1100.0

    if mode == 'control':
        opening_clamped = max(opening_min, min(100.0, opening_pct))
        opening_frac = opening_clamped / 100.0
        phi_op = _phi(opening_frac, c0, c1, c2, c3)
        m_dot_ref = Cv_rated * A_orifice * phi_op * math.sqrt(2.0 * rho_in * dP_Pa)
        opening_calc = opening_clamped
    else:
        # measure mode: ṁ → opening 역산 (bisection)
        if m_dot_meas <= 0 or rho_in <= 0:
            opening_calc = 0.0
            phi_op = 0.0
            m_dot_ref = 0.0
        else:
            denom = Cv_rated * A_orifice * math.sqrt(2.0 * rho_in * dP_Pa)
            phi_target = m_dot_meas / denom if denom > 0 else 0
            lo, hi = opening_min, 100.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                phi_mid = _phi(mid / 100.0, c0, c1, c2, c3)
                if phi_mid < phi_target:
                    lo = mid
                else:
                    hi = mid
                if abs(hi - lo) < 0.001:
                    break
            opening_calc = (lo + hi) / 2.0
            phi_op = _phi(opening_calc / 100.0, c0, c1, c2, c3)
            m_dot_ref = m_dot_meas

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
            'phi_op': phi_op,
            'rho_in': rho_in,
            'dP': P_in_bar - P_out_bar,
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
            'phi_op': 0.0,
            'rho_in': 0.0,
            'dP': P_in_bar - P_out_bar,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    A_mm2 = float(params.get('A_orifice', 3.14))   # mm²
    if A_mm2 <= 0 or A_mm2 > 100:
        issues.append({'key': 'A_orifice',
                       'msg': f'A_orifice={A_mm2:.2f}mm² — 보통 1~30 mm²'})
    elif A_mm2 < 0.1:
        issues.append({'key': 'A_orifice',
                       'msg': f'A_orifice={A_mm2:.2e}mm² 너무 작음 — 단위가 mm²로 변경됨 (옛 m² 값이면 ×1e6 필요)'})
    Cv_rated = float(params.get('Cv_rated', 0.7))
    if Cv_rated < 0.4 or Cv_rated > 0.95:
        issues.append({'key': 'Cv_rated',
                       'msg': f'Cv_rated={Cv_rated} — 0.6~0.8 권장 (R290 EEV)'})
    c0 = float(params.get('c0', 0.0))
    c1 = float(params.get('c1', 0.5))
    c2 = float(params.get('c2', 0.3))
    c3 = float(params.get('c3', 0.2))
    phi_at_full = c0 + c1 + c2 + c3
    if phi_at_full < 0.8 or phi_at_full > 1.2:
        issues.append({'key': 'curve',
                       'msg': f'Φ(1.0) = {phi_at_full:.3f} — fully open에서 1.0 가까이 권장'})
    if c0 < -0.05 or c0 > 0.1:
        issues.append({'key': 'c0',
                       'msg': f'c0={c0} — closed에서 ṁ≈0이 되려면 0 권장'})
    return issues
