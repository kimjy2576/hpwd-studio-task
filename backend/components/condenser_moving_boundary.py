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
         'group': 'Geometry', 'start': 7.0e-3, 'unit': 'm', 'description': '튜브 외경'},
        {'name': 'D_i', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 6.5e-3, 'unit': 'm', 'description': '튜브 내경'},
        {'name': 'L_tube_total', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 10.0, 'unit': 'm', 'description': '튜브 총 길이'},
        {'name': 'N_tubes', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 24.0, 'unit': '-', 'description': '튜브 본수'},
        {'name': 'N_rows', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.0, 'unit': '-', 'description': '공기 row 수'},
        {'name': 'P_t', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 25.0e-3, 'unit': 'm', 'description': 'Transverse pitch'},
        {'name': 'P_l', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 22.0e-3, 'unit': 'm', 'description': 'Longitudinal pitch'},
        {'name': 't_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.12e-3, 'unit': 'm', 'description': '핀 두께'},
        {'name': 'FPI', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 12.0, 'unit': 'fins/inch', 'description': 'FPI'},
        {'name': 'k_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 200.0, 'unit': 'W/(m·K)', 'description': '핀 열전도율'},
        {'name': 'A_o_face', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.05, 'unit': 'm²', 'description': '정면 (face) 면적'},

        # Correlation
        {'name': 'corr_cond', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': condensation.DEFAULT, 'unit': '-',
         'options': CORR_2PH_OPTIONS,
         'description': '2-phase condensation correlation'},
        {'name': 'corr_SP', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': single_phase.DEFAULT, 'unit': '-',
         'options': CORR_SP_OPTIONS,
         'description': 'Single-phase (deSH/SC) correlation'},
        {'name': 'corr_air', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlation', 'start': air_side.DEFAULT, 'unit': '-',
         'options': CORR_AIR_OPTIONS,
         'description': '공기측 correlation'},
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
    corr_cond = params.get('corr_cond', condensation.DEFAULT)
    corr_SP = params.get('corr_SP', single_phase.DEFAULT)
    corr_air = params.get('corr_air', air_side.DEFAULT)
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

    # ── 4. 공기측 α + Schmidt fin ──
    T_air_avg_K = (T_air_in_C + 273.15 + T_cond_K) / 2.0
    alpha_air = air_side.evaluate(corr_air,
                                   m_dot_air=m_dot_air, T_air_avg_K=T_air_avg_K,
                                   D_o=D_o, P_t=P_t, P_l=P_l, P_fin=P_fin,
                                   t_fin=t_fin, N_row=int(N_rows), A_o_face=A_o_face)
    alpha_air *= htc_corr_air

    eta_fin = fin_efficiency.evaluate(corr_fin,
                                       D_o=D_o, P_t=P_t, P_l=P_l,
                                       t_fin=t_fin, k_fin=k_fin, alpha_o=alpha_air)
    eta_overall = (A_tube_outer + A_fin_total * eta_fin) / A_o if A_o > 0 else eta_fin

    # ── 5. 냉매측 α — zone별 ──
    Q_2ph_demand = m_dot_ref * h_fg
    q_flux_cond_est = Q_2ph_demand / max(A_i, 1e-6)
    alpha_2ph = condensation.evaluate(corr_cond,
                                       P_Pa=P_cond_Pa, x_avg=0.5,
                                       m_dot=m_dot_ref / max(N_tubes, 1),
                                       D_i=D_i, q_flux=q_flux_cond_est, fluid=fluid)
    alpha_2ph *= htc_corr_cond

    T_deSH_avg_K = (T_ref_in_K + T_cond_K) / 2.0 if h_in_J >= h_v else T_cond_K + 5
    alpha_deSH = single_phase.evaluate(corr_SP,
                                        P_Pa=P_cond_Pa, T_avg_K=T_deSH_avg_K,
                                        m_dot=m_dot_ref / max(N_tubes, 1),
                                        D_i=D_i, fluid=fluid, heating=False)
    alpha_deSH *= htc_corr_SP

    T_SC_avg_K = T_cond_K - 5.0
    alpha_SC = single_phase.evaluate(corr_SP,
                                      P_Pa=P_cond_Pa, T_avg_K=T_SC_avg_K,
                                      m_dot=m_dot_ref / max(N_tubes, 1),
                                      D_i=D_i, fluid=fluid, heating=False)
    alpha_SC *= htc_corr_SP

    # ── 6. UA per zone (전체 면적 가정 — cascade 방식) ──
    UA_deSH_full = 1.0 / (1.0 / (alpha_deSH * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_2ph_full  = 1.0 / (1.0 / (alpha_2ph  * A_i) + 1.0 / (alpha_air * A_o * eta_overall))
    UA_SC_full   = 1.0 / (1.0 / (alpha_SC   * A_i) + 1.0 / (alpha_air * A_o * eta_overall))

    # ── 7. Cascade 3-zone ──
    T_air_curr = T_air_in_C
    h_ref_curr = h_in_J
    Q_deSH = 0.0
    Q_2ph_total = 0.0
    Q_SC = 0.0

    # Zone 1: De-SH
    if h_ref_curr > h_v and T_air_curr < T_ref_in_C:
        try:
            cp_v = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'T', T_ref_in_K, fluid)
        except Exception:
            cp_v = 1800.0
        C_ref_v = m_dot_ref * cp_v
        C_min = min(C_ref_v, C_air)
        C_max = max(C_ref_v, C_air)
        Cr = C_min / C_max if C_max > 0 else 0.0

        Q_max_deSH_ref = m_dot_ref * (h_ref_curr - h_v)
        NTU = UA_deSH_full / C_min if C_min > 0 else 0
        eps = _eps_NTU_counter(NTU, Cr)
        if C_min > 0:
            Q_deSH = eps * C_min * (T_ref_in_C - T_air_curr)
            Q_deSH = max(0.0, min(Q_deSH, Q_max_deSH_ref))
        T_air_curr += Q_deSH / C_air if C_air > 0 else 0
        h_ref_curr -= Q_deSH / m_dot_ref if m_dot_ref > 0 else 0

    # Zone 2: 2-phase
    if h_ref_curr > h_l + 1e-3 and T_air_curr < T_cond_C - 0.05:
        Q_max_2ph_ref = m_dot_ref * (h_ref_curr - h_l)
        NTU = UA_2ph_full / C_air if C_air > 0 else 0
        eps = _eps_NTU_C0(NTU)
        Q_2ph_total = eps * C_air * (T_cond_C - T_air_curr)
        Q_2ph_total = max(0.0, min(Q_2ph_total, Q_max_2ph_ref))
        T_air_curr += Q_2ph_total / C_air if C_air > 0 else 0
        h_ref_curr -= Q_2ph_total / m_dot_ref if m_dot_ref > 0 else 0

    # Zone 3: SC
    if h_ref_curr <= h_l + 1e-3 and T_air_curr < T_cond_C - 0.05:
        try:
            cp_l = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'Q', 0, fluid)
        except Exception:
            cp_l = 2700.0
        C_ref_l = m_dot_ref * cp_l
        C_min = min(C_ref_l, C_air)
        C_max = max(C_ref_l, C_air)
        Cr = C_min / C_max if C_max > 0 else 0.0

        NTU = UA_SC_full / C_min if C_min > 0 else 0
        eps = _eps_NTU_counter(NTU, Cr)
        Q_SC = eps * C_min * (T_cond_C - T_air_curr)
        Q_SC = max(0.0, Q_SC)
        T_air_curr += Q_SC / C_air if C_air > 0 else 0
        h_ref_curr -= Q_SC / m_dot_ref if m_dot_ref > 0 else 0

    # ── 8. 출구 상태 ──
    Q_total = Q_deSH + Q_2ph_total + Q_SC
    h_out_J = h_ref_curr

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

    P_atm = 101325.0
    P_ws_out = _P_sat_water(T_air_curr)
    P_w_out = W_in / (W_in + 0.622) * P_atm
    RH_out = max(0.0, min(100.0, P_w_out / P_ws_out * 100.0)) if P_ws_out > 0 else 0.0

    if Q_total > 0:
        L_deSH_frac = Q_deSH / Q_total
        L_2ph_frac = Q_2ph_total / Q_total
        L_SC_frac = Q_SC / Q_total
    else:
        L_deSH_frac = L_2ph_frac = L_SC_frac = 0.0

    P_ref_out_bar = P_cond_bar * (1.0 - dP_ref)

    return {
        'outputs': {
            'T_ref_out': T_ref_out_C,
            'h_ref_out': h_out_J / 1000.0,
            'P_ref_out': P_ref_out_bar,
            'quality_out': x_out,
            'SC_out': SC_out,
            'T_cond': T_cond_C,
            'T_air_out': T_air_curr,
            'RH_air_out': RH_out,
            'W_air_out': W_in,
            'Q_total': Q_total,
            'Q_deSH': Q_deSH,
            'Q_2ph': Q_2ph_total,
            'Q_SC': Q_SC,
            'L_deSH_fraction': L_deSH_frac,
            'L_2ph_fraction': L_2ph_frac,
            'L_SC_fraction': L_SC_frac,
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
    
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    if D_i >= D_o:
        issues.append({'key': 'D_i', 'msg': f'D_i ≥ D_o ({D_i*1000:.2f} ≥ {D_o*1000:.2f}mm)'})
    
    P_t = float(params.get('P_t', 25.0e-3))
    if P_t <= D_o:
        issues.append({'key': 'P_t', 'msg': f'P_t ({P_t*1000:.1f}mm) ≤ D_o ({D_o*1000:.1f}mm)'})
    
    FPI = float(params.get('FPI', 12.0))
    t_fin = float(params.get('t_fin', 0.12e-3))
    fin_pitch = 0.0254 / FPI
    if t_fin >= fin_pitch:
        issues.append({'key': 't_fin', 'msg': f'핀 두께({t_fin*1000:.2f}) ≥ 핀 간격({fin_pitch*1000:.2f}mm)'})
    
    corr_cond = params.get('corr_cond', condensation.DEFAULT)
    if corr_cond not in CORR_2PH_OPTIONS:
        issues.append({'key': 'corr_cond', 'msg': f"unknown condensation correlation '{corr_cond}'"})
    
    return issues
