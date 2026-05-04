"""
Condenser (L2 Semi-empirical / Moving Boundary)
═══════════════════════════════════════════════════════════════════════
3-zone cascade ε-NTU with correlation-driven UA + Schmidt fin efficiency.

진영님 정리 (B 옵션):
  • Schmidt fin + correlation은 사용 (UA 자동 계산)
  • Cascade 방식 (zone 길이 명시적 ζ 풀이는 안 함)
  • Evap moving_boundary와 유사한 부가가치, 코드 간소화

Zone 구조 (응축기):
  Zone 1: De-SH    — vapor cooling, single-phase α (Dittus-Boelter)
  Zone 2: 2-phase  — condensation α (Shah/Cavallini/Dobson-Chato/Akers)
  Zone 3: SC       — liquid cooling, single-phase α

Cascade ε-NTU:
  T_air 점진 가열 → 각 zone에서 correlation으로 α 계산 → UA = UA_ref || UA_air → ε-NTU
  
  zone 길이 분배는 사후 추정 (Q_zone / UA_zone × LMTD)

Correlation registry:
  - condensation: Shah / Cavallini-Smith / Dobson-Chato / Akers
  - single-phase: Dittus-Boelter / Gnielinski (DeSH/SC 공통)
  - air-side:     Wang-Chang-Chi / Kim / McQuiston (evap과 공유)
  - fin-efficiency: Schmidt / Sector (evap과 공유)

Wet coil: 응축기는 dry 가정 (W_air_out = W_in)
"""

import math
import CoolProp.CoolProp as CP

from .correlations import condensation, single_phase, air_side, fin_efficiency

FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf']

CORR_2PH_OPTIONS = list(condensation.CORR_REGISTRY.keys())
CORR_SP_OPTIONS = list(single_phase.CORR_REGISTRY.keys())
CORR_AIR_OPTIONS = list(air_side.CORR_REGISTRY.keys())
CORR_FIN_OPTIONS = list(fin_efficiency.CORR_REGISTRY.keys())


