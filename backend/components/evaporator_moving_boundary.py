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
# 2상 boiling은 On(segment march)과 동일 식 사용 — vendor 라이브러리 통일.
# (correlation 라이브러리가 다르면 같은 운전점에서 α가 달라져 Off/On/Semi 정합 불가)
from _vendor.hx_sim.correlations import h_with_transition as _vendor_h_tp
from _vendor.hx_sim.correlations import compute_j_factor as _vendor_j_factor
from _vendor.hx_sim.properties import RefrigerantProperties as _VendorRefProps
from _vendor.hx_sim.properties import MoistAirProperties as _VendorAirProps

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
        {'name': 'n_circuits', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.0, 'unit': '-',
         'description': '병렬 냉매 회로 수 (G = ṁ/n_circuits/A_cross). 검증 시 On circuit_mode의 회로수와 일치시킴'},
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
         'group': 'Geometry', 'start': 'chen1966', 'unit': '-',
         'options': ['chen1966', 'gungor_winterton1986', 'kandlikar1990'],
         'description': '2-phase boiling correlation (On과 동일 vendor 식)'},
        {'name': 'corr_SH', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': single_phase.DEFAULT, 'unit': '-',
         'options': CORR_SH_OPTIONS,
         'description': 'SH (single-phase gas) correlation'},
        {'name': 'corr_air', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'wang2000_plain', 'unit': '-',
         'options': ['wang2000_plain', 'gray_webb1986'],
         'description': '공기측 j-factor correlation (On과 동일 vendor 식)'},
        {'name': 'corr_fin', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': fin_efficiency.DEFAULT, 'unit': '-',
         'options': CORR_FIN_OPTIONS,
         'description': 'Fin 효율 correlation'},
        {'name': 'corr_dp_2ph', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': pressure_drop.DEFAULT_2PH, 'unit': '-',
         'options': CORR_DP_OPTIONS,
         'description': '2-phase 압력강하 correlation (Acceleration은 항상 포함, Hydrostatic 제외)'},
        {'name': 'void_model', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'Premoli', 'unit': '-',
         'options': ['Homogeneous', 'Zivi', 'Rigot', 'Hughmark', 'Premoli', 'Rouhani-Axelsson'],
         'description': 'Void fraction 모델 (charge holdup 계산용, default Premoli)'},
        {'name': 'flow_arrangement', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'counter', 'unit': '-',
         'options': ['counter', 'parallel'],
         'description': '공기-냉매 흐름 배치 (counter=대향류 default, parallel=평행류). On과 동일'},
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
        {'name': 'V_air_CMM', 'causality': 'input', 'type': 'Real',
         'unit': 'CMM', 'description': '공기 풍량 (m³/min, CMM) — 한국 HVAC 표준 단위'},

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
        {'name': 'M_holdup', 'causality': 'output', 'type': 'Real', 'unit': 'kg',
         'description': '내부 냉매 질량 (charge holdup, ζ zone 분할 + void fraction)'},
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


def _eps_parallel(NTU, Cr):
    if NTU <= 0:
        return 0.0
    if Cr < 1e-9:
        return 1.0 - math.exp(-NTU) if NTU < 50 else 1.0
    denom = 1.0 + Cr
    return (1.0 - math.exp(-min(NTU * denom, 50))) / denom


def _eps_evap(NTU, Cr, flow):
    """flow arrangement에 따른 ε-NTU (단상 zone용). Cr=0이면 둘 다 1-exp(-NTU)."""
    if flow == 'parallel':
        return _eps_parallel(NTU, Cr)
    return _eps_counterflow(NTU, Cr)


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



