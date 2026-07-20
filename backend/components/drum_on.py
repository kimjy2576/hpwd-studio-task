"""
drum_on.py — L3 (On-Design) 드럼 건조 모델 [1단계: 핵심 물리 골격]

dryer-drum-sim(kimjy2576/dryer-drum-sim)의 3-Zone 다층직물 물리를,
hpwd-studio-task 컴포넌트 표준으로 재구성. Modelica Drum_L3의 ground truth.

문헌(model-docs) 7-step 완비 + 약점 3개 개선(3단계):
  Step1 3-Zone(→N-Zone) 직물, Step2 Fick 확산, Step3 Darcy-Leverett 모세관,
  Step4 표면증발(Lewis)+텀블링 Fr, Step5 NTU-ε 4경로, Step6 gap누설, Step7 Ergun.

약점 개선 (dryer-drum-sim 대비):
  C(자유수 smooth): if 분기 → g_free=M_free/(M_free+eps_free) 연속게이트.
    eps_free→0이면 원본 수렴. Modelica 초기화 안정 (팬 softplus 철학).
  B(N셀 일반화): 3셀 하드코딩 → N_zones=len(zone_fractions) 가변.
    각 인접쌍 diffusion↔capillary blend(w_cap=i/(N-2)). N=3서 원본 정확재현
    (쌍0 순확산·쌍1 순모세관). L_char N정규화(×2/(N-1))로 수렴 유도.
    ⚠️ 완전수렴은 이산화 한계(max_J 셀의존 등) — N=3=문헌 L3 기본.
  A(물성 명시): 직물물성 출처·타당범위·민감도 주석. 거짓정밀 주장 안 함.
    실측 부족한 brooks_corey/diffusion_S는 토양값 차용 명시 + params 노출.

동적 모델 — 팬(대수)과 달리 state에 N-zone 함수율+직물온도 시간전진.
  인터페이스: step(input, params, state, dt) → {'outputs':{...}, 'newState':{...}}
  state = {'M_water_z':[3], 'M_free_water':float, 'T_fabric':float}

물리 참고:
  Fick 내부확산 + Darcy-Leverett 모세관(불포화 다공질). 표면증발 Lewis.
  텀블링 Froude Fr=ω²R/g로 zone 교환. Brooks-Corey 상대투과도.
"""
import math

# ══════════════════════════════════════════════════════════════
# 공기 물성 (psychrometrics — dryer-drum-sim 방식)
# ══════════════════════════════════════════════════════════════
P_ATM = 101325.0
CP_A = 1006.0
CP_V = 1860.0
H_FG_0 = 2_501_000.0
R_DA = 287.055
R_GAS = 8.314
# 4경로 저항·hA 상관식용 공기 물성 (~50°C, dryer-drum-sim 값)
K_AIR = 0.028      # 열전도도 W/(m·K)
MU_AIR = 2.0e-5    # 점도 Pa·s
PR_AIR = 0.71      # Prandtl
RHO_AIR = 1.05     # 밀도 kg/m³

def _p_sat(T):
    if T >= 0:
        return 611.21 * math.exp((18.678 - T / 234.5) * T / (257.14 + T))
    return 611.15 * math.exp((23.036 - T / 333.7) * T / (279.82 + T))

def _omega_sat(T, P=P_ATM):
    ps = min(_p_sat(T), P * 0.99)
    return 0.62198 * ps / (P - ps)

def _h_fg(T):
    return H_FG_0 - 2370.0 * T

def _sigma_water(T):
    return 0.0756 - 0.000139 * T

def _mu_water(T):
    return 0.001 * math.exp(-3.7188 + 578.919 / (T + 137.546))

def _rho_air(T, P=P_ATM):
    return P / (R_DA * (T + 273.15))


# ══════════════════════════════════════════════════════════════
# 직물 물성 preset (dryer-drum-sim FabricProperties)
#   약점A(물성 명시): 각 물성의 출처·타당범위·민감도를 정직하게 문서화.
#   실측 직물 데이터가 없어 문헌 추정값을 쓰되, 거짓 정밀 주장은 하지 않음.
#   ─ 물성별 근거 (cotton 기준) ─
#     D_ref [m²/s]: 섬유 수분확산계수. 직물 건조 문헌 1e-10~1e-9. 현재 5e-10 = 타당범위.
#                   [민감도 H] 감률건조 후반 속도 직결.
#     E_a [J/mol]: 흡착수 확산 활성화에너지. 섬유 30~40 kJ/mol. 현재 35000 = 타당.
#                  [민감도 M] 온도의존성.
#     K_abs [m²]: 절대투과율. 직물 다공구조 추정. [민감도 M] 모세관 이동.
#     absorption_ratio: 최대흡수량 kg水/kg건. cotton ~1.8(면), poly ~0.6(소수성). 실측 근거 있음.
#     delta [m]: 직물 두께. 도면/실측. rho_fabric: 섬유밀도(실측).
#     rho_bulk: 드럼내 벌크밀도 ~300. [민감도 M] 충전층 저항.
#   ⚠️ brooks_corey_exponent(모세관 K_r=S^n)·diffusion_S_exponent(D∝S^n)는
#      직물 위킹 실측 부족 → 토양역학값(2~4, 0.5~1) 차용. step() params로 노출.
# ══════════════════════════════════════════════════════════════
FABRIC_PRESETS = {
    "cotton": {
        "Cp_dry": 1300.0, "absorption_ratio": 1.8,
        "D_ref": 5e-10, "E_a": 35000.0, "K_abs": 1e-12, "r_pore": 50e-6,
        "contact_angle": 10.0, "delta": 1.0e-3, "rho_fabric": 1520.0, "rho_bulk": 300.0,
    },
    "poly": {
        "Cp_dry": 1100.0, "absorption_ratio": 0.6,
        "D_ref": 5e-11, "E_a": 40000.0, "K_abs": 1e-11, "r_pore": 30e-6,
        "contact_angle": 70.0, "delta": 0.6e-3, "rho_fabric": 1380.0, "rho_bulk": 300.0,
    },
    "mixed": {
        "Cp_dry": 1220.0, "absorption_ratio": 1.2,
        "D_ref": 2e-10, "E_a": 37000.0, "K_abs": 5e-12, "r_pore": 40e-6,
        "contact_angle": 40.0, "delta": 0.8e-3, "rho_fabric": 1460.0, "rho_bulk": 300.0,
    },
}


