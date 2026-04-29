"""
Air Properties — 습공기 물성치 컴포넌트
═══════════════════════════════════════════════════════════════════════
CoolProp HumidAirProp 기반. 사용자가 세 기준 물성을 직접 선택.
습공기는 자유도 3 (T, P, RH/W/T_wb/T_dp 중 하나).

단위:
  - 온도:    °C  (CoolProp 내부는 K)
  - 압력:    bar abs (CoolProp 내부는 Pa)
  - 엔탈피:  kJ/kg dry air (CoolProp 내부는 J/kg dry air)
  - 절대습도: kg water / kg dry air
  - 상대습도: % (CoolProp 내부는 0~1)
  - 비열:    kJ/(kg·K)
  - 밀도:    kg/m³ (습공기 전체 mass / 부피)
  - 점도:    Pa·s
  - 열전도율: W/(m·K)

기준 물성 코드 (CoolProp HumidAirProp 표준):
  T   - 건구온도 [°C]
  P   - 압력 [bar abs]
  R   - 상대습도 [%] (0~100)
  W   - 절대습도 [kg/kg dry air]
  B   - 습구온도 [°C]
  D   - 이슬점 [°C]
  H   - 비엔탈피 [kJ/kg dry air]

3개 기준 필요. 가장 흔한 조합: T+P+R, T+P+W, T+P+B
"""

import CoolProp.HumidAirProp as HA

# ════════ 기준 물성 코드 ════════
INPUT_KINDS = ['T', 'P', 'R', 'W', 'B', 'D', 'H']

# 사용자 단위 → CoolProp SI
def _to_SI(kind, value):
    if kind == 'T': return value + 273.15      # °C → K
    if kind == 'B': return value + 273.15      # 습구도 K
    if kind == 'D': return value + 273.15      # 이슬점도 K
    if kind == 'P': return value * 1e5          # bar → Pa
    if kind == 'R': return value / 100.0        # % → 0~1
    if kind == 'H': return value * 1000         # kJ/kg → J/kg
    return value                                 # W는 그대로


