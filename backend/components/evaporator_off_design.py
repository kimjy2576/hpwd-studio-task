"""
Evaporator (Off-design L1) — 2-zone ε-NTU
═══════════════════════════════════════════════════════════════════════
설계 변수 없음. 사용자가 UA 또는 ε를 직접 입력 (또는 fitting).

[charge holdup 미지원] Off는 형상(D_i·L_tube·V_internal)이 없는 성능 전용
모델이라 냉매 charge(=ρ×V_internal)를 산출하지 않는다. 시스템 charge 합산은
형상이 있는 Semi(moving boundary)·On(segment march)에서 수행한다. Off는
사이클을 빠르게 닫을 때(P_e/P_c 탐색)만 쓰고, charge가 필요하면 Semi/On으로 재평가.

2-zone 구조:
  ┌─ 2-phase zone ─────┐ ┌─ Superheat zone ─┐
  │ x_in → x=1         │ │ x=1 → SH_out     │
  │ Q_2ph              │ │ Q_SH             │
  └────────────────────┘ └──────────────────┘
  L_total = L_2ph + L_SH (분배는 자동 — 에너지 보존으로)

알고리즘:
  1. 입구 상태 (CoolProp): T_evap = T_sat(P_evap), x_in = (h_in - h_l) / h_fg
  2. 2-phase zone:
     Q_2ph_max = m_dot_ref × (h_v - h_in)  (냉매가 받을 수 있는 최대)
     Cmin_2ph = m_dot_air × cp_air  (refrigerant Cmin = ∞)
     ε_2ph 또는 UA_2ph 입력 → ε = 1 - exp(-NTU)  for Cmin/Cmax = 0
     Q_2ph_actual = min(ε_2ph × Cmin_2ph × (T_air_in - T_evap), Q_2ph_max)
     L_2ph_frac = Q_2ph_actual / Q_2ph_max  (이 비율로 UA 분배 — input 모드일 때)
  
  3. Superheat zone:
     공기 온도 = T_air_in 에서 T_air_2ph_out 으로 이미 떨어진 상태
     m_dot_air × cp × (T_air_in - T_air_2ph_out) = Q_2ph_actual
     SH zone: Cr = Cmin/Cmax 일반 ε-NTU (counter-flow 가정)
  
  4. 응축 (wet-coil, threshold):
     T_coil_surface ≈ T_evap (단순화 — 정확하게는 wall T)
     T_air_dewpoint > T_coil_surface 면 응축
     ω_out_sat = ω_sat(T_coil_surface)  (포화 humidity ratio)
     Q_latent = m_dot_air × h_fg_water × (ω_in - ω_out_sat)  if 응축
     Q_total = Q_sensible + Q_latent
  
  5. 출구 엔탈피, 압력 손실:
     h_ref_out = h_in + Q_total / m_dot_ref
     P_ref_out = P_evap × (1 - dP_ref)

설계 변수 0개 — 모든 fitting은 사용자가 시험 데이터로 결정.

Reference:
  - Incropera, Fundamentals of Heat & Mass Transfer (ε-NTU 기본)
  - ASHRAE Handbook (wet-coil threshold method)
"""

import math
import CoolProp.CoolProp as CP

FLUIDS = ['R290']
INPUT_MODES = ['UA', 'epsilon']  # 사용자가 toggle


