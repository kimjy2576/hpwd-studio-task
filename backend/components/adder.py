"""
Adder — 단순 가산기 컴포넌트 (검증용)

목적: Studio ↔ Python 백엔드 통신을 검증하는 가장 단순한 컴포넌트.
외부 라이브러리 의존성 없음 (순수 Python 산수만).

사용 예:
    input  = { 'a': 3, 'b': 5 }
    params = { 'gain': 2.0, 'offset': 1.0 }
    output = { 'sum': 17.0 }   # (3+5) * 2 + 1
"""

# ════════ Model Description (FMI 호환 메타데이터) ════════
modelDescription = {
    'typeNo': 500,
    'name': 'Adder',
    'category': 'math',
    'modelType': 'on-design',
    'fidelity': 1.0,
    'description': '두 입력의 합에 gain을 곱하고 offset을 더하는 단순 가산기 (검증용)',
    'backend': 'python',
    'variables': [
        # Parameters
        {
            'name': 'gain', 'causality': 'parameter', 'type': 'Real',
            'start': 1.0, 'unit': '-', 'min': -100, 'max': 100,
            'description': '출력에 곱하는 이득 (기본 1)',
        },
        {
            'name': 'offset', 'causality': 'parameter', 'type': 'Real',
            'start': 0.0, 'unit': '-', 'min': -1000, 'max': 1000,
            'description': '결과에 더하는 상수 (기본 0)',
        },

        # Inputs
        {
            'name': 'a', 'causality': 'input', 'type': 'Real',
            'unit': '-', 'description': '첫 번째 입력값',
        },
        {
            'name': 'b', 'causality': 'input', 'type': 'Real',
            'unit': '-', 'description': '두 번째 입력값',
        },

        # Outputs
        {
            'name': 'sum', 'causality': 'output', 'type': 'Real',
            'unit': '-', 'description': '(a + b) * gain + offset',
        },

        # States 없음 — 정적 컴포넌트
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
        'canHandleEvents': False,
    },
}


# ════════ State Initialization ════════
def init_state(params):
    """정적 컴포넌트라 빈 dict 반환."""
    return {}


# ════════ Computation ════════
def step(input, params, state, dt):
    """
    한 timestep의 계산.

    Args:
        input  (dict): 다른 컴포넌트의 outputs에서 받은 입력값
        params (dict): 사용자가 Properties에서 설정한 파라미터
        state  (dict): 이전 step의 state (정적 컴포넌트는 빈 dict)
        dt     (float): timestep [s] (정적 컴포넌트는 무시)

    Returns:
        dict: { 'outputs': {...}, 'newState': {...} }
    """
    # 입력값 추출 (안전하게 — 누락 시 0)
    a = float(input.get('a', 0))
    b = float(input.get('b', 0))
    gain = float(params.get('gain', 1.0))
    offset = float(params.get('offset', 0.0))

    # 계산
    sum_val = (a + b) * gain + offset

    return {
        'outputs': {
            'sum': sum_val,
        },
        'newState': state,  # 정적이라 그대로
    }


# ════════ Validation ════════
def validate(params):
    """
    파라미터 sanity 체크.

    Returns:
        list of {'key': str, 'msg': str}
    """
    errors = []
    gain = params.get('gain')
    if gain is None:
        errors.append({'key': 'gain', 'msg': 'gain 파라미터 필요'})
    elif not isinstance(gain, (int, float)):
        errors.append({'key': 'gain', 'msg': 'gain은 숫자여야 함'})
    return errors