def _cmm_to_mass(V_air_CMM, T_air_C=20.0, RH=50.0, P_atm=101325.0):
    """공기 풍량 CMM (m³/min) → mass flow kg/s.
    한국 HVAC 표준 단위 CMM = m³/min. m_dot = ρ × V / 60.
    """
    try:
        Vha = CP.HAPropsSI('Vha', 'T', T_air_C + 273.15, 'P', P_atm, 'R', max(0.001, min(0.999, RH/100.0)))
        rho = 1.0 / Vha if Vha > 0 else 1.18
    except Exception:
        rho = 1.18  # 표준 공기
    return rho * (V_air_CMM / 60.0)


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
    n_circuits = float(params.get('n_circuits', 2.0))  # 병렬 회로 수 (G 결정)
    P_t = float(params.get('P_t', 25.0e-3))
    P_l = float(params.get('P_l', 22.0e-3))
    t_fin = float(params.get('t_fin', 0.12e-3))
    FPI = float(params.get('FPI', 12.0))
    k_fin = float(params.get('k_fin', 200.0))
    A_o_face = float(params.get('A_o_face', 0.05))
    eps_over_D = float(params.get('eps_over_D', 0.0))
    # Correlations
    corr_2ph = params.get('corr_2ph', 'chen1966')
    corr_SH = params.get('corr_SH', single_phase.DEFAULT)
    corr_air = params.get('corr_air', 'wang2000_plain')
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
    m_dot_air = _cmm_to_mass(
        V_air_CMM=float(input.get('V_air_CMM', 2.54)),
        T_air_C=T_air_in_C, RH=RH_air_in,
    )

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

    # ── 4. 공기측 α — On(segment march)과 동일한 vendor j-factor 식 ──
    #   h_o = j·G_air·cp/Pr^(2/3), j = compute_j_factor(Re_Dc, geometry)
    #   G_air = ṁ_air/A_c (최소 자유면적), A_c = σ·A_fr, σ = (Pt−Dc)·gap/(Pt·Fp)
    T_air_avg_K = (T_air_in_C + 273.15 + T_evap_K) / 2.0
    _mu_a = _VendorAirProps.mu_air(T_air_avg_K, 101325.0)
    _Pr_a = _VendorAirProps.Pr_air(T_air_avg_K, 101325.0)
    _cp_a = _VendorAirProps.cp_air(T_air_avg_K, 0.0, 101325.0)
    _Dc = D_o + 2.0 * t_fin                       # collar diameter
    _gap = P_fin - t_fin
    _sigma = max((P_t - _Dc) * _gap / (P_t * P_fin), 0.1)
    _A_c = _sigma * A_o_face                       # 최소 자유면적
    _G_air = m_dot_air / max(_A_c, 1e-9)
    _Re_Dc = _G_air * _Dc / max(_mu_a, 1e-9)
    _j_air = _vendor_j_factor(corr_air, Re_Dc=_Re_Dc, Nr=int(N_rows), Dc=_Dc,
                              Pt=P_t, Pl=P_l, FPI=FPI, fin_thickness=t_fin)
    alpha_air = _j_air * _G_air * _cp_a / _Pr_a ** (2.0 / 3.0)
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

    # 2상 boiling HTC — On(segment march)과 동일한 vendor 식 사용 (정합).
    #   G = ṁ/n_circuits/A_cross (회로 기준 질량유속). vendor 시그니처로 변환.
    _A_cross = math.pi * D_i ** 2 / 4.0
    _G_2ph = (m_dot_ref / max(n_circuits, 1)) / max(_A_cross, 1e-12)
    _ref_obj = _VendorRefProps(fluid)
    alpha_2ph = _vendor_h_tp(x=x_avg_2ph, G=_G_2ph, Di=D_i, q_flux=q_flux_2ph_est,
                             ref=_ref_obj, P=P_evap_Pa, mode='evap',
                             hx_type='FT', evap_corr=corr_2ph)
    alpha_2ph *= htc_corr_2ph

    # SH zone — 평균 온도 추정 (T_evap + 일부 SH)
    T_SH_avg_K = T_evap_K + 10  # 첫 추정
    alpha_SH = single_phase.evaluate(corr_SH,
                                      P_Pa=P_evap_Pa, T_avg_K=T_SH_avg_K,
                                      m_dot=m_dot_ref / max(n_circuits, 1),
                                      D_i=D_i, fluid=fluid, heating=True)
    alpha_SH *= htc_corr_SH

    # ── 7. UA per zone (zone 길이 ζ에 비례) ──
    # 1/UA_total = 1/(α_r × A_i × ζ) + 1/(α_air × A_o × η_overall × ζ)
    # → UA(zone, ζ) = ζ × UA_zone_full
    UA_2ph_full = 1.0 / (1.0 / (alpha_2ph * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_SH_full = 1.0 / (1.0 / (alpha_SH * A_i) + 1.0 / (alpha_air * A_o * eta_overall))

    # ── 8. ζ 결정 + 2상 zone 열전달 (wet/dry 통합, enthalpy 기준) ──
    # ═══════════════════════════════════════════════════════════════════════
    # ζ = 2상 zone 길이 비율. 냉매 완전증발(x_in→1) 열을 공기가 공급하는 지점에서 결정.
    # wet일 때 냉매가 받는 열 = 공기 enthalpy 감소 전체(현열+잠열): 표면 응축 잠열도
    #   냉매로 전달되므로 ζ는 enthalpy 기준이어야 함 (기존 sensible 기준 → 결합 오류).
    # 2상 zone만 wet (표면이 차가워 제습), SH zone은 dry (표면이 따뜻해 제습 없음).
    # 표면온도는 (냉매측 저항)=(공기측 enthalpy potential) 양쪽 균형 → 보정계수 없음,
    #   회로(G) 무관 robust (On segment march의 zone-평균 등가).
    # ═══════════════════════════════════════════════════════════════════════
    is_wet = (wet_mode == 'auto') and (T_dp_in_C > T_evap_C)

    def _compute_2ph(zeta_val, T_air_2ph=None, h_air_2ph=None):
        """주어진 ζ에서 2상 zone 공급열 Q_sup[W], 표면온도 Ts[°C], eps, 포화엔탈피.
        T_air_2ph/h_air_2ph: 2상 zone 공기 입구 (counter면 SH 통과 후, parallel/None이면 신선).
        wet은 sub-zone march로 공기 점진 냉각 반영 (enthalpy potential 비선형 → On 정합)."""
        _Ta2 = T_air_in_C if T_air_2ph is None else T_air_2ph
        _ha2 = h_air_in if h_air_2ph is None else h_air_2ph
        UA_i_full = alpha_2ph * A_i * zeta_val  # 2상 zone 전체 냉매측 [W/K]
        if is_wet:
            # 공기측을 N_sub로 march: 각 sub-zone에서 공기 냉각 → 구동력 점감
            N_sub = 12
            UA_o_sub = alpha_air * A_o * zeta_val * eta_overall / N_sub
            UA_i_sub = UA_i_full / N_sub
            NTU_sub = UA_o_sub / C_air if C_air > 0 else 0
            eps_sub = 1.0 - math.exp(-NTU_sub) if NTU_sub < 50 else 1.0
            h_air_local = _ha2
            Q_sup = 0.0
            Ts_sum = 0.0
            Ts = 0.5 * (T_evap_C + _Ta2)  # warm start
            for _s in range(N_sub):
                # 표면온도 양쪽 균형 (이 sub-zone의 local 공기 엔탈피로)
                for _ in range(20):
                    Q_b = m_dot_air * eps_sub * (h_air_local - _h_air_sat(Ts))
                    Ts_new = T_evap_C + Q_b / UA_i_sub if UA_i_sub > 0 else T_evap_C
                    Ts_new = max(T_evap_C, min(Ts_new, _Ta2))
                    if abs(Ts_new - Ts) < 0.02:
                        Ts = Ts_new
                        break
                    Ts = 0.5 * (Ts_new + Ts)
                Q_s = max(0.0, m_dot_air * eps_sub * (h_air_local - _h_air_sat(Ts)))
                Q_sup += Q_s
                h_air_local -= Q_s / m_dot_air
                Ts_sum += Ts
            Ts_avg = Ts_sum / N_sub
            return Q_sup, Ts_avg, eps_sub, _h_air_sat(Ts_avg)
        else:
            UA_2ph = UA_2ph_full * zeta_val
            NTU = UA_2ph / C_air if C_air > 0 else 0
            eps = 1.0 - math.exp(-NTU) if NTU < 50 else 1.0
            Q_sup = eps * C_air * (_Ta2 - T_evap_C)  # sensible
            return Q_sup, T_evap_C, eps, None

    flow_arr = params.get('flow_arrangement', 'counter')

    # ── 8~10. flow 방향에 따라 SH↔2상 공기 결합 iteration ──
    #   parallel: 공기 2상(신선) → SH. 순차 → 1회 수렴.
    #   counter : 공기 SH(신선) → 2상. SH가 공기를 먼저 식힘 → 2상이 식은 공기 받음 → iteration.
    T_air_2ph_in = T_air_in_C   # 2상 zone 공기 입구온도
    h_air_2ph_in = h_air_in     # 2상 zone 공기 입구엔탈피 (SH는 dry라 습도는 W_in 유지)
    zeta = 0.5
    ref_fully_evap = False
    Q_2ph = Q_2ph_sup = Q_SH = Q_latent = 0.0
    T_surf_C = T_evap_C; eps_2ph_w = 0.0; h_app_2ph = None
    BF = 1.0; W_air_out = W_in
    h_air_after_2ph = h_air_in; T_air_after_2ph_C = T_air_in_C
    h_ref_out_J = h_in_J
    for _ctr in range(15):
        # ζ bisection — Q_2ph_supply(ζ)는 ζ에 단조증가, demand 고정
        Q_at_full, _, _, _ = _compute_2ph(0.999, T_air_2ph_in, h_air_2ph_in)
        if Q_at_full <= Q_2ph_demand:
            # ζ=1이어도 완전증발 불가 → 출구 2상, SH zone 없음 (On에서 흔함)
            zeta = 1.0
            ref_fully_evap = False
        else:
            _lo, _hi = 0.01, 0.999
            for _bi in range(50):
                zeta = 0.5 * (_lo + _hi)
                _Qs, _, _, _ = _compute_2ph(zeta, T_air_2ph_in, h_air_2ph_in)
                if _Qs < Q_2ph_demand:
                    _lo = zeta
                else:
                    _hi = zeta
                if _hi - _lo < 1e-4:
                    break
            zeta = 0.5 * (_lo + _hi)
            ref_fully_evap = (zeta < 0.99)
        zeta = max(0.01, min(1.0, zeta))

        # 최종 2상 zone (수렴된 ζ로, 2상 공기 입구 기준)
        Q_2ph_sup, T_surf_C, eps_2ph_w, h_app_2ph = _compute_2ph(zeta, T_air_2ph_in, h_air_2ph_in)
        Q_2ph = Q_2ph_demand if ref_fully_evap else Q_2ph_sup
        UA_SH_actual = UA_SH_full * (1.0 - zeta) if zeta < 1.0 else 0

        # 2상 zone 공기 출구 상태 (enthalpy 감소 + 제습) — 2상 공기 입구 기준
        h_air_after_2ph = h_air_2ph_in - Q_2ph / m_dot_air
        if is_wet:
            BF = (h_air_after_2ph - h_app_2ph) / max(h_air_2ph_in - h_app_2ph, 1e-6)
            BF = max(0.0, min(1.0, BF))
            W_sat_surf = _W_sat(T_surf_C)
            W_air_out = BF * W_in + (1.0 - BF) * W_sat_surf
            W_air_out = min(W_in, max(W_sat_surf, W_air_out))
            condensate_rate = m_dot_air * (W_in - W_air_out)
            h_fg_water = 2501e3 - 2.4 * T_surf_C
            Q_latent = max(0.0, condensate_rate * h_fg_water)
        else:
            BF = 1.0
            W_air_out = W_in
            condensate_rate = 0.0
            Q_latent = 0.0
        try:
            T_air_after_2ph_C = CP.HAPropsSI('T', 'H', h_air_after_2ph, 'P', 101325.0, 'W', W_air_out) - 273.15
        except Exception:
            T_air_after_2ph_C = T_air_2ph_in - (Q_2ph - Q_latent) / C_air if C_air > 0 else T_air_2ph_in

        # SH zone (dry sensible) — 공기 입구는 flow 방향: counter=신선, parallel=2상 통과 후
        Q_SH = 0.0
        h_ref_out_J = h_in_J + Q_2ph / m_dot_ref
        if ref_fully_evap and UA_SH_actual > 0:
            try:
                cp_ref_SH = CP.PropsSI('C', 'P', P_evap_Pa, 'Q', 1, fluid)
            except Exception:
                cp_ref_SH = 1700
            C_ref = m_dot_ref * cp_ref_SH
            Cmin_SH = min(C_ref, C_air)
            Cmax_SH = max(C_ref, C_air)
            Cr = Cmin_SH / Cmax_SH if Cmax_SH > 0 else 0
            NTU_SH = UA_SH_actual / Cmin_SH if Cmin_SH > 0 else 0
            eps_SH = _eps_evap(NTU_SH, Cr, flow_arr)
            T_air_SH_in = T_air_in_C if flow_arr == 'counter' else T_air_after_2ph_C
            Q_SH = max(0.0, eps_SH * Cmin_SH * (T_air_SH_in - T_evap_C))
            h_ref_out_J = h_v + Q_SH / m_dot_ref

        # 2상 공기 입구 업데이트 (counter면 SH 통과 후, parallel이면 신선 고정)
        if flow_arr == 'counter':
            T_air_2ph_new = T_air_in_C - Q_SH / C_air if C_air > 0 else T_air_in_C
            h_air_2ph_new = h_air_in - Q_SH / m_dot_air
        else:
            T_air_2ph_new = T_air_in_C
            h_air_2ph_new = h_air_in

        if abs(T_air_2ph_new - T_air_2ph_in) < 0.03:
            T_air_2ph_in, h_air_2ph_in = T_air_2ph_new, h_air_2ph_new
            break
        T_air_2ph_in, h_air_2ph_in = T_air_2ph_new, h_air_2ph_new

    eps_h = eps_2ph_w  # 하위호환 (진단/BF 참조)
    UA_2ph_actual = UA_2ph_full * zeta
    n_iter = 50
    converged = True

    # 공기 최종 출구온도 (counter=공기가 2상에서 마지막, parallel=SH에서 마지막)
    if flow_arr == 'counter':
        T_air_out_C = T_air_after_2ph_C
    else:
        T_air_out_C = (T_air_after_2ph_C - Q_SH / C_air) if C_air > 0 else T_air_after_2ph_C

    # ── 11. Q_total 집계 ──
    Q_total = Q_2ph + Q_SH
    Q_sensible_total = max(0.0, Q_total - Q_latent)
    Q_sensible_2ph = Q_2ph  # 하위호환 (2상 zone에서 냉매로 간 열 = 증발 잠열분)
    h_air_out = h_air_in - Q_total / m_dot_air

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

    # ═══════ 냉매 charge holdup (ζ zone 분할) ═══════
    # Semi는 moving boundary라 zone 길이 비율 ζ를 직접 계산 → 정확한 zone 분할.
    #   2상 zone(길이 ζ): void fraction을 quality 구간 [x_in, 1] 적분 (비선형 반영)
    #   SH zone(길이 1-ζ): 과열 증기, CoolProp(P, T_avg)
    # x_avg 1점 근사는 void(x)의 비선형성을 놓쳐 액 holdup 과대 → 10점 적분으로 개선.
    from components.correlations import void_fraction as _vf
    void_model = params.get('void_model', _vf.DEFAULT)
    A_cross = math.pi * D_i ** 2 / 4.0
    V_internal = A_cross * L_tube_total
    m_per_tube = m_dot_ref / max(n_circuits, 1)  # 회로 기준 G (alpha와 동일, On 정합)
    # 입구 quality
    x_in_2ph = max(0.0, min(1.0, (h_in_J - h_l) / max(h_fg, 1.0)))
    # 2상 zone: quality [x_in, 1] 구간 10점 적분으로 평균밀도
    _N_int = 10
    _rho_sum = 0.0
    for _i in range(_N_int):
        _x = x_in_2ph + (1.0 - x_in_2ph) * (_i + 0.5) / _N_int  # midpoint
        _a = _vf.evaluate(void_model, x=_x, P_Pa=P_evap_Pa,
                          m_dot=m_per_tube, D_i=D_i, fluid=fluid)
        _rho_sum += _vf.mean_density(_a, P_evap_Pa, fluid)
    rho_2ph = _rho_sum / _N_int
    M_2ph = rho_2ph * (zeta * V_internal)
    # SH zone (과열 증기)
    if zeta < 0.999:
        T_SH_avg_K = 0.5 * (T_evap_K + T_ref_out_K)
        try:
            rho_SH = CP.PropsSI('D', 'P', P_evap_Pa, 'T', T_SH_avg_K, fluid)
        except Exception:
            rho_SH = CP.PropsSI('D', 'P', P_evap_Pa, 'Q', 1, fluid)
        M_SH = rho_SH * ((1.0 - zeta) * V_internal)
    else:
        M_SH = 0.0
    M_holdup = M_2ph + M_SH

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
        'M_holdup': M_holdup,
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
