"""
Condenser (L1 Off-design)
═══════════════════════════════════════════════════════════════════════
3-zone cascade ε-NTU. 설계 변수 없음, UA 또는 ε 직접 입력.

[charge holdup 미지원] Off는 형상(D_i·L_tube·V_internal)이 없는 성능 전용
모델이라 냉매 charge(=ρ×V_internal)를 산출하지 않는다. 시스템 charge 합산은
형상이 있는 Semi(moving boundary)·On(segment march)에서 수행한다.

Zone 구조 (응축기 — evap의 2-zone과 다름):
  Zone 1: De-SH    — vapor cooling (T_in_SH → T_sat)
  Zone 2: 2-phase  — condensation (x=1 → x=0)
  Zone 3: SC       — liquid subcooling (T_sat → T_out)

Cascade 방식:
  • Zone 1: 입구 SH vapor → T_sat 도달까지 ε-NTU
  • Zone 2: 남은 air-side capacity로 응축 진행 (x: 1→0)
  • Zone 3: 응축 완료 후 남은 capacity로 SC 진행
  
  각 zone마다:
    - 냉매 측: 단상 (Zone 1, 3)에서 C_ref = m_dot × cp 유한, 2상 (Zone 2)에서 C_ref → ∞
    - 공기 측: T_air가 zone마다 갱신 (T_air_in_z+1 = T_air_out_z)

Wet coil:
  응축기는 외기 혹은 dryer 출구 공기 → 보통 dry 측
  Wet 가정 무시 (evaporator와의 차이점)

진영님 정리:
  ✓ 3-zone (De-SH, 2상, SC) — evap과 다른 구조
  ✓ Evap 모듈 안 건드림, 별도 모듈
  ✓ Evap과 동등한 수준 (UA / epsilon 입력 모드, dP_ref 등 동일)
"""

import math
import CoolProp.CoolProp as CP

# Evap 모듈의 helper 재사용 (humid_air_props만)
from .evaporator_off_design import _humid_air_props


# ════════ Available options ════════
FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf', 'R22', 'R407C']
INPUT_MODES = ['UA', 'epsilon']


