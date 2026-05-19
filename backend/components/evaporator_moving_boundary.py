"""
Evaporator (L2 Semi-empirical / Moving Boundary)
═══════════════════════════════════════════════════════════════════════
2-zone (2-phase + SH) ε-NTU with explicit boundary tracking.

Moving Boundary 핵심:
  ζ = L_2ph / L_total = 2-phase zone 길이 비율 (변수)
  
  ζ를 풀어야 함 — energy balance:
    Q_2ph(ζ) + Q_SH(ζ) = ṁ_ref × Δh
    Q_2ph(ζ) = ε_2ph(NTU(ζ)) × Cmin × (T_air_in - T_evap)
    Q_SH(ζ) = ε_SH(NTU(1-ζ)) × Cmin_SH × (T_air_after - T_evap)
  
  Newton iteration on ζ → 보통 5~10 iter 수렴.

Geometry (10개) — Schmidt fin 효율 자동 계산:
  D_o, D_i, L_tube_total, A_o, A_i, V_internal,
  t_fin, P_fin, k_fin, N_tubes, P_t, P_l

Correlation (4개 dropdown):
  refrigerant_2ph: Shah (Commit 1) | Wang-Chang-Chi | Kandlikar | ...
  refrigerant_SH:  Dittus-Boelter (Commit 1) | Gnielinski | ...
  air_side:        Wang-Chi-Chang (Commit 1) | Kim | McQuiston
  fin_efficiency:  Schmidt (Commit 1) | Sector

Wet-coil: Bypass factor (apparatus dew point)
  ASHRAE 표준. dry/wet 영역에서 효율적 처리.

Fitting params (4개) — calibration용 보정 multiplier:
  htc_correction_2ph, htc_correction_SH, htc_correction_air, dP_ref
"""

import math
import CoolProp.CoolProp as CP

from .correlations import boiling, single_phase, air_side, fin_efficiency, pressure_drop

FLUIDS = ['R290']

# Correlation dropdown options (Commit 2에서 더 추가됨)
CORR_2PH_OPTIONS = list(boiling.CORR_REGISTRY.keys())
CORR_SH_OPTIONS  = list(single_phase.CORR_REGISTRY.keys())
CORR_AIR_OPTIONS = list(air_side.CORR_REGISTRY.keys())
CORR_FIN_OPTIONS = list(fin_efficiency.CORR_REGISTRY.keys())
CORR_DP_OPTIONS = list(pressure_drop.TWO_PHASE_REGISTRY.keys())


