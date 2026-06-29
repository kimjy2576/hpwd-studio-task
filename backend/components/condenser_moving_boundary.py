"""
Condenser (L2 Semi-empirical / Cascade)
═══════════════════════════════════════════════════════════════════════
3-zone cascade ε-NTU + Schmidt fin + condensation correlation registry.

진영님 정리:
  ✓ B 옵션: Schmidt fin + correlation은 쓰되 cascade 방식 (≈ 400줄)
  ✓ Evap 모듈 안 건드림, 별도 모듈
  ✓ Evap L2와 동등한 수준

═══ 차이점 (vs L1 condenser_off_design) ═══
L1: UA / ε 직접 입력 (사용자 fitting)
L2: UA / α_zone를 correlation으로 자동 계산
    • α_air: Wang/Kim/McQuiston (air_side registry)
    • α_ref_2ph: Shah/Cavallini-Smith/Dobson-Chato/Akers (condensation registry)
    • α_ref_deSH/SC: Dittus-Boelter/Gnielinski (single_phase registry)
    • η_fin: Schmidt/Sector (fin_efficiency registry)

═══ Zone 구조 (응축기) ═══
Zone 1: De-SH    — vapor cooling (T_in_SH → T_sat)
Zone 2: 2-phase  — condensation (x=1 → x=0)
Zone 3: SC       — liquid subcooling (T_sat → T_out)

═══ Cascade 방식 (B 옵션의 핵심) ═══
명시적 ζ (zone 길이) 풀지 않고 cascade 방식:
  1. 각 zone에 대해 α_ref / α_air / η_fin 계산
  2. UA_zone_full = 1 / (1/(α_ref × A_i) + 1/(α_air × A_o × η_fin))
     → 각 zone이 전체 면적 사용한다고 가정
  3. ε-NTU 적용해 Q_zone 계산
  4. 사후 zone 길이 ζ = Q_zone / Q_total 비율로 추정 (진단용)

이 방식의 의의:
  • Newton iteration 불필요 → 안정 수렴
  • Zone 분배가 sequential (cascade)이라 직관적
  • 명시적 ζ 풀이는 아니지만 모든 correlation은 그대로 사용

═══ Wet coil ═══
응축기는 dry — RH 변화 없음 (W_air_out = W_in)
"""

import math
import CoolProp.CoolProp as CP

from .correlations import condensation, single_phase, air_side, fin_efficiency, pressure_drop
# 2상 condensation·공기측은 On(segment march)과 동일 vendor 식 사용 (correlation 라이브러리 통일).
from _vendor.hx_sim.correlations import h_with_transition as _vendor_h_tp
from _vendor.hx_sim.correlations import compute_j_factor as _vendor_j_factor
from _vendor.hx_sim.properties import RefrigerantProperties as _VendorRefProps
from _vendor.hx_sim.properties import MoistAirProperties as _VendorAirProps


FLUIDS = ['R290']

# Dropdown 옵션 (boiling 대신 condensation registry)
CORR_2PH_OPTIONS = list(condensation.CORR_REGISTRY.keys())
CORR_SP_OPTIONS  = list(single_phase.CORR_REGISTRY.keys())
CORR_AIR_OPTIONS = list(air_side.CORR_REGISTRY.keys())
CORR_FIN_OPTIONS = list(fin_efficiency.CORR_REGISTRY.keys())


