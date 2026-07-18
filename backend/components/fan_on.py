"""
fan_on.py — L3 (On-Design) 원심팬 단일 운전점 모델

fan-sim(kimjy2576/fan-sim)의 meanline + 손실 9종 물리를,
"형상→BEP 스윕" 설계계산기에서 "운전점 1점→Δp" 사이클 컴포넌트로 재구성.
Modelica Fan_L3(acausal)의 ground truth.

문헌 대비(model-docs): 6종(incidence/blade-loading/skin-friction/disk/recirc/volute)
초과 — 시로코(전곡 다익) 특화 tongue-recirc·uncaptured·diffuser 포함 = 9종.

fan-sim 대비 3개 개선 (물리 완결성 검토로 확정):
  (1) jet-wake 이중차감 버그 수정 → 1회만 (물리적으로 임펠러 출구 손실 1회)
  (2) recirculation 불연속(if DR>DR_crit) → softplus smooth (Modelica NLS 수렴)
      w_rec→0이면 원본 if와 수렴 (검증 파라미터)
  (3) 하드코딩 반경험 상수 전부 파라미터 노출 (약점1/3):

정직성 노트 — "fitting 0" 아님:
  문헌(model-docs)은 이 모델을 "fitting 0 순수 물리"로 기술하나, 실제로는
  순수 물리유도가 불가능한 반경험 계수를 포함한다. 이를 숨기지 않고 전부
  파라미터로 노출한다 (기본값은 fan-sim 유지, 검증가능).

  ● 순수 물리 (계수 없음): Euler head, slip(Wiesner), 속도삼각형,
      skin-friction(Colebrook f), disk-friction(Daily&Nece Cm), incidence 기하
  ● 보정 승수 (기본 1.0, 실측 calibration 대상):
      k_inc, k_fric, k_rec, k_disk, k_jw
  ● 반경험 계수 (물리유도 불가, 노출):
      c_wake=0.12(wake폭), r_scroll_w=1.1(스크롤폭비), c_scroll_v=0.7(스크롤속도),
      k_sc_mix=0.20(스크롤혼합), c_tongue_loss=0.3, eps_leak_max=0.25,
      k_tongue_a=0.82, k_tongue_b=0.7, DR_crit=0.5

인터페이스: step(input, params, state, dt) → {'outputs':{...}, 'newState':{}}
  (hpwd-studio-task 컴포넌트 표준, *_on_design.py와 동일 패턴)

손실 참고문헌:
  Oh, Yoon, Chung (1997) — incidence·blade loading·recirculation
  NASA SP-36 — skin friction
  Daily & Nece (1960) — disk friction
  Dixon & Hall — Fluid Mechanics and Thermodynamics of Turbomachinery
"""
import math

# ══════════════════════════════════════════════════════════════
# 공기 물성 (fan-sim air_properties.py 방식 — Sutherland 점도, 습공기 밀도)
# ══════════════════════════════════════════════════════════════
def _sat_pressure(T_C):
    T = T_C + 273.15
    if T_C >= 0:
        return math.exp(23.196 - 3816.44 / (T - 46.13))
    return math.exp(23.33 - 3820.0 / (T - 44.0))

def _humidity_ratio(T_C, RH, P_atm=101325.0):
    Pw = RH * _sat_pressure(T_C)
    return 0.62198 * Pw / max(1.0, P_atm - Pw)

def _air_density(T_C, omega, P_atm=101325.0):
    T_K = T_C + 273.15
    R_da, R_v = 287.055, 461.52
    Pv = P_atm * omega / (0.62198 + omega)
    Pda = P_atm - Pv
    return Pda / (R_da * T_K) + Pv / (R_v * T_K)

def _air_viscosity(T_C):
    T_K = T_C + 273.15
    T_ref, S, mu_ref = 273.15, 110.4, 1.716e-5
    return mu_ref * (T_K / T_ref) ** 1.5 * (T_ref + S) / (T_K + S)

def _air_cp(T_C, omega):
    cp_da, cp_v = 1006.0, 1860.0
    return (cp_da + omega * cp_v) / (1 + omega)


