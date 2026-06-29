"""
Compressor (이론 모델) — L1 (first-cut 설계용)
═══════════════════════════════════════════════════════════════
벤더 성능맵 없이 효율 2개(체적·등엔트로피)만 대략 추정해서 도는 압축기.
fidelity ladder의 L1 (AHRI map은 L2, Chamber는 L3).

식 (Modelica HPWD.Comp_Theoretical과 동일):
  ρ_suc   = ρ(P_suc, T_suc)
  s_suc   = s(P_suc, T_suc)
  h_dis,s = h(P_dis, s_suc)                  # 등엔트로피 토출
  ṁ       = η_vol · V_disp · (N/60) · ρ_suc  # 체적효율 기반
  W       = ṁ · (h_dis,s − h_suc) / η_isen   # 소요 동력
  h_dis   = h_suc + (h_dis,s − h_suc) / η_isen

  Inputs:  P_suc[bar], T_suc[°C], P_dis[bar], N[rpm]
  Params:  V_disp[cm³/rev], eta_vol, eta_isen, fluid
  Outputs: m_dot[kg/s], W[W], h_dis[kJ/kg], T_dis[°C], rho_suc, h_dis_s, eta_is, pi_ratio
"""
import CoolProp.CoolProp as CP

FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']


modelDescription = {
    'typeNo': 100,
    'name': 'Compressor (이론)',
    'category': 'refrigerant',
    'modelType': 'L1',
    'fidelity': 0.5,
    'description': '이론 압축기 L1 — 체적효율 + 등엔트로피효율 (벤더맵 불필요, 1차 설계용)',
    'backend': 'python',
    'variables': [
        # ═══════ Parameters ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'V_disp', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 7.5, 'unit': 'cm³',
         'description': '행정체적 (도면 초안에서 대략)'},
        {'name': 'eta_vol', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.88, 'unit': '-',
         'description': '체적효율 (추정 ~0.85)'},
        {'name': 'eta_isen', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.68, 'unit': '-',
         'description': '등엔트로피효율 (추정 ~0.65)'},

        # ═══════ Inputs ═══════
        {'name': 'P_suc', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '흡입 압력 (abs)'},
        {'name': 'T_suc', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '흡입 온도'},
        {'name': 'P_dis', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '토출 압력 (abs)'},
        {'name': 'N', 'causality': 'input', 'type': 'Real',
         'unit': 'rpm', 'description': '회전 속도'},

        # ─── Outputs ───
        {'name': 'm_dot', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'W', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '소요 동력'},
        {'name': 'h_dis', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '토출 비엔탈피'},
        {'name': 'T_dis', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '토출 온도'},
        {'name': 'rho_suc', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/m³', 'description': '흡입 밀도'},
        {'name': 'h_dis_s', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '등엔트로피 토출 엔탈피'},
        {'name': 'pi_ratio', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '압력비 P_dis/P_suc'},
    ],
    'capabilities': {'canDoStep': True, 'canGetDerivatives': False},
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    """이론 압축기 1 step 평가."""
    fluid    = params.get('fluid', 'R290')
    V_disp   = float(params.get('V_disp', 7.5)) * 1e-6   # cm³ → m³
    eta_vol  = float(params.get('eta_vol', 0.88))
    eta_isen = float(params.get('eta_isen', 0.68))

    P_suc_Pa = float(input.get('P_suc', 5.5)) * 1e5
    T_suc_K  = float(input.get('T_suc', 10.0)) + 273.15
    P_dis_Pa = float(input.get('P_dis', 19.0)) * 1e5
    N        = float(input.get('N', 1800.0))

    # 흡입 상태 (P, T) → ρ, s, h
    h_suc = CP.PropsSI('H', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
    rho_suc = CP.PropsSI('D', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
    s_suc = CP.PropsSI('S', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
    # 등엔트로피 토출
    h_dis_s = CP.PropsSI('H', 'P', P_dis_Pa, 'S', s_suc, fluid)

    if N <= 0 or eta_isen <= 0:
        m_dot = 0.0; W = 0.0; h_dis = h_suc
    else:
        m_dot = eta_vol * V_disp * (N / 60.0) * rho_suc
        h_dis = h_suc + (h_dis_s - h_suc) / eta_isen
        W = m_dot * (h_dis_s - h_suc) / eta_isen

    T_dis_K = CP.PropsSI('T', 'P', P_dis_Pa, 'H', h_dis, fluid)

    outputs = {
        'm_dot':    m_dot,
        'W':        W,
        'h_dis':    h_dis / 1000.0,
        'T_dis':    T_dis_K - 273.15,
        'rho_suc':  rho_suc,
        'h_dis_s':  h_dis_s / 1000.0,
        'pi_ratio': P_dis_Pa / P_suc_Pa if P_suc_Pa > 0 else 0.0,
    }
    return {'outputs': outputs, 'newState': state}


def validate(params):
    issues = []
    for k, lo, hi in [('eta_vol', 0.3, 1.0), ('eta_isen', 0.3, 1.0)]:
        try:
            v = float(params.get(k))
            if not (lo <= v <= hi):
                issues.append({'key': k, 'msg': f'{k}는 {lo}~{hi} 범위 권장 (받은 값: {v})'})
        except (TypeError, ValueError):
            pass
    try:
        if float(params.get('V_disp', 7.5)) <= 0:
            issues.append({'key': 'V_disp', 'msg': 'V_disp는 양수여야 함'})
    except (TypeError, ValueError):
        pass
    return issues