modelDescription = {
    'typeNo': 221,
    'name': 'Condenser (Moving Boundary / Cascade)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.7,
    'description': '3-zone cascade ε-NTU + Schmidt fin + condensation correlation (Shah/Cavallini/Dobson-Chato 등)',
    'backend': 'python',
    'variables': [
        # Material
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # Geometry — 11개
        {'name': 'D_o', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 5.0e-3, 'unit': 'm', 'description': '튜브 외경'},
        {'name': 'D_i', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 4.6e-3, 'unit': 'm', 'description': '튜브 내경'},
        {'name': 'L_tube_total', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 3.84, 'unit': 'm', 'description': '튜브 총 길이'},
        {'name': 'N_tubes', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 16.0, 'unit': '-', 'description': '튜브 본수'},
        {'name': 'N_rows', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 4.0, 'unit': '-', 'description': '공기 row 수'},
        {'name': 'n_circuits', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 1.0, 'unit': '-',
         'description': '병렬 냉매 회로 수 (G = ṁ/n_circuits/A_cross). 검증 시 On circuit_mode의 회로수와 일치시킴'},
        {'name': 'void_model', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'Premoli', 'unit': '-',
         'options': ['Homogeneous', 'Zivi', 'Rigot', 'Hughmark', 'Premoli', 'Rouhani-Axelsson'],
         'description': 'Void fraction 모델 (charge holdup 계산용, default Premoli)'},
        {'name': 'flow_arrangement', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': 'counter', 'unit': '-',
         'options': ['counter', 'parallel'],
         'description': '공기-냉매 흐름 배치 (counter=대향류 default, parallel=평행류). On과 동일'},
        {'name': 'P_t', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 14.14e-3, 'unit': 'm', 'description': 'Transverse pitch'},
        {'name': 'P_l', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 10.0e-3, 'unit': 'm', 'description': 'Longitudinal pitch'},
        {'name': 't_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.11e-3, 'unit': 'm', 'description': '핀 두께'},
        {'name': 'FPI', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 20.0, 'unit': 'fins/inch', 'description': 'FPI'},
        {'name': 'k_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 200.0, 'unit': 'W/(m·K)', 'description': '핀 열전도율'},
        {'name': 'A_o_face', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.0135744, 'unit': 'm²', 'description': '정면 (face) 면적'},

        # Correlation
        {'name': 'corr_cond', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': 'shah1979', 'unit': '-',
         'options': ['shah1979', 'cavallini2006', 'dobson_chato1998'],
         'description': '2-phase condensation correlation (On과 동일 vendor 식)'},
        {'name': 'corr_SP', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': single_phase.DEFAULT, 'unit': '-',
         'options': CORR_SP_OPTIONS,
         'description': 'Single-phase (deSH/SC) correlation'},
        {'name': 'corr_air', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': 'wang2000_plain', 'unit': '-',
         'options': ['wang2000_plain', 'gray_webb1986'],
         'description': '공기측 j-factor correlation (On과 동일 vendor 식)'},
        {'name': 'corr_fin', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': fin_efficiency.DEFAULT, 'unit': '-',
         'options': CORR_FIN_OPTIONS,
         'description': 'Fin 효율 correlation'},

        # Fitting
        {'name': 'htc_corr_cond', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'Condensation α 보정'},
        {'name': 'htc_corr_SP', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'Single-phase α 보정'},
        {'name': 'htc_corr_air', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '공기측 α 보정'},
        {'name': 'dP_ref', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.03, 'unit': '-',
         'description': '냉매 측 압력 손실 비율'},

        # Inputs
        {'name': 'P_cond', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '응축 압력 (abs)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피 (compressor 출구, SH)'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 RH'},
        {'name': 'V_air_CMM', 'causality': 'input', 'type': 'Real',
         'unit': 'CMM', 'description': '공기 풍량 (m³/min, CMM) — 한국 HVAC 표준 단위'},

        # Outputs
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'kJ/kg', 'description': '냉매 출구 엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'bar', 'description': '냉매 출구 압력'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': '출구 quality (음수=SC)'},
        {'name': 'SC_out', 'causality': 'output', 'type': 'Real', 'unit': 'K', 'description': '출구 과냉도'},
        {'name': 'T_cond', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '응축 포화 온도'},
        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real', 'unit': '°C', 'description': '공기 출구 온도'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real', 'unit': '%', 'description': '공기 출구 RH'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real', 'unit': 'kg/kg', 'description': '공기 출구 humidity'},
        {'name': 'Q_total', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': '총 열교환량'},
        {'name': 'Q_deSH', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': 'De-SH zone 열량'},
        {'name': 'Q_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': '2-phase zone 열량'},
        {'name': 'Q_SC', 'causality': 'output', 'type': 'Real', 'unit': 'W', 'description': 'SC zone 열량'},
        {'name': 'L_deSH_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': 'De-SH zone 길이 비율'},
        {'name': 'L_2ph_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': '2-phase zone 길이 비율'},
        {'name': 'L_SC_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': 'SC zone 길이 비율'},
        {'name': 'M_holdup', 'causality': 'output', 'type': 'Real', 'unit': 'kg',
         'description': '내부 냉매 질량 (charge holdup, zone 분할 + void fraction)'},
        {'name': 'M_deSH', 'causality': 'output', 'type': 'Real', 'unit': 'kg', 'description': 'De-SH zone 냉매 질량'},
        {'name': 'M_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'kg', 'description': '2상 zone 냉매 질량 (void fraction 적분)'},
        {'name': 'M_SC', 'causality': 'output', 'type': 'Real', 'unit': 'kg', 'description': 'SC zone 냉매 질량 (과냉 액)'},
        # 진단 (계산된 α, UA)
        {'name': 'alpha_air', 'causality': 'output', 'type': 'Real', 'unit': 'W/(m²·K)', 'description': '공기측 α (계산값)'},
        {'name': 'alpha_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'W/(m²·K)', 'description': '2-phase α (응축)'},
        {'name': 'alpha_SP', 'causality': 'output', 'type': 'Real', 'unit': 'W/(m²·K)', 'description': 'Single-phase α (deSH/SC)'},
        {'name': 'eta_fin', 'causality': 'output', 'type': 'Real', 'unit': '-', 'description': 'Fin 효율'},
        {'name': 'UA_2ph_full', 'causality': 'output', 'type': 'Real', 'unit': 'W/K', 'description': '2-phase zone 전체-면적 UA'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


# ════════════════════════════════════════════════════════════════════
# Helper functions
# ════════════════════════════════════════════════════════════════════
def _humid_air(T_C, RH_pct, P_atm=101325.0):
    """Humid air properties (L2 evap의 helper와 동일 패턴)."""
    try:
        from CoolProp.HumidAirProp import HAPropsSI
        T_K = T_C + 273.15
        RH = max(0.001, min(0.999, RH_pct / 100.0))
        W = HAPropsSI('W', 'T', T_K, 'P', P_atm, 'R', RH)
        h = HAPropsSI('H', 'T', T_K, 'P', P_atm, 'R', RH)
        T_dp = HAPropsSI('Tdp', 'T', T_K, 'P', P_atm, 'R', RH)
        cp = HAPropsSI('cp_ha', 'T', T_K, 'P', P_atm, 'R', RH)
        return W, h, T_dp, cp
    except Exception:
        T_K = T_C + 273.15
        RH = max(0.001, min(0.999, RH_pct / 100.0))
        Pws = 611.2 * math.exp(17.62 * T_C / (243.12 + T_C))
        Pw = RH * Pws
        W = 0.622 * Pw / max(P_atm - Pw, 1.0)
        cp = 1006 + 1860 * W
        h = cp * T_C * 1000 + W * 2501e3
        T_dp = T_K - 5
        return W, h, T_dp, cp


def _eps_NTU_C0(NTU):
    if NTU <= 0:
        return 0.0
    if NTU > 50:
        return 1.0
    return 1.0 - math.exp(-NTU)


def _eps_NTU_counter(NTU, Cr):
    if NTU <= 0:
        return 0.0
    if Cr <= 1e-6:
        return _eps_NTU_C0(NTU)
    if Cr >= 1.0 - 1e-6:
        return NTU / (1.0 + NTU)
    arg = -NTU * (1.0 - Cr)
    if arg < -50:
        return 1.0 / Cr if Cr < 1 else 1.0
    e = math.exp(arg)
    return (1.0 - e) / (1.0 - Cr * e)


def _eps_NTU_parallel(NTU, Cr):
    if NTU <= 0:
        return 0.0
    if Cr <= 1e-6:
        return _eps_NTU_C0(NTU)
    denom = 1.0 + Cr
    arg = -NTU * denom
    if arg < -50:
        return 1.0 / denom
    return (1.0 - math.exp(arg)) / denom


def _eps_NTU(NTU, Cr, flow):
    """flow arrangement에 따른 ε-NTU. Cr=0이면 둘 다 1-exp(-NTU)."""
    if flow == 'parallel':
        return _eps_NTU_parallel(NTU, Cr)
    return _eps_NTU_counter(NTU, Cr)


def _lmtd(dT_a, dT_b):
    """로그평균온도차 (zone 길이 = Q/(UA_full·ΔT_lm) 계산용)."""
    dT_a = max(dT_a, 1e-6)
    dT_b = max(dT_b, 1e-6)
    if abs(dT_a - dT_b) < 1e-9:
        return dT_a
    return (dT_a - dT_b) / math.log(dT_a / dT_b)


def _P_sat_water(T_C):
    if T_C < -50 or T_C > 200:
        T_C = max(-50, min(200, T_C))
    A, B, C = 8.07131, 1730.63, 233.426
    P_mmHg = 10 ** (A - B / (T_C + C))
    return P_mmHg * 133.322


# ════════════════════════════════════════════════════════════════════
# Main step
# ════════════════════════════════════════════════════════════════════

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
    D_o = float(params.get('D_o', 5.0e-3))
    D_i = float(params.get('D_i', 4.6e-3))
    L_tube_total = float(params.get('L_tube_total', 3.84))
    N_tubes = float(params.get('N_tubes', 16.0))
    N_rows = float(params.get('N_rows', 4.0))
    n_circuits = float(params.get('n_circuits', 1.0))  # 병렬 회로 수 (G 결정)
    P_t = float(params.get('P_t', 14.14e-3))
    P_l = float(params.get('P_l', 10.0e-3))
    t_fin = float(params.get('t_fin', 0.11e-3))
    FPI = float(params.get('FPI', 20.0))
    k_fin = float(params.get('k_fin', 200.0))
    A_o_face = float(params.get('A_o_face', 0.0135744))
    corr_cond = params.get('corr_cond', 'shah1979')
    corr_SP = params.get('corr_SP', single_phase.DEFAULT)
    corr_air = params.get('corr_air', 'wang2000_plain')
    corr_fin = params.get('corr_fin', fin_efficiency.DEFAULT)
    htc_corr_cond = float(params.get('htc_corr_cond', 1.0))
    htc_corr_SP = float(params.get('htc_corr_SP', 1.0))
    htc_corr_air = float(params.get('htc_corr_air', 1.0))
    dP_ref = float(params.get('dP_ref', 0.03))

    # ── Inputs ──
    P_cond_bar = float(input.get('P_cond', 17.0))
    h_in_kjkg = float(input.get('h_in', 680.0))
    m_dot_ref = float(input.get('m_dot_ref', 0.012))
    T_air_in_C = float(input.get('T_air_in', 35.0))
    RH_air_in = float(input.get('RH_air_in', 50.0))
    m_dot_air = _cmm_to_mass(
        V_air_CMM=float(input.get('V_air_CMM', 25.42)),
        T_air_C=T_air_in_C, RH=RH_air_in,
    )

    if P_cond_bar <= 0 or m_dot_ref <= 0 or m_dot_air <= 0:
        raise ValueError(f"입력 0 이하: P={P_cond_bar}, ṁ_ref={m_dot_ref}, ṁ_air={m_dot_air}")

    P_cond_Pa = P_cond_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    P_fin = 0.0254 / FPI

    # ── 1. 냉매 입구/포화 상태 ──
    try:
        T_cond_K = CP.PropsSI('T', 'P', P_cond_Pa, 'Q', 0.5, fluid)
        h_l = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 0, fluid)
        h_v = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 1, fluid)
        h_fg = h_v - h_l
    except Exception as e:
        raise ValueError(f"냉매 포화 상태 실패: {e}")
    T_cond_C = T_cond_K - 273.15

    if h_in_J >= h_v:
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond_K + 30.0
        x_in = 1.0
    elif h_in_J >= h_l:
        x_in = (h_in_J - h_l) / h_fg
        T_ref_in_K = T_cond_K
    else:
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond_K - 5.0
        x_in = 0.0
    T_ref_in_C = T_ref_in_K - 273.15

    # ── 2. 공기 입구 ──
    W_in, _, _, cp_air = _humid_air(T_air_in_C, RH_air_in)
    C_air = m_dot_air * cp_air

    # ── 3. 외부/내부 면적 ──
    A_tube_outer = math.pi * D_o * L_tube_total
    n_fins_per_tube = L_tube_total / N_tubes / P_fin if P_fin > 0 else 0
    A_per_fin = 2.0 * (P_t * P_l - math.pi * (D_o ** 2) / 4.0)
    A_fin_total = N_tubes * n_fins_per_tube * A_per_fin
    A_o = A_tube_outer + A_fin_total
    A_i = math.pi * D_i * L_tube_total

    # ── 4. 공기측 α — On(segment march)과 동일 vendor j-factor 식 ──
    T_air_avg_K = (T_air_in_C + 273.15 + T_cond_K) / 2.0
    _mu_a = _VendorAirProps.mu_air(T_air_avg_K, 101325.0)
    _Pr_a = _VendorAirProps.Pr_air(T_air_avg_K, 101325.0)
    _cp_a = _VendorAirProps.cp_air(T_air_avg_K, 0.0, 101325.0)
    _Dc = D_o + 2.0 * t_fin
    _gap = P_fin - t_fin
    _sigma = max((P_t - _Dc) * _gap / (P_t * P_fin), 0.1)
    _A_c = _sigma * A_o_face
    _G_air = m_dot_air / max(_A_c, 1e-9)
    _Re_Dc = _G_air * _Dc / max(_mu_a, 1e-9)
    _j_air = _vendor_j_factor(corr_air, Re_Dc=_Re_Dc, Nr=int(N_rows), Dc=_Dc,
                              Pt=P_t, Pl=P_l, FPI=FPI, fin_thickness=t_fin)
    alpha_air = _j_air * _G_air * _cp_a / _Pr_a ** (2.0 / 3.0)
    alpha_air *= htc_corr_air

    eta_fin = fin_efficiency.evaluate(corr_fin,
                                       D_o=D_o, P_t=P_t, P_l=P_l,
                                       t_fin=t_fin, k_fin=k_fin, alpha_o=alpha_air)
    eta_overall = (A_tube_outer + A_fin_total * eta_fin) / A_o if A_o > 0 else eta_fin

    # ── 5. 냉매측 α — zone별 (2상은 On과 동일 vendor condensation 식) ──
    _A_cross = math.pi * D_i ** 2 / 4.0
    _G_2ph = (m_dot_ref / max(n_circuits, 1)) / max(_A_cross, 1e-12)
    _ref_obj = _VendorRefProps(fluid)
    Q_2ph_demand = m_dot_ref * h_fg
    q_flux_cond_est = Q_2ph_demand / max(A_i, 1e-6)
    alpha_2ph = _vendor_h_tp(x=0.5, G=_G_2ph, Di=D_i, q_flux=q_flux_cond_est,
                             ref=_ref_obj, P=P_cond_Pa, mode='cond',
                             hx_type='FT', cond_corr=corr_cond)
    alpha_2ph *= htc_corr_cond

    # 단상(deSH/SC)도 On과 동일 vendor 식 — h_with_transition이 x로 영역 분기
    #   x>1.05 → 과열 vapor Gnielinski / x<0 → 과냉 liquid Gnielinski
    alpha_deSH = _vendor_h_tp(x=1.5, G=_G_2ph, Di=D_i, q_flux=q_flux_cond_est,
                              ref=_ref_obj, P=P_cond_Pa, mode='cond', hx_type='FT')
    alpha_deSH *= htc_corr_SP

    alpha_SC = _vendor_h_tp(x=-0.5, G=_G_2ph, Di=D_i, q_flux=q_flux_cond_est,
                            ref=_ref_obj, P=P_cond_Pa, mode='cond', hx_type='FT')
    alpha_SC *= htc_corr_SP

    # ── 6. UA per zone (전체 면적 가정 — cascade 방식) ──
    UA_deSH_full = 1.0 / (1.0 / (alpha_deSH * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_2ph_full  = 1.0 / (1.0 / (alpha_2ph  * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_SC_full   = 1.0 / (1.0 / (alpha_SC   * A_i) + 1.0 / (alpha_air * A_o * eta_overall))

    # ── 7. Moving Boundary 3-zone (각 zone 신선 공기 = cross-flow 근사) ──
    # 증발기 Semi와 동일 패러다임: 경계를 demand로 풀어 zone 길이 ζ를 직접 결정.
    #   ζ_deSH: deSH 끝(h_v)까지, ζ_2ph: 2상 끝(h_l)까지, ζ_SC = 나머지.
    # cascade의 공기 순차 가열(counter-flow 가정) 대신 각 zone이 신선 공기를 봄
    # → SC zone도 신선 공기 ΔT를 받아 Q 과소 해소.
    flow_arr = params.get('flow_arrangement', 'counter')
    try:
        cp_v = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'T', 0.5 * (T_ref_in_K + T_cond_K), fluid)
    except Exception:
        cp_v = 1800.0
    try:
        cp_l = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'Q', 0, fluid)
    except Exception:
        cp_l = 2700.0
    C_ref_v = m_dot_ref * cp_v
    C_ref_l = m_dot_ref * cp_l

    def _Q_deSH(z, T_air):
        if z <= 1e-9:
            return 0.0
        Cmin = min(C_ref_v, C_air); Cmax = max(C_ref_v, C_air)
        Cr = Cmin / Cmax if Cmax > 0 else 0.0
        NTU = (UA_deSH_full * z) / Cmin if Cmin > 0 else 0.0
        return _eps_NTU(NTU, Cr, flow_arr) * Cmin * (T_ref_in_C - T_air)

    def _Q_2ph(z, T_air):
        if z <= 1e-9:
            return 0.0
        NTU = (UA_2ph_full * z) / C_air if C_air > 0 else 0.0
        return _eps_NTU_C0(NTU) * C_air * (T_cond_C - T_air)

    def _Q_SC(z, T_air):
        if z <= 1e-9:
            return 0.0
        Cmin = min(C_ref_l, C_air); Cmax = max(C_ref_l, C_air)
        Cr = Cmin / Cmax if Cmax > 0 else 0.0
        NTU = (UA_SC_full * z) / Cmin if Cmin > 0 else 0.0
        return _eps_NTU(NTU, Cr, flow_arr) * Cmin * (T_cond_C - T_air)

    def _bisect_zeta(Qfunc, demand, z_max):
        """Q(z)=demand 만족하는 z (Q는 z에 단조증가). z_max로도 부족하면 z_max 반환."""
        if demand <= 1e-9 or z_max <= 1e-9:
            return 0.0
        if Qfunc(z_max) <= demand:
            return z_max
        lo, hi = 0.0, z_max
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if Qfunc(mid) < demand:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        return 0.5 * (lo + hi)

    # flow_arrangement에 따라 공기 누적 방향 결정 (zone 내 ε도 flow에 맞춤).
    #   counter : 냉매 출구쪽(SC)이 신선 공기 → deSH로 누적 (역순)
    #   parallel: 냉매 입구쪽(deSH)이 신선 공기 → SC로 누적 (순서)
    # zone 길이 ζ는 냉매 enthalpy demand(deSH/2상)로, SC는 나머지. 공기 의존 → iteration.
    C_air_safe = max(C_air, 1e-9)
    Q_deSH_demand = m_dot_ref * max(0.0, h_in_J - h_v)
    Q_2ph_demand = m_dot_ref * (h_v - h_l)
    has_deSH = Q_deSH_demand > 1e-6 and T_ref_in_C > T_cond_C

    def _zone_air_temps(zd, z2, zs):
        """현재 ζ에서 각 zone 공기 입구온도 (flow 방향으로 누적)."""
        if flow_arr == 'parallel':
            Ta_deSH = T_air_in_C
            Qd = min(_Q_deSH(zd, Ta_deSH), Q_deSH_demand) if has_deSH else 0.0
            Ta_2ph = Ta_deSH + Qd / C_air_safe
            Q2 = min(_Q_2ph(z2, Ta_2ph), Q_2ph_demand)
            Ta_SC = Ta_2ph + Q2 / C_air_safe
        else:  # counter
            Ta_SC = T_air_in_C
            Qs = _Q_SC(zs, Ta_SC); Qs = max(0.0, min(Qs, C_ref_l * (T_cond_C - Ta_SC)))
            Ta_2ph = Ta_SC + Qs / C_air_safe
            Q2 = min(_Q_2ph(z2, Ta_2ph), Q_2ph_demand)
            Ta_deSH = Ta_2ph + Q2 / C_air_safe
        return Ta_deSH, Ta_2ph, Ta_SC

    zeta_deSH = 0.15 if has_deSH else 0.0
    zeta_2ph = 0.6
    zeta_SC = max(0.0, 1.0 - zeta_deSH - zeta_2ph)
    for _it in range(40):
        Ta_deSH, Ta_2ph, Ta_SC = _zone_air_temps(zeta_deSH, zeta_2ph, zeta_SC)
        zeta_2ph_new = _bisect_zeta(lambda z: _Q_2ph(z, Ta_2ph), Q_2ph_demand, 1.0)
        if has_deSH:
            zeta_deSH_new = _bisect_zeta(lambda z: _Q_deSH(z, Ta_deSH),
                                         Q_deSH_demand, max(0.0, 1.0 - zeta_2ph_new))
        else:
            zeta_deSH_new = 0.0
        zeta_SC_new = max(0.0, 1.0 - zeta_deSH_new - zeta_2ph_new)
        if (abs(zeta_deSH_new - zeta_deSH) + abs(zeta_2ph_new - zeta_2ph)
                + abs(zeta_SC_new - zeta_SC)) < 1e-5:
            zeta_deSH, zeta_2ph, zeta_SC = zeta_deSH_new, zeta_2ph_new, zeta_SC_new
            break
        _a = 0.5
        zeta_deSH = _a * zeta_deSH_new + (1 - _a) * zeta_deSH
        zeta_2ph = _a * zeta_2ph_new + (1 - _a) * zeta_2ph
        zeta_SC = max(0.0, 1.0 - zeta_deSH - zeta_2ph)

    # 수렴된 ζ로 최종 Q
    Ta_deSH, Ta_2ph, Ta_SC = _zone_air_temps(zeta_deSH, zeta_2ph, zeta_SC)
    Q_SC = _Q_SC(zeta_SC, Ta_SC)
    Q_SC = max(0.0, min(Q_SC, C_ref_l * (T_cond_C - Ta_SC)))
    Q_2ph_total = min(_Q_2ph(zeta_2ph, Ta_2ph), Q_2ph_demand)
    Q_deSH = min(_Q_deSH(zeta_deSH, Ta_deSH), Q_deSH_demand) if has_deSH else 0.0
    # 공기 최종 출구 (counter=deSH쪽 마지막, parallel=SC쪽 마지막)
    if flow_arr == 'parallel':
        T_air_exit_C = Ta_SC + Q_SC / C_air_safe
    else:
        T_air_exit_C = Ta_deSH + Q_deSH / C_air_safe

    # ── 8. 출구 상태 ──
    Q_total = Q_deSH + Q_2ph_total + Q_SC
    h_out_J = h_in_J - Q_total / m_dot_ref if m_dot_ref > 0 else h_in_J

    if h_out_J >= h_v:
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond_K + max(0, (h_out_J - h_v) / 1800.0)
        x_out = 1.0 + max(0.0, (h_out_J - h_v) / max(h_fg, 1.0))
        SC_out = 0.0
    elif h_out_J >= h_l:
        x_out = max(0.0, min(1.0, (h_out_J - h_l) / h_fg))
        T_ref_out_K = T_cond_K
        SC_out = 0.0
    else:
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond_K - max(0, (h_l - h_out_J) / 2700.0)
        x_out = -max(0.0, (h_l - h_out_J) / max(h_fg, 1.0))
        SC_out = max(0.0, T_cond_K - T_ref_out_K)

    T_ref_out_C = T_ref_out_K - 273.15

    # 공기 출구온도 — moving boundary는 각 zone 신선 공기이므로 전체 Q로 산출
    T_air_out_C = T_air_exit_C  # counter: 공기 출구 = deSH쪽

    P_atm = 101325.0
    P_ws_out = _P_sat_water(T_air_out_C)
    P_w_out = W_in / (W_in + 0.622) * P_atm
    RH_out = max(0.0, min(100.0, P_w_out / P_ws_out * 100.0)) if P_ws_out > 0 else 0.0

    # ── zone 길이 비율 — moving boundary가 ζ를 직접 풀었으므로 그대로 사용 ──
    L_deSH_frac = zeta_deSH
    L_2ph_frac  = zeta_2ph
    L_SC_frac   = zeta_SC

    # ── charge holdup (zone 분할 + void fraction) ──
    from components.correlations import void_fraction as _vf
    void_model = params.get('void_model', _vf.DEFAULT)
    V_internal = (math.pi * D_i ** 2 / 4.0) * L_tube_total
    m_per_circuit = m_dot_ref / max(n_circuits, 1)  # 회로 기준 G (alpha와 동일)
    # deSH zone: 과열 vapor 평균밀도
    if L_deSH_frac > 1e-6:
        try:
            rho_deSH = CP.PropsSI('D', 'P', P_cond_Pa, 'T', 0.5 * (T_ref_in_K + T_cond_K), fluid)
        except Exception:
            rho_deSH = CP.PropsSI('D', 'P', P_cond_Pa, 'Q', 1, fluid)
        M_deSH = rho_deSH * (L_deSH_frac * V_internal)
    else:
        M_deSH = 0.0
    # 2상 zone: void fraction을 quality [x_out_2ph, 1] 10점 적분 (응축은 1→0 방향)
    x_out_2ph = max(0.0, min(1.0, x_out))  # SC 출구→0, 2상 출구→x_out, 과열→1(L=0)
    _N_int = 10
    _rho_sum = 0.0
    for _i in range(_N_int):
        _x = x_out_2ph + (1.0 - x_out_2ph) * (_i + 0.5) / _N_int
        _a = _vf.evaluate(void_model, x=_x, P_Pa=P_cond_Pa,
                          m_dot=m_per_circuit, D_i=D_i, fluid=fluid)
        _rho_sum += _vf.mean_density(_a, P_cond_Pa, fluid)
    rho_2ph = _rho_sum / _N_int
    M_2ph = rho_2ph * (L_2ph_frac * V_internal)
    # SC zone: 과냉 liquid 평균밀도
    if L_SC_frac > 1e-6:
        try:
            rho_SC = CP.PropsSI('D', 'P', P_cond_Pa, 'T', 0.5 * (T_cond_K + T_ref_out_K), fluid)
        except Exception:
            rho_SC = CP.PropsSI('D', 'P', P_cond_Pa, 'Q', 0, fluid)
        M_SC = rho_SC * (L_SC_frac * V_internal)
    else:
        M_SC = 0.0
    M_holdup = M_deSH + M_2ph + M_SC

    P_ref_out_bar = P_cond_bar * (1.0 - dP_ref)

    return {
        'outputs': {
            'T_ref_out': T_ref_out_C,
            'h_ref_out': h_out_J / 1000.0,
            'P_ref_out': P_ref_out_bar,
            'quality_out': x_out,
            'SC_out': SC_out,
            'T_cond': T_cond_C,
            'T_air_out': T_air_out_C,
            'RH_air_out': RH_out,
            'W_air_out': W_in,
            'Q_total': Q_total,
            'Q_deSH': Q_deSH,
            'Q_2ph': Q_2ph_total,
            'Q_SC': Q_SC,
            'L_deSH_fraction': L_deSH_frac,
            'L_2ph_fraction': L_2ph_frac,
            'L_SC_fraction': L_SC_frac,
            'M_holdup': M_holdup,
            'M_deSH': M_deSH,
            'M_2ph': M_2ph,
            'M_SC': M_SC,
            'alpha_air': alpha_air,
            'alpha_2ph': alpha_2ph,
            'alpha_SP': (alpha_deSH + alpha_SC) / 2.0,
            'eta_fin': eta_fin,
            'UA_2ph_full': UA_2ph_full,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    
    D_o = float(params.get('D_o', 5.0e-3))
    D_i = float(params.get('D_i', 4.6e-3))
    if D_i >= D_o:
        issues.append({'key': 'D_i', 'msg': f'D_i ≥ D_o ({D_i*1000:.2f} ≥ {D_o*1000:.2f}mm)'})
    
    P_t = float(params.get('P_t', 14.14e-3))
    if P_t <= D_o:
        issues.append({'key': 'P_t', 'msg': f'P_t ({P_t*1000:.1f}mm) ≤ D_o ({D_o*1000:.1f}mm)'})
    
    FPI = float(params.get('FPI', 20.0))
    t_fin = float(params.get('t_fin', 0.11e-3))
    fin_pitch = 0.0254 / FPI
    if t_fin >= fin_pitch:
        issues.append({'key': 't_fin', 'msg': f'핀 두께({t_fin*1000:.2f}) ≥ 핀 간격({fin_pitch*1000:.2f}mm)'})
    
    corr_cond = params.get('corr_cond', 'shah1979')
    if corr_cond not in ('shah1979', 'cavallini2006', 'dobson_chato1998'):
        issues.append({'key': 'corr_cond', 'msg': f"unknown condensation correlation '{corr_cond}'"})
    
    return issues