modelDescription = {
    'typeNo': 120,
    'name': 'Evaporator (Off-design)',
    'category': 'refrigerant',
    'modelType': 'off-design',
    'fidelity': 0.3,
    'description': '2-zone ε-NTU. 설계 변수 없음, UA 또는 ε 직접 입력.',
    'backend': 'python',
    'variables': [
        # ═══════ Parameters ═══════
        # Material
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},

        # Operating — Wet-coil 모드는 사용자가 끄고 싶을 수도
        {'name': 'wet_coil', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'auto', 'unit': '-',
         'options': ['auto', 'off'],
         'description': 'Wet-coil 응축 처리: auto=threshold 자동, off=무시(dry-coil)'},

        # Fitting — input 모드 toggle
        {'name': 'input_mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Fitting', 'start': 'UA', 'unit': '-', 'options': INPUT_MODES,
         'description': 'UA 직접 입력 vs ε 직접 입력 (UA가 일반적)'},

        # Fitting — UA 모드 — HPWD R290 typical 부품 (W=0.4, H=0.3, FPI=12) 기준
        # 비율: 2ph:SH ≈ 6:1, Total UA ≈ 29 W/K → Evap On★ default geometry와 일치
        {'name': 'UA_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 15.9, 'unit': 'W/K',
         'description': '2-phase 영역 UA (input_mode=UA 시 사용) — HPWD typical 25 W/K'},
        {'name': 'UA_SH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 2.2, 'unit': 'W/K',
         'description': 'Superheat 영역 UA (input_mode=UA 시 사용) — HPWD typical 4 W/K'},
        {'name': 'eps_2ph', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.85, 'unit': '-',
         'description': '2-phase 영역 ε (input_mode=epsilon 시 사용)'},
        {'name': 'eps_SH', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.5, 'unit': '-',
         'description': 'Superheat 영역 ε (input_mode=epsilon 시 사용)'},
        {'name': 'dP_ref', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.02, 'unit': '-',
         'description': '냉매 측 압력 손실 비율 (P_out = P_in × (1 - dP_ref))'},

        # ═══════ Inputs ═══════
        # Refrigerant 측
        {'name': 'P_evap', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '증발 압력 (abs)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피 (팽창밸브 후, 보통 2-phase)'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        # Air 측
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도 (드럼 출구, HPWD에선 40~60°C)'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 상대습도 (HPWD에선 80~100%)'},
        {'name': 'V_air_CMM', 'causality': 'input', 'type': 'Real',
         'unit': 'CMM', 'description': '공기 풍량 (m³/min, CMM) — 한국 HVAC 표준 단위'},

        # ═══════ Outputs ═══════
        # Refrigerant 측
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 출구 비엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '냉매 출구 압력 (압력 손실 후)'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '냉매 출구 quality (>1이면 SH 영역)'},
        {'name': 'SH_out', 'causality': 'output', 'type': 'Real',
         'unit': 'K', 'description': '출구 과열도 (0이면 2-phase로 종료)'},
        {'name': 'T_evap', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '증발 포화 온도'},
        # Air 측
        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '공기 출구 온도'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': '공기 출구 상대습도'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/kg', 'description': '공기 출구 humidity ratio'},
        # 열량
        {'name': 'Q_total', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '총 열교환량 (sensible + latent)'},
        {'name': 'Q_sensible', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '현열 (공기 온도 강하)'},
        {'name': 'Q_latent', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '잠열 (응축 — 건조기에선 핵심)'},
        {'name': 'condensate_rate', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '응축수 발생량 (단위 시간당 건조량)'},
        # Zone 분배
        {'name': 'L_2ph_fraction', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '2-phase zone이 차지하는 길이 비율 (UA 분배 진단)'},
        {'name': 'is_wet', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '응축 발생 여부 (1=wet, 0=dry)'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def _humid_air_props(T_C, RH_pct, P_atm_Pa=101325.0):
    """공기 상태 — humidity ratio + dewpoint + h.
    CoolProp HumidAirProp 사용."""
    T_K = T_C + 273.15
    RH_frac = max(0.001, min(0.999, RH_pct / 100.0))
    try:
        W = CP.HAPropsSI('W', 'T', T_K, 'P', P_atm_Pa, 'R', RH_frac)  # humidity ratio
        h = CP.HAPropsSI('H', 'T', T_K, 'P', P_atm_Pa, 'W', W)        # J/kg dry air
        T_dp = CP.HAPropsSI('Tdp', 'T', T_K, 'P', P_atm_Pa, 'W', W)   # dewpoint K
        cp = CP.HAPropsSI('cp_ha', 'T', T_K, 'P', P_atm_Pa, 'W', W)   # J/(kg dry air × K)
    except Exception:
        # Fallback (단순 추정)
        W = 0.622 * RH_frac * 1000 / (P_atm_Pa - RH_frac * 1000)
        h = 1006 * T_C + W * (2501e3 + 1860 * T_C)
        T_dp = T_K - 5  # 매우 거친 추정
        cp = 1006 + 1860 * W
    return {'W': W, 'h': h, 'T_dp_K': T_dp, 'cp': cp}


def _W_sat(T_surface_C, P_atm_Pa=101325.0):
    """표면 온도에서 포화 humidity ratio (응축 시 출구 W)."""
    try:
        T_K = T_surface_C + 273.15
        # 100% RH에서의 humidity ratio
        return CP.HAPropsSI('W', 'T', T_K, 'P', P_atm_Pa, 'R', 0.999)
    except Exception:
        # Fallback Magnus formula
        Psat = 611.2 * math.exp(17.62 * T_surface_C / (243.12 + T_surface_C))
        return 0.622 * Psat / (P_atm_Pa - Psat)



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
    fluid       = params.get('fluid', 'R290')
    wet_mode    = params.get('wet_coil', 'auto')
    input_mode  = params.get('input_mode', 'UA')
    UA_2ph      = float(params.get('UA_2ph', 15.9))
    UA_SH       = float(params.get('UA_SH', 2.2))
    eps_2ph_in  = float(params.get('eps_2ph', 0.85))
    eps_SH_in   = float(params.get('eps_SH', 0.5))
    dP_ref      = float(params.get('dP_ref', 0.02))

    # ── Inputs ──
    P_evap_bar = float(input.get('P_evap', 5.0))
    h_in_kjkg  = float(input.get('h_in', 280.0))
    m_dot_ref  = float(input.get('m_dot_ref', 0.005))
    T_air_in_C = float(input.get('T_air_in', 50.0))
    RH_air_in  = float(input.get('RH_air_in', 90.0))
    m_dot_air  = _cmm_to_mass(
        V_air_CMM=float(input.get('V_air_CMM', 2.54)),
        T_air_C=T_air_in_C, RH=RH_air_in,
    )

    # ── 입력 검증 ──
    if P_evap_bar <= 0:
        raise ValueError(f"P_evap는 양수여야 함: {P_evap_bar}")
    if m_dot_ref <= 0 or m_dot_air <= 0:
        raise ValueError(f"질량 유량은 양수: ref={m_dot_ref}, air={m_dot_air}")
    if not (0 < RH_air_in <= 100):
        raise ValueError(f"RH 범위: 0 < RH ≤ 100, 받음: {RH_air_in}")

    P_evap_Pa = P_evap_bar * 1e5
    h_in_J    = h_in_kjkg * 1000.0

    # ── 1. 냉매 입구 상태 (CoolProp) ──
    try:
        T_evap_K = CP.PropsSI('T', 'P', P_evap_Pa, 'Q', 0.5, fluid)
        h_l = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 0, fluid)
        h_v = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 1, fluid)
        h_fg = h_v - h_l
    except Exception as e:
        raise ValueError(f"냉매 포화 상태 계산 실패 (P={P_evap_bar}bar, fluid={fluid}): {e}")

    T_evap_C = T_evap_K - 273.15

    # 입구 quality (h_in 위치)
    if h_in_J < h_l:
        x_in = 0.0  # subcool 상태로 들어옴 (드뭄 — TXV 후 정상)
    elif h_in_J > h_v:
        x_in = 1.0 + 1e-6  # 이미 SH 상태 (역시 드뭄)
    else:
        x_in = (h_in_J - h_l) / h_fg

    # ── 2. 공기 입구 상태 ──
    air_in = _humid_air_props(T_air_in_C, RH_air_in)
    cp_air = air_in['cp']
    W_in = air_in['W']
    T_dp_in_C = air_in['T_dp_K'] - 273.15

    C_air = m_dot_air * cp_air  # 공기 측 capacity rate (W/K)

    # ── 3. Wet-coil 판단 ──
    # 표면 온도 ≈ T_evap (단순화). 정확하게는 wall T인데 L1엔 충분.
    T_surface_C = T_evap_C
    is_wet = (wet_mode == 'auto') and (T_dp_in_C > T_surface_C)

    # ── 4. 2-phase zone (응축 포함 가능) ──
    # 냉매 측: 일정 온도 T_evap, x_in → x=1 까지 → C_ref → ∞ → Cmin = C_air
    # ε-NTU: Cr = Cmin/Cmax = 0 → ε = 1 - exp(-NTU)

    # Q_max_2ph: 냉매가 받을 수 있는 최대 열량 (x_in → x=1)
    Q_max_2ph_ref = m_dot_ref * (h_v - h_in_J)
    # 공기가 줄 수 있는 최대 (T_air_in → T_evap)
    Q_max_2ph_air = C_air * (T_air_in_C - T_evap_C)
    # Cmin 결정: 어느 쪽이 먼저 한계?
    Q_max_2ph = min(Q_max_2ph_ref, Q_max_2ph_air)

    # ε_2ph 결정
    if input_mode == 'UA':
        # NTU = UA / Cmin (Cmin = C_air, since C_ref → ∞)
        if C_air > 0:
            NTU_2ph = UA_2ph / C_air
            eps_2ph = 1.0 - math.exp(-NTU_2ph) if NTU_2ph < 50 else 1.0
        else:
            eps_2ph = 0
    else:
        eps_2ph = max(0.0, min(0.999, eps_2ph_in))

    # 2-phase 열량 (sensible only, 응축은 따로)
    Q_sensible_2ph = eps_2ph * C_air * (T_air_in_C - T_evap_C)
    Q_sensible_2ph = max(0.0, Q_sensible_2ph)

    # 응축 처리 (latent)
    if is_wet:
        W_sat_surface = _W_sat(T_surface_C)
        # 단순 모델: 공기가 표면에 닿는 비율 = ε_2ph (sensible과 동일 ε 가정)
        # ω_out = ω_in - ε × (ω_in - ω_sat_surface)  if ω_in > ω_sat_surface
        if W_in > W_sat_surface:
            dW = eps_2ph * (W_in - W_sat_surface)
            condensate_rate = m_dot_air * dW  # kg/s
            # h_fg of water at T_surface
            h_fg_water = 2501e3 - 2.4 * T_surface_C  # J/kg, linear approx
            Q_latent = condensate_rate * h_fg_water
        else:
            condensate_rate = 0.0
            Q_latent = 0.0
    else:
        condensate_rate = 0.0
        Q_latent = 0.0

    Q_2ph_total = Q_sensible_2ph + Q_latent

    # 냉매 한계 체크: Q_2ph가 Q_max_2ph_ref를 넘으면 SH 영역도 침범
    if Q_2ph_total > Q_max_2ph_ref:
        # 냉매가 다 증발 (x_out = 1) + 일부 SH도 발생할 여유
        Q_2ph_total = Q_max_2ph_ref
        # 응축은 Q_max_2ph_ref 안에서 비율 조정
        if Q_sensible_2ph + Q_latent > 0:
            ratio = Q_max_2ph_ref / (Q_sensible_2ph + Q_latent)
            Q_sensible_2ph *= ratio
            Q_latent *= ratio
            condensate_rate *= ratio
        ref_fully_evap = True
    else:
        ref_fully_evap = (Q_2ph_total >= Q_max_2ph_ref - 1e-6)

    # 2-phase 후 공기 온도
    T_air_after_2ph_C = T_air_in_C - Q_sensible_2ph / C_air if C_air > 0 else T_air_in_C

    # 2-phase 출구 quality
    h_after_2ph_J = h_in_J + Q_2ph_total / m_dot_ref
    if h_after_2ph_J >= h_v - 1e-3:
        x_after_2ph = 1.0
    else:
        x_after_2ph = (h_after_2ph_J - h_l) / h_fg

    # ── 5. SH zone (있다면) ──
    Q_SH = 0.0
    h_ref_out_J = h_after_2ph_J
    T_air_out_C = T_air_after_2ph_C

    if ref_fully_evap and x_after_2ph >= 0.999:
        # SH zone 활성. C_ref_SH = m_dot × cp_SH (냉매 cp 사용)
        try:
            cp_ref_SH = CP.PropsSI('C', 'P', P_evap_Pa, 'Q', 1, fluid)
        except Exception:
            cp_ref_SH = 1700.0  # R290 가스 근사
        C_ref = m_dot_ref * cp_ref_SH
        Cmin_SH = min(C_ref, C_air)
        Cmax_SH = max(C_ref, C_air)
        Cr = Cmin_SH / Cmax_SH if Cmax_SH > 0 else 0

        if input_mode == 'UA':
            if Cmin_SH > 0:
                NTU_SH = UA_SH / Cmin_SH
                # Counter-flow ε-NTU
                if abs(Cr - 1.0) < 1e-6:
                    eps_SH = NTU_SH / (1 + NTU_SH)
                elif Cr < 1e-9:
                    eps_SH = 1.0 - math.exp(-NTU_SH)
                else:
                    num = 1.0 - math.exp(-NTU_SH * (1 - Cr))
                    den = 1.0 - Cr * math.exp(-NTU_SH * (1 - Cr))
                    eps_SH = num / den
                eps_SH = max(0.0, min(0.999, eps_SH))
            else:
                eps_SH = 0
        else:
            eps_SH = max(0.0, min(0.999, eps_SH_in))

        Q_SH = eps_SH * Cmin_SH * (T_air_after_2ph_C - T_evap_C)
        Q_SH = max(0.0, Q_SH)

        h_ref_out_J = h_after_2ph_J + Q_SH / m_dot_ref
        T_air_out_C = T_air_after_2ph_C - Q_SH / C_air if C_air > 0 else T_air_after_2ph_C

        # L_2ph_fraction (UA 비율로)
        if UA_2ph + UA_SH > 0:
            L_2ph_fraction = UA_2ph / (UA_2ph + UA_SH)
        else:
            L_2ph_fraction = 1.0
    else:
        # 냉매 다 증발 못함 → 전체가 2-phase zone
        L_2ph_fraction = 1.0

    # ── 6. 출구 상태 ──
    Q_total = Q_2ph_total + Q_SH
    Q_sensible_total = Q_sensible_2ph + Q_SH

    # 냉매 출구
    P_ref_out_Pa = P_evap_Pa * (1.0 - dP_ref)
    P_ref_out_bar = P_ref_out_Pa / 1e5
    try:
        T_ref_out_K = CP.PropsSI('T', 'P', P_ref_out_Pa, 'H', h_ref_out_J, fluid)
        T_ref_out_C = T_ref_out_K - 273.15
    except Exception:
        T_ref_out_C = T_evap_C

    # quality / SH
    if h_ref_out_J >= h_v:
        quality_out = 1.0 + (h_ref_out_J - h_v) / max(h_fg, 1)  # > 1 means SH
        SH_out = max(0.0, T_ref_out_C - T_evap_C)
    else:
        quality_out = (h_ref_out_J - h_l) / h_fg if h_fg > 0 else 0.0
        SH_out = 0.0

    # 공기 출구 W
    W_air_out = W_in - condensate_rate / m_dot_air if m_dot_air > 0 else W_in

    # 공기 출구 RH
    try:
        T_air_out_K = T_air_out_C + 273.15
        RH_air_out_frac = CP.HAPropsSI('R', 'T', T_air_out_K, 'P', 101325.0, 'W', max(W_air_out, 1e-6))
        RH_air_out = max(0.0, min(100.0, RH_air_out_frac * 100))
    except Exception:
        RH_air_out = RH_air_in  # fallback

    outputs = {
        'T_ref_out':       T_ref_out_C,
        'h_ref_out':       h_ref_out_J / 1000.0,
        'P_ref_out':       P_ref_out_bar,
        'quality_out':     quality_out,
        'SH_out':          SH_out,
        'T_evap':          T_evap_C,
        'T_air_out':       T_air_out_C,
        'RH_air_out':      RH_air_out,
        'W_air_out':       W_air_out,
        'Q_total':         Q_total,
        'Q_sensible':      Q_sensible_total,
        'Q_latent':        Q_latent,
        'condensate_rate': condensate_rate,
        'L_2ph_fraction':  L_2ph_fraction,
        'is_wet':          1.0 if is_wet else 0.0,
    }
    return {'outputs': outputs, 'newState': state}


def validate(params):
    errors = []
    fluid = params.get('fluid')
    if fluid not in FLUIDS:
        errors.append({'key': 'fluid', 'msg': f'fluid는 {FLUIDS} 중 하나'})
    mode = params.get('input_mode', 'UA')
    if mode not in INPUT_MODES:
        errors.append({'key': 'input_mode', 'msg': f'input_mode는 {INPUT_MODES} 중'})
    for key, lo, hi in [
        ('UA_2ph', 0.1, 1e5),
        ('UA_SH', 0.1, 1e5),
        ('eps_2ph', 0.0, 1.0),
        ('eps_SH', 0.0, 1.0),
        ('dP_ref', 0.0, 0.5),
    ]:
        v = params.get(key)
        if v is None: continue
        if not (lo <= v <= hi):
            errors.append({'key': key, 'msg': f'{key} 범위: {v} (허용 {lo}~{hi})'})
    return errors
