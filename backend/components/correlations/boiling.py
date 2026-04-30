"""
Refrigerant-side boiling heat transfer correlations
═══════════════════════════════════════════════════════════════════════
2-phase 영역 내부 튜브 흐름. 각 함수는 운전 조건 + geometry를 받고
평균 α [W/m²K]를 반환.

Available:
  - Shah (1976)            — 학계 표준, 단순
  - Wang-Chang-Chi (2000)  — fin-tube 특화 (Chen-style E×α_l + S×α_pb)
  - Kandlikar (1990)       — 일반 boiling, NBD/CBD region 자동
  - Gungor-Winterton (1986)— horizontal flow boiling
  - Cooper (1984)          — pool boiling-like (nucleate dominant)
"""

import math
import CoolProp.CoolProp as CP


def _liquid_props(P_Pa, fluid):
    return {
        'rho_l': CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid),
        'mu_l':  CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid),
        'k_l':   CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid),
        'cp_l':  CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid),
        'rho_v': CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid),
        'mu_v':  CP.PropsSI('V', 'P', P_Pa, 'Q', 1, fluid),
        'h_l':   CP.PropsSI('H', 'P', P_Pa, 'Q', 0, fluid),
        'h_v':   CP.PropsSI('H', 'P', P_Pa, 'Q', 1, fluid),
    }


def _G_from_mdot(m_dot, D_i):
    A_cross = math.pi * (D_i ** 2) / 4.0
    return m_dot / max(A_cross, 1e-12)


def _alpha_liquid_DB(rho_l, mu_l, k_l, cp_l, G, x, D_i):
    Re_l = G * (1 - x) * D_i / mu_l if mu_l > 0 else 1e4
    Re_l = max(Re_l, 100.0)
    Pr_l = mu_l * cp_l / k_l if k_l > 0 else 3.0
    return 0.023 * (Re_l ** 0.8) * (Pr_l ** 0.4) * k_l / D_i


def _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid):
    try:
        mu = CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid)
        k  = CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid)
        cp = CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid)
    except Exception:
        return 1000.0
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / mu if mu > 0 else 1e4
    Pr = mu * cp / k if k > 0 else 3.0
    return 0.023 * (Re ** 0.8) * (Pr ** 0.4) * k / D_i


# ════════════════════════════════════════════════════════════════════
# 1. Shah (1976)
# ════════════════════════════════════════════════════════════════════
def shah(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    if x_avg <= 0 or x_avg >= 1:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    h_lv = p['h_v'] - p['h_l']

    G = _G_from_mdot(m_dot, D_i)
    alpha_l = _alpha_liquid_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, x_avg, D_i)

    Co = ((1 - x_avg) / x_avg) ** 0.8 * (p['rho_v'] / p['rho_l']) ** 0.5
    Bo = q_flux / (G * h_lv) if (G * h_lv) > 0 else 0.0
    Fr = G ** 2 / (p['rho_l'] ** 2 * 9.81 * D_i) if p['rho_l'] > 0 else 1.0

    if Fr >= 0.04:
        N = Co
    else:
        N = 0.38 * (Fr ** -0.3) * Co

    F = 14.7 if Bo > 1.9e-5 else 15.43
    psi_nb = F * (Bo ** 0.5) * math.exp(2.74 * (max(N, 1e-6) ** -0.1))
    psi_cb = 1.8 / (max(N, 1e-6) ** 0.8)
    psi = max(psi_nb, psi_cb, 1.0)
    return max(alpha_l * psi, 100.0)


# ════════════════════════════════════════════════════════════════════
# 2. Wang-Chang-Chi (Chen-style E × α_l + S × α_pb)
# ════════════════════════════════════════════════════════════════════
def wang_chang_chi(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    if x_avg <= 0 or x_avg >= 1:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    try:
        p = _liquid_props(P_Pa, fluid)
        P_crit = CP.PropsSI('Pcrit', fluid)
        M = CP.PropsSI('molar_mass', fluid) * 1000
    except Exception:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)

    G = _G_from_mdot(m_dot, D_i)
    alpha_l = _alpha_liquid_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, x_avg, D_i)

    # Lockhart-Martinelli X_tt
    X_tt = ((1 - x_avg) / x_avg) ** 0.9 * (p['rho_v'] / p['rho_l']) ** 0.5 * (p['mu_l'] / p['mu_v']) ** 0.1
    X_tt = max(X_tt, 1e-6)

    # Enhancement factor (Chen)
    inv_Xtt = 1 / X_tt
    if inv_Xtt >= 0.1:
        E = 2.35 * (inv_Xtt + 0.213) ** 0.736
    else:
        E = 1.0

    # Cooper pool boiling
    Pr_red = max(min(P_Pa / P_crit, 0.9), 0.001)
    alpha_pb = 55 * (Pr_red ** 0.12) * (-math.log10(Pr_red)) ** -0.55 * (M ** -0.5) * (q_flux ** 0.67)
    alpha_pb = max(alpha_pb, 100.0)

    # Suppression factor (Chen)
    Re_l = G * (1 - x_avg) * D_i / p['mu_l'] if p['mu_l'] > 0 else 1e4
    Re_tp = Re_l * (E ** 1.25)
    S = 1 / (1 + 2.53e-6 * (Re_tp ** 1.17))
    S = max(0.0, min(1.0, S))

    return max(E * alpha_l + S * alpha_pb, 100.0)


