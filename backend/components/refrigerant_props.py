"""
Refrigerant Properties — 냉매 물성치 컴포넌트
═══════════════════════════════════════════════════════════════════════
CoolProp 기반 R290 물성치 조회. 사용자가 두 기준 물성을 직접 선택
(예: T+P, P+Q, P+H 등). 출력은 모든 주요 물성을 한 번에.

단위:
  - 온도:    °C  (CoolProp 내부는 K)
  - 압력:    bar abs (CoolProp 내부는 Pa)
  - 엔탈피:  kJ/kg
  - 엔트로피: kJ/(kg·K)
  - 비열:    kJ/(kg·K)
  - 밀도:    kg/m³
  - 점도:    Pa·s
  - 열전도율: W/(m·K)
  - 건도:    -  (0=포화액, 1=포화증기, 그 사이는 2상)

기준 물성 코드 (CoolProp 표준):
  T  - 온도 [°C]
  P  - 압력 [bar abs]
  Q  - 건도 [-]
  H  - 비엔탈피 [kJ/kg]
  S  - 비엔트로피 [kJ/(kg·K)]
  D  - 밀도 [kg/m³]
  U  - 비내부에너지 [kJ/kg]

사용자가 input1_kind, input2_kind 파라미터로 두 기준을 고르고,
input1_value, input2_value 입력 포트로 실제 값을 넣음.
또는 input1_value를 다른 컴포넌트의 출력에 연결해도 됨.
"""

import CoolProp.CoolProp as CP

FLUID = 'R290'

# ════════ 기준 물성 코드 ════════
# 사용자가 dropdown으로 선택. CoolProp PropsSI의 첫 인자 형식.
INPUT_KINDS = ['T', 'P', 'Q', 'H', 'S', 'D', 'U']

# 사용자 단위 → CoolProp SI 단위 변환
def _to_SI(kind, value):
    if kind == 'T': return value + 273.15        # °C → K
    if kind == 'P': return value * 1e5            # bar → Pa
    if kind == 'H': return value * 1000           # kJ/kg → J/kg
    if kind == 'S': return value * 1000           # kJ/kg·K → J/kg·K
    if kind == 'U': return value * 1000           # kJ/kg → J/kg
    return value                                   # Q, D는 단위 그대로

# CoolProp SI → 사용자 단위 변환
def _from_SI(kind, value):
    if kind == 'T':       return value - 273.15
    if kind == 'P':       return value / 1e5
    if kind in ('H','S','U','CP','CV'): return value / 1000
    return value

# Phase 코드 정수 → 문자열 라벨
_PHASE_LABELS = {
    0: 'liquid',
    1: 'supercritical',
    2: 'supercritical_gas',
    3: 'supercritical_liquid',
    4: 'critical_point',
    5: 'gas',
    6: 'two_phase',
    7: 'unknown',
    8: 'not_imposed',
}


