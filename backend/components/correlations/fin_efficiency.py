"""
Fin efficiency correlations
═══════════════════════════════════════════════════════════════════════
Plain fin (circular fin equivalent), staggered or inline.

Available:
  - Schmidt (1949)  — circular fin equivalent, hexagonal cell
  - Sector method   — fin을 sector로 나누고 각 sector를 적분
"""

import math


def _equivalent_radius(D_o, P_t, P_l, layout):
    """Equivalent fin radius for hexagonal/rectangular cell."""
    if layout == 'staggered':
        M = P_t / 2.0
        L = math.sqrt((P_t / 2.0) ** 2 + P_l ** 2) / 2.0
        beta_1 = L / max(M, 1e-9)
        psi = M / max(D_o / 2.0, 1e-9)
        r_e_over_r = 1.27 * psi * math.sqrt(max(beta_1 - 0.3, 0.01))
    else:  # inline
        psi = (P_t / 2.0) / max(D_o / 2.0, 1e-9)
        beta_1 = (P_l / 2.0) / max(P_t / 2.0, 1e-9)
        r_e_over_r = 1.28 * psi * math.sqrt(max(beta_1 - 0.2, 0.01))
    return max(r_e_over_r, 1.01)


def _eta_circular_fin(r_e_over_r, D_o, t_fin, k_fin, alpha_o):
    """Standard circular fin efficiency from m·r·phi."""
    r = D_o / 2.0
    phi = (r_e_over_r - 1) * (1 + 0.35 * math.log(r_e_over_r))
    if k_fin * t_fin > 0:
        m = math.sqrt(2 * alpha_o / (k_fin * t_fin))
    else:
        m = 0
    m_r = m * r * phi
    if m_r > 0:
        eta = math.tanh(m_r) / m_r
    else:
        eta = 1.0
    return max(0.1, min(1.0, eta))


# ════════════════════════════════════════════════════════════════════
# 1. Schmidt (1949)
# ════════════════════════════════════════════════════════════════════
def schmidt(D_o, P_t, P_l, t_fin, k_fin, alpha_o, layout='staggered'):
    """Schmidt circular fin equivalent."""
    r_e_over_r = _equivalent_radius(D_o, P_t, P_l, layout)
    return _eta_circular_fin(r_e_over_r, D_o, t_fin, k_fin, alpha_o)


# ════════════════════════════════════════════════════════════════════
# 2. Sector method
# ════════════════════════════════════════════════════════════════════
def sector(D_o, P_t, P_l, t_fin, k_fin, alpha_o, layout='staggered', N_sectors=8):
    """Sector method — fin을 N_sectors로 나누고 각 sector의 effective
    radius로 평균. 사각형/육각형 cell의 형상 이방성을 반영.
    
    Schmidt는 단일 equivalent radius를 사용하지만, Sector는 각 방향
    radius를 따로 계산하여 평균. plain fin staggered에서 보통 ±2% 차이.
    """
    if layout == 'staggered':
        M = P_t / 2.0
        L = math.sqrt((P_t / 2.0) ** 2 + P_l ** 2) / 2.0
        # Sector별 effective radius — angle θ에 따라 cell 경계까지 거리
        # 단순화: M과 L 사이 보간
        eta_sum = 0
        for i in range(N_sectors):
            theta = (i + 0.5) * (math.pi / 2) / N_sectors  # 0~π/2
            # Hexagonal cell의 경계까지 거리 — 단순 ellipse 가정
            r_boundary = math.sqrt(
                (M * math.sin(theta)) ** 2 + (L * math.cos(theta)) ** 2
            )
            r_e_over_r_sec = max(r_boundary / max(D_o / 2.0, 1e-9), 1.01)
            eta_sum += _eta_circular_fin(r_e_over_r_sec, D_o, t_fin, k_fin, alpha_o)
        return max(0.1, min(1.0, eta_sum / N_sectors))
    else:
        # Inline은 직사각형 — 더 단순
        a = P_t / 2.0
        b = P_l / 2.0
        eta_sum = 0
        for i in range(N_sectors):
            theta = (i + 0.5) * (math.pi / 2) / N_sectors
            r_boundary = math.sqrt(
                (a * math.sin(theta)) ** 2 + (b * math.cos(theta)) ** 2
            )
            r_e_over_r_sec = max(r_boundary / max(D_o / 2.0, 1e-9), 1.01)
            eta_sum += _eta_circular_fin(r_e_over_r_sec, D_o, t_fin, k_fin, alpha_o)
        return max(0.1, min(1.0, eta_sum / N_sectors))


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
CORR_REGISTRY = {
    'Schmidt': schmidt,
    'Sector':  sector,
}

DEFAULT = 'Schmidt'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