# ════════ modelDescription ════════
modelDescription = {
    'typeNo': 220,
    'name': 'Condenser (Off-design)',
    'category': 'refrigerant',
    'modelType': 'off-design',
    'fidelity': 0.3,
    'description': '3-zone cascade ε-NTU (De-SH / 2-phase / SC). 설계 변수 없음, UA 또는 ε 직접 입력.',
    'backend': 'python',
    'variables': [
        # ═══════ Parameters ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # Fitting — input 모드
        {'name': 'input_mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Fitting', 'start': 'UA', 'unit': '-', 'options': INPUT_MODES,
         'description': 'UA 직접 입력 vs ε 직접 입력'},

        # UA mode (3-zone) — HPWD R290 typical 부품 (W=0.4, H=0.3, FPI=12) 기준
        # 비율: deSH:2ph:SC ≈ 1:6.25:0.625 (응축 영역이 가장 크고, SC는 작은 영역)
        # Total UA ≈ 63 W/K → Cond On★ default geometry와 일치 (Q ≈ 690W @ HPWD 운전점)
        {'name': 'UA_deSH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 15.5, 'unit': 'W/K',
         'description': 'De-superheat 영역 UA (vapor cooling) — HPWD typical 8 W/K'},
        {'name': 'UA_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 280.0, 'unit': 'W/K',
         'description': '2-phase (응축) 영역 UA — 보통 가장 큼, HPWD typical 50 W/K'},
        {'name': 'UA_SC', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.5, 'unit': 'W/K',
         'description': 'Subcool 영역 UA (liquid cooling) — HPWD typical 5 W/K'},

        # epsilon mode
        {'name': 'eps_deSH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.4, 'unit': '-',
         'description': 'De-superheat 영역 ε'},
        {'name': 'eps_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.85, 'unit': '-',
         'description': '2-phase 영역 ε'},
        {'name': 'eps_SC', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.3, 'unit': '-',
         'description': 'Subcool 영역 ε'},

        {'name': 'dP_ref', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.03, 'unit': '-',
         'description': '냉매 측 압력 손실 비율 (P_out = P_in × (1 - dP_ref))'},

        # ═══════ Inputs ═══════
        {'name': 'P_cond', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '응축 압력 (abs) — R290에서 보통 14~20bar'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피 (compressor 출구, SH vapor 보통)'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도 (외기 혹은 dryer 후 25~40°C)'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 상대습도'},
        {'name': 'V_air_CMM', 'causality': 'input', 'type': 'Real',
         'unit': 'CMM', 'description': '공기 풍량 (m³/min, CMM) — 한국 HVAC 표준 단위'},

        # ═══════ Outputs ═══════
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 출구 비엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '냉매 출구 압력'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '냉매 출구 quality (<0이면 SC 영역, evap의 ">1이면 SH"의 반대)'},
        {'name': 'SC_out', 'causality': 'output', 'type': 'Real',
         'unit': 'K', 'description': '출구 과냉도 (0이면 2상으로 종료)'},
        {'name': 'T_cond', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '응축 포화 온도'},

        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '공기 출구 온도 (응축기는 가열됨)'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': '공기 출구 상대습도 (응축기는 가열되어 RH 감소)'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/kg', 'description': '공기 출구 humidity ratio (변화 없음 — dry process)'},

        {'name': 'Q_total', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '총 열교환량 (응축기는 sensible only)'},
        {'name': 'Q_deSH', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': 'De-SH zone 열량'},
        {'name': 'Q_2ph', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '2-phase (응축) zone 열량'},
        {'name': 'Q_SC', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': 'SC zone 열량'},

        # Zone 분배 진단
        {'name': 'L_deSH_fraction', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'De-SH zone 길이 비율'},
        {'name': 'L_2ph_fraction', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '2-phase zone 길이 비율'},
        {'name': 'L_SC_fraction', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'SC zone 길이 비율'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _eps_NTU_C0(NTU):
    """C_r=0 ε-NTU (단상 또는 2상에서 한쪽이 ∞일 때):
    ε = 1 - exp(-NTU)
    """
    if NTU <= 0:
        return 0.0
    if NTU > 50:
        return 1.0
    return 1.0 - math.exp(-NTU)


def _eps_NTU_counter(NTU, Cr):
    """Counter-flow ε-NTU (양쪽 다 유한 capacity, Cr = Cmin/Cmax):
    ε = (1 - exp(-NTU(1-Cr))) / (1 - Cr × exp(-NTU(1-Cr)))
    Cr = 0 일 때는 _eps_NTU_C0 사용 권장
    """
    if NTU <= 0:
        return 0.0
    if Cr <= 1e-6:
        return _eps_NTU_C0(NTU)
    if Cr >= 1.0 - 1e-6:
        # Cr = 1 special case
        return NTU / (1.0 + NTU)
    arg = -NTU * (1.0 - Cr)
    if arg < -50:
        return 1.0 / Cr if Cr < 1 else 1.0
    e = math.exp(arg)
    return (1.0 - e) / (1.0 - Cr * e)



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
    """Condenser 3-zone cascade ε-NTU step.
    
    Cascade:
        T_air_in → [Zone 1: De-SH] → T_air_after_deSH
                 → [Zone 2: 2상]   → T_air_after_2ph
                 → [Zone 3: SC]    → T_air_out
    
    각 zone에서 air capacity 소진되면 해당 zone에서 종료.
    """
    # ═══════ Parameters ═══════
    fluid = params.get('fluid', 'R290')
    input_mode = params.get('input_mode', 'UA')
    
    UA_deSH = float(params.get('UA_deSH', 15.5))
    UA_2ph = float(params.get('UA_2ph', 280.0))
    UA_SC = float(params.get('UA_SC', 0.5))
    eps_deSH_in = float(params.get('eps_deSH', 0.4))
    eps_2ph_in = float(params.get('eps_2ph', 0.85))
    eps_SC_in = float(params.get('eps_SC', 0.3))
    dP_ref = float(params.get('dP_ref', 0.03))
    
    # ═══════ Inputs ═══════
    P_cond_bar = float(input.get('P_cond', 17.0))
    h_in_kjkg = float(input.get('h_in', 680.0))   # 75°C SH @ 17bar 정도가 대표
    m_dot_ref = float(input.get('m_dot_ref', 0.012))
    T_air_in_C = float(input.get('T_air_in', 35.0))
    RH_air_in = float(input.get('RH_air_in', 50.0))
    m_dot_air = _cmm_to_mass(
        V_air_CMM=float(input.get('V_air_CMM', 25.42)),
        T_air_C=T_air_in_C, RH=RH_air_in,
    )
    
    if P_cond_bar <= 0 or m_dot_ref <= 0:
        raise ValueError(f"입력 0 이하: P_cond={P_cond_bar}, m_dot_ref={m_dot_ref}")
    
    # ═══════ 입구 상태 ═══════
    P_cond_Pa = P_cond_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    
    # 포화 상태
    T_cond = CP.PropsSI('T', 'P', P_cond_Pa, 'Q', 0, fluid)
    T_cond_C = T_cond - 273.15
    h_l_sat = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 0, fluid)
    h_v_sat = CP.PropsSI('H', 'P', P_cond_Pa, 'Q', 1, fluid)
    h_fg = h_v_sat - h_l_sat
    
    # 입구 상태 분류
    if h_in_J >= h_v_sat:
        # SH vapor (정상 응축기 입구)
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond + 30.0
        x_in = 1.0  # nominal
        SH_in = T_ref_in_K - T_cond
    elif h_in_J >= h_l_sat:
        # 2-phase (가끔)
        x_in = (h_in_J - h_l_sat) / h_fg
        T_ref_in_K = T_cond
        SH_in = 0.0
    else:
        # SC liquid (드뭄 — 입구가 이미 sub-cool 상태)
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_cond - 5.0
        x_in = 0.0
        SH_in = 0.0
    
    T_ref_in_C = T_ref_in_K - 273.15
    
    # 공기 측 properties
    air_in = _humid_air_props(T_air_in_C, RH_air_in)
    cp_air = air_in['cp']
    W_in = air_in['W']
    
    C_air_total = m_dot_air * cp_air  # W/K
    
    # ═══════════════════════════════════════════
    # Cascade 3-zone (T_air_in → Zone1 → Zone2 → Zone3)
    # Pinch check: T_air > T_cond 이면 zone 진행 불가
    # ═══════════════════════════════════════════
    
    T_air_curr = T_air_in_C  # 점진적으로 가열되며 갱신
    h_ref_curr = h_in_J       # 점진적으로 감소
    Q_deSH = 0.0
    Q_2ph_total = 0.0
    Q_SC = 0.0
    
    # Pinch check
    if T_air_curr >= T_cond_C - 0.1:
        # 공기가 응축 온도와 같거나 더 뜨거우면 응축 안 일어남
        # (운전 조건 비정상 — warning이지만 그냥 진행)
        pass
    
    # ─── Zone 1: De-superheat (vapor cooling) ───
    if h_ref_curr > h_v_sat and T_air_curr < T_ref_in_C:
        # 단상 vapor — refrigerant 측 cp_v
        try:
            cp_v = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'T', T_ref_in_K, fluid)
        except Exception:
            cp_v = 1800.0  # R290 vapor 근사
        C_ref_v = m_dot_ref * cp_v
        C_min = min(C_ref_v, C_air_total)
        C_max = max(C_ref_v, C_air_total)
        Cr = C_min / C_max if C_max > 0 else 0.0
        
        # Q_max for de-SH: T_ref_in → T_cond 까지 가능
        Q_max_deSH_ref = m_dot_ref * (h_ref_curr - h_v_sat)  # vapor cooling to sat
        Q_max_deSH_air = C_air_total * (T_ref_in_C - T_air_curr)
        Q_max_deSH = min(Q_max_deSH_ref, Q_max_deSH_air)
        
        # ε
        if input_mode == 'UA':
            NTU = UA_deSH / C_min if C_min > 0 else 0
            eps = _eps_NTU_counter(NTU, Cr)
        else:
            eps = max(0.0, min(0.999, eps_deSH_in))
        
        # Q
        if C_min > 0:
            Q_deSH = eps * C_min * (T_ref_in_C - T_air_curr)
            Q_deSH = max(0.0, min(Q_deSH, Q_max_deSH_ref))  # ref 한계 cap
        else:
            Q_deSH = 0.0
        
        # 공기 갱신
        T_air_curr += Q_deSH / C_air_total if C_air_total > 0 else 0
        h_ref_curr -= Q_deSH / m_dot_ref if m_dot_ref > 0 else 0
    
    # ─── Zone 2: 2-phase condensation ───
    if h_ref_curr > h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05:
        # 2상 — C_ref → ∞ (정확히는 dh/dT = ∞ at saturated)
        # Cr = 0, 단순 ε-NTU
        Q_max_2ph_ref = m_dot_ref * (h_ref_curr - h_l_sat)
        Q_max_2ph_air = C_air_total * (T_cond_C - T_air_curr)
        Q_max_2ph = min(Q_max_2ph_ref, Q_max_2ph_air)
        
        if input_mode == 'UA':
            NTU = UA_2ph / C_air_total if C_air_total > 0 else 0
            eps = _eps_NTU_C0(NTU)
        else:
            eps = max(0.0, min(0.999, eps_2ph_in))
        
        Q_2ph_total = eps * C_air_total * (T_cond_C - T_air_curr)
        Q_2ph_total = max(0.0, min(Q_2ph_total, Q_max_2ph_ref))  # ref 한계 cap
        
        T_air_curr += Q_2ph_total / C_air_total if C_air_total > 0 else 0
        h_ref_curr -= Q_2ph_total / m_dot_ref if m_dot_ref > 0 else 0
    
    # ─── Zone 3: Subcool (liquid cooling) ───
    if h_ref_curr <= h_l_sat + 1e-3 and T_air_curr < T_cond_C - 0.05:
        # 단상 liquid
        try:
            cp_l = CP.PropsSI('CPMASS', 'P', P_cond_Pa, 'Q', 0, fluid)
        except Exception:
            cp_l = 2700.0  # R290 liquid 근사
        C_ref_l = m_dot_ref * cp_l
        C_min = min(C_ref_l, C_air_total)
        C_max = max(C_ref_l, C_air_total)
        Cr = C_min / C_max if C_max > 0 else 0.0
        
        # T_ref가 현재 T_cond에서 출발해 → 어디까지 내려갈 수 있나
        # Q_max: T_cond → T_air_curr 까지 가능
        Q_max_SC = C_min * (T_cond_C - T_air_curr) if C_min > 0 else 0
        
        if input_mode == 'UA':
            NTU = UA_SC / C_min if C_min > 0 else 0
            eps = _eps_NTU_counter(NTU, Cr)
        else:
            eps = max(0.0, min(0.999, eps_SC_in))
        
        Q_SC = eps * C_min * (T_cond_C - T_air_curr)
        Q_SC = max(0.0, Q_SC)
        
        T_air_curr += Q_SC / C_air_total if C_air_total > 0 else 0
        h_ref_curr -= Q_SC / m_dot_ref if m_dot_ref > 0 else 0
    
    # ═══════ 출구 상태 ═══════
    Q_total = Q_deSH + Q_2ph_total + Q_SC
    
    # 출구 enthalpy 기반 출구 상태 결정
    h_out_J = h_ref_curr
    
    if h_out_J >= h_v_sat:
        # 여전히 SH (응축 거의 안 일어남 — 작은 응축기)
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond + max(0, (h_out_J - h_v_sat) / 1800.0)
        x_out = 1.0 + max(0.0, (h_out_J - h_v_sat) / max(h_fg, 1.0))  # >1 → SH
        SC_out = 0.0  # SH 상태
    elif h_out_J >= h_l_sat:
        # 2상 종료 (응축은 일부)
        x_out = max(0.0, min(1.0, (h_out_J - h_l_sat) / h_fg))
        T_ref_out_K = T_cond
        SC_out = 0.0
    else:
        # SC 영역 도달
        try:
            T_ref_out_K = CP.PropsSI('T', 'P', P_cond_Pa, 'H', h_out_J, fluid)
        except Exception:
            T_ref_out_K = T_cond - max(0, (h_l_sat - h_out_J) / 2700.0)
        x_out = -max(0.0, (h_l_sat - h_out_J) / max(h_fg, 1.0))  # 음수 → SC
        SC_out = max(0.0, T_cond - T_ref_out_K)
    
    T_ref_out_C = T_ref_out_K - 273.15
    
    # 공기 측 RH (가열 → RH 감소, W는 그대로 — dry)
    P_atm = 101325.0
    P_ws_out = _P_sat_water(T_air_curr)
    P_w_out = W_in / (W_in + 0.622) * P_atm  # partial pressure of water vapor (unchanged)
    RH_out = max(0.0, min(100.0, P_w_out / P_ws_out * 100.0)) if P_ws_out > 0 else 0.0
    
    # Zone 길이 비율 (UA 비례 가정 → 단순 normalized)
    if Q_total > 0:
        L_deSH_frac = Q_deSH / Q_total
        L_2ph_frac = Q_2ph_total / Q_total
        L_SC_frac = Q_SC / Q_total
    else:
        L_deSH_frac = L_2ph_frac = L_SC_frac = 0.0
    
    # 출구 압력
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
        },
        'newState': {},
    }