# ══════════════════════════════════════════════════════════════
# Blade 경로장 Lb (형상만, Qm3s 무관 — 사전계산)
#   Modelica: parameter algorithm으로 동일 계산
# ══════════════════════════════════════════════════════════════
def _blade_length(r1, r2, b1R, b2R, n=20):
    Lb = 0.0
    px, py, th = r1, 0.0, 0.0
    for i in range(1, n + 1):
        t = i / n
        r = r1 + t * (r2 - r1)
        rP = r1 + (i - 1) / n * (r2 - r1)
        rM = (r + rP) / 2
        tM = (t + (i - 1) / n) / 2
        bM = b1R + tM * (b2R - b1R)
        if abs(math.tan(bM)) > 0.001:
            th += (-1 / (rM * math.tan(bM))) * (r - rP)
        x = r * math.cos(th)
        y = r * math.sin(th)
        Lb += math.sqrt((x - px) ** 2 + (y - py) ** 2)
        px, py = x, y
    return Lb


def _softplus(x, w):
    """(x)+ 의 smooth 근사. w→0이면 max(x,0). 오버플로 가드."""
    z = x / w
    if z > 30:
        return x
    if z < -30:
        return 0.0
    return w * math.log1p(math.exp(z))


def init_state(params):
    return {}


def step(input, params, state, dt):
    """
    fidelity 파라미터로 L1/L2/L3 선택 (기본 L3).
      params['fidelity'] ∈ {'L1','L2','L3'}
    L1(Euler+Stodola 이론)/L2(손실분해 반경험)는 Modelica Fan_L1/L2와
    동일 SI 식. L3(Meanline 9손실)는 fan-sim 포팅(아래 _step_L3).
    ⚠️ L1/L2는 SI 단위(D2[m], N[rpm]), L3는 fan-sim 단위(mm/°) — 주의.
    ⚠️ 부호 규약: 정방향(+) 유량이 정상. 하네스 outlet의 BoundaryAir_mflow는
       +m이 정방향(드럼은 inlet이 mflow라 -m이 정방향 — 반대).
       구 하네스(CmpAir Fan_L1_pt/L2_pt, CmpAirParts)가 -m을 써서 역류
       (Fan_L3 eta=0)였고, Python도 -로 맞춰 "일치"시킨 오류가 있었음 → 수정됨.
       동일 BC 검증(통일기하 D2=0.175/b2=0.050/D1=0.120/b1=0.060/Z=36/
       β2=145/β1=30, N=3000, 20°C/W=0.008, m=+0.05):
         L1 dp 727.079 ↔ Mod 727.091,  L2 dp 842.905 ↔ Mod 842.919
    """
    fidelity = params.get('fidelity', 'L3')
    if fidelity == 'L1':
        return _step_L1(input, params, state, dt)
    elif fidelity == 'L2':
        return _step_L2(input, params, state, dt)
    else:
        return _step_L3(input, params, state, dt)


# ══════════════════════════════════════════════════════════════
# L1 — Euler + Stodola slip (교과서 이론, Modelica Fan_L1 동형)
# ══════════════════════════════════════════════════════════════
def _step_L1(input, params, state, dt):
    """ΔP = η_h·ρ·U2·cθ2. Euler 수두 × 상수 유압효율. SI 단위."""
    D2 = float(params.get('D2', 0.15))       # m
    b2 = float(params.get('b2', 0.04))       # m
    Z = float(params.get('Z', 40))
    beta2 = float(params.get('beta2', 150.0))  # deg
    eta_h = float(params.get('eta_h', 0.78))
    eta_mech = float(params.get('eta_mech', 0.95))
    N = float(params.get('N', 3000.0))       # rpm

    T_in = float(input.get('T_in', 20.0))
    omega = float(input.get('omega', 0.008))
    P_in = float(input.get('P_in', 101325.0))
    rho = _air_density(T_in, omega, P_in)

    if 'm_dot_da' in input:
        m_dot_da = float(input['m_dot_da'])
        V_dot = m_dot_da * (1 + omega) / rho
    else:
        V_dot = float(input.get('V_dot', 0.05))
        m_dot_da = V_dot * rho / (1 + omega)

    beta2_rad = math.radians(beta2)
    U2 = math.pi * D2 * N / 60
    cm2 = V_dot / (math.pi * D2 * b2)
    sigma = 1 - math.pi * math.sin(beta2_rad) / Z
    ctheta2 = sigma * U2 - cm2 / math.tan(beta2_rad)
    dp_t = rho * U2 * ctheta2
    dp = eta_h * dp_t
    W_sh = rho * V_dot * U2 * ctheta2 / eta_mech

    return {'outputs': {
        'dp': dp, 'dp_t': dp_t, 'P_out': P_in + dp,
        'U2': U2, 'cm2': cm2, 'sigma': sigma, 'ctheta2': ctheta2,
        'V_dot': V_dot, 'm_dot_da': m_dot_da, 'rho': rho, 'W_shaft': W_sh,
        'fidelity': 'L1',
    }, 'newState': {}}


