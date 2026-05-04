"""
EEV — Electronic Expansion Valve (L2 Semi-empirical / Cv polynomial)
═══════════════════════════════════════════════════════════════════════
L1 (eev_off_design)의 한계 — Cd는 상수 0.65 가정.
실제 EEV는 opening %마다 discharge coefficient가 변동 (작은 opening: 0.5,
큰 opening: 0.75 등).

L2 핵심 차별점:
  • Cd_eff(opening) = c0 + c1·op + c2·op² + c3·op³  (3차 다항식)
    → opening 0~100% 범위에서 변동 표현
    → c0~c3가 fitting 가능 (실험 ṁ 데이터로 보정)
  • Choke 처리: flashing/2-phase choke 시 ṁ 상한
    Critical pressure ratio (P_out/P_in)_crit ≈ 0.5 (R290 기준 학계 보고)
    P_out < (P_out)_crit 이면 ṁ는 ΔP에 더 이상 비례 안 함

═══ 구조 ═══
ṁ = Cd_eff(opening) × A_throat × √(2ρ_in × ΔP_eff)
where:
  ΔP_eff = min(ΔP_actual, ΔP_choke)
  ΔP_choke = (P_in - P_out_crit) where P_out_crit = P_in × (P_out/P_in)_crit
  A_throat = (opening/100) × A_max  (full open 가정)

═══ Calibration 시나리오 ═══
실험에서 (P_in, P_out, opening, ṁ) 측정 → Cv 다항식 계수 4개 fitting
fitting 변수: c0, c1, c2, c3, A_max (5 params 동시 최적화 가능)

═══ Default 값 (R290 EEV) ═══
일반적인 R290 EEV (Danfoss CCM, Saginomiya STF) 학계 보고:
  • opening 0~10%: Cd ≈ 0.4~0.55 (소유량 영역, 고정도 떨어짐)
  • opening 10~50%: Cd ≈ 0.55~0.70 (선형 증가)
  • opening 50~100%: Cd ≈ 0.70~0.78 (포화)
이를 3차 다항식으로 근사:
  Cd(0)=0.50, Cd(0.5)=0.65, Cd(1.0)=0.75
  → c0=0.50, c1=0.40, c2=-0.20, c3=0.05 (예시)

진영님 정리:
  ✓ Semi-empirical — Cv 곡선이 opening의 함수
  ✓ L1과 다른 모듈 (별도 파일)
  ✓ Fitting 가능한 다항식 계수 (calibration 친화)
"""

import math
import CoolProp.CoolProp as CP


FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']
MODES = ['control', 'measure']