modelDescription = {
    'typeNo': 221,
    'name': 'Condenser (Moving Boundary)',
    'category': 'refrigerant',
    'modelType': 'semi-empirical',
    'fidelity': 0.7,
    'description': '3-zone cascade ε-NTU with correlation-driven UA + Schmidt fin (응축).',
    'backend': 'python',
    'variables': [
        # ═══════ Material ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # ═══════ Geometry ═══════
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
         'description': '튜브 본수'},
        {'name': 'N_rows', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.0, 'unit': '-',
         'description': '공기 흐름 방향 row 수'},
        {'name': 'P_t', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 25.0e-3, 'unit': 'm',
         'description': 'Transverse pitch'},
        {'name': 'P_l', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 22.0e-3, 'unit': 'm',
         'description': 'Longitudinal pitch'},
        {'name': 't_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.12e-3, 'unit': 'm',
         'description': '핀 두께'},
        {'name': 'FPI', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 12.0, 'unit': 'fins/inch',
         'description': '핀 밀도'},
        {'name': 'k_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 200.0, 'unit': 'W/(m·K)',
         'description': '핀 열전도율 (Al~200, Cu~390)'},
        {'name': 'A_o_face', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.05, 'unit': 'm²',
         'description': '정면 (face) 면적'},

        # ═══════ Correlation 선택 ═══════
        {'name': 'corr_2ph', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': condensation.DEFAULT, 'unit': '-',
         'options': CORR_2PH_OPTIONS,
         'description': '응축 (2-phase) correlation'},
        {'name': 'corr_sp', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': single_phase.DEFAULT, 'unit': '-',
         'options': CORR_SP_OPTIONS,
         'description': 'Single-phase (DeSH/SC 공통) correlation'},
        {'name': 'corr_air', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': air_side.DEFAULT, 'unit': '-',
         'options': CORR_AIR_OPTIONS,
         'description': '공기측 correlation'},
        {'name': 'corr_fin', 'causality': 'parameter', 'type': 'String',
         'group': 'Geometry', 'start': fin_efficiency.DEFAULT, 'unit': '-',
         'options': CORR_FIN_OPTIONS,
         'description': 'Fin 효율 correlation'},

        # ═══════ Fitting ═══════
        {'name': 'htc_corr_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '2-phase α 보정'},
        {'name': 'htc_corr_sp', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'Single-phase α 보정'},
        {'name': 'htc_corr_air', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '공기측 α 보정'},
        {'name': 'dP_ref', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.03, 'unit': '-',
         'description': '냉매 측 압력 손실 비율'},

        # ═══════ Inputs ═══════
        {'name': 'P_cond', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '응축 압력 (abs)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피 (보통 SH vapor)'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 RH'},
        {'name': 'm_dot_air', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '공기 질량 유량'},

        # ═══════ Outputs ═══════
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real', 'unit': '°C',
         'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'kJ/kg',
         'description': '냉매 출구 엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real', 'unit': 'bar',
         'description': '냉매 출구 압력'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': '출구 quality (음수=SC)'},
        {'name': 'SC_out', 'causality': 'output', 'type': 'Real', 'unit': 'K',
         'description': '출구 과냉도'},
        {'name': 'T_cond', 'causality': 'output', 'type': 'Real', 'unit': '°C',
         'description': '응축 포화 온도'},
        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real', 'unit': '°C',
         'description': '공기 출구 온도'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real', 'unit': '%',
         'description': '공기 출구 RH'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real', 'unit': 'kg/kg',
         'description': '공기 출구 humidity (불변)'},
        {'name': 'Q_total', 'causality': 'output', 'type': 'Real', 'unit': 'W',
         'description': '총 열량'},
        {'name': 'Q_deSH', 'causality': 'output', 'type': 'Real', 'unit': 'W',
         'description': 'De-SH zone 열량'},
        {'name': 'Q_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'W',
         'description': '2-phase zone 열량'},
        {'name': 'Q_SC', 'causality': 'output', 'type': 'Real', 'unit': 'W',
         'description': 'SC zone 열량'},
        # 진단
        {'name': 'UA_deSH', 'causality': 'output', 'type': 'Real', 'unit': 'W/K',
         'description': 'De-SH zone UA (correlation 자동 계산)'},
        {'name': 'UA_2ph', 'causality': 'output', 'type': 'Real', 'unit': 'W/K',
         'description': '2-phase zone UA'},
        {'name': 'UA_SC', 'causality': 'output', 'type': 'Real', 'unit': 'W/K',
         'description': 'SC zone UA'},
        {'name': 'L_deSH_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'De-SH zone 길이 비율'},
        {'name': 'L_2ph_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': '2-phase zone 길이 비율'},
        {'name': 'L_SC_fraction', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'SC zone 길이 비율'},
        {'name': 'eta_fin', 'causality': 'output', 'type': 'Real', 'unit': '-',
         'description': 'Fin 효율 (Schmidt 가정)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _eps_NTU_C0(NTU):
    """C_r=0 ε-NTU."""
    if NTU <= 0:
        return 0.0
    if NTU > 50:
        return 1.0
    return 1.0 - math.exp(-NTU)


def _eps_NTU_counter(NTU, Cr):
    """Counter-flow ε-NTU."""
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


def _humid_air_props(T_C, RH_pct, P_atm_Pa=101325.0):
    """Reuse from evaporator_moving_boundary or recompute."""
    try:
        T_K = T_C + 273.15
        cp = CP.HAPropsSI('cp_ha', 'T', T_K, 'P', P_atm_Pa, 'R', RH_pct/100.0)
        W = CP.HAPropsSI('W', 'T', T_K, 'P', P_atm_Pa, 'R', RH_pct/100.0)
        return {'cp': cp, 'W': W}
    except Exception:
        return {'cp': 1006.0, 'W': 0.01}


def step(input, params, state, dt):
    """3-zone cascade with correlation-driven UA."""
    # ═══════ Parameters ═══════
    fluid = params.get('fluid', 'R290')
    
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    L_tube_total = float(params.get('L_tube_total', 10.0))
    N_tubes = int(float(params.get('N_tubes', 24.0)))
    N_rows = int(float(params.get('N_rows', 2.0)))
    P_t = float(params.get('P_t', 25.0e-3))
    P_l = float(params.get('P_l', 22.0e-3))
    t_fin = float(params.get('t_fin', 0.12e-3))
    FPI = float(params.get('FPI', 12.0))
    k_fin = float(params.get('k_fin', 200.0))
    A_o_face = float(params.get('A_o_face', 0.05))
    
    corr_2ph = params.get('corr_2ph', condensation.DEFAULT)
    corr_sp = params.get('corr_sp', single_phase.DEFAULT)
    corr_air = params.get('corr_air', air_side.DEFAULT)
    corr_fin = params.get('corr_fin', fin_efficiency.DEFAULT)
    
    htc_2ph = float(params.get('htc_corr_2ph', 1.0))
    htc_sp = float(params.get('htc_corr_sp', 1.0))
    htc_air = float(params.get('htc_corr_air', 1.0))
    dP_ref_frac = float(params.get('dP_ref', 0.03))
    
    # ═══════ Inputs ═══════
    P_cond_bar = float(input.get('P_cond', 17.0))
    h_in_kjkg = float(input.get('h_in', 680.0))
    m_dot_ref = float(input.get('m_dot_ref', 0.012))
    T_air_in_C = float(input.get('T_air_in', 35.0))
    RH_air_in = float(input.get('RH_air_in', 50.0))
    m_dot_air = float(input.get('m_dot_air', 0.5))
    
    if P_cond_bar <= 0 or m_dot_ref <= 0:
        raise ValueError(f"입력 0 이하: P_cond={P_cond_bar}, m_dot_ref={m_dot_ref}")
    
    # ═══════ 입구 / 포화 ═══════
    P_cond_Pa = P_cond_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    
    T_cond = CP.PropsSI('T', 'P', P_cond_Pa, 'Q', 0, fluid)
    T_cond_C = T_cond - 273.15
    h_l_sat = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 0, fluid)
    h_v_sat = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 1, fluid)
    h_fg = h_v_sat - h_l_sat
    
    # 입구 상태
    if h_in_J >= h_v_sat:
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond + 30.0
    elif h_in_J >= h_l_sat:
        T_ref_in_K = T_cond
    else:
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond - 5.0
    T_ref_in_C = T_ref_in_K - 273.15
    
    # ═══════ Geometry derivations ═══════
    # Fin pitch
    P_fin = 0.0254 / FPI
    # Tube outer surface area
    A_tube_outer = math.pi * D_o * L_tube_total
    # Inner surface area
    A_tube_inner = math.pi * D_i * L_tube_total
    # Fin count along tube
    N_fins_per_tube = int(L_tube_total / N_tubes / P_fin) if N_tubes > 0 else 0
    # Fin face area (single fin) — 단순: P_t × P_l × N_rows / N_tubes_per_row 정도 — 근사
    # 더 정확히는 (W × D) − tube circle. Simplification:
    A_fin_per_tube = max(0.0, 2 * P_t * P_l * N_rows - math.pi * D_o ** 2 / 4 * N_tubes / max(N_rows, 1))
    A_fin_total = A_fin_per_tube * N_fins_per_tube * N_tubes
    # Total air-side area
    A_air = A_tube_outer * (1.0 - t_fin / P_fin) + A_fin_total
    A_air = max(A_air, A_tube_outer)  # safety floor
    
    # face area & velocity
    V_air = m_dot_air / (1.2 * A_o_face) if A_o_face > 0 else 1.0
    
    # ═══════ Air-side α (zone 공통, T_air 큰 변동 없으니 approximate) ═══════
    air_corr_fn = air_side.CORR_REGISTRY.get(corr_air, air_side.CORR_REGISTRY[air_side.DEFAULT])
    try:
        alpha_air = air_corr_fn(
            V_face=V_air, T_air_K=T_air_in_C + 273.15,
            D_o=D_o, P_t=P_t, P_l=P_l, t_fin=t_fin, P_fin=P_fin, N_rows=N_rows,
        ) * htc_air
    except Exception:
        alpha_air = 50.0 * htc_air  # fallback
    alpha_air = max(alpha_air, 10.0)
    
    # Schmidt fin efficiency (zone 공통)
    fin_corr_fn = fin_efficiency.CORR_REGISTRY.get(corr_fin, fin_efficiency.CORR_REGISTRY[fin_efficiency.DEFAULT])
    try:
        eta_f = fin_corr_fn(D_o=D_o, P_t=P_t, P_l=P_l, t_fin=t_fin,
                            k_fin=k_fin, alpha_air=alpha_air)
    except Exception:
        eta_f = 0.85
    eta_f = max(0.5, min(0.99, eta_f))
    # Surface efficiency
    eta_o = 1.0 - (A_fin_total / A_air) * (1.0 - eta_f) if A_air > 0 else eta_f
    
    # ═══════ T_air 갱신 변수 ═══════
    air_in = _humid_air_props(T_air_in_C, RH_air_in)
    cp_air = air_in['cp']
    W_in = air_in['W']
    C_air = m_dot_air * cp_air
    
    T_air_curr = T_air_in_C
    h_ref_curr = h_in_J
    
    # zone별 결과
    zone_results = {'deSH': {}, '2ph': {}, 'SC': {}}
    
    # ── Zone 1: De-SH ──
    Q_deSH = 0.0
    UA_deSH = 0.0
    if h_ref_curr > h_v_sat and T_air_curr < T_ref_in_C:
        try:
            cp_v = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'T', T_ref_in_K, fluid)
        except Exception:
            cp_v = 1800.0
        # Single-phase α (vapor)
        sp_corr_fn = single_phase.CORR_REGISTRY.get(corr_sp, single_phase.CORR_REGISTRY[single_phase.DEFAULT])
        try:
            alpha_ref = sp_corr_fn(
                P_Pa=P_cond_Pa, T_K=T_ref_in_K, m_dot=m_dot_ref,
                D_i=D_i, fluid=fluid, phase='vapor'
            ) * htc_sp
        except TypeError:
            # 어떤 single_phase signature는 phase= 안 받음
            try:
                alpha_ref = sp_corr_fn(P_Pa=P_cond_Pa, T_K=T_ref_in_K,
                                       m_dot=m_dot_ref, D_i=D_i, fluid=fluid) * htc_sp
            except Exception:
                alpha_ref = 200.0 * htc_sp
        except Exception:
            alpha_ref = 200.0 * htc_sp
        alpha_ref = max(alpha_ref, 50.0)
        
        # UA — zone fraction은 Q에 비례 가정 (cascade에서 계산 후 정정)
        # 여기서는 모든 surface가 zone에 할당된다고 가정 → zone Q 비율로 사후 분배
        # 단순화: UA_zone = (1/(α_ref × A_inner) + 1/(α_air × η_o × A_air))^(-1)
        UA_full = 1.0 / (1.0 / (alpha_ref * A_tube_inner) + 1.0 / (alpha_air * eta_o * A_air))
        
        # zone fraction은 ζ_deSH 미지수. 단순히 Q-balance로:
        # Q_deSH가 작으면 ζ도 작음 → cascade로 Q 먼저 풀고 사후 정정
        # 일단 잠정 UA = full UA × estimate (이전 zone 비율 추정 0.15)
        zeta_est = 0.15
        UA_deSH = UA_full * zeta_est
        
        C_ref_v = m_dot_ref * cp_v
        C_min = min(C_ref_v, C_air)
        C_max = max(C_ref_v, C_air)
        Cr = C_min / C_max if C_max > 0 else 0.0
        NTU = UA_deSH / C_min if C_min > 0 else 0
        eps = _eps_NTU_counter(NTU, Cr)
        
        Q_max_ref = m_dot_ref * (h_ref_curr - h_v_sat)
        Q_deSH = eps * C_min * (T_ref_in_C - T_air_curr)
        Q_deSH = max(0.0, min(Q_deSH, Q_max_ref))
        
        T_air_curr += Q_deSH / C_air if C_air > 0 else 0
        h_ref_curr -= Q_deSH / m_dot_ref if m_dot_ref > 0 else 0
        zone_results['deSH'] = {'Q': Q_deSH, 'alpha_ref': alpha_ref, 'UA_full': UA_full}
    
    # ── Zone 2: 2-phase condensation ──
    Q_2ph_total = 0.0
    UA_2ph = 0.0
    if h_ref_curr > h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05:
        # x_avg of zone (입구 1 → 출구 0 가정 → 0.5 평균)
        x_in_2ph = max(0.0, min(1.0, (h_ref_curr - h_l_sat) / h_fg))
        x_avg = x_in_2ph * 0.5  # 입구 ~1 → 출구 0 가정 시 평균. 단순화: 0.5
        
        cond_corr_fn = condensation.CORR_REGISTRY.get(corr_2ph, condensation.CORR_REGISTRY[condensation.DEFAULT])
        try:
            alpha_ref_2ph = cond_corr_fn(
                P_Pa=P_cond_Pa, x_avg=max(0.5, x_avg), m_dot=m_dot_ref,
                D_i=D_i, fluid=fluid
            ) * htc_2ph
        except Exception:
            alpha_ref_2ph = 3000.0 * htc_2ph  # 응축 typical
        alpha_ref_2ph = max(alpha_ref_2ph, 100.0)
        
        UA_full = 1.0 / (1.0 / (alpha_ref_2ph * A_tube_inner) + 1.0 / (alpha_air * eta_o * A_air))
        # 2상은 통상 70% 할당 가정
        zeta_est = 0.7
        UA_2ph = UA_full * zeta_est
        
        # C_r = 0 (refrigerant 측 C_ref → ∞ in 2-phase)
        NTU = UA_2ph / C_air if C_air > 0 else 0
        eps = _eps_NTU_C0(NTU)
        
        Q_max_ref = m_dot_ref * (h_ref_curr - h_l_sat)
        Q_2ph_total = eps * C_air * (T_cond_C - T_air_curr)
        Q_2ph_total = max(0.0, min(Q_2ph_total, Q_max_ref))
        
        T_air_curr += Q_2ph_total / C_air if C_air > 0 else 0
        h_ref_curr -= Q_2ph_total / m_dot_ref if m_dot_ref > 0 else 0
        zone_results['2ph'] = {'Q': Q_2ph_total, 'alpha_ref': alpha_ref_2ph, 'UA_full': UA_full}
    
    # ── Zone 3: SC ──
    Q_SC = 0.0
    UA_SC = 0.0
    if h_ref_curr <= h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05:
        try:
            cp_l = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'Q', 0, fluid)
        except Exception:
            cp_l = 2700.0
        sp_corr_fn = single_phase.CORR_REGISTRY.get(corr_sp, single_phase.CORR_REGISTRY[single_phase.DEFAULT])
        try:
            alpha_ref_sc = sp_corr_fn(
                P_Pa=P_cond_Pa, T_K=T_cond, m_dot=m_dot_ref,
                D_i=D_i, fluid=fluid, phase='liquid'
            ) * htc_sp
        except TypeError:
            try:
                alpha_ref_sc = sp_corr_fn(P_Pa=P_cond_Pa, T_K=T_cond,
                                          m_dot=m_dot_ref, D_i=D_i, fluid=fluid) * htc_sp
            except Exception:
                alpha_ref_sc = 1000.0 * htc_sp
        except Exception:
            alpha_ref_sc = 1000.0 * htc_sp
        alpha_ref_sc = max(alpha_ref_sc, 50.0)
        
        UA_full = 1.0 / (1.0 / (alpha_ref_sc * A_tube_inner) + 1.0 / (alpha_air * eta_o * A_air))
        zeta_est = 0.15
        UA_SC = UA_full * zeta_est
        
        C_ref_l = m_dot_ref * cp_l
        C_min = min(C_ref_l, C_air)
        C_max = max(C_ref_l, C_air)
        Cr = C_min / C_max if C_max > 0 else 0.0
        NTU = UA_SC / C_min if C_min > 0 else 0
        eps = _eps_NTU_counter(NTU, Cr)
        
        Q_SC = eps * C_min * (T_cond_C - T_air_curr)
        Q_SC = max(0.0, Q_SC)
        
        T_air_curr += Q_SC / C_air if C_air > 0 else 0
        h_ref_curr -= Q_SC / m_dot_ref if m_dot_ref > 0 else 0
        zone_results['SC'] = {'Q': Q_SC, 'alpha_ref': alpha_ref_sc, 'UA_full': UA_full}
    
    # ═══════ 출구 상태 ═══════
    Q_total = Q_deSH + Q_2ph_total + Q_SC
    h_out_J = h_ref_curr
    
    if h_out_J >= h_v_sat:
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond + max(0, (h_out_J - h_v_sat) / 1800.0)
        x_out = 1.0 + max(0.0, (h_out_J - h_v_sat) / max(h_fg, 1.0))
        SC_out = 0.0
    elif h_out_J >= h_l_sat:
        x_out = max(0.0, min(1.0, (h_out_J - h_l_sat) / h_fg))
        T_ref_out_K = T_cond
        SC_out = 0.0
    else:
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond - max(0, (h_l_sat - h_out_J) / 2700.0)
        x_out = -max(0.0, (h_l_sat - h_out_J) / max(h_fg, 1.0))
        SC_out = max(0.0, T_cond - T_ref_out_K)
    T_ref_out_C = T_ref_out_K - 273.15
    
    # 공기 RH (가열되어 RH 감소 — W_in 그대로)
    P_atm = 101325.0
    P_ws_out = _P_sat_water_simple(T_air_curr)
    P_w_out = W_in / (W_in + 0.622) * P_atm
    RH_out = max(0.0, min(100.0, P_w_out / P_ws_out * 100.0)) if P_ws_out > 0 else 0.0
    
    # zone fraction 사후 정정 (Q 비례)
    if Q_total > 0:
        L_deSH_frac = Q_deSH / Q_total
        L_2ph_frac = Q_2ph_total / Q_total
        L_SC_frac = Q_SC / Q_total
    else:
        L_deSH_frac = L_2ph_frac = L_SC_frac = 0.0
    
    # 출구 압력
    P_ref_out_bar = P_cond_bar * (1.0 - dP_ref_frac)
    
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
            'UA_deSH': UA_deSH,
            'UA_2ph': UA_2ph,
            'UA_SC': UA_SC,
            'L_deSH_fraction': L_deSH_frac,
            'L_2ph_fraction': L_2ph_frac,
            'L_SC_fraction': L_SC_frac,
            'eta_fin': eta_f,
        },
        'newState': {},
    }


def _P_sat_water_simple(T_C):
    """간이 Antoine."""
    T_C = max(-50, min(200, T_C))
    A, B, C = 8.07131, 1730.63, 233.426
    P_mmHg = 10 ** (A - B / (T_C + C))
    return P_mmHg * 133.322


def validate(params):
    issues = []
    
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    if D_i >= D_o:
        issues.append({'key': 'D_i', 'msg': f'D_i ≥ D_o — 비현실적'})
    
    P_t = float(params.get('P_t', 25.0e-3))
    if P_t <= D_o:
        issues.append({'key': 'P_t', 'msg': f'P_t ({P_t*1000:.1f}mm) ≤ D_o — 튜브 겹침'})
    
    corr_2ph = params.get('corr_2ph', condensation.DEFAULT)
    if corr_2ph not in CORR_2PH_OPTIONS:
        issues.append({'key': 'corr_2ph', 'msg': f"unknown corr_2ph='{corr_2ph}'"})
    
    return issues
