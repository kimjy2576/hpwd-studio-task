"""
EEV — Electronic Expansion Valve (L1 Off-design / Simple)
═══════════════════════════════════════════════════════════════════════
간단한 isenthalpic 팽창 모델 + Cd × A_throat 기반 mass flow.

물리:
  • Isenthalpic: h_out = h_in (단열·정상상태 expansion 가정)
  • Mass flow: m_dot = Cd × A_throat × √(2 × ρ_in × (P_in - P_out))
    - Cd: discharge coefficient (보통 0.5~0.8, R290 응축기 출구 기준 0.65 평균)
    - A_throat: orifice 단면적 (m²) — opening % × A_max
    - ρ_in: 입구 밀도 (subcool liquid → 보통 500~600 kg/m³ for R290)
    - ΔP: P_cond - P_evap

모드 (mode 파라미터):
  • 'control'  — opening % 입력 → m_dot 출력 (제어 시뮬)
  • 'measure'  — m_dot 입력 → opening % 역산 (calibration)

Choke 처리:
  L1에서는 incompressible 가정만 — 실제로는 critical pressure ratio 넘어가면
  flashing/choke가 일어나지만 L2/L3에서 처리. L1은 충분 (가정상 응축기 후).

R290 default Cd:
  • 학계 보고: 0.6~0.7 범위
  • 일반 EEV (Danfoss/Saginomiya): 0.65 ± 0.05
"""

import math
import CoolProp.CoolProp as CP


FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']
MODES = ['control', 'measure']


