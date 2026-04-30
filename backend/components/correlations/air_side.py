"""
Air-side fin-tube heat transfer correlations
═══════════════════════════════════════════════════════════════════════
Plain fin-tube heat exchanger, staggered tube layout.

Commit 1: Wang-Chi-Chang only (default)
Commit 2 추가 예정: Kim et al (wavy fin), McQuiston

Reference:
  Wang C.C., Chi K.Y., Chang C.J., "Heat transfer and friction
  characteristics of plain fin-and-tube heat exchangers, part II",
  Int. J. Heat Mass Transfer 43 (2000) 2693-2700.
"""

import math


def wang_chi_chang(m_dot_air, T_air_avg_K, D_o, P_t, P_l, P_fin, t_fin,
                   N_row, A_o_face, fluid='air'):
    """Wang-Chi-Chang (2000) — plain fin staggered tube.
    
    j (Colburn factor) → Nu → α
    
    Args:
        m_dot_air  : 공기 질량 유량 [kg/s]
        T_air_avg_K: 공기 평균 온도 [K]
        D_o        : 튜브 외경 [m]
        P_t        : tube transverse pitch [m]
        P_l        : tube longitudinal pitch [m]
        P_fin      : fin pitch [m] (1/FPI 환산)
        t_fin      : fin thickness [m]
        N_row      : tube rows in airflow direction
        A_o_face   : 정면 풍속 면적 [m²]
    
    Returns: α_o [W/m²K]
    """
    # Air properties at avg T (단순 dry air)
    T = T_air_avg_K
    rho = 101325 / (287.05 * T)  # ideal gas
    mu = 1.458e-6 * (T ** 1.5) / (T + 110.4)  # Sutherland
    k = 0.02614 + 7.5e-5 * (T - 273.15)  # 단순 보간
    cp = 1006 + 0.05 * (T - 273.15)
    Pr = mu * cp / k

    # Maximum velocity (between tubes, contracted)
    if A_o_face > 0:
        V_face = m_dot_air / (rho * A_o_face)
    else:
        V_face = 1.0
    # 단순 sigma (contraction ratio)
    sigma = 1.0 - (D_o / P_t)
    sigma = max(sigma, 0.1)
    V_max = V_face / sigma

    # Re_Dc (collared diameter ≈ D_o for plain fin)
    Re_Dc = rho * V_max * D_o / mu if mu > 0 else 1e3
    Re_Dc = max(Re_Dc, 100)

    # Wang-Chi-Chang j-factor for plain fin (regression)
    # 단순화 식 — 정확하게는 Re_Dc 범위/N_row별 다른 P1, P2, P3, P4 계수
    # Commit 1엔 핵심 거동만:
    j = 0.394 * (Re_Dc ** -0.392) * ((P_fin / D_o) ** -0.0449) * (N_row ** -0.0897)
    j = max(j, 0.001)

    # St × Pr^(2/3) = j  →  St = j / Pr^(2/3)
    St = j / (Pr ** (2.0/3.0))

    # α_o = St × ρ × V × cp
    alpha_o = St * rho * V_max * cp
    return max(alpha_o, 5.0)


CORR_REGISTRY = {
    'Wang-Chi-Chang': wang_chi_chang,
    # Commit 2: 'Kim', 'McQuiston'
}

DEFAULT = 'Wang-Chi-Chang'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