# ══════════════════════════════════════════════════════════════
# L2 — 손실분해 Euler − Incidence − Friction (Modelica Fan_L2 동형)
# ══════════════════════════════════════════════════════════════
def _step_L2(input, params, state, dt):
    """ΔP = Euler − incidence − friction − scroll. 상수효율 대신 유량의존 손실. SI.
    ⚠️ scroll(볼류트 덤프)은 시로코 지배 손실 — 없으면 L2가 L1보다 나쁨."""
    D2 = float(params.get('D2', 0.15))
    b2 = float(params.get('b2', 0.04))
    D1 = float(params.get('D1', 0.075))
    b1 = float(params.get('b1', 0.045))
    Z = float(params.get('Z', 40))
    beta2 = float(params.get('beta2', 150.0))
    beta1 = float(params.get('beta1', 35.0))
    f_inc = float(params.get('f_inc', 0.6))
    f_fric = float(params.get('f_fric', 0.8))
    # 스크롤 덤프 손실계수: 볼류트가 회수 못하는 임펠러 출구 동압 비율.
    #   문헌 통상 0.2~0.3. L3(fan-sim) dP_scroll/(0.5ρc2²)가 φ 전범위
    #   0.225~0.269(평균 0.248)로 안정 → 상수 0.25 (반올림, 거짓정밀 회피).
    k_scroll = float(params.get('k_scroll', 0.25))
    eta_mech = float(params.get('eta_mech', 0.95))
    N = float(params.get('N', 3000.0))

    T_in = float(input.get('T_in', 20.0))
    omega = float(input.get('omega', 0.008))
    P_in = float(input.get('P_in', 101325.0))
    rho = _air_density(T_in, omega, P_in)

    if 'm_dot_da' in input:
        m_dot_da = float(input['m_dot_da'])
        V_dot = m_dot_da * (1 + omega) / rho
    else:
        V_dot = float(input.get('V_dot', 0.05))
        m_dot_da = V_dot * rho / (1 + omega)

    beta2_rad = math.radians(beta2)
    beta1_rad = math.radians(beta1)
    U2 = math.pi * D2 * N / 60
    U1 = math.pi * D1 * N / 60
    cm2 = V_dot / (math.pi * D2 * b2)
    cm1 = V_dot / (math.pi * D1 * b1)
    sigma = 1 - math.pi * math.sin(beta2_rad) / Z
    ctheta2 = sigma * U2 - cm2 / math.tan(beta2_rad)
    w2 = math.sqrt(cm2**2 + (U2 - ctheta2)**2)
    c2 = math.sqrt(cm2**2 + ctheta2**2)      # 임펠러 출구 절대속도

    dp_euler = rho * U2 * ctheta2
    dp_inc = 0.5 * rho * f_inc * (U1 - cm1 / math.tan(beta1_rad))**2
    dp_fric = 0.5 * rho * f_fric * w2**2
    dp_scroll = k_scroll * 0.5 * rho * c2**2   # 볼류트 덤프 (지배 손실)
    dp = dp_euler - dp_inc - dp_fric - dp_scroll
    eta_h = dp / dp_euler if dp_euler != 0 else 0.0
    W_sh = rho * V_dot * U2 * ctheta2 / eta_mech

    return {'outputs': {
        'dp': dp, 'dp_euler': dp_euler, 'dp_inc': dp_inc, 'dp_fric': dp_fric,
        'dp_scroll': dp_scroll,
        'eta_h': eta_h, 'P_out': P_in + dp,
        'U2': U2, 'U1': U1, 'cm2': cm2, 'cm1': cm1, 'sigma': sigma,
        'ctheta2': ctheta2, 'w2': w2, 'c2': c2,
        'V_dot': V_dot, 'm_dot_da': m_dot_da, 'rho': rho, 'W_shaft': W_sh,
        'fidelity': 'L2',
    }, 'newState': {}}


