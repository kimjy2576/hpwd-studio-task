"""
Compressor (AHRI 10-coefficient) — Off-design L2
═══════════════════════════════════════════════════════════════════════
ARI/AHRI Standard 540 polynomial. 압축기 제조사가 제공하는 표준
시험 데이터 형식. 학계/산업 양쪽에서 가전 R&D 표준.

Polynomial 정의:
  Y = C1 + C2·T_e + C3·T_c + C4·T_e² + C5·T_e·T_c + C6·T_c² 
      + C7·T_e³ + C8·T_c·T_e² + C9·T_e·T_c² + C10·T_c³
  
  Y는 ṁ_ref [kg/h] 또는 W_elec [W].
  T_e [°C] = 증발 포화 온도, T_c [°C] = 응축 포화 온도.
  
  → 두 set의 10개 계수 (총 20개) — 질량유량용 + 전력용

가변속 (RPM):
  RPM 보정 계수 method — 1 set의 10-coef + (N/N_rated) 비례 보정.
  ṁ(N) = ṁ_AHRI × (N / N_rated)
  W(N) = W_AHRI × (N / N_rated) ^ alpha_W   (alpha_W ~ 1)

인터페이스:
  Inputs: P_suc[bar], T_suc[°C], P_dis[bar], N[rpm]
  → 내부에서 T_e = T_sat(P_suc), T_c = T_sat(P_dis) 변환 (CoolProp)
  
Default 계수:
  R290 ~10cc 가전 reciprocating의 published 추정값.
  실제 사내 압축기와는 다를 수 있음 — Properties에서 교체 가능.

Reference:
  ANSI/AHRI Standard 540-2020, "Performance Rating of Positive
  Displacement Refrigerant Compressors and Compressor Units"
"""

import math
import json
import CoolProp.CoolProp as CP

FLUIDS = ['R290']

# ════════ Default 10-coef (R290 ~10cc, 가전 reciprocating) ════════
# Winandy 결과를 grid 평가하여 회귀로 fitting (T_e -15~15°C × T_c 30~70°C, 63 points).
# RMSE: ṁ 0.06%, W_elec 5.1%. 두 모델이 같은 압축기를 표현하도록 동기화.
# 사내 시험 데이터 받으면 교체 권장.
DEFAULT_M_COEF = [
    # ṁ [kg/h] = C1 + C2·Te + ... + C10·Tc³
    +1.584115e+01,    # C1
    +4.950100e-01,    # C2
    -2.289228e-02,    # C3
    +5.213752e-03,    # C4
    +5.696390e-04,    # C5
    -1.838950e-04,    # C6
    +2.544573e-05,    # C7
    +1.200546e-05,    # C8
    -5.465480e-06,    # C9
    -1.224724e-06,    # C10
]
DEFAULT_W_COEF = [
    # W_elec [W]
    +2.207072e+02,    # D1
    +5.981247e+01,    # D2
    -3.230793e+00,    # D3
    +2.018269e+00,    # D4
    -2.429011e+00,    # D5
    +1.463795e-01,    # D6
    +1.191119e-02,    # D7
    -3.784984e-02,    # D8
    +1.995116e-02,    # D9
    +8.855172e-04,    # D10
]


def _ahri_poly(coefs, T_e, T_c):
    """AHRI 540 polynomial 평가."""
    if len(coefs) != 10:
        raise ValueError(f"AHRI coef는 10개여야 함 (받은 길이: {len(coefs)})")
    C = coefs
    Te, Tc = T_e, T_c
    return (C[0]
            + C[1]*Te + C[2]*Tc
            + C[3]*Te**2 + C[4]*Te*Tc + C[5]*Tc**2
            + C[6]*Te**3 + C[7]*Tc*Te**2 + C[8]*Te*Tc**2 + C[9]*Tc**3)