modelDescription = {
    'typeNo': 210,
    'name': 'Air Props',
    'category': 'air',
    'modelType': 'on-design',
    'fidelity': 1.0,
    'description': 'CoolProp HumidAirProp 기반 습공기 물성치. 모든 입력은 parameter (단위: SI + °C + bar + %)',
    'backend': 'python',
    'variables': [
        # Parameters — 모든 입력은 사용자가 직접 지정 (input port 없음)
        {
            'name': 'input1_kind', 'causality': 'parameter', 'type': 'String',
            'start': 'T', 'unit': '-',
            'options': INPUT_KINDS,
            'description': '첫 번째 기준 (T[°C],P[bar],R[%],W[kg/kg],B[°C],D[°C],H[kJ/kg] 중 선택)',
        },
        {
            'name': 'input1_value', 'causality': 'parameter', 'type': 'Real',
            'start': 25.0, 'unit': '-',
            'description': '첫 번째 기준 값',
        },
        {
            'name': 'input2_kind', 'causality': 'parameter', 'type': 'String',
            'start': 'P', 'unit': '-',
            'options': INPUT_KINDS,
            'description': '두 번째 기준',
        },
        {
            'name': 'input2_value', 'causality': 'parameter', 'type': 'Real',
            'start': 1.01325, 'unit': '-',
            'description': '두 번째 기준 값',
        },
        {
            'name': 'input3_kind', 'causality': 'parameter', 'type': 'String',
            'start': 'R', 'unit': '-',
            'options': INPUT_KINDS,
            'description': '세 번째 기준 (습공기는 자유도 3)',
        },
        {
            'name': 'input3_value', 'causality': 'parameter', 'type': 'Real',
            'start': 50.0, 'unit': '-',
            'description': '세 번째 기준 값',
        },
        # Outputs
        {'name': 'T_db','causality': 'output','type': 'Real', 'unit': '°C',     'description': '건구온도'},
        {'name': 'P',   'causality': 'output','type': 'Real', 'unit': 'bar',    'description': '압력 (abs)'},
        {'name': 'RH',  'causality': 'output','type': 'Real', 'unit': '%',      'description': '상대습도'},
        {'name': 'W',   'causality': 'output','type': 'Real', 'unit': 'kg/kg',  'description': '절대습도 (per kg dry air)'},
        {'name': 'T_wb','causality': 'output','type': 'Real', 'unit': '°C',     'description': '습구온도'},
        {'name': 'T_dp','causality': 'output','type': 'Real', 'unit': '°C',     'description': '이슬점'},
        {'name': 'h',   'causality': 'output','type': 'Real', 'unit': 'kJ/kg',  'description': '비엔탈피 (per kg dry air)'},
        {'name': 'rho', 'causality': 'output','type': 'Real', 'unit': 'kg/m³',  'description': '습공기 밀도'},
        {'name': 'cp',  'causality': 'output','type': 'Real', 'unit': 'kJ/kg·K','description': '정압비열 (per kg dry air)'},
        {'name': 'mu',  'causality': 'output','type': 'Real', 'unit': 'Pa·s',   'description': '점도'},
        {'name': 'k',   'causality': 'output','type': 'Real', 'unit': 'W/m·K',  'description': '열전도율'},
        {'name': 'P_w', 'causality': 'output','type': 'Real', 'unit': 'bar',    'description': '수증기 분압'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
        'canHandleEvents': False,
    },
    'metadata': {
        'units_note': 'SI + Celsius + bar(abs) + %. 모든 비율(h, W, cp)은 per kg dry air 기준.',
    },
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    """주어진 세 기준 물성으로 모든 습공기 물성치를 한 번에 조회.
    모든 입력은 params에서 옴 (input port는 사용 안 함)."""
    k1 = params.get('input1_kind', 'T')
    k2 = params.get('input2_kind', 'P')
    k3 = params.get('input3_kind', 'R')
    v1 = float(params.get('input1_value', 25.0))
    v2 = float(params.get('input2_value', 1.01325))
    v3 = float(params.get('input3_value', 50.0))

    # 중복 거부
    kinds = [k1, k2, k3]
    if len(set(kinds)) < 3:
        raise ValueError(f"세 기준이 모두 달라야 함 (입력: {kinds})")

    # 사용자 단위 → SI
    v1_si = _to_SI(k1, v1)
    v2_si = _to_SI(k2, v2)
    v3_si = _to_SI(k3, v3)

    def _props(out_code):
        try:
            return HA.HAPropsSI(out_code, k1, v1_si, k2, v2_si, k3, v3_si)
        except Exception:
            return float('nan')

    T_K   = _props('T')      # K
    P_Pa  = _props('P')      # Pa
    R     = _props('R')      # 0~1
    W     = _props('W')      # kg/kg
    Twb_K = _props('B')      # K
    Tdp_K = _props('D')      # K
    h_J   = _props('H')      # J/kg dry air
    cp_J  = _props('C')      # J/kg·K dry air
    mu    = _props('M')      # Pa·s
    k_th  = _props('K')      # W/m·K
    Vha   = _props('V')      # m³ / kg dry air (specific volume of moist air per dry air)
    Pw_Pa = _props('P_w')    # 수증기 분압

    # 습공기 밀도: (1+W) / V_per_dry_air
    rho = (1 + W) / Vha if Vha and Vha == Vha else float('nan')

    outputs = {
        'T_db':  T_K - 273.15,
        'P':     P_Pa / 1e5,
        'RH':    R * 100.0,
        'W':     W,
        'T_wb':  Twb_K - 273.15,
        'T_dp':  Tdp_K - 273.15,
        'h':     h_J / 1000,
        'rho':   rho,
        'cp':    cp_J / 1000,
        'mu':    mu,
        'k':     k_th,
        'P_w':   Pw_Pa / 1e5,
    }

    return {'outputs': outputs, 'newState': state}


def validate(params):
    errors = []
    k1 = params.get('input1_kind')
    k2 = params.get('input2_kind')
    k3 = params.get('input3_kind')
    for i, k in enumerate([k1, k2, k3], start=1):
        if k not in INPUT_KINDS:
            errors.append({'key': f'input{i}_kind', 'msg': f"input{i}_kind는 {INPUT_KINDS} 중 하나"})
    if len({k1, k2, k3}) < 3:
        errors.append({'key': 'input3_kind', 'msg': '세 기준이 모두 달라야 함'})
    return errors
