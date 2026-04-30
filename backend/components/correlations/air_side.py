"""
Air-side fin-tube heat transfer correlations
═══════════════════════════════════════════════════════════════════════
Plain fin-tube heat exchanger, staggered tube layout.

Available:
  - Wang-Chi-Chang (2000) — plain fin, staggered, 가전 표준
  - Kim et al (1999)      — wavy fin (high performance)
  - McQuiston (1981)      — 학계 시초, plain fin (gentle slope)

Reference:
  Wang C.C. et al, Int. J. Heat Mass Transfer 43 (2000) 2693-2700.
  Kim N.H. et al, ASHRAE Trans. 105 (1999) 769-779.
  McQuiston F.C., ASHRAE Trans. 87 (1981) 1077-1085.
"""

import math


def _air_props(T_K):
    """Dry air properties (moist air W는 무시 — 1차 근사)."""
    rho = 101325 / (287.05 * T_K)
    mu = 1.458e-6 * (T_K ** 1.5) / (T_K + 110.4)  # Sutherland
    k = 0.02614 + 7.5e-5 * (T_K - 273.15)
    cp = 1006 + 0.05 * (T_K - 273.15)
    Pr = mu * cp / k
    return rho, mu, k, cp, Pr


def _v_max(m_dot_air, T_K, D_o, P_t, A_o_face):
    """Max velocity (between tubes, contracted)."""
    rho, _, _, _, _ = _air_props(T_K)
    if A_o_face > 0:
        V_face = m_dot_air / (rho * A_o_face)
    else:
        V_face = 1.0
    sigma = 1.0 - (D_o / max(P_t, 1e-6))
    sigma = max(sigma, 0.1)
    return V_face / sigma, rho


# ════════════════════════════════════════════════════════════════════
# 1. Wang-Chi-Chang (2000) — plain fin staggered
# ════════════════════════════════════════════════════════════════════
def wang_chi_chang(m_dot_air, T_air_avg_K, D_o, P_t, P_l, P_fin, t_fin,
                   N_row, A_o_face, fluid='air'):
    """Wang-Chi-Chang (2000) j-factor for plain fin staggered tube.
    
    Re_Dc 범위 + N_row 별 다른 P1, P2, P3, P4 계수 — 단순화한 form.
    """
    rho, mu, k, cp, Pr = _air_props(T_air_avg_K)
    V_max, _ = _v_max(m_dot_air, T_air_avg_K, D_o, P_t, A_o_face)

    Re_Dc = rho * V_max * D_o / mu if mu > 0 else 1e3
    Re_Dc = max(Re_Dc, 100)

    # Plain-fin staggered j-factor (regression)
    j = 0.394 * (Re_Dc ** -0.392) * \
        ((P_fin / max(D_o, 1e-6)) ** -0.0449) * \
        (max(N_row, 1) ** -0.0897)
    j = max(j, 0.001)

    # St × Pr^(2/3) = j
    St = j / (Pr ** (2.0/3.0))
    return max(St * rho * V_max * cp, 5.0)


# ════════════════════════════════════════════════════════════════════
# 2. Kim et al (1999) — wavy fin
# ════════════════════════════════════════════════════════════════════
def kim(m_dot_air, T_air_avg_K, D_o, P_t, P_l, P_fin, t_fin,
        N_row, A_o_face, fluid='air'):
    """Kim et al (1999) — wavy (herringbone) fin, staggered.
    
    Wavy fin은 plain fin보다 enhancement ~30~50%. wave amplitude는
    무시 (단순화 — 형상 정보 없으면 standard wavy 가정).
    """
    rho, mu, k, cp, Pr = _air_props(T_air_avg_K)
    V_max, _ = _v_max(m_dot_air, T_air_avg_K, D_o, P_t, A_o_face)

    Re_Dc = rho * V_max * D_o / mu if mu > 0 else 1e3
    Re_Dc = max(Re_Dc, 100)

    # Kim wavy fin j-factor (단순화)
    # Wavy enhancement factor ~1.4× plain fin in same Re range
    j_plain = 0.394 * (Re_Dc ** -0.392) * \
              ((P_fin / max(D_o, 1e-6)) ** -0.0449) * \
              (max(N_row, 1) ** -0.0897)
    
    # Kim wavy 추가 항 (wavelength, amplitude 정보 없으니 평균 enhancement)
    enhancement = 1.42  # typical wavy fin enhancement factor over plain
    j = j_plain * enhancement
    j = max(j, 0.001)

    St = j / (Pr ** (2.0/3.0))
    return max(St * rho * V_max * cp, 5.0)


# ════════════════════════════════════════════════════════════════════
# 3. McQuiston (1981)
# ════════════════════════════════════════════════════════════════════
def mcquiston(m_dot_air, T_air_avg_K, D_o, P_t, P_l, P_fin, t_fin,
              N_row, A_o_face, fluid='air'):
    """McQuiston (1981) — 학계 시초 plain fin.
    
    j_4 = 0.0014 + 0.2618 × Re_D^-0.4 × (A_o / A_t)^-0.15
    
    A_o = total external area, A_t = bare tube area. 정확하지만
    Wang-Chi-Chang보다 보수적 (under-predict 경향).
    """
    rho, mu, k, cp, Pr = _air_props(T_air_avg_K)
    V_max, _ = _v_max(m_dot_air, T_air_avg_K, D_o, P_t, A_o_face)

    Re_D = rho * V_max * D_o / mu if mu > 0 else 1e3
    Re_D = max(Re_D, 100)

    # A_o/A_t ratio — 단순 추정 (FPI가 핀 밀도 정보 제공)
    # P_fin 작을수록 A_o/A_t 큼 (fin이 더 많음)
    if P_fin > 0:
        A_ratio = max((P_t * P_l) / (P_fin * D_o), 5)  # 대략적 — 5~30 범위
    else:
        A_ratio = 15
    A_ratio = min(A_ratio, 30)

    # McQuiston j-factor (4 row reference, 다른 row는 보정 필요)
    j_4 = 0.0014 + 0.2618 * (Re_D ** -0.4) * (A_ratio ** -0.15)
    
    # Row count correction (J_N / J_4)
    if N_row >= 4:
        j = j_4
    else:
        # 1, 2, 3 row 보정
        row_factor = {1: 1.30, 2: 1.15, 3: 1.05}.get(int(N_row), 1.0)
        j = j_4 * row_factor

    j = max(j, 0.001)

    St = j / (Pr ** (2.0/3.0))
    return max(St * rho * V_max * cp, 5.0)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
CORR_REGISTRY = {
    'Wang-Chi-Chang': wang_chi_chang,
    'Kim':            kim,
    'McQuiston':      mcquiston,
}

DEFAULT = 'Wang-Chi-Chang'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
