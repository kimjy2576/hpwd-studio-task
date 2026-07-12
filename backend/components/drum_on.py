"""
drum_on.py — L3 (On-Design) 드럼 건조 모델 [1단계: 핵심 물리 골격]

dryer-drum-sim(kimjy2576/dryer-drum-sim)의 3-Zone 다층직물 물리를,
hpwd-studio-task 컴포넌트 표준으로 재구성. Modelica Drum_L3의 ground truth.

문헌(model-docs) 7-step 중 1단계는 핵심 건조물리만:
  Step1 3-Zone 직물, Step2 Fick 확산, Step3 Darcy-Leverett 모세관,
  Step4 표면증발(Lewis)+텀블링 Fr, (부분)Step5 NTU-ε 열전달.
  [다음 단계] 4경로 저항(gap누설/Ergun), 약점개선(자유수 smooth·N셀·물성).

동적 모델 — 팬(대수)과 달리 상태변수(3-zone 함수율 + 직물온도)를 시간전진.
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
#   ⚠️ 약점A: D_ref/E_a/K_abs는 토양·문헌 추정값 (직물 실측 부족).
#      3단계서 출처 명시·직물문헌값 격상 예정. 현재는 원본 유지.
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
    fabric = FABRIC_PRESETS[params.get("fabric", "cotton")]
    M_dry = float(params.get("M_dry", 3.0))
    zone_fractions = params.get("zone_fractions", (0.25, 0.35, 0.40))
    # tuning 계수 (약점A: 노출, 근거는 원본 tuning_params 주석)
    diffusion_S_exp = float(params.get("diffusion_S_exponent", 0.5))
    brooks_corey = float(params.get("brooks_corey_exponent", 3.0))
    f_wet_exp = float(params.get("f_wet_exponent", 0.5))
    L_char_mult = float(params.get("L_char_multiplier", 3.0))
    S_critical = float(params.get("S_critical", 0.15))
    k_exch_slide = float(params.get("k_exchange_sliding", 0.05))
    k_exch_casc = float(params.get("k_exchange_cascading", 0.30))
    k_exch_high = float(params.get("k_exchange_high", 0.02))

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

    # 입구 공기
    T_air = float(input.get("T_air", 60.0))
    omega_air = float(input.get("omega_air", 0.010))
    m_dot_air = float(input.get("m_dot_air", 0.035))

    # 상태 언팩
    M_water_z = list(state["M_water_z"])
    M_water_max_z = list(state["M_water_max_z"])
    M_free = state["M_free_water"]
    T_fab = state["T_fabric"]

    # 기하 유도
    M_dry_z = [M_dry * f for f in zone_fractions]
    A_fabric = M_dry / (fabric["rho_fabric"] * fabric["delta"]) * 2
    L_char = fabric["delta"] * L_char_mult
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
        return [M_water_z[i] / max(M_water_max_z[i], 1e-12) for i in range(3)]

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
        dM12 = ex * (M_water_z[0] - M_water_z[1]) / 2
        dM23 = ex * (M_water_z[1] - M_water_z[2]) / 2
        M_water_z[0] -= dM12
        M_water_z[1] += dM12 - dM23
        M_water_z[2] += dM23
        for i in range(3):
            M_water_z[i] = max(M_water_z[i], 0.0)

    # ══════════════════ 업데이트 로직 ══════════════════
    # ⚠️ 약점C(자유수 분기): 1단계는 원본 방식 유지. 3단계서 smooth 전이.
    if M_free > 1e-8:
        # 자유수 있음 → 완전습윤 표면 최대증발 (3-zone 건너뜀)
        m_evap_supply = M_free / max(dt, 1e-6)
        f_wet = 1.0
        S = saturation()
    else:
        # 3-zone 메커니즘
        tumbling_exchange()
        S = saturation()
        J_diff = diffusion_flux(S[0], S[1], T_fab)
        J_cap = capillary_flux(S[1], S[2], T_fab)
        f_wet = surface_evap_fwet(S[2])

        # 플럭스 제한 (보유량 초과 방지)
        max_J_diff = M_water_z[0] / max(A_fabric * dt, 1e-12) * 0.5
        max_J_cap = M_water_z[1] / max(A_fabric * dt, 1e-12) * 0.5
        J_diff = min(J_diff, max_J_diff)
        J_cap = min(J_cap, max_J_cap)

        # 내부 수분 이동 (zone1→2, zone2→3)
        M_water_z[0] = max(M_water_z[0] - J_diff * A_fabric * dt, 0.0)
        M_water_z[1] = max(M_water_z[1] + (J_diff - J_cap) * A_fabric * dt, 0.0)
        M_water_z[2] = max(M_water_z[2] + J_cap * A_fabric * dt, 0.0)
        # 포화 상한 → 자유수 재유입
        for i in range(3):
            if M_water_z[i] > M_water_max_z[i]:
                M_free += M_water_z[i] - M_water_max_z[i]
                M_water_z[i] = M_water_max_z[i]

        # supply limit (연속 전이)
        blend = min((S[2] / max(S_critical, 1e-6)) ** f_wet_exp, 1.0)
        supply_buffer = M_water_z[2] / max(dt, 1e-6)
        supply_internal = J_cap * A_fabric
        m_evap_supply = supply_internal + blend * (supply_buffer - supply_internal)

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
    evap_mass = min(evap_mass, M_water_z[2])
    M_water_z[2] = max(M_water_z[2] - evap_mass, 0.0)

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
            "S_surface": S[2] if 'S' in dir() else 0.0,
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
