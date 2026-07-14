"""
filter_on.py — 린트 필터 압력강하 모델 (L1/L2/L3)

건조기 린트(보풀) 필터의 clean 상태 압력강하. Modelica Filter_L1/L2/L3의
ground truth. 팬(fan_on)·드럼(drum_on)과 동일 step() 인터페이스.

필터는 정적(대수) 모델 — 상태변수 없음, 열·물질전달 무시(h_tilde,W pass-through).
팬/드럼과 달리 Ergun은 교과서 표준식(fit 아닌 기하 유도)이라 외부 저장소 없이
문헌 수식으로 직접 구현.

문헌(model-docs) fidelity 3급:
  L1(OFF): Darcy-Forchheimer 단순화 — ΔP = K·u·|u| (관성항만)
  L2(SEMI): DF 2항 — ΔP = a·μu + b·ρu² (점성+관성, a·b fit)
  L3(ON): 메쉬 기하 → Ergun — ε,d_f에서 a·b 도출 + 다층

3급 공통 (면 기하 → media velocity):
  A_media = A_face·r_pleat/cos(θ_face)  [도면 측정값, fit 아님]
  u = V̇/A_media,  V̇ = m_da·(1+W)/ρ(p_ref)  [비압축]

참고문헌:
  Darcy-Forchheimer porous media pressure drop (점성항+관성항)
  Ergun equation — 공극률·입경에서 점성·관성계수 도출
"""
import math

# ══════════════════════════════════════════════════════════════
# 공기 물성 (건조기 필터 통과 공기, ~50°C 대표)
# ══════════════════════════════════════════════════════════════
P_ATM = 101325.0
R_DA = 287.055

def _air_density(T_C, omega, P=P_ATM):
    """습공기 밀도 (dry-air partial + vapor)."""
    T_K = T_C + 273.15
    R_v = 461.52
    Pv = P * omega / (0.62198 + omega)
    Pda = P - Pv
    return Pda / (R_DA * T_K) + Pv / (R_v * T_K)

def _air_viscosity(T_C):
    """공기 점도 (Sutherland)."""
    T_K = T_C + 273.15
    T_ref, S, mu_ref = 273.15, 110.4, 1.716e-5
    return mu_ref * (T_K / T_ref) ** 1.5 * (T_ref + S) / (T_K + S)


def init_state(params):
    return {}


def _media_velocity(input, params):
    """3급 공통: 면 기하 → media velocity u, 밀도/점도 반환."""
    A_face = float(params.get("A_face", 0.05))
    r_pleat = float(params.get("r_pleat", 1.0))
    theta_face = float(params.get("theta_face", 0.0))

    T_in = float(input.get("T_in", 50.0))
    omega = float(input.get("omega", 0.010))
    P_in = float(input.get("P_in", P_ATM))

    rho = _air_density(T_in, omega, P_in)
    mu = _air_viscosity(T_in)

    if "m_dot_da" in input:
        m_dot_da = float(input["m_dot_da"])
        V_dot = m_dot_da * (1 + omega) / rho
    else:
        V_dot = float(input.get("V_dot", 0.03))
        m_dot_da = V_dot * rho / (1 + omega)

    theta_rad = math.radians(theta_face)
    A_media = A_face * r_pleat / math.cos(theta_rad)
    u = V_dot / A_media
    return u, rho, mu, V_dot, m_dot_da, A_media


def step(input, params, state, dt):
    """
    fidelity 파라미터로 L1/L2/L3 선택 (기본 L1).
      params['fidelity'] ∈ {'L1','L2','L3'}
    """
    fidelity = params.get("fidelity", "L1")
    u, rho, mu, V_dot, m_dot_da, A_media = _media_velocity(input, params)

    if fidelity == "L1":
        dp, extra = _dp_L1(u, rho, params)
    elif fidelity == "L2":
        dp, extra = _dp_L2(u, rho, mu, params)
    elif fidelity == "L3":
        dp, extra = _dp_L3(u, rho, mu, params)
    else:
        raise ValueError(f"unknown fidelity: {fidelity}")

    # 출구 (pass-through, 압력만 강하)
    P_in = float(input.get("P_in", P_ATM))
    out = {
        "dp": dp,                    # Pa — 압력강하
        "P_out": P_in - dp,          # Pa
        "u": u,                      # m/s — media velocity
        "V_dot": V_dot,              # m³/s
        "m_dot_da": m_dot_da,        # kg_da/s
        "A_media": A_media,          # m²
        "rho": rho, "mu": mu,
        "fidelity": fidelity,
    }
    out.update(extra)
    return {"outputs": out, "newState": {}}


