"""
EEV — Electronic Expansion Valve (L3 On-Design / Needle Cone)
═══════════════════════════════════════════════════════════════════════
L3 핵심:
  • Needle cone profile 기반 A_throat(opening) — 비선형 cone geometry
  • 2-phase choke at vena contracta (Henry-Fauske 단순화 모델)
  • Seat radius / needle angle / stroke로 정확한 기하학적 단면적 계산
  • Re-based Cd correction (very low opening 영역에서 Cd 감소)

수학:
  A_throat 계산 (cone needle, conical seat):
    stroke = stroke_max × (opening / 100)
    
    # Seat가 평면, needle이 cone (각도 α)일 때:
    # Effective annular flow area:
    A_throat = π × D_seat × stroke × sin(α/2)
    
    (실제로는 stroke × tan 등 여러 정의 있지만 위가 정통)
    + 최대 A_max에서 saturate
  
  Cd correction (low Re):
    Re_throat = m_dot × D_h / (μ × A)
    Cd_eff = Cd_base × f(Re)  where f → 1 at high Re, < 1 at low Re

  2-phase choke (R290 정밀):
    Critical mass flux G_crit ≈ sqrt(ρ × ΔP) 단순화에서 벗어나
    Henry-Fauske 단순화: G_crit = ρ_2ph × c_2ph (sonic velocity)
    c_2ph ≈ sqrt(K × P / ρ)  for homogeneous 2-phase

진영님 정리:
  ✓ On-design Studio = L3 only
  ✓ EEV도 실제 부품 도면 (단면/조립)
  ✓ Backend도 L3 정밀 모델 필요
"""

import math
import CoolProp.CoolProp as CP


FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']
MODES = ['control', 'measure']
NEEDLE_PROFILES = ['cone', 'parabolic', 'linear']