def init_state(params):
    """초기 상태: 3-zone 함수율 분배 + 자유수 분리."""
    fabric = FABRIC_PRESETS[params.get("fabric", "cotton")]
    M_dry = float(params.get("M_dry", 3.0))
    X0 = float(params.get("X0", 0.6))                    # 초기 함수율 kg水/kg건
    M_water_init = M_dry * X0
    zone_fractions = params.get("zone_fractions", (0.25, 0.35, 0.40))
    T_fab0 = float(params.get("T_fabric_init", 25.0))

    M_dry_z = [M_dry * f for f in zone_fractions]
    M_water_max_z = [md * fabric["absorption_ratio"] for md in M_dry_z]
    M_water_max_total = sum(M_water_max_z)

    if M_water_init > M_water_max_total:
        M_free = M_water_init - M_water_max_total
        S_init = 1.0
    else:
        M_free = 0.0
        S_init = M_water_init / max(M_water_max_total, 1e-12)
    M_water_z = [mx * S_init for mx in M_water_max_z]

    return {
        "M_water_z": M_water_z,
        "M_water_max_z": M_water_max_z,
        "M_free_water": M_free,
        "T_fabric": T_fab0,
    }


def step(input, params, state, dt):
    """
    fidelity 파라미터로 L1/L2/L3 선택 (기본 L3).
      params['fidelity'] ∈ {'L1','L2','L3'}
    L1(Lewis+항률)/L2(감률+흡착)는 Modelica Drum_L1/L2와 동일 식 —
    MoistAir 선형 psychrometrics(_ma_* 함수) 정확 복제로 궤적 일치.
    L3(3-Zone 4경로 동적)는 dryer-drum-sim 포팅(_step_L3).
    ⚠️ 동적 모델: init_state로 상태 초기화 후 step 반복. L1/L2는 상태
       {m_w, T_cl}, L3는 {M_water_z[N], T_fabric, M_free}.
    """
    fidelity = params.get('fidelity', 'L3')
    if fidelity == 'L1':
        return _step_L1(input, params, state, dt)
    elif fidelity == 'L2':
        return _step_L2(input, params, state, dt)
    else:
        return _step_L3(input, params, state, dt)


# ══════════════════════════════════════════════════════════════
# Modelica MoistAir 정합 psychrometrics (L1/L2 궤적 일치용)
#   ⚠️ L3용 _p_sat/_omega_sat와 별개 — Modelica MoistAir 식 정확 복제.
#   상수: cp_da=1005, cp_v=1860, cp_w=4186, R_da=287.05, eps=0.622,
#         T0=273.15, hfg0=2.501e6, p_ref=101325.
# ══════════════════════════════════════════════════════════════
_MA_cp_da = 1005.0; _MA_cp_v = 1860.0; _MA_cp_w = 4186.0
_MA_R_da = 287.05; _MA_eps = 0.622; _MA_T0 = 273.15
_MA_hfg0 = 2.501e6; _MA_p_ref = 101325.0

def _ma_p_vs(T):      # 포화증기압 Magnus (T in K)
    Tc = T - _MA_T0
    return 610.78 * math.exp(17.27 * Tc / (Tc + 237.3))

def _ma_W_sat(T):     # 포화습도비 @ p_ref
    pvs = _ma_p_vs(T)
    return _MA_eps * pvs / (_MA_p_ref - pvs)

def _ma_rho_da(T, W): # dry-air 부분밀도 @ p_ref
    return _MA_p_ref * _MA_eps / ((_MA_eps + W) * _MA_R_da * T)

def _ma_h_g(T):       # 증기 엔탈피
    return _MA_hfg0 + _MA_cp_v * (T - _MA_T0)

def _ma_h_fg(T):      # 잠열
    return _MA_hfg0 + (_MA_cp_v - _MA_cp_w) * (T - _MA_T0)

def _ma_h_da(T, W):   # per-dry-air 엔탈피 h_tilde
    return _MA_cp_da * (T - _MA_T0) + W * (_MA_hfg0 + _MA_cp_v * (T - _MA_T0))

def _ma_T_from_h(h, W):  # 역함수 T(h_tilde, W)
    return _MA_T0 + (h - W * _MA_hfg0) / (_MA_cp_da + W * _MA_cp_v)