def _P_sat_water(T_C):
    """Antoine equation for water (Pa)."""
    if T_C < -50 or T_C > 200:
        T_C = max(-50, min(200, T_C))
    T_K = T_C + 273.15
    # Wagner equation (simplified) — 실용 범위 0~100°C 정확
    # Antoine: log10(P/Pa) = A - B/(T+C)  for 1 < T < 100
    A, B, C = 8.07131, 1730.63, 233.426  # T in °C, P in mmHg
    P_mmHg = 10 ** (A - B / (T_C + C))
    return P_mmHg * 133.322  # mmHg → Pa


def validate(params):
    issues = []
    
    input_mode = params.get('input_mode', 'UA')
    if input_mode not in INPUT_MODES:
        issues.append({'key': 'input_mode', 'msg': f'input_mode는 {INPUT_MODES} 중'})
    
    if input_mode == 'UA':
        UA_2ph = float(params.get('UA_2ph', 300.0))
        if UA_2ph <= 0:
            issues.append({'key': 'UA_2ph', 'msg': f'UA_2ph={UA_2ph} ≤ 0 — 양수여야'})
        UA_deSH = float(params.get('UA_deSH', 50.0))
        UA_SC = float(params.get('UA_SC', 30.0))
        if UA_deSH > UA_2ph * 0.7:
            issues.append({'key': 'UA_deSH',
                          'msg': f'UA_deSH({UA_deSH}) > UA_2ph({UA_2ph})×0.7 — 보통 De-SH UA가 더 작음'})
    else:
        for k in ('eps_deSH', 'eps_2ph', 'eps_SC'):
            v = float(params.get(k, 0.5))
            if v < 0 or v >= 1.0:
                issues.append({'key': k, 'msg': f'{k}={v} — 0 ≤ ε < 1 이어야'})
    
    dP_ref = float(params.get('dP_ref', 0.03))
    if dP_ref < 0 or dP_ref > 0.3:
        issues.append({'key': 'dP_ref', 'msg': f'dP_ref={dP_ref} — 0~0.3 범위 권장 (응축은 보통 2~5%)'})
    
    return issues
