"""
Fin efficiency correlations
═══════════════════════════════════════════════════════════════════════
Plain fin (circular fin equivalent) — 학계 표준은 Schmidt.

Commit 1: Schmidt
Commit 2: Sector method
"""

import math


def schmidt(D_o, P_t, P_l, t_fin, k_fin, alpha_o, layout='staggered'):
    """Schmidt (1949) circular fin equivalent.
    
    Plain fin staggered tube → hexagonal cell 가정 → equivalent circular fin.
    
    Args:
        D_o     : 튜브 외경 [m]
        P_t     : transverse pitch [m]
        P_l     : longitudinal pitch [m]
        t_fin   : 핀 두께 [m]
        k_fin   : 핀 열전도율 [W/mK] (Al ~ 200)
        alpha_o : 외부 α [W/m²K]
        layout  : 'staggered' or 'inline'
    
    Returns: η_fin [-]
    """
    # Equivalent circular fin radius (Schmidt 식)
    if layout == 'staggered':
        # Hexagonal cell radius
        M = P_t / 2.0
        L = math.sqrt((P_t / 2.0) ** 2 + P_l ** 2) / 2.0
        # phi factor
        beta_1 = L / M if M > 0 else 1.0
        psi = M / (D_o / 2.0) if D_o > 0 else 2.0
        # Equivalent radius ratio
        r_e_over_r = 1.27 * psi * math.sqrt(beta_1 - 0.3)
    else:  # inline
        psi = (P_t / 2.0) / (D_o / 2.0) if D_o > 0 else 2.0
        beta_1 = (P_l / 2.0) / (P_t / 2.0) if P_t > 0 else 1.0
        r_e_over_r = 1.28 * psi * math.sqrt(beta_1 - 0.2)

    r_e_over_r = max(r_e_over_r, 1.01)  # avoid log(0)

    r = D_o / 2.0
    r_e = r_e_over_r * r

    # phi for tanh argument
    phi = (r_e_over_r - 1) * (1 + 0.35 * math.log(r_e_over_r))

    # m × r
    if k_fin * t_fin > 0:
        m = math.sqrt(2 * alpha_o / (k_fin * t_fin))
    else:
        m = 0
    m_r = m * r * phi

    # Fin efficiency
    if m_r > 0:
        eta_fin = math.tanh(m_r) / m_r
    else:
        eta_fin = 1.0

    return max(0.1, min(1.0, eta_fin))


CORR_REGISTRY = {
    'Schmidt': schmidt,
    # Commit 2: 'Sector'
}

DEFAULT = 'Schmidt'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