# ══════════════════════════════════════════════════════════════
# L1 — Lewis + 항률건조 (Modelica Drum_L1 동형, 동적)
# ══════════════════════════════════════════════════════════════
def init_state_L1(params):
    m_cl_dry = float(params.get('m_cl_dry', 3.0))
    X0 = float(params.get('X0', 0.6))
    Tcl0 = float(params.get('Tcl0', 298.15))
    return {'m_w': X0 * m_cl_dry, 'T_cl': Tcl0}

def _step_L1(input, params, state, dt):
    """Lewis analogy + 항률증발. well-mixed 공기 CV. der→오일러."""
    m_cl_dry = float(params.get('m_cl_dry', 3.0))
    c_p_cl = float(params.get('c_p_cl', 1500.0))
    A_eff = float(params.get('A_eff', 10.0))
    h_a = float(params.get('h_a', 50.0))
    A_drum = float(params.get('A_drum', 0.15))
    K_drum = float(params.get('K_drum', 30.0))
    UA_amb = float(params.get('UA_amb', 0.0))
    T_amb = float(params.get('T_amb', 298.15))

    m_w = state['m_w']; T_cl = state['T_cl']
    # 입구 공기 (K, 절대)
    T_in = float(input.get('T_in_K', input.get('T_in', 293.15) + (273.15 if input.get('T_in', 293.15) < 200 else 0)))
    W_in = float(input.get('W_in', input.get('omega', 0.010)))
    m_flow_da = float(input.get('m_flow_da', input.get('m_dot_air', 0.035)))

    # well-mixed 공기 CV 대수해: W_out, T_out
    #   Lewis: m_evap = h_m·A·(W_s - W_out)·g_dry, h_m = h_a/cp_da
    #   g_dry = m_w/(m_w+eps_dry): 잔수 게이트 (Modelica Drum_L1 동형).
    #     물 없으면 증발 정지 → m_w<0 방지(물리 타당성 가드).
    #     fidelity 업그레이드 아님 — 항률만 유지, 건조점서 멈출 뿐.
    #   질량: m_flow·(W_out - W_in) = m_evap → W_out 대수
    eps_dry = float(params.get('eps_dry', 1e-3))
    g_dry = m_w / (m_w + eps_dry)
    W_s = _ma_W_sat(T_cl)
    h_m = h_a / _MA_cp_da
    # m_flow·(W_out-W_in) = g_dry·h_m·A·(W_s-W_out)
    hmA = h_m * A_eff * g_dry
    W_out = (m_flow_da * W_in + hmA * W_s) / (m_flow_da + hmA)
    m_evap = hmA * (W_s - W_out)

    # 에너지 CV: T_out (well-mixed)
    #   m_flow·(h_out-h_in) = -h_a·A·(T_out-T_cl) + m_evap·h_g(T_cl) - Q_amb
    #   h_out = h_da(T_out, W_out), h_in = h_da(T_in, W_in)
    #   선형이라 T_out 대수해 가능
    h_in = _ma_h_da(T_in, W_in)
    hg = _ma_h_g(T_cl)
    # h_out = cp_da·(T_out-T0) + W_out·(hfg0+cp_v·(T_out-T0))
    #       = (cp_da+W_out·cp_v)·(T_out-T0) + W_out·hfg0
    # m_flow·[(cp_da+W_out·cp_v)(T_out-T0)+W_out·hfg0 - h_in]
    #   = -h_a·A·(T_out-T_cl) + m_evap·hg - UA·(T_out-T_amb)
    cpm = _MA_cp_da + W_out * _MA_cp_v
    # LHS: m_flow·cpm·T_out - m_flow·cpm·T0 + m_flow·W_out·hfg0 - m_flow·h_in
    # RHS: -h_a·A·T_out + h_a·A·T_cl + m_evap·hg - UA·T_out + UA·T_amb
    # (m_flow·cpm + h_a·A + UA)·T_out = m_flow·cpm·T0 - m_flow·W_out·hfg0 + m_flow·h_in + h_a·A·T_cl + m_evap·hg + UA·T_amb
    haA = h_a * A_eff
    lhs_coef = m_flow_da * cpm + haA + UA_amb
    rhs = (m_flow_da * cpm * _MA_T0 - m_flow_da * W_out * _MA_hfg0
           + m_flow_da * h_in + haA * T_cl + m_evap * hg + UA_amb * T_amb)
    T_out = rhs / lhs_coef

    # cloth 동특성 (오일러 전진)
    hfg = _ma_h_fg(T_cl)
    dm_w = -m_evap
    dT_cl = (haA * (T_out - T_cl) - m_evap * hfg) / (m_cl_dry * c_p_cl + m_w * _MA_cp_w)
    m_w_new = m_w + dm_w * dt
    T_cl_new = T_cl + dT_cl * dt

    # 압력강하
    rho_da = _ma_rho_da(T_in, W_in)
    u = m_flow_da / (rho_da * A_drum)
    dp_drum = K_drum * u * abs(u)

    X = m_w / m_cl_dry
    return {'outputs': {
        'X': X, 'm_w': m_w, 'T_cl': T_cl - 273.15, 'T_cl_K': T_cl,
        'm_evap': m_evap, 'W_out': W_out, 'T_out': T_out - 273.15,
        'W_s': W_s, 'dp_drum': dp_drum, 'fidelity': 'L1',
    }, 'newState': {'m_w': m_w_new, 'T_cl': T_cl_new}}


# ══════════════════════════════════════════════════════════════
# L2 — 감률 + 흡착 (Modelica Drum_L2 동형, 동적)
# ══════════════════════════════════════════════════════════════
def init_state_L2(params):
    return init_state_L1(params)