# ══════════════════════════════════════════════════════════════
# L1 — Darcy-Forchheimer 단순화 (관성항만)
# ══════════════════════════════════════════════════════════════
def _dp_L1(u, rho, params):
    """ΔP = K·u·|u|. 관성항만(b·ρ 특수형). 역류 부호보존 C¹."""
    K = float(params.get("K", 20.0))
    dp = K * u * abs(u)
    return dp, {}


# ══════════════════════════════════════════════════════════════
# L2 — Darcy-Forchheimer 2항 (점성 + 관성)
# ══════════════════════════════════════════════════════════════
def _dp_L2(u, rho, mu, params):
    """
    ΔP = a·μ·u + b·ρ·u·|u|.
      a [1/m²] 점성(Darcy), b [1/m] 관성(Forchheimer). 측정곡선 회귀.
      L1의 K = b·ρ 특수형 (점성항 a·μu 추가로 저유속 정확).
      역류 부호보존: 관성항 u·|u|.
    """
    a_visc = float(params.get("a_visc", 5.0e4))   # 1/m² (점성 계수)
    b_inert = float(params.get("b_inert", 17.0))  # 1/m  (관성 계수)
    dp_visc = a_visc * mu * u
    dp_inert = b_inert * rho * u * abs(u)
    dp = dp_visc + dp_inert
    return dp, {"dp_visc": dp_visc, "dp_inert": dp_inert}


# ══════════════════════════════════════════════════════════════
# L3 — 메쉬 기하 → Ergun (다층)
# ══════════════════════════════════════════════════════════════
def _dp_L3(u, rho, mu, params):
    """
    메쉬 기하(MPI, wire경)에서 Ergun a·b 도출 → 두께 적분 → 다층 합.
      Step2: ε=(1-d_w·MPI)², d_f=d_w
      Step3: a=150(1-ε)²/(ε³d_f²), b=1.75(1-ε)/(ε³d_f)   [Ergun, fit 아닌 기하]
      Step4: ΔP_layer = (a·μu + b·ρu²)·L
      Step5: ΔP_tot = Σ_layers
    layers = [{'MPI','d_w','L'}, ...] (pre-filter + main)
    """
    cf_ergun = float(params.get("cf_ergun", 1.0))  # 재질 거칠기 보정
    # 건조기 린트필터: 얇은 성긴 플라스틱 메쉬 (구멍 커서 공기 잘 통과, 린트만 포집).
    #   MPI~15-30(성긴), d_w~0.3-0.4mm(굵은 wire), L~0.5-0.6mm(얇은 단층).
    #   ⚠️ HEPA급(MPI 200)은 d_w·MPI>1로 ε 음수. 린트용 성긴값 필수.
    layers = params.get("layers", [
        {"MPI": 15.0, "d_w": 0.0004, "L": 0.0006},   # 단일 린트 메쉬 (대표값)
    ])

    dp_tot = 0.0
    layer_dp = []
    for ly in layers:
        MPI = float(ly["MPI"])          # 인치당 메쉬수 (1/inch)
        d_w = float(ly["d_w"])          # wire경 (m)
        L = float(ly["L"])              # 두께 (m)
        MPI_per_m = MPI / 0.0254        # 1/inch → 1/m
        # Step2: 개구율·섬유경
        eps = (1 - d_w * MPI_per_m) ** 2
        eps = max(min(eps, 0.999), 0.05)
        d_f = d_w
        # Step3: Ergun a·b (기하 유도)
        a_erg = 150.0 * (1 - eps) ** 2 / (eps ** 3 * d_f ** 2)
        b_erg = 1.75 * (1 - eps) / (eps ** 3 * d_f)
        # Step4: 층 ΔP (두께 적분 = 균질이라 ·L)
        dp_ly = cf_ergun * (a_erg * mu * u + b_erg * rho * u * abs(u)) * L
        dp_tot += dp_ly
        layer_dp.append({"eps": eps, "d_f": d_f, "a_erg": a_erg, "b_erg": b_erg, "dp": dp_ly})

    return dp_tot, {"layers": layer_dp, "n_layers": len(layers)}


def validate(params):
    issues = []
    fidelity = params.get("fidelity", "L1")
    if fidelity not in ("L1", "L2", "L3"):
        issues.append(f"unknown fidelity: {fidelity}")
    r_pleat = float(params.get("r_pleat", 1.0))
    if r_pleat < 1.0:
        issues.append("r_pleat must be ≥1 (1=flat)")
    if fidelity == "L3":
        for ly in params.get("layers", []):
            d_w = float(ly.get("d_w", 0))
            MPI = float(ly.get("MPI", 0))
            if d_w * MPI / 0.0254 >= 1.0:
                issues.append(f"layer d_w·MPI too high → ε≤0 (d_w={d_w}, MPI={MPI})")
    return issues
