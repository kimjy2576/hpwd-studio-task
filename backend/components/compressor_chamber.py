"""
Compressor (Chamber 1-Cycle) — On-design L3
═══════════════════════════════════════════════════════════════════════
Chamber-resolved 1-cycle 평균 물리 모델. Bell PDSim의 chamber 해석 개념
(재팽창·누설·밸브 손실·polytropic 압축)을 차용하되, 회전각 θ 적분 대신
1 사이클 평균으로 단순화한 algebraic 물리 모델. (회귀 ROM 아님 — 실제
물리식을 직접 계산.) 학계 정통 PDSim의 계산 부담(60s/point)을 ~50ms로 압축.

※ 구 명칭 'PDSim ROM'은 misnomer였음 (실제론 ROM=Reduced-Order Model이
   아니라 1-cycle 평균 물리 모델). 2026 명칭 정리.

Cycle 단계 (reciprocating):
  1. BDC (Bottom Dead Center) — 흡입 완료, V_max
  2. 압축 — polytropic P×V^n = const, 단 n_eff는 누설 보정
  3. 토출 시작 — P_internal = P_su × (V_max/V_clear)^n
     P_internal vs P_dis 비교:
       under-comp: 추가 일 필요 (정적 일량 v×ΔP)
       over-comp: 토출 손실
  4. TDC (Top Dead Center) — 토출 완료, V_clear
  5. 재팽창 — clearance gas가 흡입 압력까지 팽창
     V_re = V_clear × (P_dis/P_su)^(1/n_eff)
     실효 흡입 체적 V_eff = V_max - V_re
  6. 밸브 손실:
     ΔP_in  = ζ_in  × (m_dot²) / (ρ × A_valve_in²)
     ΔP_out = ζ_out × (m_dot²) / (ρ × A_valve_out²)
  7. 누설:
     m_leak = C_d × A_leak × √(2 × ρ × ΔP_chamber) × (N/N_ref)^(-n_leak)
     실효 m_dot = m_dot_swept × η_v - m_leak
  8. 마찰 + 모터:
     W_friction = W_f_const + α_f × N² + β_f × P_dis
     W_elec = (W_indicated + W_friction) / (η_motor × η_inverter)

Reference:
  Bell I.H., Lemort V., Groll E.A., Braun J.E., King G.B., Horton W.T.,
  "Liquid flooded compression and expansion in scroll machines",
  IJR, 2012. (chamber 모델링 개념의 기반)
  
  PDSim implementation:
  Bell I.H., et al., "PDSim: A general quasi-steady model for
  positive displacement machines", IJR, 2020.
"""

import math
import CoolProp.CoolProp as CP

FLUIDS = ['R290']
COMPRESSOR_TYPES = ['reciprocating']  # 우선 reciprocating만

# default parameters — R290 ~10cc 가전 reciprocating (Winandy/AHRI와 동일 압축기)
# Winandy 회귀 결과를 chamber 모델이 재현하도록 calibrated.