# ════════════════════════════════════════════════════════════════════
# 3. Kandlikar (1990) — NBD/CBD region 자동
# ════════════════════════════════════════════════════════════════════
def kandlikar(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    if x_avg <= 0 or x_avg >= 1:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    h_lv = p['h_v'] - p['h_l']

    G = _G_from_mdot(m_dot, D_i)
    alpha_l = _alpha_liquid_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, x_avg, D_i)

    Co = ((1 - x_avg) / x_avg) ** 0.8 * (p['rho_v'] / p['rho_l']) ** 0.5
    Bo = q_flux / (G * h_lv) if (G * h_lv) > 0 else 0.0
    Fr_lo = G ** 2 / (p['rho_l'] ** 2 * 9.81 * D_i) if p['rho_l'] > 0 else 1.0

    F_fl = 1.0  # R290

    # NBD region: 0 < Co ≤ 0.65
    C1_n, C2_n, C3_n, C4_n, C5_n = 0.6683, -0.2, 1058.0, 0.7, 0.3
    # CBD region: Co > 0.65
    C1_c, C2_c, C3_c, C4_c, C5_c = 1.1360, -0.9, 667.2, 0.7, 0.3

    Fr_factor_n = (25 * Fr_lo) ** C5_n if Fr_lo < 0.04 else 1.0
    Fr_factor_c = (25 * Fr_lo) ** C5_c if Fr_lo < 0.04 else 1.0

    Co_safe = max(Co, 1e-6)
    psi_NBD = C1_n * (Co_safe ** C2_n) * Fr_factor_n + C3_n * (Bo ** C4_n) * F_fl
    psi_CBD = C1_c * (Co_safe ** C2_c) * Fr_factor_c + C3_c * (Bo ** C4_c) * F_fl

    psi = max(psi_NBD, psi_CBD)
    return max(alpha_l * psi, 100.0)


# ════════════════════════════════════════════════════════════════════
# 4. Gungor-Winterton (1986)
# ════════════════════════════════════════════════════════════════════
def gungor_winterton(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    if x_avg <= 0 or x_avg >= 1:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    try:
        p = _liquid_props(P_Pa, fluid)
        P_crit = CP.PropsSI('Pcrit', fluid)
        M = CP.PropsSI('molar_mass', fluid) * 1000
    except Exception:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)
    h_lv = p['h_v'] - p['h_l']

    G = _G_from_mdot(m_dot, D_i)
    alpha_l = _alpha_liquid_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, x_avg, D_i)

    Bo = q_flux / (G * h_lv) if (G * h_lv) > 0 else 0.0
    Fr_lo = G ** 2 / (p['rho_l'] ** 2 * 9.81 * D_i) if p['rho_l'] > 0 else 1.0

    X_tt = ((1 - x_avg) / x_avg) ** 0.9 * (p['rho_v'] / p['rho_l']) ** 0.5 * (p['mu_l'] / p['mu_v']) ** 0.1
    X_tt = max(X_tt, 1e-6)

    # Enhancement factor (G-W)
    E = 1 + 24000 * (Bo ** 1.16) + 1.37 * ((1 / X_tt) ** 0.86)

    # Stratification correction
    if Fr_lo < 0.05:
        E *= Fr_lo ** (0.1 - 2 * Fr_lo)
        S2 = math.sqrt(Fr_lo)
    else:
        S2 = 1.0

    # Cooper pool boiling
    Pr_red = max(min(P_Pa / P_crit, 0.9), 0.001)
    alpha_pb = 55 * (Pr_red ** 0.12) * (-math.log10(Pr_red)) ** -0.55 * (M ** -0.5) * (q_flux ** 0.67)
    alpha_pb = max(alpha_pb, 100.0)

    Re_l = G * (1 - x_avg) * D_i / p['mu_l'] if p['mu_l'] > 0 else 1e4
    S = 1 / (1 + 1.15e-6 * (E ** 2) * (Re_l ** 1.17))
    S *= S2
    S = max(0.0, min(1.0, S))

    return max(E * alpha_l + S * alpha_pb, 100.0)


# ════════════════════════════════════════════════════════════════════
# 5. Cooper (1984)
# ════════════════════════════════════════════════════════════════════
def cooper(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    """Pool boiling-like — convective 무시. nucleate dominant 영역."""
    try:
        P_crit = CP.PropsSI('Pcrit', fluid)
        M = CP.PropsSI('molar_mass', fluid) * 1000
    except Exception:
        return _liquid_DB_fallback(P_Pa, m_dot, D_i, fluid)

    Pr_red = max(min(P_Pa / P_crit, 0.9), 0.001)
    alpha = 55 * (Pr_red ** 0.12) * (-math.log10(Pr_red)) ** -0.55 * (M ** -0.5) * (q_flux ** 0.67)
    return max(alpha, 100.0)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
CORR_REGISTRY = {
    'Shah':              shah,
    'Wang-Chang-Chi':    wang_chang_chi,
    'Kandlikar':         kandlikar,
    'Gungor-Winterton':  gungor_winterton,
    'Cooper':            cooper,
}

DEFAULT = 'Shah'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