modelDescription = {
    'typeNo': 121,
    'name': 'Evaporator (Moving Boundary)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.7,
    'description': 'Moving Boundary 2-zone ε-NTU + Schmidt fin + Bypass wet-coil + 4 correlation dropdown',
    'backend': 'python',
    'variables': [
        # ═══════ Material ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # ═══════ Operating ═══════
        {'name': 'wet_coil_mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'auto', 'unit': '-', 'options': ['auto', 'off'],
         'description': 'Wet-coil 처리: auto=bypass factor, off=dry-coil'},

        # ═══════ Geometry — 10개 ═══════
        {'name': 'D_o', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 7.0e-3, 'unit': 'm',
         'description': '튜브 외경'},
        {'name': 'D_i', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 6.5e-3, 'unit': 'm',
         'description': '튜브 내경'},
        {'name': 'L_tube_total', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 10.0, 'unit': 'm',
         'description': '튜브 총 길이 (모든 튜브 합)'},
        {'name': 'N_tubes', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 24.0, 'unit': '-',
         'description': '튜브 본수 (병렬 회로 기준 분포)'},
        {'name': 'N_rows', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.0, 'unit': '-',
         'description': '공기 흐름 방향 row 수'},
        {'name': 'P_t', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 25.0e-3, 'unit': 'm',
         'description': '튜브 transverse pitch (공기 방향 수직)'},
        {'name': 'P_l', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 22.0e-3, 'unit': 'm',
         'description': '튜브 longitudinal pitch (공기 방향)'},
        {'name': 't_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.12e-3, 'unit': 'm',
         'description': '핀 두께'},
        {'name': 'FPI', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 12.0, 'unit': 'fins/inch',
         'description': '핀 밀도 (FPI=12 → P_fin ≈ 2.12mm)'},
        {'name': 'k_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 200.0, 'unit': 'W/(m·K)',
         'description': '핀 열전도율 (Al~200, Cu~390)'},
        {'name': 'A_o_face', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.05, 'unit': 'm²',
         'description': '정면 (face) 면적 — V_max 계산용'},

        # ═══════ Correlation 선택 (dropdown) ═══════
        {'name': 'corr_2ph', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': boiling.DEFAULT, 'unit': '-',
         'options': CORR_2PH_OPTIONS,
         'description': '2-phase boiling correlation'},
        {'name': 'corr_SH', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': single_phase.DEFAULT, 'unit': '-',
         'options': CORR_SH_OPTIONS,
         'description': 'SH (single-phase gas) correlation'},
        {'name': 'corr_air', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': air_side.DEFAULT, 'unit': '-',
         'options': CORR_AIR_OPTIONS,
         'description': '공기측 correlation'},
        {'name': 'corr_fin', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': fin_efficiency.DEFAULT, 'unit': '-',
         'options': CORR_FIN_OPTIONS,
         'description': 'Fin 효율 correlation'},
        {'name': 'corr_dp_2ph', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': pressure_drop.DEFAULT_2PH, 'unit': '-',
         'options': CORR_DP_OPTIONS,
         'description': '2-phase 압력강하 correlation (Acceleration은 항상 포함, Hydrostatic 제외)'},
        {'name': 'eps_over_D', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.0, 'unit': '-',
         'description': '튜브 내면 거칠기/직경 (0=smooth, 1.5e-6/D ~ 0.0002 일반 stainless)'},

        # ═══════ Fitting (calibration multipliers) ═══════
        {'name': 'htc_corr_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '2-phase α 보정 (실험 값 / correlation 값)'},
        {'name': 'htc_corr_SH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'SH α 보정'},
        {'name': 'htc_corr_air', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '공기측 α 보정'},
        {'name': 'dp_corr_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '2-phase 마찰 dP 보정'},
        {'name': 'dp_corr_SH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'SH 마찰 dP 보정'},

        # ═══════ Inputs (6) ═══════
        {'name': 'P_evap', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '증발 압력 (abs)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 상대습도'},
        {'name': 'm_dot_air', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '공기 질량 유량 (건조공기)'},

        # ═══════ Outputs ═══════
        # Refrigerant
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'kJ/kg', 'description': '냉매 출구 엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'bar', 'description': '냉매 출구 압력'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': '출구 quality (>1 = SH)'},
        {'name': 'SH_out', 'causality': 'output', 'type': 'Real', 'unit': 'K', 'description': '출구 과열도'},
        {'name': 'T_evap', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '증발 포화 온도'},
        # Air
        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '공기 출구 온도'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real', 'unit': '%', 'description': '공기 출구 RH'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real', 'unit': 'kg/kg', 'description': '공기 출구 humidity'},
        # 열량
        {'name': 'Q_total', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': '총 열교환량'},
        {'name': 'Q_sensible', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': '현열'},
        {'name': 'Q_latent', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': '잠열'},
        {'name': 'condensate_rate', 'causality': 'output', 'type': 'Real', 'unit': 'kg/s', 'description': '응축수 (건조량)'},
        # Moving Boundary 특유 출력
        {'name': 'zeta_2ph', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'Moving Boundary: 2-phase zone 길이 비율 (수렴 결과)'},
        {'name': 'alpha_r_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'W/m²K',
         'description': '냉매측 2-phase α (correlation 결과)'},
        {'name': 'alpha_r_SH', 'causality': 'output', 'type': 'Real', 'unit': 'W/m²K',
         'description': '냉매측 SH α (correlation 결과)'},
        {'name': 'alpha_air', 'causality': 'output', 'type': 'Real', 'unit': 'W/m²K',
         'description': '공기측 α'},
        {'name': 'eta_fin_calc', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'Schmidt 핀 효율'},
        {'name': 'UA_2ph_calc', 'causality': 'output', 'type': 'Real', 'unit': 'W/K',
         'description': '계산된 UA_2ph'},
        {'name': 'UA_SH_calc', 'causality': 'output', 'type': 'Real', 'unit': 'W/K',
         'description': '계산된 UA_SH'},
        {'name': 'BF_air', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'Bypass factor (wet-coil)'},
        {'name': 'is_wet', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': '응축 여부 (1=wet)'},
        {'name': 'newton_iter', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'Newton iteration 횟수 (진단)'},
        # 압력 강하 진단
        {'name': 'dP_friction_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'Pa',
         'description': '2-phase zone 마찰 압력강하'},
        {'name': 'dP_friction_SH', 'causality': 'output', 'type': 'Real', 'unit': 'Pa',
         'description': 'SH zone 마찰 압력강하'},
        {'name': 'dP_acceleration', 'causality': 'output', 'type': 'Real', 'unit': 'Pa',
         'description': '가속 압력강하 (homogeneous)'},
        {'name': 'dP_total', 'causality': 'output', 'type': 'Real', 'unit': 'Pa',
         'description': '총 압력강하 (마찰 + 가속, hydrostatic 제외)'},
        {'name': 'T_evap_avg', 'causality': 'output', 'type': 'Real', 'unit': '°C',
         'description': '2-phase zone 평균 T_sat (P_avg 기반)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {'zeta_prev': 0.7}  # warm start


# ════════ Helper: humid air ════════
def _humid_air(T_C, RH_pct, P_atm=101325.0):
    T_K = T_C + 273.15
    RH = max(0.001, min(0.999, RH_pct / 100.0))
    try:
        W = CP.HAPropsSI('W', 'T', T_K, 'P', P_atm, 'R', RH)
        h = CP.HAPropsSI('H', 'T', T_K, 'P', P_atm, 'W', W)
        T_dp = CP.HAPropsSI('Tdp', 'T', T_K, 'P', P_atm, 'W', W)
        cp = CP.HAPropsSI('cp_ha', 'T', T_K, 'P', P_atm, 'W', W)
    except Exception:
        W = 0.622 * RH * 1000 / (P_atm - RH * 1000)
        h = 1006 * T_C + W * (2501e3 + 1860 * T_C)
        T_dp = T_K - 5
        cp = 1006 + 1860 * W
    return W, h, T_dp, cp


def _W_sat(T_C, P_atm=101325.0):
    try:
        return CP.HAPropsSI('W', 'T', T_C + 273.15, 'P', P_atm, 'R', 0.999)
    except Exception:
        Psat = 611.2 * math.exp(17.62 * T_C / (243.12 + T_C))
        return 0.622 * Psat / (P_atm - Psat)


def _h_air_sat(T_C, P_atm=101325.0):
    """포화 공기 비엔탈피 (J/kg dry air) at temperature T_C.
    학계 표준 wet coil 모델에서 'apparatus dew point' 가정용.
    """
    try:
        return CP.HAPropsSI('H', 'T', T_C + 273.15, 'P', P_atm, 'R', 0.999)
    except Exception:
        W_sat = _W_sat(T_C, P_atm)
        return 1006.0 * T_C + W_sat * (2501e3 + 1860.0 * T_C)


def _b_slope(T1_C, T2_C, P_atm=101325.0):
    """포화 공기 엔탈피의 평균 기울기: b = (h_sat(T2) - h_sat(T1)) / (T2 - T1).
    Mirth-Ramadhyani의 m_w* (= b / cp_air) 계산에 사용.
    """
    if abs(T2_C - T1_C) < 0.1:
        # 작은 ΔT — 미분으로 근사
        dT = 0.5
        return (_h_air_sat(T1_C + dT, P_atm) - _h_air_sat(T1_C - dT, P_atm)) / (2.0 * dT)
    return (_h_air_sat(T2_C, P_atm) - _h_air_sat(T1_C, P_atm)) / (T2_C - T1_C)


# ════════ ε-NTU ════════
def _eps_counterflow(NTU, Cr):
    if NTU <= 0: return 0.0
    if abs(Cr - 1.0) < 1e-6:
        return NTU / (1 + NTU)
    if Cr < 1e-9:
        return 1.0 - math.exp(-NTU) if NTU < 50 else 1.0
    NTU = min(NTU, 50)
    num = 1.0 - math.exp(-NTU * (1 - Cr))
    den = 1.0 - Cr * math.exp(-NTU * (1 - Cr))
    return num / den


# ════════ Q_total(ζ) — Newton 변수 ════════
def _q_residual(zeta, ctx):
    """ζ 가정 → UA 분배 → Q_2ph + Q_SH 계산 → energy balance 잔차.
    
    energy balance: Q_total(ζ) = ṁ × (h_out_target - h_in)
    h_out_target는 ζ에서 결정됨:
      if 냉매가 다 증발 못하면 (ζ < 1): h_out = h_l + x_out × h_fg  (x_out 추적 안 됨)
      Moving Boundary 정의: 2-phase 끝나는 점 = h_v
        Q_2ph_demand = ṁ × (h_v - h_in)  (이게 2-phase에서 받아야 할 열)
      
    더 정확한 정의:
      Q_2ph_supply(ζ) = ε_2ph(NTU_2ph(ζ)) × C_air × (T_air_in - T_evap)  (공기가 zone에 줄 수 있는 열)
      Q_2ph_demand   = ṁ × (h_v - h_in)  (냉매가 2-phase에서 받아야 다 증발하는 열)
      
    수렴 조건: Q_2ph_supply(ζ) = Q_2ph_demand  → ζ 결정
    """
    UA_2ph = ctx['UA_total'] * zeta
    NTU_2ph = UA_2ph / ctx['C_air'] if ctx['C_air'] > 0 else 0
    eps_2ph = 1.0 - math.exp(-NTU_2ph) if NTU_2ph < 50 else 1.0
    Q_2ph_supply = eps_2ph * ctx['C_air'] * (ctx['T_air_in'] - ctx['T_evap'])
    return Q_2ph_supply - ctx['Q_2ph_demand']


def step(input, params, state, dt):
    # ── Parameters ──
    fluid = params.get('fluid', 'R290')
    wet_mode = params.get('wet_coil_mode', 'auto')
    # Geometry
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    L_tube_total = float(params.get('L_tube_total', 10.0))
    N_tubes = float(params.get('N_tubes', 24.0))
    N_rows = float(params.get('N_rows', 2.0))
    P_t = float(params.get('P_t', 25.0e-3))
    P_l = float(params.get('P_l', 22.0e-3))
    t_fin = float(params.get('t_fin', 0.12e-3))
    FPI = float(params.get('FPI', 12.0))
    k_fin = float(params.get('k_fin', 200.0))
    A_o_face = float(params.get('A_o_face', 0.05))
    eps_over_D = float(params.get('eps_over_D', 0.0))
    # Correlations
    corr_2ph = params.get('corr_2ph', boiling.DEFAULT)
    corr_SH = params.get('corr_SH', single_phase.DEFAULT)
    corr_air = params.get('corr_air', air_side.DEFAULT)
    corr_fin = params.get('corr_fin', fin_efficiency.DEFAULT)
    corr_dp_2ph = params.get('corr_dp_2ph', pressure_drop.DEFAULT_2PH)
    # Fitting
    htc_corr_2ph = float(params.get('htc_corr_2ph', 1.0))
    htc_corr_SH = float(params.get('htc_corr_SH', 1.0))
    htc_corr_air = float(params.get('htc_corr_air', 1.0))
    dp_corr_2ph = float(params.get('dp_corr_2ph', 1.0))
    dp_corr_SH = float(params.get('dp_corr_SH', 1.0))

    # ── Inputs ──
    P_evap_bar = float(input.get('P_evap', 4.0))
    h_in_kjkg = float(input.get('h_in', 282.0))
    m_dot_ref = float(input.get('m_dot_ref', 0.005))
    T_air_in_C = float(input.get('T_air_in', 50.0))
    RH_air_in = float(input.get('RH_air_in', 85.0))
    m_dot_air = float(input.get('m_dot_air', 0.05))

    # 검증
    if P_evap_bar <= 0 or m_dot_ref <= 0 or m_dot_air <= 0:
        raise ValueError(f"입력 값이 0 이하: P={P_evap_bar}, ṁ_ref={m_dot_ref}, ṁ_air={m_dot_air}")

    P_evap_Pa = P_evap_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    P_fin = 0.0254 / FPI  # m

    # ── 1. 냉매 입구/포화 상태 ──
    try:
        T_evap_K = CP.PropsSI('T', 'P', P_evap_Pa, 'Q', 0.5, fluid)
        h_l = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 0, fluid)
        h_v = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 1, fluid)
        h_fg = h_v - h_l
    except Exception as e:
        raise ValueError(f"냉매 포화 상태 실패: {e}")
    T_evap_C = T_evap_K - 273.15
    x_in = (h_in_J - h_l) / h_fg if h_fg > 0 else 0
    x_in = max(0.0, min(1.0 + 1e-6, x_in))

    # ── 2. 공기 입구 ──
    W_in, h_air_in, T_dp_K, cp_air = _humid_air(T_air_in_C, RH_air_in)
    T_dp_in_C = T_dp_K - 273.15
    C_air = m_dot_air * cp_air

    # ── 3. 외부 면적 — A_o, A_i 자동 계산 ──
    # plain fin staggered tube: A_o = π D_o L_tube + fin area
    # 단순화: A_o ≈ π × D_o × L_tube_total × enhancement_factor (FPI에 따라)
    # 정확히는 각 fin 면적도 더해야 — 아래는 합리적 근사
    A_tube_outer = math.pi * D_o * L_tube_total
    # Fin enhancement: 한 fin당 면적 = 2 × (P_t × P_l - π × D_o²/4)
    n_fins_per_tube = L_tube_total / N_tubes / P_fin if P_fin > 0 else 0
    A_per_fin = 2.0 * (P_t * P_l - math.pi * (D_o ** 2) / 4.0)
    A_fin_total = N_tubes * n_fins_per_tube * A_per_fin
    A_o = A_tube_outer + A_fin_total
    A_i = math.pi * D_i * L_tube_total

    # ── 4. 공기측 α ──
    T_air_avg_K = (T_air_in_C + 273.15 + T_evap_K) / 2.0
    alpha_air = air_side.evaluate(corr_air,
                                   m_dot_air=m_dot_air, T_air_avg_K=T_air_avg_K,
                                   D_o=D_o, P_t=P_t, P_l=P_l, P_fin=P_fin,
                                   t_fin=t_fin, N_row=int(N_rows), A_o_face=A_o_face)
    alpha_air *= htc_corr_air

    # ── 5. Fin 효율 ──
    eta_fin = fin_efficiency.evaluate(corr_fin,
                                       D_o=D_o, P_t=P_t, P_l=P_l,
                                       t_fin=t_fin, k_fin=k_fin, alpha_o=alpha_air)

    # 외부 effective UA per unit length basis: α_air × (A_o × eta_fin)
    # tube portion은 eta=1, fin portion은 eta_fin이지만 단순화 — 평균 사용
    # 정확히: η_overall = (A_tube + A_fin × eta_fin) / A_o
    eta_overall = (A_tube_outer + A_fin_total * eta_fin) / A_o if A_o > 0 else eta_fin
    UA_air_total = alpha_air * A_o * eta_overall

    # ── 6. 냉매측 α — zone별 계산 ──
    # Zone 평균 quality
    x_avg_2ph = (x_in + 1.0) / 2.0
    # 열유속 q_flux 추정 — Q/A_i (앞 단계 추정으로)
    # 첫 추정: Q ≈ ṁ × (h_v - h_in) (다 증발 가정)
    Q_2ph_demand = m_dot_ref * (h_v - h_in_J)
    q_flux_2ph_est = Q_2ph_demand / max(A_i, 1e-6)

    alpha_2ph = boiling.evaluate(corr_2ph,
                                  P_Pa=P_evap_Pa, x_avg=x_avg_2ph,
                                  m_dot=m_dot_ref / max(N_tubes, 1),
                                  D_i=D_i, q_flux=q_flux_2ph_est, fluid=fluid)
    alpha_2ph *= htc_corr_2ph

    # SH zone — 평균 온도 추정 (T_evap + 일부 SH)
    T_SH_avg_K = T_evap_K + 10  # 첫 추정
    alpha_SH = single_phase.evaluate(corr_SH,
                                      P_Pa=P_evap_Pa, T_avg_K=T_SH_avg_K,
                                      m_dot=m_dot_ref / max(N_tubes, 1),
                                      D_i=D_i, fluid=fluid, heating=True)
    alpha_SH *= htc_corr_SH

    # ── 7. UA per zone (zone 길이 ζ에 비례) ──
    # 1/UA_total = 1/(α_r × A_i × ζ) + 1/(α_air × A_o × η_overall × ζ)
    # → UA(zone, ζ) = ζ × UA_zone_full
    UA_2ph_full = 1.0 / (1.0 / (alpha_2ph * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_SH_full = 1.0 / (1.0 / (alpha_SH * A_i) + 1.0 / (alpha_air * A_o * eta_overall))

    # ── 8. Newton iteration on ζ ──
    # Q_2ph_demand: 냉매가 2-phase 영역에서 받아야 할 열 (x_in → x=1)
    # Q_2ph_supply(ζ): 공기가 2-phase 영역에 줄 수 있는 열
    # 균형: Q_2ph_supply(ζ*) = Q_2ph_demand → ζ* 결정
    
    zeta = state.get('zeta_prev', 0.7)
    zeta = max(0.01, min(0.99, zeta))
    
    n_iter = 0
    converged = False
    for n_iter in range(1, 21):
        # Q_2ph_supply(ζ) = ε_2ph × C_air × (T_air_in - T_evap)
        UA_2ph = UA_2ph_full * zeta
        NTU_2ph = UA_2ph / C_air if C_air > 0 else 0
        eps_2ph = 1.0 - math.exp(-NTU_2ph) if NTU_2ph < 50 else 1.0
        Q_2ph_supply = eps_2ph * C_air * (T_air_in_C - T_evap_C)

        residual = Q_2ph_supply - Q_2ph_demand

        if abs(residual) < 0.5:  # 0.5 W
            converged = True
            break

        # Newton: dR/dζ = dQ_supply/dζ
        # dε/dNTU = exp(-NTU), dNTU/dζ = UA_full / C_air
        # dQ/dζ = exp(-NTU) × UA_full × ΔT
        if NTU_2ph < 50:
            dQ_dzeta = math.exp(-NTU_2ph) * UA_2ph_full * (T_air_in_C - T_evap_C)
        else:
            dQ_dzeta = 0.001  # saturated, very flat

        if abs(dQ_dzeta) > 1e-9:
            zeta_new = zeta - residual / dQ_dzeta
        else:
            zeta_new = zeta

        # Bound + relax
        zeta_new = max(0.01, min(0.999, zeta_new))
        zeta = zeta + 0.7 * (zeta_new - zeta)  # under-relaxation

    # 최종 ζ
    zeta = max(0.01, min(1.0, zeta))

    # ── 9. 실제 Q 계산 (수렴된 ζ로) ──
    UA_2ph_actual = UA_2ph_full * zeta
    UA_SH_actual = UA_SH_full * (1.0 - zeta) if zeta < 1.0 else 0

    # ζ ≥ 0.99이면: 냉매가 2-phase 영역에서 다 증발 못함 → SH zone 0
    ref_fully_evap = (zeta < 0.99) and (UA_SH_actual > 0)

    # 2-phase actual Q (Q_2ph_demand로 cap)
    NTU_2ph = UA_2ph_actual / C_air if C_air > 0 else 0
    eps_2ph = 1.0 - math.exp(-NTU_2ph) if NTU_2ph < 50 else 1.0
    Q_sensible_2ph = eps_2ph * C_air * (T_air_in_C - T_evap_C)
    Q_sensible_2ph = min(Q_sensible_2ph, Q_2ph_demand)

    # 공기 온도 after 2-phase
    T_air_after_2ph_C = T_air_in_C - Q_sensible_2ph / C_air if C_air > 0 else T_air_in_C

    # ── 10. SH zone (ζ < 1 일 때) ──
    Q_SH = 0
    h_ref_out_J = h_in_J + Q_sensible_2ph / m_dot_ref
    T_air_out_C = T_air_after_2ph_C

    if ref_fully_evap:
        try:
            cp_ref_SH = CP.PropsSI('C', 'P', P_evap_Pa, 'Q', 1, fluid)
        except Exception:
            cp_ref_SH = 1700
        C_ref = m_dot_ref * cp_ref_SH
        Cmin_SH = min(C_ref, C_air)
        Cmax_SH = max(C_ref, C_air)
        Cr = Cmin_SH / Cmax_SH if Cmax_SH > 0 else 0
        NTU_SH = UA_SH_actual / Cmin_SH if Cmin_SH > 0 else 0
        eps_SH = _eps_counterflow(NTU_SH, Cr)
        Q_SH = eps_SH * Cmin_SH * (T_air_after_2ph_C - T_evap_C)
        Q_SH = max(0, Q_SH)
        h_ref_out_J = h_v + Q_SH / m_dot_ref
        T_air_out_C = T_air_after_2ph_C - Q_SH / C_air if C_air > 0 else T_air_after_2ph_C

    # ── 11. Wet-coil with Enthalpy Potential Method ──
    # ═══════════════════════════════════════════════════════════════════════
    # Reference: 
    #   Mirth & Ramadhyani (1993) IJHMT — "Prediction of cooling-coil 
    #     performance under condensing conditions"
    #   ASHRAE Handbook of Fundamentals Ch.6
    #   Threlkeld (1970) "Thermal Environmental Engineering"
    #
    # 학계 표준 wet coil 모델:
    #   Q_total = m_dot_air × (h_air_in - h_air_out)
    #   ε_h = 1 - exp(-NTU_h × ξ)
    #   NTU_h = UA_o × η_o / (m_dot_air × cp_air)
    #   ξ = m_w* = b / cp_air  (saturation enthalpy slope correction)
    #   h_air_out = h_air_in - ε_h × (h_air_in - h_apparatus)
    #   h_apparatus = h_sat(T_evap)  ← refrigerant 측 saturation temp의 포화공기
    #
    # 이전 코드 버그:
    #   sensible Q와 latent Q를 따로 풀어서 더함 → double counting
    #   ref-side capacity 무시 → enthalpy 발산
    # ═══════════════════════════════════════════════════════════════════════
    
    is_wet = (wet_mode == 'auto') and (T_dp_in_C > T_evap_C)
    
    if is_wet:
        # ── air-side enthalpy potential ε-NTU ──
        h_apparatus = _h_air_sat(T_evap_C)  # apparatus dew point = T_evap
        
        # Saturation enthalpy slope b (J/kg-dry-air per K)
        # 평균 슬로프 사용: T_evap ~ T_air_in 사이
        b_sat = _b_slope(T_evap_C, T_air_in_C)
        # m_w* = b / cp_air (Threlkeld saturation enthalpy slope correction)
        m_w_star = b_sat / cp_air if cp_air > 0 else 1.0
        
        # NTU_h: air-side enthalpy NTU
        # UA_o_eff: 외부 effective UA = α_air × A_o × η_overall (전체 coil)
        UA_o_eff = alpha_air * A_o * eta_overall
        NTU_h_air = UA_o_eff / (m_dot_air * cp_air) if (m_dot_air * cp_air) > 0 else 0
        
        # ref-side enthalpy NTU (2-phase: α_r × A_i / m_w*)
        # 2-phase: ref-side T 거의 일정 (T_evap) → Cr_h → 0 (single stream limit)
        # 이 경우 ε_h = 1 - exp(-NTU_h_overall)
        # NTU_h_overall = 1 / (1/NTU_h_air + m_w*/NTU_h_ref)
        UA_i_eff_2ph = alpha_2ph * A_i  # 2-phase 측 UA (전체 zone 가정 — 보수적)
        # SH zone도 있으면 가중평균
        if ref_fully_evap and UA_SH_actual > 0:
            UA_i_eff = (alpha_2ph * A_i * zeta + alpha_SH * A_i * (1 - zeta))
        else:
            UA_i_eff = alpha_2ph * A_i
        
        NTU_h_ref = UA_i_eff / (m_dot_ref * 1.0) if m_dot_ref > 0 else 0  # m_w_star 단위 맞춤
        # ε_h: combined NTU (overall)
        # 1/UA_overall_h = 1/UA_o_eff + m_w*/UA_i_eff
        if UA_i_eff > 0 and m_w_star > 0:
            inv_UA_h = 1.0 / UA_o_eff + m_w_star / UA_i_eff
            UA_h_overall = 1.0 / inv_UA_h if inv_UA_h > 0 else 0
        else:
            UA_h_overall = UA_o_eff  # 2-phase ref limit
        NTU_h_overall = UA_h_overall / (m_dot_air * cp_air) if (m_dot_air * cp_air) > 0 else 0
        
        # ε_h: single-stream (ref-side T const → Cr ~ 0 가정)
        eps_h = 1.0 - math.exp(-NTU_h_overall) if NTU_h_overall < 50 else 1.0
        
        # ── air outlet enthalpy ──
        h_air_out = h_air_in - eps_h * (h_air_in - h_apparatus)
        
        # ── Q_total (air-side enthalpy balance) ──
        Q_total = m_dot_air * (h_air_in - h_air_out)
        
        # ── Outlet air state (T_out, W_out, RH_out) ──
        # 포화 공기 line상 점 — 보수적 가정:
        # ADP (apparatus dew point): T_air_apparatus = T_evap, fully saturated
        # 실제 outlet은 ADP와 inlet 사이의 직선 위 (Threlkeld 가정)
        # Bypass factor BF (enthalpy-based) = (h_out - h_apparatus) / (h_in - h_apparatus)
        BF = (h_air_out - h_apparatus) / max(h_air_in - h_apparatus, 1e-6)
        BF = max(0.0, min(1.0, BF))
        
        # Outlet humidity: ω_out = BF × ω_in + (1-BF) × ω_sat(T_apparatus)
        W_apparatus = _W_sat(T_evap_C)
        W_air_out = BF * W_in + (1.0 - BF) * W_apparatus
        # Bounds
        W_air_out = min(W_in, max(W_apparatus, W_air_out))
        
        # condensate, Q_latent
        condensate_rate = m_dot_air * (W_in - W_air_out)
        h_fg_water = 2501e3 - 2.4 * T_evap_C
        Q_latent = condensate_rate * h_fg_water
        Q_latent = max(0, Q_latent)
        
        # Q_sensible = Q_total - Q_latent (결과로서 분해)
        Q_sensible_total = max(0, Q_total - Q_latent)
        
        # T_air_out from enthalpy + humidity
        try:
            T_air_out_K = CP.HAPropsSI('T', 'H', h_air_out, 'P', 101325.0, 'W', W_air_out)
            T_air_out_C = T_air_out_K - 273.15
        except Exception:
            # fallback: enthalpy linearize
            T_air_out_C = T_air_in_C - Q_sensible_total / C_air if C_air > 0 else T_air_in_C
        
        # ── ref-side cap (안전 안전책) ──
        # ref가 흡수 가능한 max enthalpy: vapor + 충분한 SH 한도
        # 만약 Q_total이 ref capacity 넘으면 cap (실제로 enthalpy potential method가 이미 처리하지만 보수적)
        try:
            cp_vapor = CP.PropsSI('C', 'P', P_evap_Pa, 'Q', 1, fluid)
        except Exception:
            cp_vapor = 1700
        # ref 최대 흡수: vapor 도달 + SH 50K
        h_ref_max = h_v + cp_vapor * 50.0
        Q_ref_max = m_dot_ref * (h_ref_max - h_in_J)
        if Q_total > Q_ref_max and Q_ref_max > 0:
            # ref 한도로 cap + air-side 재조정
            scale = Q_ref_max / Q_total
            Q_total = Q_ref_max
            Q_sensible_total *= scale
            Q_latent *= scale
            condensate_rate *= scale
            W_air_out = W_in - condensate_rate / m_dot_air
            h_air_out = h_air_in - Q_total / m_dot_air
            try:
                T_air_out_K = CP.HAPropsSI('T', 'H', h_air_out, 'P', 101325.0, 'W', W_air_out)
                T_air_out_C = T_air_out_K - 273.15
            except Exception:
                T_air_out_C = T_air_in_C - Q_sensible_total / C_air if C_air > 0 else T_air_in_C
    else:
        # Dry coil — 기존 sensible-only 결과 유지
        BF = 1.0
        W_air_out = W_in
        condensate_rate = 0.0
        Q_latent = 0.0
        Q_sensible_total = Q_sensible_2ph + Q_SH
        Q_total = Q_sensible_total
        # T_air_out_C 는 위에서 이미 계산됨

    # ── 12. 압력 강하 계산 (마찰 + 가속) ──
    # zone별 길이 = ζ × L_total / N_tubes (1 회로 길이 가정)
    L_2ph_zone = L_tube_total * zeta
    L_SH_zone = L_tube_total * (1 - zeta) if zeta < 0.99 else 0.0
    
    # 1 튜브당 유량 (병렬 회로면 N_tubes로 분배 — 단순 가정)
    m_dot_per_tube = m_dot_ref  # 한 회로 가정. 여러 회로면 / N_circuits

    # 2-phase 출구 quality (Q_2ph로 결정)
    if m_dot_ref > 0 and h_fg > 0:
        x_at_2ph_end = x_in + Q_sensible_2ph / (m_dot_ref * h_fg)
        x_at_2ph_end = max(0.0, min(1.0, x_at_2ph_end))
    else:
        x_at_2ph_end = x_in

    # 2-phase 마찰 dP
    if L_2ph_zone > 0:
        dP_friction_2ph = pressure_drop.evaluate_2phase(
            corr_dp_2ph,
            P_Pa=P_evap_Pa, x_in=x_in, x_out=x_at_2ph_end,
            m_dot=m_dot_per_tube, D_i=D_i, L=L_2ph_zone, fluid=fluid
        )
        dP_friction_2ph *= dp_corr_2ph
    else:
        dP_friction_2ph = 0.0

    # SH 마찰 dP (Churchill 단상)
    if L_SH_zone > 0 and ref_fully_evap:
        # Average T in SH zone
        T_SH_avg_K = T_evap_K + 5.0  # 1차 추정 — 추후 개선 가능
        dP_friction_SH = pressure_drop.single_phase_dp(
            P_Pa=P_evap_Pa, T_K=T_SH_avg_K,
            m_dot=m_dot_per_tube, D_i=D_i, L=L_SH_zone,
            fluid=fluid, is_liquid=False, eps_over_D=eps_over_D
        )
        dP_friction_SH *= dp_corr_SH
    else:
        dP_friction_SH = 0.0

    # Acceleration dP (homogeneous)
    # 입구 → 2-phase 끝까지의 가속만 (SH은 단상이라 무시)
    dP_acceleration = pressure_drop.acceleration_dp(
        P_Pa=P_evap_Pa, x_in=x_in, x_out=x_at_2ph_end,
        m_dot=m_dot_per_tube, D_i=D_i, fluid=fluid
    )

    dP_total_Pa = dP_friction_2ph + dP_friction_SH + dP_acceleration
    
    # 출구 압력
    P_ref_out_Pa = P_evap_Pa - dP_total_Pa
    P_ref_out_Pa = max(P_ref_out_Pa, 1e3)  # floor — 압력이 너무 낮으면 안 됨
    P_ref_out_bar = P_ref_out_Pa / 1e5

    # ── 13. 출구 상태 ──
    # Q_total로 h_ref_out 다시 (latent 더한 것 반영)
    h_ref_out_final_J = h_in_J + Q_total / m_dot_ref
    try:
        T_ref_out_K = CP.PropsSI('T', 'P', P_ref_out_Pa, 'H', h_ref_out_final_J, fluid)
        T_ref_out_C = T_ref_out_K - 273.15
    except Exception:
        T_ref_out_C = T_evap_C

    # T_evap_avg (P_avg 기반 — 진단용)
    P_avg_Pa = (P_evap_Pa + P_ref_out_Pa) / 2.0
    try:
        T_evap_avg_K = CP.PropsSI('T', 'P', P_avg_Pa, 'Q', 0.5, fluid)
        T_evap_avg_C = T_evap_avg_K - 273.15
    except Exception:
        T_evap_avg_C = T_evap_C

    if h_ref_out_final_J >= h_v:
        quality_out = 1.0 + (h_ref_out_final_J - h_v) / max(h_fg, 1)
        SH_out = max(0, T_ref_out_C - T_evap_C)
    else:
        quality_out = (h_ref_out_final_J - h_l) / h_fg if h_fg > 0 else 0
        SH_out = 0

    # 공기 출구 RH
    try:
        RH_air_out = CP.HAPropsSI('R', 'T', T_air_out_C + 273.15, 'P', 101325.0,
                                   'W', max(W_air_out, 1e-6)) * 100
        RH_air_out = max(0, min(100, RH_air_out))
    except Exception:
        RH_air_out = RH_air_in

    # ── 새 state ──
    new_state = {'zeta_prev': zeta}

    outputs = {
        'T_ref_out': T_ref_out_C,
        'h_ref_out': h_ref_out_final_J / 1000,
        'P_ref_out': P_ref_out_bar,
        'quality_out': quality_out,
        'SH_out': SH_out,
        'T_evap': T_evap_C,
        'T_air_out': T_air_out_C,
        'RH_air_out': RH_air_out,
        'W_air_out': W_air_out,
        'Q_total': Q_total,
        'Q_sensible': Q_sensible_total,
        'Q_latent': Q_latent,
        'condensate_rate': condensate_rate,
        'zeta_2ph': zeta,
        'alpha_r_2ph': alpha_2ph,
        'alpha_r_SH': alpha_SH,
        'alpha_air': alpha_air,
        'eta_fin_calc': eta_fin,
        'UA_2ph_calc': UA_2ph_actual,
        'UA_SH_calc': UA_SH_actual,
        'BF_air': BF if is_wet else 1.0,
        'is_wet': 1.0 if is_wet else 0.0,
        'newton_iter': float(n_iter),
        'dP_friction_2ph': dP_friction_2ph,
        'dP_friction_SH': dP_friction_SH,
        'dP_acceleration': dP_acceleration,
        'dP_total': dP_total_Pa,
        'T_evap_avg': T_evap_avg_C,
    }
    return {'outputs': outputs, 'newState': new_state}


def validate(params):
    errors = []
    if params.get('fluid') not in FLUIDS:
        errors.append({'key': 'fluid', 'msg': f'fluid는 {FLUIDS}'})
    for key, lo, hi in [
        ('D_o', 1e-3, 50e-3), ('D_i', 0.5e-3, 50e-3),
        ('L_tube_total', 0.1, 1000), ('N_tubes', 1, 1000), ('N_rows', 1, 20),
        ('P_t', 5e-3, 100e-3), ('P_l', 5e-3, 100e-3),
        ('t_fin', 0.05e-3, 1e-3), ('FPI', 4, 30), ('k_fin', 50, 500),
        ('A_o_face', 0.001, 10),
        ('htc_corr_2ph', 0.1, 5), ('htc_corr_SH', 0.1, 5),
        ('htc_corr_air', 0.1, 5),
        ('dp_corr_2ph', 0.1, 5), ('dp_corr_SH', 0.1, 5),
        ('eps_over_D', 0, 0.05),
    ]:
        v = params.get(key)
        if v is None: continue
        if not (lo <= v <= hi):
            errors.append({'key': key, 'msg': f'{key} 범위: {v} ({lo}~{hi})'})
    return errors