def _step_L3(input, params, state, dt):
    D1 = float(params.get('D1', 120.0))
    D2 = float(params.get('D2', 175.0))
    b1 = float(params.get('b1', 60.0))
    b2 = float(params.get('b2', 50.0))
    beta1 = float(params.get('beta1', 30.0))
    beta2 = float(params.get('beta2', 145.0))
    Z = float(params.get('Z', 36.0))
    RPM = float(params.get('RPM', 1400.0))
    tBlade = float(params.get('tBlade', 1.0))
    cutoffGap = float(params.get('cutoffGap', 8.0))
    Rtongue = float(params.get('Rtongue', 5.0))
    wrapAngle = float(params.get('wrapAngle', 360.0))
    scrollExpRate = float(params.get('scrollExpRate', 0.12))
    diffAngle = float(params.get('diffAngle', 7.0))
    diffLength = float(params.get('diffLength', 40.0))

    # ── 보정계수 (약점1: 기본 1.0, semi-empirical시 조정) ──
    k_inc = float(params.get('k_inc', 1.0))
    k_fric = float(params.get('k_fric', 1.0))
    k_rec = float(params.get('k_rec', 0.0085))
    DR_crit = float(params.get('DR_crit', 0.5))
    k_disk = float(params.get('k_disk', 1.0))
    k_jw = float(params.get('k_jw', 1.0))
    k_sc_mix = float(params.get('k_sc_mix', 0.20))
    k_tongue_a = float(params.get('k_tongue_a', 0.82))
    k_tongue_b = float(params.get('k_tongue_b', 0.7))
    w_rec = float(params.get('w_rec', 0.02))  # recirc smooth 전이폭 (약점5)
    # ── 이전 하드코딩 상수 → 명시적 파라미터 노출 (약점3/1) ──
    #   "fitting 0"은 부정확했음. 아래는 순수 물리유도 불가한 반경험 계수로,
    #   숨기지 않고 노출해 정직성·검증가능성 확보. 기본값은 fan-sim 값 유지.
    c_wake = float(params.get('c_wake', 0.12))          # jet-wake 기저 폭분율 (Whitfield: 0.1~0.15, slip 후 wake)
    r_scroll_w = float(params.get('r_scroll_w', 1.1))   # 스크롤/임펠러 폭비 (통상 스크롤 약간 넓음)
    c_scroll_v = float(params.get('c_scroll_v', 0.7))   # 스크롤 유효속도계수 (단면평균 대비, 반경험)
    c_tongue_loss = float(params.get('c_tongue_loss', 0.3))  # tongue 손실계수 (누설분율×임펠러압 대비)
    eps_leak_max = float(params.get('eps_leak_max', 0.25))   # tongue 누설분율 물리상한

    # ── 입구 공기 상태 (input) ──
    T_in = float(input.get('T_in', 25.0))       # °C
    RH_in = input.get('RH_in', None)
    if RH_in is not None:
        omega = _humidity_ratio(T_in, float(RH_in))
    else:
        omega = float(input.get('omega', 0.010))  # kg/kg_da
    P_in = float(input.get('P_in', 101325.0))     # Pa

    # ── 운전점 유량 (input): dry-air mass flow 또는 V̇ 직접 ──
    # 약점2(비압축): rho는 입구 기준 상수. 검토결과 팬 Δp~700-800Pa/대기압
    #   = 밀도변화 <1% → 비압축 타당(손실오차<1%). cf. 압축기는 rp~2배라 압축성 필수.
    #   온도상승(모터열)은 출구 dT_fan에 별도 반영. 문헌 비압축 규약과 일치.
    rho = _air_density(T_in, omega, P_in)
    mu = _air_viscosity(T_in)
    cp = _air_cp(T_in, omega)
    if 'm_dot_da' in input:
        m_dot_da = float(input['m_dot_da'])       # kg_da/s
        Qm3s = m_dot_da * (1 + omega) / rho       # dry-air basis V̇
    else:
        Qm3s = float(input.get('Qm3s', 0.05))     # m³/s 직접
        m_dot_da = Qm3s * rho / (1 + omega)

    # ── 사전계산 (형상, Qm3s 무관) ──
    omega_rot = 2 * math.pi * RPM / 60
    r1, r2 = D1 / 2000, D2 / 2000
    b1m, b2m = b1 / 1000, b2 / 1000
    b1R, b2R = math.radians(beta1), math.radians(beta2)
    U1, U2 = omega_rot * r1, omega_rot * r2
    sigma = 1 - (math.pi * math.sin(b2R)) / Z      # Wiesner slip
    pitch2 = math.pi * (D2 / 1000) / Z
    Dh = 2 * pitch2 * b2m / (pitch2 + b2m)
    tBladeM = tBlade / 1000
    k_inc_base = 1 - (tBladeM / (math.pi * (D1 / 1000) / Z)) ** 2
    gapM = cutoffGap / 1000
    wrapFrac = min(1.0, wrapAngle / 360)
    Lb = _blade_length(r1, r2, b1R, b2R)

    # ── 속도삼각형 ──
    Cr1 = Qm3s / (math.pi * (D1 / 1000) * b1m) if b1m > 0 else 0.0
    Cr2 = Qm3s / (math.pi * (D2 / 1000) * b2m) if b2m > 0 else 0.0
    Ct2 = sigma * U2 - Cr2 / math.tan(b2R) if abs(math.tan(b2R)) > 1e-6 else sigma * U2
    C2 = math.sqrt(Cr2 ** 2 + Ct2 ** 2)
    W1 = math.sqrt(Cr1 ** 2 + U1 ** 2)
    W2 = math.sqrt(Cr2 ** 2 + (Ct2 - U2) ** 2)
    Pt_e = rho * U2 * Ct2                            # Euler 이론 전압

    # ── 임펠러 손실 5종 ──
    # ① Incidence (Oh 1997)
    inc_A = math.atan2(Cr1, U1) - b1R
    dP_inc = k_inc_base * k_inc * 0.5 * rho * (W1 * math.sin(inc_A)) ** 2
    # ③ Skin friction (NASA SP-36)
    Wa = (W1 + W2) / 2
    Re = rho * Wa * Dh / mu if mu > 0 else 1e5
    if Re > 2300:
        f = 1 / (-1.8 * math.log10(6.9 / Re + (5e-5 / Dh / 3.7) ** 1.11)) ** 2
    elif Re > 0:
        f = 64 / Re
    else:
        f = 0.02
    dP_fric = k_fric * f * (Lb / Dh) * 0.5 * rho * Wa ** 2
    # ⑤ Recirculation (Oh 1997) — 약점5: softplus smooth (원본 if 대체)
    DR = 1 - W2 / W1 + abs(Ct2) / (2 * Z * W1 / math.pi) if W1 > 0 else 0.0
    dP_rec = k_rec * _softplus(DR - DR_crit, w_rec) ** 2 * rho * U2 ** 2
    # ④ Disk friction (Daily & Nece 1960)
    Re_disk = rho * omega_rot * r2 ** 2 / mu if mu > 0 else 1e6
    Cm = 0.0622 / Re_disk ** 0.2 if Re_disk > 0 else 0.005
    Pdf = k_disk * 2 * 0.5 * Cm * rho * omega_rot ** 3 * r2 ** 5
    dP_disk = Pdf / Qm3s if Qm3s > 1e-6 else Pdf / 1e-6
    dP_disk = min(dP_disk, Pt_e * 0.5)
    # ② Jet-wake / diffusion (blade loading)
    eps_jw = c_wake + 0.5 * tBladeM / pitch2
    dP_jw = k_jw * 0.5 * rho * C2 ** 2 * eps_jw ** 2

    # 임펠러 출구 전압 (jet-wake 1회 반영 — 버그 수정: 여기서만)
    Pt_imp = max(0.0, Pt_e - dP_inc - dP_fric - dP_rec - dP_disk - dP_jw)
    Pdyn_imp = 0.5 * rho * C2 ** 2

    # ── ⑥ Scroll 손실 ──
    Pdyn_cap = Pdyn_imp * wrapFrac
    L_scroll = 2 * math.pi * r2 * wrapFrac
    bScrollM = b2m * r_scroll_w
    rExit = r2 + r2 * scrollExpRate * wrapFrac * 2 * math.pi
    A_sc_exit = bScrollM * (rExit - r2)
    A_sc = max(A_sc_exit, Qm3s / max(1.0, C2 * 0.5) if Qm3s > 0 else bScrollM * 0.02)
    D_h_sc = 2 * A_sc / (math.sqrt(A_sc / bScrollM) + bScrollM) if bScrollM > 0 else 0.01
    C_sc = Qm3s / max(1e-4, A_sc) * c_scroll_v if Qm3s > 0 else C2 * 0.5
    Re_sc = rho * abs(C_sc) * max(0.005, D_h_sc) / mu if mu > 0 else 1e5
    f_sc = 0.316 / Re_sc ** 0.25 if Re_sc > 2300 else (64 / Re_sc if Re_sc > 0 else 0.02)
    dP_sc_fric = f_sc * (L_scroll / max(0.005, D_h_sc)) * 0.5 * rho * C_sc ** 2
    dP_sc_mix = k_sc_mix * Pdyn_cap
    dP_scroll = dP_sc_fric + dP_sc_mix

    # ── Tongue 재순환 (시로코 특화) ──
    gapRatio = gapM / (2 * r2)
    denom_tongue = 1 + Rtongue / cutoffGap if cutoffGap > 0 else 1
    eps_leak = min(eps_leak_max, k_tongue_a * gapRatio ** k_tongue_b / denom_tongue)
    Q_recirc = Qm3s * eps_leak
    Q_delivered = Qm3s * (1 - eps_leak)
    dP_tongue = eps_leak * Pt_imp * c_tongue_loss

    # ── Diffuser (출구 확산 압력회복) ──
    if diffLength > 0:
        diffAR = 1 + 2 * (diffLength / 1000) * math.tan(abs(diffAngle) * math.pi / 180) / max(0.01, math.sqrt(A_sc))
    else:
        diffAR = 1.0
    A_exit = max(0.001, A_sc * max(1.0, diffAR))

    # ── Uncaptured (scroll wrap<1 미회수 동압) ──
    dP_uncap = 0.5 * rho * (C2 * math.sqrt(1 - wrapFrac)) ** 2 * (1 - wrapFrac)

    # ── 팬 전압 (jet-wake 재차감 제거 — 버그 수정) ──
    Pt_fan = max(0.0, Pt_imp - dP_scroll - dP_tongue - dP_uncap)
    V_exit = Q_delivered / A_exit if Q_delivered > 0 else 0.0
    Pdyn_exit = 0.5 * rho * V_exit ** 2
    Ps = Pt_fan - Pdyn_exit                          # 정압 상승 (사이클에 전달)

    # ── 축동력·효율 ──
    Pshaft = Pt_e * Qm3s + Pdf if Qm3s > 1e-6 else Pdf
    eta = max(0.0, Ps * Q_delivered) / Pshaft if Pshaft > 0 else 0.0

    # ── 출구 공기 상태 (모터열 → 승온, 습도 불변) ──
    m_dot_total = rho * Qm3s
    Q_heat = Pshaft * (1 - eta) if (Pshaft > 0 and eta < 1) else 0.0
    dT_fan = Q_heat / (m_dot_total * cp) if m_dot_total > 0 else 0.0
    T_out = T_in + dT_fan

    return {
        'outputs': {
            'dP_static': Ps,              # Pa — 정압 상승 (Modelica port_b.p - port_a.p)
            'dP_total': Pt_fan,           # Pa — 전압
            'Pt_euler': Pt_e,             # Pa — Euler 이론
            'Pt_imp': Pt_imp,             # Pa — 임펠러 출구 전압
            'eta': eta,                   # — 팬 효율
            'W_shaft': Pshaft,            # W — 축동력
            'Qm3s': Qm3s,                 # m³/s
            'Q_delivered': Q_delivered,   # m³/s (tongue 누설 제외)
            'm_dot_da': m_dot_da,         # kg_da/s
            'T_out': T_out,               # °C
            'dT_fan': dT_fan,             # K
            'omega_out': omega,           # kg/kg (불변)
            'rho': rho, 'mu': mu,
            'U2': U2, 'Ct2': Ct2, 'C2': C2, 'sigma': sigma,
            # 손실 9종 (검증·분해용)
            'dP_inc': dP_inc,
            'dP_fric': dP_fric,
            'dP_rec': dP_rec,
            'dP_disk': dP_disk,
            'dP_jw': dP_jw,
            'dP_scroll': dP_scroll,
            'dP_tongue': dP_tongue,
            'dP_uncap': dP_uncap,
            'DR': DR,
            'eps_leak': eps_leak,
            'Lb': Lb,
        },
        'newState': {},
    }


def validate(params):
    issues = []
    D1 = float(params.get('D1', 120.0))
    D2 = float(params.get('D2', 175.0))
    beta2 = float(params.get('beta2', 145.0))
    Z = float(params.get('Z', 36.0))
    if D2 <= D1:
        issues.append("D2(외경) must exceed D1(입구경)")
    if not (90.0 < beta2 < 180.0):
        issues.append("beta2 should be >90° for forward-curved (전곡) sirocco")
    if Z < 4:
        issues.append("blade count Z too low")
    return issues