modelDescription = {
    'typeNo': 130,
    'name': 'EEV (Off-design)',
    'category': 'refrigerant',
    'modelType': 'off-design',
    'fidelity': 0.4,
    'description': 'Simple isenthalpic EEV — Cd × A_throat × √(2ρΔP). control/measure 모드.',
    'backend': 'python',
    'variables': [
        # ═══════ Material ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # ═══════ Operating mode ═══════
        {'name': 'mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'control', 'unit': '-', 'options': MODES,
         'description': "control: opening→m_dot / measure: m_dot→opening 역산"},

        # ═══════ Geometry ═══════
        {'name': 'A_max', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 1.5e-6, 'unit': 'm²',
         'description': 'Full-open orifice 단면적 (R290 EEV: 1~3 mm² 일반)'},
        {'name': 'opening_min', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 5.0, 'unit': '%',
         'description': 'Minimum opening % (0% 닫혔다고 표시되더라도 누설 있음)'},

        # ═══════ Fitting ═══════
        {'name': 'Cd', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.65, 'unit': '-',
         'description': 'Discharge coefficient (R290 EEV 표준: 0.6~0.7)'},

        # ═══════ Inputs ═══════
        {'name': 'P_in', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '입구 압력 (응축기 후, 보통 14~20 bar for R290)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '입구 비엔탈피 (응축기 출구, subcooled liquid)'},
        {'name': 'P_out', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '출구 압력 (증발기, 보통 4~7 bar for R290)'},
        # control mode 입력
        {'name': 'opening', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '(control mode) Opening 0~100%'},
        # measure mode 입력
        {'name': 'm_dot_meas', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '(measure mode) 측정된 mass flow → opening 역산'},

        # ═══════ Outputs ═══════
        {'name': 'm_dot_ref', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 mass flow (control mode 시 계산값, measure 시 입력 echo)'},
        {'name': 'opening_calc', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': 'opening % (measure mode 시 역산값, control 시 입력 echo)'},
        {'name': 'h_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '출구 비엔탈피 (= h_in, isenthalpic)'},
        {'name': 'T_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '출구 온도 (보통 T_evap)'},
        {'name': 'x_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '출구 quality (보통 0.1~0.3)'},
        {'name': 'rho_in', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '입구 밀도 (계산 진단)'},
        {'name': 'dP', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'P_in - P_out'},
        {'name': 'A_throat', 'causality': 'output', 'type': 'Real',
         'unit': 'mm²', 'description': '실제 orifice 단면적 (opening 비례)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    # ═══════ Parameters ═══════
    fluid = params.get('fluid', 'R290')
    mode = params.get('mode', 'control')
    A_max = float(params.get('A_max', 1.5e-6))
    opening_min = float(params.get('opening_min', 5.0))
    Cd = float(params.get('Cd', 0.65))

    # ═══════ Inputs ═══════
    P_in_bar = float(input.get('P_in', 17.0))
    h_in_kjkg = float(input.get('h_in', 280.0))   # subcool liquid R290 ~280 kJ/kg
    P_out_bar = float(input.get('P_out', 5.84))
    opening_pct = float(input.get('opening', 50.0))
    m_dot_meas = float(input.get('m_dot_meas', 0.012))

    if P_in_bar <= 0 or P_out_bar <= 0:
        raise ValueError(f"압력 0 이하: P_in={P_in_bar}, P_out={P_out_bar}")
    if P_out_bar >= P_in_bar:
        # P_out ≥ P_in이면 expansion 안 일어남 → 0 mass flow
        return _zero_output(P_in_bar, P_out_bar, h_in_kjkg, fluid, mode, opening_pct)

    P_in_Pa = P_in_bar * 1e5
    P_out_Pa = P_out_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0

    # ═══════ 입구 밀도 (CoolProp) ═══════
    try:
        # h_in이 saturated liquid보다 작으면 subcooled
        rho_in = CP.PropsSI('D', 'P', P_in_Pa, 'H', h_in_J, fluid)
    except Exception:
        # Fallback: liquid R290 ~580 kg/m³
        rho_in = 580.0 if fluid == 'R290' else 1100.0

    # ═══════ Mode-specific 계산 ═══════
    dP_Pa = P_in_Pa - P_out_Pa

    if mode == 'control':
        # opening → m_dot
        opening_clamped = max(opening_min, min(100.0, opening_pct))
        opening_frac = opening_clamped / 100.0
        A_throat = opening_frac * A_max
        m_dot_ref = Cd * A_throat * math.sqrt(2.0 * rho_in * dP_Pa)
        opening_calc = opening_clamped
    else:  # 'measure'
        # m_dot → opening 역산
        if m_dot_meas <= 0 or rho_in <= 0:
            opening_calc = 0.0
            A_throat = 0.0
            m_dot_ref = 0.0
        else:
            denom = Cd * A_max * math.sqrt(2.0 * rho_in * dP_Pa)
            if denom > 0:
                opening_frac = min(1.0, m_dot_meas / denom)
                opening_calc = max(opening_min, opening_frac * 100.0)
                A_throat = opening_frac * A_max
                m_dot_ref = m_dot_meas  # echo
            else:
                opening_calc = 0.0
                A_throat = 0.0
                m_dot_ref = 0.0

    # ═══════ 출구 상태 (isenthalpic) ═══════
    h_out_J = h_in_J  # isenthalpic
    try:
        # P_out에서 h_out으로 quality 계산
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
        T_out_K = CP.PropsSI('T', 'P', P_out_Pa, 'Q', 0.2, fluid) if fluid == 'R290' else 280.0

    return {
        'outputs': {
            'm_dot_ref': m_dot_ref,
            'opening_calc': opening_calc,
            'h_out': h_out_J / 1000.0,
            'T_out': T_out_K - 273.15,
            'x_out': x_out,
            'rho_in': rho_in,
            'dP': (P_in_bar - P_out_bar),
            'A_throat': A_throat * 1e6,  # m² → mm²
        },
        'newState': {},
    }


def _zero_output(P_in_bar, P_out_bar, h_in_kjkg, fluid, mode, opening_pct):
    """ΔP ≤ 0 또는 비정상 케이스."""
    return {
        'outputs': {
            'm_dot_ref': 0.0,
            'opening_calc': opening_pct if mode == 'control' else 0.0,
            'h_out': h_in_kjkg,
            'T_out': float('nan'),
            'x_out': 0.0,
            'rho_in': 0.0,
            'dP': P_in_bar - P_out_bar,
            'A_throat': 0.0,
        },
        'newState': {},
    }


def validate(params):
    issues = []

    Cd = float(params.get('Cd', 0.65))
    if Cd <= 0 or Cd > 1.5:
        issues.append({'key': 'Cd', 'msg': f'Cd={Cd} — 0.5~0.9 권장 (1.0 초과는 비물리)'})
    
    A_max = float(params.get('A_max', 1.5e-6))
    if A_max <= 0:
        issues.append({'key': 'A_max', 'msg': f'A_max={A_max} ≤ 0'})
    
    mode = params.get('mode', 'control')
    if mode not in MODES:
        issues.append({'key': 'mode', 'msg': f'mode는 {MODES} 중'})
    
    opening_min = float(params.get('opening_min', 5.0))
    if opening_min < 0 or opening_min > 30:
        issues.append({'key': 'opening_min', 'msg': f'opening_min={opening_min} — 0~20% 권장'})
    
    return issues
