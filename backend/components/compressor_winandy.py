"""
Compressor (Winandy Semi-empirical) — Winandy/Lebrun 1999/2002 정형
═══════════════════════════════════════════════════════════════════════
학계 표준 semi-empirical compressor 모델. Reciprocating + Scroll 일반.
가변속도(rpm) 지원.

물리 흐름:
  흡입(P_suc, T_suc)
    └─→ 흡입 압력 손실 (dP_su)
    └─→ 흡입 가열 chamber (AU_su × ΔT)         [T_wall과 열교환]
    └─→ 등엔트로피 압축 (P_su2 → rv_in × P_su2)
    └─→ over/under-compression 보정 (P_internal vs P_dis)
    └─→ 토출(h_dis, T_dis)
  
  병렬:
    체적 효율 η_v = V_swept_eff × (1 - rv_in × ((P_dis/P_su2)^(1/n) - 1))
    기계 손실 W_loss = W_loss_const + α × W_shaft
    외부 열손실 Q_loss = AU_loss × (T_wall - T_amb)
    T_wall energy balance (iteration)

파라미터 (9개, literature default for R290 reciprocating ~10cc):
  V_disp        : cm³        # 행정 체적
  AU_loss       : W/K        # 외부 열손실 UA
  AU_su         : W/K        # 흡입 가열 UA
  dP_su         : -          # 흡입 압력 손실 비율 (P_suc 대비)
  V_swept_eff   : -          # 체적 효율 baseline
  rv_in         : -          # 내부 체적비 (built-in volume ratio)
  W_loss_const  : W          # 정수 기계 손실
  alpha_loss    : -          # 비례 기계 손실
  eta_motor     : -          # 모터 효율

Reference:
  Winandy E., Saavedra C., Lebrun J.,
  "Simplified modelling of an open-type reciprocating compressor",
  International Journal of Thermal Sciences, 41 (2002) 183-192
"""

import math
import CoolProp.CoolProp as CP

FLUIDS = ['R290']
COMPRESSOR_TYPES = ['reciprocating', 'scroll']