def _parse_coef_input(raw, default):
    """Properties UI에서 들어온 계수 입력을 list로 변환.
    JSON 문자열, list, 빈 값 모두 처리."""
    if raw is None or raw == '' or raw == 'default':
        return default
    if isinstance(raw, list) and len(raw) == 10:
        return [float(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) == 10:
                return [float(x) for x in parsed]
        except Exception:
            pass
    return default


modelDescription = {
    'typeNo': 102,
    'name': 'Compressor (AHRI)',
    'category': 'refrigerant',
    'modelType': 'off-design',
    'fidelity': 0.9,
    'description': 'AHRI 540 10-coefficient polynomial. 가전 R&D 표준.',
    'backend': 'python',
    'variables': [
        # ─── Parameters: 일반 ───
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'N_rated', 'causality': 'parameter', 'type': 'Real',
         'start': 3000.0, 'unit': 'rpm',
         'description': 'AHRI 시험 정격 회전수'},
        {'name': 'SH_ref', 'causality': 'parameter', 'type': 'Real',
         'start': 5.0, 'unit': 'K',
         'description': 'AHRI 시험 흡입 과열도 (정보용 — 보정 안 함)'},
        {'name': 'SC_ref', 'causality': 'parameter', 'type': 'Real',
         'start': 0.0, 'unit': 'K',
         'description': 'AHRI 시험 과냉도 (정보용)'},
        {'name': 'eta_motor', 'causality': 'parameter', 'type': 'Real',
         'start': 0.92, 'unit': '-',
         'description': '모터 효율 (W_shaft 추정 — AHRI W는 이미 포함)'},
        # ─── Parameters: AHRI coefficients ───
        # JSON 문자열 또는 'default' 입력. UI는 textarea 또는 textbox 사용.
        {'name': 'm_coef', 'causality': 'parameter', 'type': 'String',
         'start': 'default', 'unit': '-',
         'description': 'ṁ 10-coef (JSON list 또는 default). 단위: kg/h'},
        {'name': 'w_coef', 'causality': 'parameter', 'type': 'String',
         'start': 'default', 'unit': '-',
         'description': 'W_elec 10-coef (JSON list 또는 default). 단위: W'},
        # ─── Parameters: RPM 보정 ───
        {'name': 'alpha_W_rpm', 'causality': 'parameter', 'type': 'Real',
         'start': 1.0, 'unit': '-',
         'description': 'W_elec의 N 의존성 (W ∝ (N/N_rated)^α). 1.0=선형, 0.9~1.1 일반'},

        # ─── Inputs ───
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
        {'name': 'W_elec', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '전기 입력 (RPM 보정 후)'},
        {'name': 'W_shaft', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '축 일 (W_elec × η_motor)'},
        {'name': 'T_dis', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '토출 온도'},
        {'name': 'h_dis', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '토출 비엔탈피'},
        {'name': 'eta_is', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '추정 등엔트로피 효율 (정보용)'},
        {'name': 'T_e', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '증발 포화 온도 (P_suc 기준)'},
        {'name': 'T_c', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '응축 포화 온도 (P_dis 기준)'},
        {'name': 'pi_ratio', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '압력비 P_dis/P_suc'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    """AHRI polynomial 한 번 평가.
    1. P_suc, P_dis → T_e, T_c (CoolProp 포화 변환)
    2. AHRI poly로 ṁ, W 산정
    3. RPM 보정 (N/N_rated)
    4. 토출 엔탈피/온도 (CoolProp)
    """

    # ── Parameters ──
    fluid       = params.get('fluid', 'R290')
    N_rated     = float(params.get('N_rated', 3000.0))
    eta_motor   = float(params.get('eta_motor', 0.92))
    m_coef      = _parse_coef_input(params.get('m_coef'), DEFAULT_M_COEF)
    w_coef      = _parse_coef_input(params.get('w_coef'), DEFAULT_W_COEF)
    alpha_W_rpm = float(params.get('alpha_W_rpm', 1.0))

    # ── Inputs ──
    P_suc_bar = float(input.get('P_suc', 5.0))
    T_suc_C   = float(input.get('T_suc', 5.0))
    P_dis_bar = float(input.get('P_dis', 18.0))
    N_rpm     = float(input.get('N', 3000.0))

    # ── 입력 검증 ──
    if P_suc_bar <= 0 or P_dis_bar <= 0:
        raise ValueError(f"압력은 양수 (P_suc={P_suc_bar}, P_dis={P_dis_bar})")
    if P_dis_bar <= P_suc_bar:
        raise ValueError(f"P_dis ({P_dis_bar}) <= P_suc ({P_suc_bar})")
    if N_rpm <= 0:
        raise ValueError(f"N은 양수 (받은 값: {N_rpm})")
    if N_rated <= 0:
        raise ValueError(f"N_rated는 양수 (받은 값: {N_rated})")

    P_suc_Pa = P_suc_bar * 1e5
    P_dis_Pa = P_dis_bar * 1e5

    # ── 1. T_e, T_c (CoolProp 포화 변환) ──
    try:
        T_e_K = CP.PropsSI('T', 'P', P_suc_Pa, 'Q', 1, fluid)  # 포화증기
        T_c_K = CP.PropsSI('T', 'P', P_dis_Pa, 'Q', 0, fluid)  # 포화액
        T_e_C = T_e_K - 273.15
        T_c_C = T_c_K - 273.15
    except Exception as e:
        raise ValueError(f"포화 온도 계산 실패 (P_suc={P_suc_bar}bar, P_dis={P_dis_bar}bar, fluid={fluid}): {e}")

    # ── 2. AHRI polynomial 평가 ──
    m_dot_kgh = _ahri_poly(m_coef, T_e_C, T_c_C)
    W_elec_W_ref = _ahri_poly(w_coef, T_e_C, T_c_C)

    # 음수 방지 (AHRI poly가 외삽에서 음수 낼 수 있음)
    m_dot_kgh = max(0.0, m_dot_kgh)
    W_elec_W_ref = max(0.0, W_elec_W_ref)

    # ── 3. RPM 보정 ──
    rpm_ratio = N_rpm / N_rated
    m_dot_kgs_corr = (m_dot_kgh / 3600.0) * rpm_ratio       # 질량유량은 선형
    W_elec_W_corr  = W_elec_W_ref * (rpm_ratio ** alpha_W_rpm)

    # ── 4. 토출 엔탈피 + 온도 (energy balance) ──
    # AHRI W_elec은 모터+기계+압축 전부. 즉 모터 입력 → 가스가 받는 일은
    # W_shaft = W_elec × η_motor (모터 손실 제외)
    # 일부는 외부 손실로 빠지지만 단순 모델은 모두 가스로:
    # h_dis = h_suc + W_shaft / m_dot
    
    if m_dot_kgs_corr < 1e-9:
        # 거의 0 유량 — 토출 정의 안 됨
        T_dis_C = T_suc_C
        h_dis_J = 0.0
        eta_is = 0.0
        h_suc_J = 0.0
    else:
        T_suc_K = T_suc_C + 273.15
        try:
            h_suc_J = CP.PropsSI('H', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
            s_suc_J = CP.PropsSI('S', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        except Exception as e:
            raise ValueError(f"흡입 상태 계산 실패: {e}")

        W_shaft_W = W_elec_W_corr * eta_motor
        h_dis_J = h_suc_J + W_shaft_W / m_dot_kgs_corr

        try:
            T_dis_K = CP.PropsSI('T', 'P', P_dis_Pa, 'H', h_dis_J, fluid)
            T_dis_C = T_dis_K - 273.15
            # 등엔트로피 효율 추정 (정보용)
            h_dis_is_J = CP.PropsSI('H', 'P', P_dis_Pa, 'S', s_suc_J, fluid)
            w_is = h_dis_is_J - h_suc_J
            w_actual = h_dis_J - h_suc_J
            eta_is = max(0.0, min(1.0, w_is / w_actual)) if abs(w_actual) > 1e-3 else 0.0
        except Exception:
            T_dis_C = T_suc_C + 50  # fallback
            eta_is = 0.0

    W_shaft_W_out = W_elec_W_corr * eta_motor
    pi_ratio = P_dis_bar / P_suc_bar

    outputs = {
        'm_dot':    m_dot_kgs_corr,
        'W_elec':   W_elec_W_corr,
        'W_shaft':  W_shaft_W_out,
        'T_dis':    T_dis_C,
        'h_dis':    h_dis_J / 1000.0 if m_dot_kgs_corr > 1e-9 else 0.0,
        'eta_is':   eta_is,
        'T_e':      T_e_C,
        'T_c':      T_c_C,
        'pi_ratio': pi_ratio,
    }

    return {'outputs': outputs, 'newState': state}


def validate(params):
    errors = []
    fluid = params.get('fluid')
    if fluid not in FLUIDS:
        errors.append({'key': 'fluid', 'msg': f'fluid는 {FLUIDS} 중 하나'})

    for key, lo, hi in [
        ('N_rated', 100, 10000),
        ('eta_motor', 0.1, 1.0),
        ('alpha_W_rpm', 0.5, 1.5),
    ]:
        v = params.get(key)
        if v is None: continue
        if not (lo <= v <= hi):
            errors.append({'key': key, 'msg': f'{key} 범위 벗어남: {v} (허용 {lo}~{hi})'})

    # coef 입력 검증
    for key in ['m_coef', 'w_coef']:
        raw = params.get(key)
        if raw is None or raw == '' or raw == 'default':
            continue
        if isinstance(raw, list):
            if len(raw) != 10:
                errors.append({'key': key, 'msg': f'{key}는 10개 값 필요 (받음: {len(raw)})'})
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, list) or len(parsed) != 10:
                    errors.append({'key': key, 'msg': f'{key}는 10개 숫자 list (예: [c1, c2, ..., c10])'})
            except Exception:
                errors.append({'key': key, 'msg': f'{key} 파싱 실패. JSON list 또는 "default"'})
    return errors