modelDescription = {
    'typeNo': 131,
    'name': 'EEV (Moving Boundary / Cv polynomial)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.7,
    'description': 'Cv polynomial Cd(opening) + choke ceiling. fitting 4 다항식 계수 + A_max',
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
         'description': 'Full-open orifice 단면적'},
        {'name': 'opening_min', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 5.0, 'unit': '%',
         'description': 'Minimum opening %'},

        # ═══════ Choke ═══════
        {'name': 'choke_ratio', 'causality': 'parameter', 'type': 'Real',
         'group': 'Operating', 'start': 0.5, 'unit': '-',
         'description': 'Critical pressure ratio (P_out/P_in)_crit (R290: ~0.5, 일반 valve: 0.5~0.6)'},
        {'name': 'use_choke', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'on', 'unit': '-', 'options': ['on', 'off'],
         'description': 'Choke ceiling 사용 여부 (off: L1 모드)'},

        # ═══════ Cv polynomial coefficients ═══════
        # Cd(op) = c0 + c1·op + c2·op² + c3·op³  (op = opening/100, 0~1)
        {'name': 'c0', 'causality': 'parameter', 'type': 'Real',
         'group': 'Cv polynomial', 'start': 0.50, 'unit': '-',
         'description': 'Cd polynomial 상수항 (op=0 기준)'},
        {'name': 'c1', 'causality': 'parameter', 'type': 'Real',
         'group': 'Cv polynomial', 'start': 0.40, 'unit': '-',
         'description': 'Cd polynomial 1차'},
        {'name': 'c2', 'causality': 'parameter', 'type': 'Real',
         'group': 'Cv polynomial', 'start': -0.20, 'unit': '-',
         'description': 'Cd polynomial 2차'},
        {'name': 'c3', 'causality': 'parameter', 'type': 'Real',
         'group': 'Cv polynomial', 'start': 0.05, 'unit': '-',
         'description': 'Cd polynomial 3차'},

        # ═══════ Fitting (calibration multipliers) ═══════
        {'name': 'cf_Cd', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '전체 Cd 보정 multiplier (실험 fitting)'},
        {'name': 'cf_A', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'A_max 보정 multiplier'},

        # ═══════ Inputs ═══════
        {'name': 'P_in', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '입구 압력 (응축기 후)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '입구 비엔탈피 (subcooled liquid)'},
        {'name': 'P_out', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '출구 압력 (증발기)'},
        {'name': 'opening', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '(control mode) Opening 0~100%'},
        {'name': 'm_dot_meas', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '(measure mode) 측정된 ṁ'},

        # ═══════ Outputs ═══════
        {'name': 'm_dot_ref', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 mass flow'},
        {'name': 'opening_calc', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': 'opening (measure 시 역산)'},
        {'name': 'h_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '출구 비엔탈피 (= h_in)'},
        {'name': 'T_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '출구 온도 (T_evap)'},
        {'name': 'x_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '출구 quality'},
        # 진단 outputs
        {'name': 'Cd_eff', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '실제 적용된 Cd_eff(opening)'},
        {'name': 'rho_in', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '입구 밀도'},
        {'name': 'dP', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'P_in - P_out'},
        {'name': 'dP_eff', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '실제 효과 ΔP (choke cap 적용)'},
        {'name': 'is_choked', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Choke 발생 여부 (1=choke, 0=normal)'},
        {'name': 'A_throat', 'causality': 'output', 'type': 'Real',
         'unit': 'mm²', 'description': '실제 orifice 단면적'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _Cd_polynomial(opening_frac, c0, c1, c2, c3):
    """Cd(op) = c0 + c1·op + c2·op² + c3·op³, op = opening/100 (0~1)"""
    op = max(0.0, min(1.0, opening_frac))
    Cd = c0 + c1 * op + c2 * (op ** 2) + c3 * (op ** 3)
    return max(0.05, min(1.0, Cd))  # clamp 0.05~1.0


def step(input, params, state, dt):
    # ═══════ Parameters ═══════
    fluid = params.get('fluid', 'R290')
    mode = params.get('mode', 'control')
    A_max = float(params.get('A_max', 1.5e-6))
    opening_min = float(params.get('opening_min', 5.0))
    choke_ratio = float(params.get('choke_ratio', 0.5))
    use_choke = params.get('use_choke', 'on')
    
    c0 = float(params.get('c0', 0.50))
    c1 = float(params.get('c1', 0.40))
    c2 = float(params.get('c2', -0.20))
    c3 = float(params.get('c3', 0.05))
    
    cf_Cd = float(params.get('cf_Cd', 1.0))
    cf_A = float(params.get('cf_A', 1.0))

    # ═══════ Inputs ═══════
    P_in_bar = float(input.get('P_in', 17.0))
    h_in_kjkg = float(input.get('h_in', 280.0))
    P_out_bar = float(input.get('P_out', 5.84))
    opening_pct = float(input.get('opening', 50.0))
    m_dot_meas = float(input.get('m_dot_meas', 0.012))

    if P_in_bar <= 0 or P_out_bar <= 0:
        raise ValueError(f"압력 0 이하: P_in={P_in_bar}, P_out={P_out_bar}")
    if P_out_bar >= P_in_bar:
        return _zero_output(P_in_bar, P_out_bar, h_in_kjkg, fluid, mode, opening_pct)

    P_in_Pa = P_in_bar * 1e5
    P_out_Pa = P_out_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    A_max_eff = A_max * cf_A

    # ═══════ 입구 밀도 ═══════
    try:
        rho_in = CP.PropsSI('D', 'P', P_in_Pa, 'H', h_in_J, fluid)
    except Exception:
        rho_in = 580.0 if fluid == 'R290' else 1100.0

    # ═══════ Choke check ═══════
    is_choked = 0
    dP_actual_Pa = P_in_Pa - P_out_Pa
    dP_eff_Pa = dP_actual_Pa
    
    if use_choke == 'on':
        # Choke 조건: P_out/P_in < critical_ratio
        if (P_out_bar / P_in_bar) < choke_ratio:
            P_out_choke_Pa = P_in_Pa * choke_ratio
            dP_eff_Pa = P_in_Pa - P_out_choke_Pa
            is_choked = 1
    
    dP_eff_bar = dP_eff_Pa / 1e5

    # ═══════ Mode-specific 계산 ═══════
    if mode == 'control':
        # opening → m_dot
        opening_clamped = max(opening_min, min(100.0, opening_pct))
        opening_frac = opening_clamped / 100.0
        Cd_eff = _Cd_polynomial(opening_frac, c0, c1, c2, c3) * cf_Cd
        A_throat = opening_frac * A_max_eff
        m_dot_ref = Cd_eff * A_throat * math.sqrt(2.0 * rho_in * dP_eff_Pa)
        opening_calc = opening_clamped
    else:  # 'measure'
        # m_dot → opening 역산
        # 다항식 Cd 때문에 Newton iteration 필요 (linear bisection으로 안정)
        if m_dot_meas <= 0 or rho_in <= 0:
            opening_calc = 0.0
            A_throat = 0.0
            Cd_eff = 0.0
            m_dot_ref = 0.0
        else:
            # Bisection: opening 0~100 사이에서 m_dot 일치하는 op 찾기
            lo, hi = opening_min, 100.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                op_frac = mid / 100.0
                Cd_test = _Cd_polynomial(op_frac, c0, c1, c2, c3) * cf_Cd
                A_test = op_frac * A_max_eff
                m_test = Cd_test * A_test * math.sqrt(2.0 * rho_in * dP_eff_Pa)
                if m_test < m_dot_meas:
                    lo = mid
                else:
                    hi = mid
                if abs(hi - lo) < 0.001:
                    break
            opening_calc = (lo + hi) / 2.0
            op_final = opening_calc / 100.0
            Cd_eff = _Cd_polynomial(op_final, c0, c1, c2, c3) * cf_Cd
            A_throat = op_final * A_max_eff
            m_dot_ref = m_dot_meas  # echo

    # ═══════ 출구 상태 (isenthalpic) ═══════
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
        T_out_K = CP.PropsSI('T', 'P', P_out_Pa, 'Q', 0.2, fluid) if fluid == 'R290' else 280.0

    return {
        'outputs': {
            'm_dot_ref': m_dot_ref,
            'opening_calc': opening_calc,
            'h_out': h_out_J / 1000.0,
            'T_out': T_out_K - 273.15,
            'x_out': x_out,
            'Cd_eff': Cd_eff,
            'rho_in': rho_in,
            'dP': P_in_bar - P_out_bar,
            'dP_eff': dP_eff_bar,
            'is_choked': float(is_choked),
            'A_throat': A_throat * 1e6,
        },
        'newState': {},
    }


def _zero_output(P_in_bar, P_out_bar, h_in_kjkg, fluid, mode, opening_pct):
    return {
        'outputs': {
            'm_dot_ref': 0.0,
            'opening_calc': opening_pct if mode == 'control' else 0.0,
            'h_out': h_in_kjkg,
            'T_out': float('nan'),
            'x_out': 0.0,
            'Cd_eff': 0.0,
            'rho_in': 0.0,
            'dP': P_in_bar - P_out_bar,
            'dP_eff': 0.0,
            'is_choked': 0.0,
            'A_throat': 0.0,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    
    A_max = float(params.get('A_max', 1.5e-6))
    if A_max <= 0:
        issues.append({'key': 'A_max', 'msg': f'A_max={A_max} ≤ 0'})
    
    mode = params.get('mode', 'control')
    if mode not in MODES:
        issues.append({'key': 'mode', 'msg': f'mode는 {MODES} 중'})
    
    choke_ratio = float(params.get('choke_ratio', 0.5))
    if choke_ratio < 0.3 or choke_ratio > 0.7:
        issues.append({'key': 'choke_ratio',
                      'msg': f'choke_ratio={choke_ratio} — 0.4~0.6 권장'})
    
    # Cv polynomial은 op=0~1에서 0.05~1.0 범위 안에 들어가야
    c0 = float(params.get('c0', 0.50))
    c1 = float(params.get('c1', 0.40))
    c2 = float(params.get('c2', -0.20))
    c3 = float(params.get('c3', 0.05))
    
    Cd_at_0 = c0
    Cd_at_1 = c0 + c1 + c2 + c3
    if Cd_at_0 < 0.05 or Cd_at_0 > 1.0:
        issues.append({'key': 'c0',
                      'msg': f'Cd(op=0) = c0 = {Cd_at_0:.3f} — 0.3~0.6 권장'})
    if Cd_at_1 < 0.3 or Cd_at_1 > 1.2:
        issues.append({'key': 'c0,c1,c2,c3',
                      'msg': f'Cd(op=1) = {Cd_at_1:.3f} — 0.6~0.85 권장'})
    
    return issues