modelDescription = {
    'typeNo': 100,
    'name': 'Compressor (Winandy)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.7,
    'description': 'Winandy/Lebrun 정형 — 흡입가열 + 등엔트로피 + over/under-comp + 외부 열손실',
    'backend': 'python',
    'variables': [
        # ─── Parameters: 일반 ───
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'comp_type', 'causality': 'parameter', 'type': 'String',
         'start': 'reciprocating', 'unit': '-', 'options': COMPRESSOR_TYPES,
         'description': '압축기 형태 (정보용 — 알고리즘은 동일)'},
        {'name': 'T_amb', 'causality': 'parameter', 'type': 'Real',
         'start': 25.0, 'unit': '°C',
         'description': '주변 공기 온도 (외부 열손실 기준)'},

        # ─── Parameters: Winandy 9개 (literature default for R290 ~10cc reciprocating) ───
        {'name': 'V_disp', 'causality': 'parameter', 'type': 'Real',
         'start': 10.0, 'unit': 'cm³',
         'description': '행정 체적 (배제 용적)'},
        {'name': 'AU_loss', 'causality': 'parameter', 'type': 'Real',
         'start': 5.0, 'unit': 'W/K',
         'description': '외부 열손실 UA (cabinet → 주변 공기)'},
        {'name': 'AU_su', 'causality': 'parameter', 'type': 'Real',
         'start': 3.0, 'unit': 'W/K',
         'description': '흡입 가열 UA (T_wall → 흡입 가스). 소형 가전 ~3, 대형 ~30'},
        {'name': 'dP_su', 'causality': 'parameter', 'type': 'Real',
         'start': 0.05, 'unit': '-',
         'description': '흡입 압력 손실 비율 (0=없음, 0.05=5%)'},
        {'name': 'V_swept_eff', 'causality': 'parameter', 'type': 'Real',
         'start': 0.95, 'unit': '-',
         'description': '체적 효율 baseline (clearance 외 손실)'},
        {'name': 'rv_in', 'causality': 'parameter', 'type': 'Real',
         'start': 2.5, 'unit': '-',
         'description': '내부 체적비 (built-in volume ratio)'},
        {'name': 'W_loss_const', 'causality': 'parameter', 'type': 'Real',
         'start': 30.0, 'unit': 'W',
         'description': '정수 기계 손실'},
        {'name': 'alpha_loss', 'causality': 'parameter', 'type': 'Real',
         'start': 0.1, 'unit': '-',
         'description': '비례 기계 손실 계수 (W_shaft에 곱)'},
        {'name': 'eta_motor', 'causality': 'parameter', 'type': 'Real',
         'start': 0.92, 'unit': '-',
         'description': '모터 효율'},

        # ─── Inputs ───
        {'name': 'P_suc', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '흡입 압력 (abs)'},
        {'name': 'T_suc', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '흡입 온도 (compressor shell 입구)'},
        {'name': 'P_dis', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '토출 압력 (abs)'},
        {'name': 'N', 'causality': 'input', 'type': 'Real',
         'unit': 'rpm', 'description': '회전 속도'},

        # ─── Outputs ───
        {'name': 'm_dot', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_dis', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '토출 온도'},
        {'name': 'h_dis', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '토출 비엔탈피'},
        {'name': 'W_elec', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '전기 입력 (모터 + 기계 손실 포함)'},
        {'name': 'W_shaft', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '축 일 (기계 손실 제외)'},
        {'name': 'Q_loss', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '외부 열손실 (cabinet → 주변)'},
        {'name': 'eta_is', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '등엔트로피 효율'},
        {'name': 'eta_v', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '체적 효율'},
        {'name': 'T_wall', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '쉘 벽 온도 (수렴값)'},
        {'name': 'pi_ratio', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '압력비 P_dis/P_suc'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    # T_wall은 첫 step에서 추정 — state로 들고 다님 (warm start)
    return {'T_wall_C': 60.0}


def step(input, params, state, dt):
    """Winandy 정형 한 번 평가. T_wall은 fixed-point iteration."""

    # ── Parameters ──
    fluid     = params.get('fluid', 'R290')
    T_amb_C   = float(params.get('T_amb', 25.0))
    V_disp_cm3 = float(params.get('V_disp', 10.0))
    AU_loss   = float(params.get('AU_loss', 5.0))
    AU_su     = float(params.get('AU_su', 3.0))
    dP_su     = float(params.get('dP_su', 0.05))
    V_se      = float(params.get('V_swept_eff', 0.95))
    rv_in     = float(params.get('rv_in', 2.5))
    W_loss0   = float(params.get('W_loss_const', 30.0))
    alpha     = float(params.get('alpha_loss', 0.1))
    eta_motor = float(params.get('eta_motor', 0.92))

    # ── Inputs ──
    P_suc_bar = float(input.get('P_suc', 5.0))
    T_suc_C   = float(input.get('T_suc', 5.0))
    P_dis_bar = float(input.get('P_dis', 18.0))
    N_rpm     = float(input.get('N', 3000.0))

    # ── 입력 검증 ──
    if P_suc_bar <= 0 or P_dis_bar <= 0:
        raise ValueError(f"압력은 양수여야 함 (P_suc={P_suc_bar}, P_dis={P_dis_bar})")
    if P_dis_bar <= P_suc_bar:
        raise ValueError(f"P_dis ({P_dis_bar}) <= P_suc ({P_suc_bar}). 압축기는 압력을 올려야 함.")
    if N_rpm <= 0:
        raise ValueError(f"N은 양수 (rpm > 0). 받은 값: {N_rpm}")
    if T_suc_C < -100 or T_suc_C > 200:
        raise ValueError(f"T_suc 범위 벗어남: {T_suc_C}°C")

    # ── 단위 변환 ──
    P_suc_Pa = P_suc_bar * 1e5
    P_dis_Pa = P_dis_bar * 1e5
    T_suc_K  = T_suc_C + 273.15
    T_amb_K  = T_amb_C + 273.15
    V_disp_m3 = V_disp_cm3 * 1e-6
    omega    = N_rpm / 60.0   # rev/s
    pi_ratio = P_dis_bar / P_suc_bar

    # ── 1. 흡입 압력 손실 ──
    P_su2_Pa = P_suc_Pa * (1.0 - dP_su)

    # ── 2. 흡입 chamber 입구 상태 (CoolProp) ──
    # T_suc는 compressor shell 입구. 여기서 T_wall과 열교환 후 cylinder 입구(T_su2)로.
    try:
        h_su1 = CP.PropsSI('H', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        cp_su1 = CP.PropsSI('C', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
    except Exception as e:
        raise ValueError(f"흡입 상태 계산 실패 (P={P_suc_bar}bar, T={T_suc_C}°C): {e}")

    # ── 3. T_wall fixed-point iteration ──
    # T_wall은 외부 열손실과 흡입 가열을 균형시키는 wall 온도.
    # 초기값: state warm start
    T_wall_K = state.get('T_wall_C', 60.0) + 273.15

    eta_is_cur = 0.7   # 초기 추정
    m_dot     = 0.0
    h_su2_J   = h_su1
    T_su2_K   = T_suc_K
    h_dis_J   = h_su1
    W_shaft_W = 0.0

    MAX_ITER = 15
    for it in range(MAX_ITER):
        # 3a. 흡입 가열: NTU-effectiveness 모델
        # cylinder 입구 가스 ~ T_wall (한쪽 단열)
        if AU_su > 0 and m_dot > 1e-9 and cp_su1 > 0:
            NTU = AU_su / (m_dot * cp_su1)
            eps = 1.0 - math.exp(-NTU) if NTU < 50 else 1.0
            T_su2_K = T_suc_K + eps * (T_wall_K - T_suc_K)
        else:
            # 첫 iteration엔 m_dot 모름 — 단순 평균
            T_su2_K = 0.5 * (T_suc_K + T_wall_K)
        try:
            h_su2_J  = CP.PropsSI('H', 'P', P_su2_Pa, 'T', T_su2_K, fluid)
            s_su2_J  = CP.PropsSI('S', 'P', P_su2_Pa, 'T', T_su2_K, fluid)
            rho_su2  = CP.PropsSI('D', 'P', P_su2_Pa, 'T', T_su2_K, fluid)
            v_su2    = 1.0 / rho_su2
        except Exception as e:
            raise ValueError(f"cylinder 입구 상태 계산 실패: {e}")

        # 3b. 체적 효율
        # η_v = V_se × (1 - rv_in × (rp^(1/γ) - 1))의 단순화형
        # Winandy 원형: η_v = V_se × (1 - C × (rp^(1/γ) - 1))
        # 여기선 C ≈ rv_in 비례 사용 (단순화)
        gamma_approx = 1.13  # propane 근사 (실제는 cp/cv 사용 가능)
        try:
            cp_g = CP.PropsSI('C', 'P', P_su2_Pa, 'T', T_su2_K, fluid)
            cv_g = CP.PropsSI('O', 'P', P_su2_Pa, 'T', T_su2_K, fluid)
            if cv_g > 0:
                gamma_approx = cp_g / cv_g
        except Exception:
            pass

        rp_intern = pi_ratio  # 단순화: rp_internal ~ pi_ratio
        try:
            clearance_term = max(0.0, rp_intern ** (1.0 / gamma_approx) - 1.0)
        except Exception:
            clearance_term = 0.0
        eta_v = max(0.05, V_se - 0.05 * clearance_term)  # 보수적 floor

        # 3c. 질량 유량
        m_dot_swept = V_disp_m3 * omega * rho_su2  # 이론 질량유량
        m_dot = eta_v * m_dot_swept

        # 3d. 등엔트로피 토출 (CoolProp)
        try:
            h_dis_is_J = CP.PropsSI('H', 'P', P_dis_Pa, 'S', s_su2_J, fluid)
        except Exception as e:
            raise ValueError(f"등엔트로피 토출 계산 실패: {e}")
        w_is = h_dis_is_J - h_su2_J  # J/kg

        # 3e. over/under-compression 보정 (Winandy scroll 정형)
        # P_internal = P_su2 × rv_in (built-in volume ratio 효과)
        P_internal_Pa = P_su2_Pa * (rv_in ** gamma_approx)
        w_extra = v_su2 * (P_dis_Pa - P_internal_Pa)  # J/kg
        # under-compression: w_extra > 0 (추가 일 필요)
        # over-compression: w_extra < 0 (이미 충분 압축됨, 손실)
        if w_extra < 0:
            w_extra = 0.5 * abs(w_extra)  # over-comp 손실은 절반 정도로

        w_actual = w_is + w_extra  # J/kg
        h_dis_J = h_su2_J + w_actual

        # 3f. 등엔트로피 효율 정의
        if abs(w_actual) > 1e-3:
            eta_is_cur = max(0.05, min(0.99, w_is / w_actual))
        else:
            eta_is_cur = 0.7

        # 3g. Shaft work
        W_shaft_W = m_dot * w_actual  # W

        # 3h. 기계 손실
        W_loss_mech = W_loss0 + alpha * W_shaft_W

        # 3i. 외부 열손실 + wall energy balance
        # Energy in (W_loss_mech + 모터에서 가열 일부) - Q_loss(외부) - Q_su(가스 가열) = 0
        # 단순 모델: Q_loss = AU_loss × (T_wall - T_amb)
        #          Q_su   = AU_su × (T_wall - T_su1)
        Q_loss = AU_loss * (T_wall_K - T_amb_K)
        Q_su   = AU_su * (T_wall_K - T_suc_K)

        # wall energy balance:
        # W_loss_mech (들어옴) = Q_loss (외부로) + Q_su (가스로)
        # → T_wall 새로 풀기:
        #   AU_loss × (T_wall - T_amb) + AU_su × (T_wall - T_suc) = W_loss_mech
        denom = AU_loss + AU_su
        if denom > 1e-6:
            T_wall_new_K = (W_loss_mech + AU_loss * T_amb_K + AU_su * T_suc_K) / denom
        else:
            T_wall_new_K = T_wall_K

        # 3j. 수렴 검사
        dT = abs(T_wall_new_K - T_wall_K)
        # under-relaxation
        T_wall_K = T_wall_K + 0.7 * (T_wall_new_K - T_wall_K)
        if dT < 0.05:
            break

    # 수렴 못 했으면 warning (마지막 값 사용)
    converged = (dT < 0.5)

    # ── 4. 전기 입력 ──
    W_loss_mech = W_loss0 + alpha * W_shaft_W
    W_elec_W = (W_shaft_W + W_loss_mech) / eta_motor

    # ── 5. 외부 열손실 (마지막 값) ──
    Q_loss_W = AU_loss * (T_wall_K - T_amb_K)

    # ── 6. T_dis (CoolProp) ──
    try:
        T_dis_K = CP.PropsSI('T', 'P', P_dis_Pa, 'H', h_dis_J, fluid)
    except Exception:
        T_dis_K = T_su2_K + 50  # fallback

    # ── 새 state ──
    new_state = {'T_wall_C': T_wall_K - 273.15}

    outputs = {
        'm_dot':    m_dot,
        'T_dis':    T_dis_K - 273.15,
        'h_dis':    h_dis_J / 1000,
        'W_elec':   W_elec_W,
        'W_shaft':  W_shaft_W,
        'Q_loss':   Q_loss_W,
        'eta_is':   eta_is_cur,
        'eta_v':    eta_v,
        'T_wall':   T_wall_K - 273.15,
        'pi_ratio': pi_ratio,
    }

    return {'outputs': outputs, 'newState': new_state}


def validate(params):
    errors = []
    fluid = params.get('fluid')
    if fluid not in FLUIDS:
        errors.append({'key': 'fluid', 'msg': f'fluid는 {FLUIDS} 중 하나'})
    for key, lo, hi in [
        ('V_disp', 0.1, 1000),
        ('AU_loss', 0, 1000),
        ('AU_su', 0, 1000),
        ('dP_su', 0, 0.5),
        ('V_swept_eff', 0.1, 1.0),
        ('rv_in', 1.0, 10.0),
        ('W_loss_const', 0, 1000),
        ('alpha_loss', 0, 1.0),
        ('eta_motor', 0.1, 1.0),
    ]:
        v = params.get(key)
        if v is None: continue
        if not (lo <= v <= hi):
            errors.append({'key': key, 'msg': f'{key} 범위 벗어남: {v} (허용 {lo}~{hi})'})
    return errors