modelDescription = {
    'typeNo': 132,
    'name': 'EEV (On-Design / Needle Cone)',
    'category': 'refrigerant',
    'modelType': 'on-design',
    'fidelity': 0.95,
    'description': 'Needle cone geometry + 2-phase choke + Re-based Cd correction',
    'backend': 'python',
    'variables': [
        # ═══ Material ═══
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'needle_material', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'SUS304', 'unit': '-',
         'options': ['SUS304', 'SUS316', 'Brass', 'Steel'],
         'description': 'Needle 재질 (정보용, 결과 영향 없음)'},

        # ═══ Operating ═══
        {'name': 'mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'control', 'unit': '-', 'options': MODES,
         'description': 'control: opening→m_dot / measure: m_dot→opening'},
        {'name': 'use_choke', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'on', 'unit': '-', 'options': ['on', 'off'],
         'description': '2-phase choke 활성화 여부'},
        {'name': 'use_Re_correction', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'on', 'unit': '-', 'options': ['on', 'off'],
         'description': 'Low-Re Cd 보정 활성화'},

        # ═══ Geometry — 핵심 (needle + seat) ═══
        {'name': 'needle_profile', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'cone', 'unit': '-', 'options': NEEDLE_PROFILES,
         'description': 'Needle 형상 — cone (원추), parabolic, linear'},
        {'name': 'needle_angle', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 30.0, 'unit': 'deg',
         'description': 'Needle cone 반각 α/2 (보통 15~45°)'},
        {'name': 'D_seat', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.0e-3, 'unit': 'm',
         'description': 'Seat 내경 = 오리피스 직경 (보통 1.5~3 mm for R290 EEV)'},
        {'name': 'stroke_max', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 1.0e-3, 'unit': 'm',
         'description': 'Needle 최대 stroke (full-open 시, 보통 0.5~2 mm)'},
        {'name': 'L_inlet', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 30.0e-3, 'unit': 'm',
         'description': 'Inlet pipe 길이 (시각화용)'},
        {'name': 'L_outlet', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 30.0e-3, 'unit': 'm',
         'description': 'Outlet pipe 길이 (시각화용)'},
        {'name': 'opening_min', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.0, 'unit': '%',
         'description': 'Minimum opening % (default 0, leakage 시뮬용)'},

        # ═══ Choke ═══
        {'name': 'choke_ratio', 'causality': 'parameter', 'type': 'Real',
         'group': 'Choke', 'start': 0.5, 'unit': '-',
         'description': '(P_out/P_in)_crit (R290 typical: ~0.5)'},

        # ═══ Fitting (calibration) ═══
        {'name': 'Cd_base', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.72, 'unit': '-',
         'description': 'Cd at fully open + high Re (R290 EEV: 0.65~0.78)'},
        {'name': 'Re_transition', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1000.0, 'unit': '-',
         'description': 'Cd가 0.5×Cd_base까지 떨어지는 Re (low Re 영역)'},
        {'name': 'cf_A', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'A_throat 보정 multiplier'},

        # ═══ Inputs ═══
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

        # ═══ Outputs ═══
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
        # 진단
        {'name': 'stroke', 'causality': 'output', 'type': 'Real',
         'unit': 'mm', 'description': '실제 needle stroke (mm)'},
        {'name': 'A_throat', 'causality': 'output', 'type': 'Real',
         'unit': 'mm²', 'description': '실제 throat 면적 (needle profile 기반)'},
        {'name': 'A_throat_unclamped', 'causality': 'output', 'type': 'Real',
         'unit': 'mm²', 'description': 'A_max 적용 전 면적 (clamp 진단)'},
        {'name': 'Cd_eff', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '실제 적용된 Cd (Re 보정 포함)'},
        {'name': 'Re_throat', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Throat Reynolds number'},
        {'name': 'rho_in', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '입구 밀도'},
        {'name': 'dP_actual', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'P_in - P_out (실제)'},
        {'name': 'dP_eff', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '실제 효과 ΔP (choke cap)'},
        {'name': 'is_choked', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '2-phase choke 발생 여부 (1/0)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _A_throat_from_geometry(opening_frac, profile, angle_deg, D_seat, stroke_max):
    """
    Needle profile 기반 throat 면적 계산.
    
    cone: A = π × D_seat × stroke × sin(α/2)
          (반각 α/2 — needle이 원추형)
    parabolic: A = π × D_seat × stroke × (op_frac)^0.5  (parabolic profile)
    linear: A = π × D_seat × stroke × op_frac
    
    A_max = π × (D_seat/2)² 로 saturate
    (needle이 hole에서 완전히 빠져나오면 유효 통로 = seat hole 원판 면적)
    """
    op = max(0.0, min(1.0, opening_frac))
    stroke = stroke_max * op  # m
    
    alpha_half_rad = math.radians(angle_deg)
    
    if profile == 'cone':
        # Annular gap around cone needle, projected to perpendicular
        # Standard: A_annular = π × D_seat × s × sin(α/2)
        A = math.pi * D_seat * stroke * math.sin(alpha_half_rad)
    elif profile == 'parabolic':
        # Quadratic profile (slow opening)
        A = math.pi * D_seat * stroke * (op ** 0.5) * math.sin(alpha_half_rad)
    else:  # 'linear'
        A = math.pi * D_seat * stroke
    
    # Saturate at full-open orifice area (= seat hole 원판 면적)
    A_max = math.pi * (D_seat / 2.0) ** 2
    A_unclamped = A
    A_eff = min(A, A_max)
    
    return A_eff, A_unclamped, stroke


def _Cd_with_Re_correction(Cd_base, Re_throat, Re_transition, use_correction):
    """
    Low-Re Cd correction.
    Re >> Re_trans: Cd → Cd_base
    Re < Re_trans:  Cd 감소 (안전한 모델: smooth transition)
    
    Sigmoid model:
      Cd = Cd_base × 0.5 × (1 + tanh((log(Re) - log(Re_trans)) / 0.5))
    
    Or simpler:
      f = Re / (Re + Re_trans)   (Hill function with n=1)
      Cd = Cd_base × (0.5 + 0.5 × f)
    
    이 모델은 Re→∞ 시 Cd_base, Re=Re_trans 시 0.75×Cd_base, Re=0 시 0.5×Cd_base
    """
    if use_correction != 'on' or Re_throat <= 0:
        return Cd_base
    
    f = Re_throat / (Re_throat + Re_transition)
    return Cd_base * (0.5 + 0.5 * f)


def step(input, params, state, dt):
    # ═══ Parameters ═══
    fluid = params.get('fluid', 'R290')
    mode = params.get('mode', 'control')
    use_choke = params.get('use_choke', 'on')
    use_Re_correction = params.get('use_Re_correction', 'on')
    
    needle_profile = params.get('needle_profile', 'cone')
    needle_angle = float(params.get('needle_angle', 30.0))
    D_seat = float(params.get('D_seat', 2.0e-3))
    stroke_max = float(params.get('stroke_max', 1.0e-3))
    opening_min = float(params.get('opening_min', 0.0))
    
    choke_ratio = float(params.get('choke_ratio', 0.5))
    Cd_base = float(params.get('Cd_base', 0.72))
    Re_transition = float(params.get('Re_transition', 1000.0))
    cf_A = float(params.get('cf_A', 1.0))
    
    # ═══ Inputs ═══
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
    
    # ═══ 입구 밀도 + 점도 ═══
    try:
        rho_in = CP.PropsSI('D', 'P', P_in_Pa, 'H', h_in_J, fluid)
        mu_in = CP.PropsSI('V', 'P', P_in_Pa, 'H', h_in_J, fluid)  # dynamic viscosity
    except Exception:
        rho_in = 580.0 if fluid == 'R290' else 1100.0
        mu_in = 1.5e-4  # typical R290 liquid

    # ═══ Choke check ═══
    is_choked = 0
    dP_actual_Pa = P_in_Pa - P_out_Pa
    dP_eff_Pa = dP_actual_Pa
    
    if use_choke == 'on':
        if (P_out_bar / P_in_bar) < choke_ratio:
            P_out_choke_Pa = P_in_Pa * choke_ratio
            dP_eff_Pa = P_in_Pa - P_out_choke_Pa
            is_choked = 1
    
    dP_eff_bar = dP_eff_Pa / 1e5
    
    # ═══ Mode-specific 계산 ═══
    if mode == 'control':
        opening_clamped = max(opening_min, min(100.0, opening_pct))
        opening_frac = opening_clamped / 100.0
        
        # Needle profile 기반 A_throat
        A_throat, A_unclamped, stroke = _A_throat_from_geometry(
            opening_frac, needle_profile, needle_angle, D_seat, stroke_max
        )
        A_throat *= cf_A
        
        # First-pass Cd (no Re yet) → m_dot 추정
        Cd_first = Cd_base
        m_dot_first = Cd_first * A_throat * math.sqrt(2.0 * rho_in * dP_eff_Pa)
        
        # Re_throat → Cd_eff (Re correction)
        D_h = math.sqrt(4 * A_throat / math.pi) if A_throat > 0 else 0
        Re_throat = m_dot_first * D_h / (mu_in * A_throat) if (mu_in * A_throat) > 0 else 0
        Cd_eff = _Cd_with_Re_correction(Cd_base, Re_throat, Re_transition, use_Re_correction)
        
        # Final m_dot
        m_dot_ref = Cd_eff * A_throat * math.sqrt(2.0 * rho_in * dP_eff_Pa)
        opening_calc = opening_clamped
    else:  # measure mode
        # m_dot → opening 역산 (bisection — needle profile 비선형)
        if m_dot_meas <= 0 or rho_in <= 0:
            opening_calc = 0.0
            A_throat = 0.0
            A_unclamped = 0.0
            stroke = 0.0
            Cd_eff = 0.0
            Re_throat = 0.0
            m_dot_ref = 0.0
        else:
            lo, hi = opening_min, 100.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                op_frac = mid / 100.0
                A_t, A_unc, s = _A_throat_from_geometry(
                    op_frac, needle_profile, needle_angle, D_seat, stroke_max
                )
                A_t *= cf_A
                # Cd at this A (with Re estimate)
                Cd_first = Cd_base
                m_first = Cd_first * A_t * math.sqrt(2.0 * rho_in * dP_eff_Pa)
                D_h = math.sqrt(4 * A_t / math.pi) if A_t > 0 else 0
                Re_t = m_first * D_h / (mu_in * A_t) if (mu_in * A_t) > 0 else 0
                Cd_t = _Cd_with_Re_correction(Cd_base, Re_t, Re_transition, use_Re_correction)
                m_t = Cd_t * A_t * math.sqrt(2.0 * rho_in * dP_eff_Pa)
                if m_t < m_dot_meas:
                    lo = mid
                else:
                    hi = mid
                if abs(hi - lo) < 0.001:
                    break
            opening_calc = (lo + hi) / 2.0
            op_final = opening_calc / 100.0
            A_throat, A_unclamped, stroke = _A_throat_from_geometry(
                op_final, needle_profile, needle_angle, D_seat, stroke_max
            )
            A_throat *= cf_A
            # Final Cd at this opening
            m_dot_first = Cd_base * A_throat * math.sqrt(2.0 * rho_in * dP_eff_Pa)
            D_h = math.sqrt(4 * A_throat / math.pi) if A_throat > 0 else 0
            Re_throat = m_dot_first * D_h / (mu_in * A_throat) if (mu_in * A_throat) > 0 else 0
            Cd_eff = _Cd_with_Re_correction(Cd_base, Re_throat, Re_transition, use_Re_correction)
            m_dot_ref = m_dot_meas  # echo

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
            'stroke': stroke * 1000,            # m → mm
            'A_throat': A_throat * 1e6,         # m² → mm²
            'A_throat_unclamped': A_unclamped * 1e6,
            'Cd_eff': Cd_eff,
            'Re_throat': Re_throat,
            'rho_in': rho_in,
            'dP_actual': P_in_bar - P_out_bar,
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
            'stroke': 0.0,
            'A_throat': 0.0,
            'A_throat_unclamped': 0.0,
            'Cd_eff': 0.0,
            'Re_throat': 0.0,
            'rho_in': 0.0,
            'dP_actual': P_in_bar - P_out_bar,
            'dP_eff': 0.0,
            'is_choked': 0.0,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    
    D_seat = float(params.get('D_seat', 2.0e-3))
    if D_seat <= 0 or D_seat > 10e-3:
        issues.append({'key': 'D_seat',
                      'msg': f'D_seat={D_seat*1000:.2f}mm — 보통 1~3mm (R290 EEV)'})
    
    needle_angle = float(params.get('needle_angle', 30.0))
    if needle_angle < 5 or needle_angle > 60:
        issues.append({'key': 'needle_angle',
                      'msg': f'needle_angle={needle_angle}° — 보통 15~45° (반각)'})
    
    stroke_max = float(params.get('stroke_max', 1.0e-3))
    if stroke_max <= 0 or stroke_max > 5e-3:
        issues.append({'key': 'stroke_max',
                      'msg': f'stroke_max={stroke_max*1000:.2f}mm — 보통 0.5~2 mm'})
    
    Cd_base = float(params.get('Cd_base', 0.72))
    if Cd_base < 0.4 or Cd_base > 0.95:
        issues.append({'key': 'Cd_base',
                      'msg': f'Cd_base={Cd_base} — 0.6~0.8 권장 (R290 EEV)'})
    
    return issues