def _step_L2(input, params, state, dt):
    """L1 + 흡착평형 X_eq(RH) + 감률인자 f_dry. der→오일러."""
    m_cl_dry = float(params.get('m_cl_dry', 3.0))
    c_p_cl = float(params.get('c_p_cl', 1500.0))
    A_eff = float(params.get('A_eff', 10.0))
    h_a = float(params.get('h_a', 50.0))
    A_drum = float(params.get('A_drum', 0.15))
    K_drum = float(params.get('K_drum', 30.0))
    UA_amb = float(params.get('UA_amb', 0.0))
    T_amb = float(params.get('T_amb', 298.15))
    X_cr = float(params.get('X_cr', 0.2))
    a_sorp = float(params.get('a_sorp', 0.25))
    n_sorp = float(params.get('n_sorp', 2.0))

    m_w = state['m_w']; T_cl = state['T_cl']
    T_in = float(input.get('T_in_K', input.get('T_in', 293.15) + (273.15 if input.get('T_in', 293.15) < 200 else 0)))
    W_in = float(input.get('W_in', input.get('omega', 0.010)))
    m_flow_da = float(input.get('m_flow_da', input.get('m_dot_air', 0.035)))

    X = m_w / m_cl_dry
    W_s = _ma_W_sat(T_cl)
    h_m = h_a / _MA_cp_da
    hmA = h_m * A_eff
    haA = h_a * A_eff
    h_in = _ma_h_da(T_in, W_in)
    hg = _ma_h_g(T_cl)

    # L2는 f_dry가 RH_air(W_out, T_out)에 의존 → 비선형 연립.
    #   Modelica는 동시 대수해. Python 순차 고정점은 진동 → 이전스텝 T_out
    #   시드 + under-relaxation으로 안정화 (동적이라 T_out 연속).
    W_out = state.get('W_out_prev', W_in + 1e-4)
    T_out = state.get('T_out_prev', T_in)
    f_dry = 1.0; X_eq = 0.0; RH_air = 0.0
    relax = 0.5
    for _ in range(200):
        W_sat_out = _ma_W_sat(T_out)
        RH_air = W_out / max(W_sat_out, 1e-9)
        X_eq = min(a_sorp * RH_air**n_sorp, 0.9 * X_cr)
        f_dry = max(0.0, min(1.0, (X - X_eq) / (X_cr - X_eq)))
        W_out_tgt = (m_flow_da * W_in + f_dry * hmA * W_s) / (m_flow_da + f_dry * hmA)
        m_evap_it = f_dry * hmA * (W_s - W_out_tgt)
        cpm = _MA_cp_da + W_out_tgt * _MA_cp_v
        lhs_coef = m_flow_da * cpm + haA + UA_amb
        rhs = (m_flow_da * cpm * _MA_T0 - m_flow_da * W_out_tgt * _MA_hfg0
               + m_flow_da * h_in + haA * T_cl + m_evap_it * hg + UA_amb * T_amb)
        T_out_tgt = rhs / lhs_coef
        # under-relaxation (진동 억제)
        W_out_new = W_out + relax * (W_out_tgt - W_out)
        T_out_new = T_out + relax * (T_out_tgt - T_out)
        if abs(W_out_new - W_out) < 1e-12 and abs(T_out_new - T_out) < 1e-9:
            W_out = W_out_new; T_out = T_out_new; break
        W_out = W_out_new; T_out = T_out_new

    m_evap = f_dry * hmA * (W_s - W_out)

    hfg = _ma_h_fg(T_cl)
    dm_w = -m_evap
    dT_cl = (haA * (T_out - T_cl) - m_evap * hfg) / (m_cl_dry * c_p_cl + m_w * _MA_cp_w)
    m_w_new = m_w + dm_w * dt
    T_cl_new = T_cl + dT_cl * dt

    rho_da = _ma_rho_da(T_in, W_in)
    u = m_flow_da / (rho_da * A_drum)
    dp_drum = K_drum * u * abs(u)

    return {'outputs': {
        'X': X, 'm_w': m_w, 'T_cl': T_cl - 273.15, 'T_cl_K': T_cl,
        'm_evap': m_evap, 'W_out': W_out, 'T_out': T_out - 273.15,
        'X_eq': X_eq, 'f_dry': f_dry, 'RH_air': RH_air,
        'W_s': W_s, 'dp_drum': dp_drum, 'fidelity': 'L2',
    }, 'newState': {'m_w': m_w_new, 'T_cl': T_cl_new,
                    'W_out_prev': W_out, 'T_out_prev': T_out}}