# ════════ Model Description ════════
modelDescription = {
    'typeNo': 110,
    'name': 'Refrigerant Props',
    'category': 'refrigerant',
    'modelType': 'on-design',
    'fidelity': 1.0,
    'description': 'CoolProp 기반 R290 냉매 물성치 (단위: SI + °C + bar)',
    'backend': 'python',
    'variables': [
        # Parameters — 기준 물성 두 개 선택
        {
            'name': 'input1_kind', 'causality': 'parameter', 'type': 'String',
            'start': 'T', 'unit': '-',
            'options': INPUT_KINDS,
            'description': '첫 번째 기준 물성 (T,P,Q,H,S,D,U 중 선택)',
        },
        {
            'name': 'input2_kind', 'causality': 'parameter', 'type': 'String',
            'start': 'P', 'unit': '-',
            'options': INPUT_KINDS,
            'description': '두 번째 기준 물성',
        },
        # Inputs — 두 기준의 실제 값
        {
            'name': 'input1_value', 'causality': 'input', 'type': 'Real',
            'unit': '-', 'description': '첫 번째 기준 값 (단위는 kind에 따름: T[°C], P[bar], H[kJ/kg]...)',
        },
        {
            'name': 'input2_value', 'causality': 'input', 'type': 'Real',
            'unit': '-', 'description': '두 번째 기준 값',
        },
        # Outputs — 주요 물성치 모두
        {'name': 'T', 'causality': 'output', 'type': 'Real', 'unit': '°C',     'description': '온도'},
        {'name': 'P', 'causality': 'output', 'type': 'Real', 'unit': 'bar',    'description': '압력 (abs)'},
        {'name': 'rho','causality': 'output','type': 'Real', 'unit': 'kg/m³',  'description': '밀도'},
        {'name': 'h', 'causality': 'output', 'type': 'Real', 'unit': 'kJ/kg',  'description': '비엔탈피'},
        {'name': 's', 'causality': 'output', 'type': 'Real', 'unit': 'kJ/kg·K','description': '비엔트로피'},
        {'name': 'cp','causality': 'output', 'type': 'Real', 'unit': 'kJ/kg·K','description': '정압비열'},
        {'name': 'cv','causality': 'output', 'type': 'Real', 'unit': 'kJ/kg·K','description': '정적비열'},
        {'name': 'mu','causality': 'output', 'type': 'Real', 'unit': 'Pa·s',   'description': '점도'},
        {'name': 'k', 'causality': 'output', 'type': 'Real', 'unit': 'W/m·K',  'description': '열전도율'},
        {'name': 'Q', 'causality': 'output', 'type': 'Real', 'unit': '-',      'description': '건도 (-1=과냉/과열, 0~1=2상)'},
        {'name': 'T_sat', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '주어진 P의 포화온도'},
        {'name': 'P_sat', 'causality': 'output', 'type': 'Real', 'unit': 'bar','description': '주어진 T의 포화압력'},
        {'name': 'phase','causality': 'output', 'type': 'String','unit': '-',  'description': '상 (liquid/two_phase/gas/...)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
        'canHandleEvents': False,
    },
    'metadata': {
        'fluid': FLUID,
        'units_note': 'SI + Celsius + bar(abs). CoolProp 내부는 K + Pa로 자동 변환.',
    },
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    """주어진 두 기준 물성으로 모든 물성치를 한 번에 조회."""
    k1 = params.get('input1_kind', 'T')
    k2 = params.get('input2_kind', 'P')
    v1 = float(input.get('input1_value', 0))
    v2 = float(input.get('input2_value', 0))

    # 같은 기준 두 번 사용 거부
    if k1 == k2:
        raise ValueError(f"두 기준 물성이 같음 (둘 다 '{k1}'). 서로 다른 종류 선택 필요.")

    # 사용자 단위 → SI
    v1_si = _to_SI(k1, v1)
    v2_si = _to_SI(k2, v2)

    # 모든 출력 물성을 한 번에 조회
    def _props(out_code):
        try:
            return CP.PropsSI(out_code, k1, v1_si, k2, v2_si, FLUID)
        except Exception:
            return float('nan')

    T_K = _props('T')
    P_Pa = _props('P')
    rho = _props('D')
    h_J = _props('H')
    s_J = _props('S')
    cp_J = _props('C')
    cv_J = _props('O')
    mu = _props('V')      # 동점도 (Pa·s)
    k_th = _props('L')    # 열전도율 (W/m·K)
    quality = _props('Q')  # 2상 영역 외에선 -1 (또는 큰 음수)

    # 포화 물성 (단상/2상 구분 없이 시도)
    try:
        T_sat_K = CP.PropsSI('T', 'P', P_Pa, 'Q', 0, FLUID)
        T_sat_C = T_sat_K - 273.15
    except Exception:
        T_sat_C = float('nan')
    try:
        P_sat_Pa = CP.PropsSI('P', 'T', T_K, 'Q', 0, FLUID)
        P_sat_bar = P_sat_Pa / 1e5
    except Exception:
        P_sat_bar = float('nan')

    # Phase
    try:
        phase_int = int(CP.PhaseSI(k1, v1_si, k2, v2_si, FLUID) if False else 7)
        # PhaseSI는 string을 반환 — get_phase_index 사용
        phase_str = CP.PhaseSI(k1, v1_si, k2, v2_si, FLUID)
    except Exception:
        phase_str = 'unknown'

    outputs = {
        'T':     T_K - 273.15 if T_K == T_K else float('nan'),
        'P':     P_Pa / 1e5,
        'rho':   rho,
        'h':     h_J / 1000,
        's':     s_J / 1000,
        'cp':    cp_J / 1000,
        'cv':    cv_J / 1000,
        'mu':    mu,
        'k':     k_th,
        'Q':     quality if -1.5 < quality < 1.5 else -1.0,
        'T_sat': T_sat_C,
        'P_sat': P_sat_bar,
        'phase': phase_str,
    }

    return {'outputs': outputs, 'newState': state}


def validate(params):
    errors = []
    k1 = params.get('input1_kind')
    k2 = params.get('input2_kind')
    if k1 not in INPUT_KINDS:
        errors.append({'key': 'input1_kind', 'msg': f"input1_kind는 {INPUT_KINDS} 중 하나"})
    if k2 not in INPUT_KINDS:
        errors.append({'key': 'input2_kind', 'msg': f"input2_kind는 {INPUT_KINDS} 중 하나"})
    if k1 == k2:
        errors.append({'key': 'input2_kind', 'msg': '두 기준이 같음 — 서로 다른 종류 선택'})
    # 비호환 조합 (CoolProp 한계) — 자주 실수하는 조합 미리 거르기
    bad_pairs = {('Q', 'D'), ('D', 'Q')}  # 건도+밀도는 잘 안 됨
    if (k1, k2) in bad_pairs:
        errors.append({'key': 'input2_kind', 'msg': f'{k1}+{k2} 조합은 CoolProp 안정성 낮음 (T,P,Q,H 추천)'})
    return errors