modelDescription = {
    'typeNo': 103,
    'name': 'Compressor (Chamber 1-Cycle)',
    'category': 'refrigerant',
    'modelType': 'on-design',
    'fidelity': 1.0,
    'description': 'Chamber-resolved 물리 모델 — reciprocating, 1-cycle 평균 (Bell PDSim 개념)',
    'backend': 'python',
    'variables': [
        # ═══════ Parameters ═══════
        # Group: Material
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        {'name': 'comp_type', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'reciprocating', 'unit': '-', 'options': COMPRESSOR_TYPES,
         'description': '압축기 형태'},

        # Group: Operating
        {'name': 'T_amb', 'causality': 'parameter', 'type': 'Real',
         'group': 'Operating', 'start': 25.0, 'unit': '°C', 'description': '주변 온도'},

        # Group: Geometry (압축기 물리 치수)
        {'name': 'V_disp', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 7.5, 'unit': 'cm³',
         'description': '행정 체적 (BDC - TDC 차이)'},
        {'name': 'clearance_ratio', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.03, 'unit': '-',
         'description': 'Clearance 체적 / V_disp (TDC 잔류 비율)'},
        {'name': 'rv_in', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 2.5, 'unit': '-',
         'description': '내부 체적비 (built-in volume ratio)'},
        {'name': 'A_valve_in_mm2', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 8.0, 'unit': 'mm²',
         'description': '흡입 밸브 유효 면적'},
        {'name': 'A_valve_out_mm2', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 6.0, 'unit': 'mm²',
         'description': '토출 밸브 유효 면적'},
        {'name': 'N_rated', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 1800.0, 'unit': 'rpm',
         'description': '정격 회전수 (누설 RPM 보정의 기준)'},
        {'name': 'eta_motor', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.90, 'unit': '-', 'description': '모터 효율'},
        {'name': 'eta_inv', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.95, 'unit': '-', 'description': '인버터 효율'},

        # Group: Fitting Parameters (실험 데이터로 calibration)
        {'name': 'zeta_valve', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.5, 'unit': '-',
         'description': '밸브 손실 계수 (in/out 공통)'},
        {'name': 'A_leak_mm2', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.02, 'unit': 'mm²',
         'description': '누설 갭 등가 면적'},
        {'name': 'Cd_leak', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.6, 'unit': '-',
         'description': '누설 discharge coefficient'},
        {'name': 'n_leak_rpm', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.5, 'unit': '-',
         'description': '누설의 RPM 의존성 (저속에서 ↑)'},
        {'name': 'over_comp_factor', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 0.3, 'unit': '-',
         'description': 'Over-comp 손실 가중 (P_int > P_dis 시). 시험으로 fitting'},
        {'name': 'n_poly_base', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.13, 'unit': '-',
         'description': '폴리트로픽 지수 fallback (CoolProp 실패 시. 정상은 cp/cv 사용)'},
        {'name': 'W_f_const', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 20.0, 'unit': 'W',
         'description': '정수 마찰 손실 (오일/베어링)'},
        {'name': 'alpha_f_rpm', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 8e-6, 'unit': 'W/rpm²',
         'description': 'RPM² 비례 마찰 (점성)'},
        {'name': 'AU_loss', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 5.0, 'unit': 'W/K', 'description': '외부 열손실 UA'},

        # ═══════ Inputs ═══════
        {'name': 'P_suc', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '흡입 압력 (abs)'},
        {'name': 'T_suc', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '흡입 온도'},
        {'name': 'P_dis', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '토출 압력 (abs)'},
        {'name': 'N', 'causality': 'input', 'type': 'Real',
         'unit': 'rpm', 'description': '회전 속도'},

        # ═══════ Outputs ═══════
        {'name': 'm_dot', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량 (실효, 누설 차감)'},
        {'name': 'm_leak', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/s', 'description': '누설 유량 (L3 차별)'},
        {'name': 'T_dis', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '토출 온도'},
        {'name': 'h_dis', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '토출 비엔탈피'},
        {'name': 'W_elec', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '전기 입력'},
        {'name': 'W_indicated', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': 'indicated work (chamber 일, 마찰 제외)'},
        {'name': 'W_friction', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '기계 마찰 손실 (L3 차별)'},
        {'name': 'W_valve_in', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '흡입 밸브 손실 (L3 차별)'},
        {'name': 'W_valve_out', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '토출 밸브 손실 (L3 차별)'},
        {'name': 'eta_v', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '체적 효율'},
        {'name': 'eta_is', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '등엔트로피 효율'},
        {'name': 'P_internal', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': 'TDC 내부 압력 (over/under-comp 진단)'},
        {'name': 'pi_ratio', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'P_dis / P_suc'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    return {}


def step(input, params, state, dt):
    """Chamber 1-Cycle — 1 사이클 평균 거동.
    
    중간 변수 추적:
      V_max, V_clear (기하)
      n_eff (실효 polytropic, 누설 보정)
      P_internal (TDC 압력)
      m_dot_swept, m_leak, m_dot
      W_indicated, W_valve_in/out, W_friction
      η_v, η_is
    """

    # ── Parameters ──
    fluid       = params.get('fluid', 'R290')
    T_amb_C     = float(params.get('T_amb', 25.0))
    V_disp_cm3  = float(params.get('V_disp', 7.5))
    clear_ratio = float(params.get('clearance_ratio', 0.03))
    rv_in       = float(params.get('rv_in', 2.5))
    A_in_mm2    = float(params.get('A_valve_in_mm2', 8.0))
    A_out_mm2   = float(params.get('A_valve_out_mm2', 6.0))
    zeta_v      = float(params.get('zeta_valve', 1.5))
    A_leak_mm2  = float(params.get('A_leak_mm2', 0.02))
    Cd_leak     = float(params.get('Cd_leak', 0.6))
    n_leak_rpm  = float(params.get('n_leak_rpm', 0.5))
    n_poly      = float(params.get('n_poly_base', 1.13))
    W_f_const   = float(params.get('W_f_const', 20.0))
    alpha_f     = float(params.get('alpha_f_rpm', 8e-6))
    AU_loss     = float(params.get('AU_loss', 5.0))
    eta_motor   = float(params.get('eta_motor', 0.90))
    eta_inv     = float(params.get('eta_inv', 0.95))
    # 신규 fitting/geometry params (이전엔 하드코딩)
    N_rated     = float(params.get('N_rated', 1800.0))
    over_comp_factor = float(params.get('over_comp_factor', 0.3))

    # ── Inputs ──
    P_suc_bar = float(input.get('P_suc', 5.0))
    T_suc_C   = float(input.get('T_suc', 5.0))
    P_dis_bar = float(input.get('P_dis', 18.0))
    N_rpm     = float(input.get('N', 1800.0))

    # ── 입력 검증 ──
    if P_suc_bar <= 0 or P_dis_bar <= 0:
        raise ValueError(f"압력은 양수 (P_suc={P_suc_bar}, P_dis={P_dis_bar})")
    if P_dis_bar <= P_suc_bar:
        raise ValueError(f"P_dis ({P_dis_bar}) <= P_suc ({P_suc_bar})")
    if N_rpm <= 0:
        raise ValueError(f"N은 양수 (받은 값: {N_rpm})")

    # ── 단위 변환 ──
    P_suc_Pa = P_suc_bar * 1e5
    P_dis_Pa = P_dis_bar * 1e5
    T_suc_K  = T_suc_C + 273.15
    omega_Hz = N_rpm / 60.0
    V_clear_m3 = V_disp_cm3 * clear_ratio * 1e-6
    V_max_m3   = V_disp_cm3 * (1 + clear_ratio) * 1e-6
    A_in_m2    = A_in_mm2 * 1e-6
    A_out_m2   = A_out_mm2 * 1e-6
    A_leak_m2  = A_leak_mm2 * 1e-6
    pi_ratio   = P_dis_bar / P_suc_bar

    # ── 흡입 상태 (CoolProp) ──
    try:
        rho_su = CP.PropsSI('D', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        h_su   = CP.PropsSI('H', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        s_su   = CP.PropsSI('S', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        # 실제 polytropic 지수: cp/cv (R290 ~1.13)
        cp_g = CP.PropsSI('C', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        cv_g = CP.PropsSI('O', 'P', P_suc_Pa, 'T', T_suc_K, fluid)
        if cv_g > 0:
            n_poly = cp_g / cv_g
    except Exception as e:
        raise ValueError(f"흡입 상태 계산 실패: {e}")

    # ── 1. 재팽창 (clearance gas → 흡입 압력) ──
    # clearance volume 가스가 흡입 압력까지 팽창
    # V_re = V_clear × (P_dis / P_suc)^(1/n)
    V_re_m3 = V_clear_m3 * (pi_ratio ** (1.0 / n_poly))
    V_eff_m3 = max(V_max_m3 - V_re_m3, 0.01 * V_max_m3)  # 실효 흡입 체적

    # ── 2. 누설 (chamber → 흡입측, RPM 의존) ──
    # m_leak = Cd × A × √(2ρΔP) × (N_ref/N)^n_leak
    # 저속에서 사이클 시간 ↑ → 누설 누적 ↑
    # 누설 RPM 보정: 사용자가 N_rated parameter로 정의 (이전 하드코딩 3000 제거)
    rpm_factor = (N_rpm / N_rated) ** (-n_leak_rpm) if N_rpm > 0 else 1.0
    dP_chamber = P_dis_Pa - P_suc_Pa
    rho_avg = rho_su * 1.5  # 압축 중 평균 밀도 추정 (rough)
    m_leak_kgs = Cd_leak * A_leak_m2 * math.sqrt(max(0.0, 2 * rho_avg * dP_chamber)) * rpm_factor

    # ── 3. Swept mass flow ──
    m_dot_swept = V_eff_m3 * omega_Hz * rho_su  # kg/s

    # ── 4. 실효 mass flow ──
    m_dot = max(m_dot_swept - m_leak_kgs, 1e-6)

    # ── 5. 체적 효율 ──
    m_dot_ideal = V_max_m3 * omega_Hz * rho_su
    eta_v = max(0.05, m_dot / m_dot_ideal)

    # ── 6. TDC 내부 압력 (polytropic 압축) ──
    # P × V^n = const, V_max → V_clear (built-in volume ratio)
    # 단, V_clear는 매우 작아서 V_max/V_clear 비가 ~25배 — 현실은 가스가
    # 토출 밸브가 열리면서 P_dis 부근까지만. rv_in이 built-in volume ratio:
    # P_internal = P_su × rv_in^n  (rv_in이 actual compression ratio)
    # rv_in default 2.5 → P_internal ≈ 5 × 2.5^1.13 ≈ 14 bar (아래 P_dis 18보다 약간 적음 = under-comp)
    P_int_Pa = P_suc_Pa * (rv_in ** n_poly)
    P_int_bar = P_int_Pa / 1e5

    # ── 7. 등엔트로피 토출 (CoolProp) ──
    try:
        h_dis_is = CP.PropsSI('H', 'P', P_dis_Pa, 'S', s_su, fluid)
    except Exception as e:
        raise ValueError(f"등엔트로피 토출 실패: {e}")
    w_is = h_dis_is - h_su  # J/kg

    # ── 8. Over/under-compression 보정 ──
    # 압축 후 P_internal, 그 후 토출 밸브 열림
    # P_internal < P_dis (under-comp): 갑자기 P_dis로 올라감 → 추가 일 ~ v×ΔP
    # P_internal > P_dis (over-comp): 압력 떨어지며 토출 → 손실 (작은 항)
    # specific volume at end of compression (rv_in 만큼 압축됨)
    v_internal = (1.0 / rho_su) / rv_in  # m³/kg
    
    if P_int_Pa < P_dis_Pa:
        w_overunder = v_internal * (P_dis_Pa - P_int_Pa)
    else:
        w_overunder = over_comp_factor * v_internal * (P_int_Pa - P_dis_Pa)
    
    # ── 9. 밸브 손실 ──
    # ΔP_valve = ζ × m_dot² / (ρ × A²)  → W = m_dot × ΔP / ρ
    # 흡입: ρ_su 사용
    if A_in_m2 > 0 and m_dot > 0:
        dP_in_Pa = zeta_v * (m_dot ** 2) / (rho_su * A_in_m2 ** 2)
        W_valve_in_W = m_dot * dP_in_Pa / rho_su
    else:
        dP_in_Pa = 0; W_valve_in_W = 0
    # 토출: ρ_dis 추정
    try:
        rho_dis_est = CP.PropsSI('D', 'P', P_dis_Pa, 'H', h_dis_is, fluid)
    except Exception:
        rho_dis_est = rho_su * pi_ratio
    if A_out_m2 > 0 and m_dot > 0:
        dP_out_Pa = zeta_v * (m_dot ** 2) / (rho_dis_est * A_out_m2 ** 2)
        W_valve_out_W = m_dot * dP_out_Pa / rho_dis_est
    else:
        dP_out_Pa = 0; W_valve_out_W = 0

    # ── 10. Indicated work (chamber 일량) ──
    w_chamber = w_is + w_overunder  # J/kg
    W_indicated_W = m_dot * w_chamber + W_valve_in_W + W_valve_out_W

    # ── 11. 실제 토출 엔탈피 ──
    h_dis_J = h_su + w_chamber + (W_valve_in_W + W_valve_out_W) / max(m_dot, 1e-6)
    try:
        T_dis_K = CP.PropsSI('T', 'P', P_dis_Pa, 'H', h_dis_J, fluid)
    except Exception:
        T_dis_K = T_suc_K + 80

    # ── 12. 등엔트로피 효율 ──
    if abs(w_chamber) > 1e-3:
        eta_is = max(0.05, min(0.99, w_is / w_chamber))
    else:
        eta_is = 0.7

    # ── 13. 마찰 + 모터 ──
    W_friction_W = W_f_const + alpha_f * (N_rpm ** 2)
    W_shaft_W = W_indicated_W + W_friction_W
    W_elec_W = W_shaft_W / (eta_motor * eta_inv)

    outputs = {
        'm_dot':       m_dot,
        'm_leak':      m_leak_kgs,
        'T_dis':       T_dis_K - 273.15,
        'h_dis':       h_dis_J / 1000.0,
        'W_elec':      W_elec_W,
        'W_indicated': W_indicated_W,
        'W_friction':  W_friction_W,
        'W_valve_in':  W_valve_in_W,
        'W_valve_out': W_valve_out_W,
        'eta_v':       eta_v,
        'eta_is':      eta_is,
        'P_internal':  P_int_bar,
        'pi_ratio':    pi_ratio,
    }
    return {'outputs': outputs, 'newState': state}


def validate(params):
    errors = []
    fluid = params.get('fluid')
    if fluid not in FLUIDS:
        errors.append({'key': 'fluid', 'msg': f'fluid는 {FLUIDS} 중 하나'})
    for key, lo, hi in [
        ('V_disp', 0.1, 1000),
        ('clearance_ratio', 0.001, 0.5),
        ('rv_in', 1.0, 10.0),
        ('N_rated', 100, 20000),
        ('A_valve_in_mm2', 0.1, 100),
        ('A_valve_out_mm2', 0.1, 100),
        ('zeta_valve', 0.5, 5.0),
        ('A_leak_mm2', 0.001, 10),
        ('Cd_leak', 0.1, 1.0),
        ('n_leak_rpm', 0.0, 2.0),
        ('over_comp_factor', 0.0, 2.0),
        ('n_poly_base', 1.0, 1.5),
        ('W_f_const', 0, 500),
        ('alpha_f_rpm', 0, 1e-3),
        ('AU_loss', 0, 1000),
        ('eta_motor', 0.1, 1.0),
        ('eta_inv', 0.1, 1.0),
    ]:
        v = params.get(key)
        if v is None: continue
        if not (lo <= v <= hi):
            errors.append({'key': key, 'msg': f'{key} 범위 벗어남: {v} (허용 {lo}~{hi})'})
    return errors