def _step_L3(input, params, state, dt):
    fabric = FABRIC_PRESETS[params.get("fabric", "cotton")]
    M_dry = float(params.get("M_dry", 3.0))
    zone_fractions = params.get("zone_fractions", (0.25, 0.35, 0.40))
    N_zones = len(zone_fractions)   # 약점B: N셀 일반화 (기본 3 = L3 정의)
    # tuning 계수 (약점A: 노출, 근거는 원본 tuning_params 주석)
    diffusion_S_exp = float(params.get("diffusion_S_exponent", 0.5))
    brooks_corey = float(params.get("brooks_corey_exponent", 3.0))
    f_wet_exp = float(params.get("f_wet_exponent", 0.5))
    L_char_mult = float(params.get("L_char_multiplier", 3.0))
    S_critical = float(params.get("S_critical", 0.15))
    k_exch_slide = float(params.get("k_exchange_sliding", 0.05))
    k_exch_casc = float(params.get("k_exchange_cascading", 0.30))
    k_exch_high = float(params.get("k_exchange_high", 0.02))
    eps_free = float(params.get("eps_free", 0.01))   # 자유수 smooth 게이트 폭 (약점C, →0이면 원본 if)

    # 드럼 기하 (텀블링 Fr용)
    drum_radius = float(params.get("drum_radius", 0.27))
    drum_length = float(params.get("drum_length", 0.45))
    RPM = float(params.get("RPM", 45.0))
    # ── 4경로 저항 도면 기하 (dryer-drum-sim) ──
    A_rear_hole = float(params.get("A_rear_hole", 0.012))
    A_side_hole = float(params.get("A_side_hole", 0.006))
    gap_width = float(params.get("gap_width", 0.008))
    L_side_hole = float(params.get("L_side_hole", 0.15))
    seal_depth = float(params.get("seal_depth", 0.03))
    C_d = float(params.get("C_d", 0.62))
    # ── rasti hA 상관식 tuning ──
    Fr_opt = float(params.get("Fr_opt", 0.3))
    Fr_sigma = float(params.get("Fr_sigma", 0.25))
    fill_optimal = float(params.get("fill_optimal", 0.6))
    f_conv_sliding = float(params.get("f_conv_sliding", 0.7))
    f_conv_peak = float(params.get("f_conv_peak", 1.7))
    f_conv_centrifuge = float(params.get("f_conv_centrifuge", 0.3))
    hA_multiplier = float(params.get("hA_multiplier", 1.0))
    bypass_multiplier = float(params.get("bypass_multiplier", 1.0))

    # 입구 공기 (air_loop은 T_air_in/RH_air_in, 단독 호출은 T_air/omega_air)
    T_air = float(input.get("T_air", input.get("T_air_in", 60.0)))
    # omega: omega_air 직접 또는 RH_air_in+T로 환산
    if "omega_air" in input:
        omega_air = float(input["omega_air"])
    elif "W_in" in input:
        omega_air = float(input["W_in"])
    elif "RH_air_in" in input:
        _rh = float(input["RH_air_in"])
        _Psat = 611.2 * math.exp(17.62 * T_air / (243.12 + T_air))
        _Pw = (_rh / 100.0) * _Psat
        omega_air = 0.622 * _Pw / max(101325.0 - _Pw, 1.0)
    else:
        omega_air = 0.010
    m_dot_air = float(input.get("m_dot_air", 0.035))

    # 상태 언팩
    M_water_z = list(state["M_water_z"])
    M_water_max_z = list(state["M_water_max_z"])
    M_free = state["M_free_water"]
    T_fab = state["T_fabric"]

    # 기하 유도
    M_dry_z = [M_dry * f for f in zone_fractions]
    A_fabric = M_dry / (fabric["rho_fabric"] * fabric["delta"]) * 2
    # 약점B: L_char을 N셀 정규화. 인접 셀 중심간 거리 = 전체두께/(N-1).
    #   N=3서 ×1(원본 유지), N>3서 거리 축소 → flux 보정 → N 수렴.
    L_char = fabric["delta"] * L_char_mult * (2.0 / (N_zones - 1)) if N_zones > 1 else fabric["delta"] * L_char_mult
    Cp_dry = fabric["Cp_dry"]
    # 4경로 파생 면적 (dryer-drum-sim)
    A_drum_cross = math.pi * drum_radius**2
    A_gap = 2.0 * math.pi * drum_radius * gap_width
    d_char = fabric["delta"] * 2.0
    rho_bulk = fabric.get("rho_bulk", 300.0)
    rho_fiber = fabric["rho_fabric"]

    # 텀블링 Froude
    omega_rot = 2 * math.pi * RPM / 60
    Fr = omega_rot**2 * drum_radius / 9.81

    # ── 상태 헬퍼 ──
    def saturation():
        return [M_water_z[i] / max(M_water_max_z[i], 1e-12) for i in range(N_zones)]

    def M_water_total():
        return sum(M_water_z) + M_free

    # ══════════════════ 4경로 저항 (dryer-drum-sim 이식) ══════════════════
    def R_orifice(A_hole):
        if A_hole < 1e-8:
            return 1e8
        return 1.0 / (2.0 * RHO_AIR * C_d**2 * A_hole**2)

    def R_laundry(fill):
        eps = max(1.0 - rho_bulk / rho_fiber, 0.15)
        L_bed = 2.0 * drum_radius * max(fill, 0.01)**0.5
        A_flow = A_drum_cross * eps
        if A_flow < 1e-8 or d_char < 1e-8:
            return 1e6
        coeff = 1.75 * L_bed * (1 - eps) / (d_char * eps**3)
        return coeff / (2.0 * RHO_AIR * A_flow**2)

    def R_gap():
        D_h = 2.0 * gap_width
        L_gap = seal_depth
        K_entry_exit = 1.5
        f_friction = 0.05
        if A_gap < 1e-8:
            return 1e8
        fL = f_friction * L_gap / D_h + K_entry_exit
        return fL / (2.0 * RHO_AIR * A_gap**2)

    def segment_fill_angle(fill):
        lo, hi = 0.0, math.pi
        for _ in range(60):
            mid = (lo + hi) / 2
            ratio = (mid - math.sin(mid) * math.cos(mid)) / math.pi
            if ratio < fill:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def fabric_top_height(fill):
        R = drum_radius
        theta_static = segment_fill_angle(fill)
        h_static = -R * math.cos(theta_static)
        if Fr < 0.01:
            return h_static
        elif Fr < 0.1:
            lift = 0.1 * (Fr / 0.1)
            return h_static + R * lift
        elif Fr < 0.5:
            lift = 0.1 + 0.6 * (Fr - 0.1) / 0.4
            return min(h_static + R * lift, R * 0.9)
        elif Fr < 1.0:
            lift = 0.7 + 0.25 * (Fr - 0.5) / 0.5
            return min(h_static + R * lift, R * 0.95)
        else:
            return R * 0.95

    def circle_area_below_h(h):
        R = drum_radius
        h_n = max(min(h / R, 0.999), -0.999)
        return (math.acos(-h_n) - (-h_n) * math.sqrt(1 - h_n**2)) / math.pi

    def compute_resistances(fill):
        h_top = fabric_top_height(fill)
        rear_covered = circle_area_below_h(h_top)
        A_rear_eff = A_rear_hole * rear_covered
        A_rear_bypass = A_rear_hole * (1.0 - rear_covered)
        theta_fab = segment_fill_angle(fill)
        if Fr < 0.01:
            ang = theta_fab
        elif Fr < 0.5:
            ang = min(theta_fab * (1.0 + 0.8 * Fr / 0.5), math.pi * 0.85)
        elif Fr < 1.0:
            ang = min(theta_fab * (1.8 + 0.4 * (Fr - 0.5) / 0.5), math.pi * 0.9)
        else:
            ang = math.pi * 0.95
        side_covered = min(ang / math.pi, 0.95)
        A_side_eff = A_side_hole * side_covered
        R_eff = R_orifice(A_rear_eff) + R_laundry(fill)
        side_path_ratio = L_side_hole / max(drum_length, 0.01)
        R_partial = R_orifice(A_side_eff) + R_laundry(fill) * side_path_ratio
        R_rear_bypass = R_orifice(A_rear_bypass) if A_rear_bypass > 1e-8 else 1e8
        R_g = R_gap()
        return R_eff, R_partial, R_rear_bypass, R_g, rear_covered

    def distribute_flow(fill):
        R_e, R_p, R_rb, R_g, rear_cover = compute_resistances(fill)
        Ge = 1.0 / math.sqrt(max(R_e, 1.0))
        Gp = 1.0 / math.sqrt(max(R_p, 1.0))
        Grb = 1.0 / math.sqrt(max(R_rb, 1.0)) * bypass_multiplier
        Gg = 1.0 / math.sqrt(max(R_g, 1.0)) * bypass_multiplier
        Gt = Ge + Gp + Grb + Gg
        return (Ge/Gt, Gp/Gt, Grb/Gt, Gg/Gt, rear_cover)

    # ══════════════════ rasti hA 상관식 (dryer-drum-sim) ══════════════════
    def fill_ratio():
        V_drum = math.pi * drum_radius**2 * drum_length
        M_water_tot = M_water_total()
        V_fabric = M_dry / rho_bulk
        V_water_swell = M_water_tot * 0.3 / 1000.0  # 수분 팽윤 (원본 0.3 계수)
        V_occupied = V_fabric + V_water_swell
        return min(V_occupied / max(V_drum, 1e-6), 1.0)

    def compute_h(m_dot_eff, fill):
        eps = max(0.85 - 0.4 * fill, 0.15)
        A_flow = A_drum_cross * eps
        v_air = m_dot_eff / max(RHO_AIR * A_flow, 1e-8)
        Re = max(RHO_AIR * v_air * d_char / MU_AIR, 0.1)
        Nu = 2.0 + 1.1 * Re**0.6 * PR_AIR**(1.0/3.0)
        return Nu * K_AIR / d_char

    def f_contact(fill):
        f_Fr = math.exp(-((Fr - Fr_opt)**2) / (2 * Fr_sigma**2))
        f_fill = max(1.0 - 0.5 * ((fill - fill_optimal) / fill_optimal)**2, 0.2)
        return f_Fr * f_fill

    def f_conv():
        if Fr < 0.1:
            return f_conv_sliding
        if Fr < 0.5:
            return f_conv_sliding + (f_conv_peak - f_conv_sliding) * (Fr - 0.1) / 0.4
        if Fr < 1.0:
            return f_conv_peak + (f_conv_centrifuge - f_conv_peak) * (Fr - 0.5) / 0.5
        return f_conv_centrifuge

    def compute_hA(m_dot_eff, fill):
        h = compute_h(m_dot_eff, fill)
        fc = f_contact(fill)
        fv = f_conv()
        return h * A_fabric * fc * fv * hA_multiplier, h, fc, fv

    # ── 유효유량·hA (4경로 분배) ──
    fill = fill_ratio()
    f_eff, f_partial, f_rbypass, f_gap, rear_cover = distribute_flow(fill)
    m_dot_eff = m_dot_air * f_eff       # cloth 관통 유효유량
    m_dot_partial = m_dot_air * f_partial
    hA, h_conv, fc, fv = compute_hA(m_dot_eff, fill)

    # eta_partial (부분경로 hA 배율): side_hole 위치/드럼길이
    eta_partial = min(L_side_hole / max(drum_length, 0.01), 0.5)

    # ── 경로별 NTU-ε (원본 _ntu_path) ──
    def ntu_path(m_dot_path, hA_path, f_wet_val):
        if m_dot_path < 1e-8:
            return T_air, omega_air, 0.0
        NTU_p = hA_path / max(m_dot_path * CP_A, 1e-6)
        eps_p = 1 - math.exp(-NTU_p)
        T_out = T_air - eps_p * (T_air - T_fab)
        ws = _omega_sat(T_fab)
        w_out = omega_air + eps_p * (ws - omega_air) * f_wet_val
        # 과포화 → 응축
        w_sat_out = _omega_sat(T_out)
        if w_out > w_sat_out:
            cond = m_dot_path * (w_out - w_sat_out)
            dT_cond = cond * _h_fg(T_out) / max(m_dot_path * CP_A, 1e-6)
            T_out += dT_cond
            w_out = _omega_sat(T_out)
        m_ev = m_dot_path * max(w_out - omega_air, 0.0)
        return T_out, w_out, m_ev

    # ── Fick 확산 flux (zone_from → zone_to) ──
    def D_eff(T, S_val):
        D = fabric["D_ref"] * math.exp(-fabric["E_a"] / (R_GAS * (T + 273.15)))
        return D * max(S_val, 0.01) ** diffusion_S_exp

    def diffusion_flux(S_from, S_to, T):
        D = D_eff(T, S_from)
        return D * (S_from - S_to) / L_char * fabric["rho_fabric"]

    # ── Darcy-Leverett 모세관 flux ──
    def capillary_flux(S_from, S_to, T):
        sigma = _sigma_water(T)
        mu = _mu_water(T)
        K = fabric["K_abs"]
        sf = max(min(S_from, 0.999), 0.01)
        st = max(min(S_to, 0.999), 0.01)
        K_r = 0.5 * (sf**brooks_corey + st**brooks_corey)
        J_from = 0.364 * (1 - sf)**0.5 - 0.221 * (1 - sf)
        J_to = 0.364 * (1 - st)**0.5 - 0.221 * (1 - st)
        dP = (sigma / math.sqrt(K)) * (J_from - J_to)
        J = K * K_r / mu * dP / L_char * 1000.0
        return max(J, 0.0)

    # ── 표면증발 (Lewis f_wet) ──
    def surface_evap_fwet(S3):
        if S3 >= S_critical:
            f_wet = 1.0
        else:
            f_wet = min((S3 / max(S_critical, 1e-6)) ** f_wet_exp, 1.0)
        return max(f_wet, 0.0)

    # ── 텀블링 zone 교환 ──
    def tumbling_exchange():
        if Fr < 0.1:
            k = k_exch_slide
        elif Fr < 0.5:
            k = k_exch_slide + (k_exch_casc - k_exch_slide) * (Fr - 0.1) / 0.4
        elif Fr < 1.0:
            k = k_exch_casc + (k_exch_high - k_exch_casc) * (Fr - 0.5) / 0.5
        else:
            k = k_exch_high
        ex = min(k * RPM / 60.0 * dt, 0.4)
        # N셀 인접쌍 교환 (약점B): 각 쌍 i→i+1 균등화
        dM = [ex * (M_water_z[i] - M_water_z[i+1]) / 2 for i in range(N_zones - 1)]
        for i in range(N_zones - 1):
            M_water_z[i] -= dM[i]
            M_water_z[i+1] += dM[i]
        for i in range(N_zones):
            M_water_z[i] = max(M_water_z[i], 0.0)

    # ══════════════════ 업데이트 로직 ══════════════════
    # 약점C 개선: 자유수 if 분기 → smooth blend (Modelica 초기화 안정).
    #   g_free = M_free/(M_free+eps_free): 자유수 존재도 연속 게이트 (0~1).
    #   eps_free→0이면 원본 if와 수렴. 3-zone은 항상 계산 후 가중 blend.
    #   자유수 물리(표면 완전습윤 최대증발) 보존하되 불연속만 제거.
    g_free = M_free / (M_free + eps_free)

    # 3-zone 메커니즘 (항상 계산 — blend 위해)
    tumbling_exchange()
    S = saturation()
    # ── N셀 수분이동 flux (약점B): 각 인접쌍에 diffusion↔capillary blend ──
    #   w_cap(i) = i/(N-2): 내부(i작음)=확산지배, 표면(i큼)=모세관지배.
    #   N=3서 쌍0 순확산·쌍1 순모세관 = 원본과 정확히 일치.
    J_pair = [0.0] * (N_zones - 1)
    for i in range(N_zones - 1):
        J_d = diffusion_flux(S[i], S[i+1], T_fab)
        J_c = capillary_flux(S[i], S[i+1], T_fab)
        w_cap = i / (N_zones - 2) if N_zones > 2 else (0.0 if i == 0 else 1.0)
        w_cap = max(0.0, min(w_cap, 1.0))
        J_blend = (1 - w_cap) * J_d + w_cap * J_c
        # 플럭스 제한 (공급 셀 보유량 초과 방지)
        max_J = M_water_z[i] / max(A_fabric * dt, 1e-12) * 0.5
        J_pair[i] = min(J_blend, max_J)
    f_wet_3zone = surface_evap_fwet(S[N_zones - 1])

    # 내부 수분 이동 적용 (i → i+1)
    for i in range(N_zones - 1):
        M_water_z[i] = max(M_water_z[i] - J_pair[i] * A_fabric * dt, 0.0)
        M_water_z[i+1] = M_water_z[i+1] + J_pair[i] * A_fabric * dt
    # 포화 상한 → 자유수 재유입
    for i in range(N_zones):
        if M_water_z[i] > M_water_max_z[i]:
            M_free += M_water_z[i] - M_water_max_z[i]
            M_water_z[i] = M_water_max_z[i]

    # 3-zone supply (연속 전이) — 표면셀(N-1) 기준
    S_surf = M_water_z[N_zones - 1] / max(M_water_max_z[N_zones - 1], 1e-12)
    blend_3z = min((S_surf / max(S_critical, 1e-6)) ** f_wet_exp, 1.0)
    supply_buffer = M_water_z[N_zones - 1] / max(dt, 1e-6)
    supply_internal = J_pair[N_zones - 2] * A_fabric   # 최표면 쌍 flux
    supply_3zone = supply_internal + blend_3z * (supply_buffer - supply_internal)

    # ── 자유수 ↔ 3-zone smooth blend (약점C) ──
    supply_free = M_free / max(dt, 1e-6)
    m_evap_supply = g_free * supply_free + (1 - g_free) * supply_3zone
    f_wet = g_free * 1.0 + (1 - g_free) * f_wet_3zone

    # ── 4경로 NTU-ε (원본: cloth e1 + partial e2 증발, bypass 2경로는 우회) ──
    T1, w1, e1 = ntu_path(m_dot_eff, hA, f_wet)
    T2, w2, e2 = ntu_path(m_dot_partial, hA * eta_partial, f_wet)
    T_rb = T_air * 0.98; w_rb = omega_air     # 후면 바이패스 (미접촉)
    T_g = T_air * 0.98; w_g = omega_air       # 간극 바이패스 (완전 우회)

    # ── 공기측 demand를 fabric supply로 제한 ──
    e_air_demand = e1 + e2
    if e_air_demand > 0 and m_evap_supply >= 0:
        cap_ratio = min(m_evap_supply / max(e_air_demand, 1e-12), 1.0)
    else:
        cap_ratio = 1.0
    if cap_ratio < 1.0:
        e1 *= cap_ratio
        e2 *= cap_ratio
        w1 = omega_air + cap_ratio * (w1 - omega_air)
        w2 = omega_air + cap_ratio * (w2 - omega_air)

    actual_evap = e1 + e2

    # ── 증발량 제거 (자유수 우선, 나머지 zone3) ──
    evap_mass = actual_evap * dt
    if M_free > 0:
        from_free = min(evap_mass, M_free)
        M_free -= from_free
        evap_mass -= from_free
    evap_mass = min(evap_mass, M_water_z[N_zones-1])
    M_water_z[N_zones-1] = max(M_water_z[N_zones-1] - evap_mass, 0.0)

    # ── 에너지 밸런스 (원본 update_temperature: 전체유량 m_dot_air NTU) ──
    hfg = _h_fg(T_fab)
    Q_lat = actual_evap * hfg
    NTU_e = hA / max(m_dot_air * CP_A, 1e-6)   # 원본: 전체유량 기준
    eps = 1 - math.exp(-NTU_e)
    Q_tot = m_dot_air * CP_A * eps * (T_air - T_fab)
    Q_sen = Q_tot - Q_lat
    mCp = M_dry * Cp_dry + M_water_total() * 4186.0
    T_fab_new = T_fab + Q_sen * dt / max(mCp, 1.0)
    T_fab_new = max(5.0, min(T_fab_new, 95.0))

    # ── 출구 공기 (4경로 질량가중 혼합) ──
    mt = m_dot_air
    me = m_dot_eff; mp = m_dot_partial
    mrb = m_dot_air * f_rbypass; mg = m_dot_air * f_gap
    T_air_out = (me*T1 + mp*T2 + mrb*T_rb + mg*T_g) / max(mt, 1e-8)
    omega_out = (me*w1 + mp*w2 + mrb*w_rb + mg*w_g) / max(mt, 1e-8)

    X_out = M_water_total() / M_dry

    new_state = {
        "M_water_z": M_water_z,
        "M_water_max_z": M_water_max_z,
        "M_free_water": M_free,
        "T_fabric": T_fab_new,
    }
    return {
        "outputs": {
            "X": X_out,                    # 함수율 kg水/kg건
            "m_evap": actual_evap,         # kg/s
            "T_fabric": T_fab_new,         # °C
            "T_air_out": T_air_out,        # °C
            "omega_out": omega_out,        # kg/kg
            "Q_total": Q_tot,              # W
            "Q_latent": Q_lat,             # W
            "Q_sensible": Q_sen,           # W
            "f_wet": f_wet,
            "Fr": Fr,
            "S_surface": S[N_zones-1] if 'S' in dir() else 0.0,
            "M_free_water": M_free,
            "eps": eps,
            # 4경로 + hA 진단
            "hA": hA,
            "h_conv": h_conv,
            "f_contact": fc,
            "f_conv": fv,
            "fill": fill,
            "m_dot_eff": m_dot_eff,
            "f_eff": f_eff,
            "f_partial": f_partial,
            "f_rbypass": f_rbypass,
            "f_gap": f_gap,
        },
        "newState": new_state,
    }


def validate(params):
    issues = []
    if params.get("fabric", "cotton") not in FABRIC_PRESETS:
        issues.append(f"unknown fabric preset: {params.get('fabric')}")
    zf = params.get("zone_fractions", (0.25, 0.35, 0.40))
    if abs(sum(zf) - 1.0) > 1e-6:
        issues.append(f"zone_fractions must sum to 1.0 (got {sum(zf)})")
    return issues
