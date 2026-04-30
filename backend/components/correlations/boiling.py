"""
Refrigerant-side boiling heat transfer correlations
═══════════════════════════════════════════════════════════════════════
2-phase 영역 내부 튜브 흐름. 각 함수는 입력으로 운전 조건 + geometry
를 받고 평균 α [W/m²K]를 반환.

이 모듈에 옵션을 추가하려면:
  1. 함수 추가
  2. CORR_REGISTRY에 등록
  3. evaporator_moving_boundary.py의 step()에서 자동 사용

Commit 1: Shah only (default)
Commit 2 추가 예정: Wang-Chang-Chi, Kandlikar, Gungor-Winterton, Cooper
"""

import math
import CoolProp.CoolProp as CP


def shah(P_Pa, x_avg, m_dot, D_i, q_flux, fluid='R290'):
    """Shah (1976) — 학계 표준 2-phase boiling correlation.
    
    α_2ph = α_l × ψ
    α_l = Dittus-Boelter for liquid (Re_l, Pr_l)
    ψ = max(ψ_NB, ψ_CB) — Nucleate boiling 또는 convective boiling 큰 쪽
    
    Args:
        P_Pa     : 압력 [Pa]
        x_avg    : 평균 quality (zone 평균값)
        m_dot    : 냉매 유량 [kg/s] per tube cross-section
        D_i      : 튜브 내경 [m]
        q_flux   : 열유속 [W/m²]
        fluid    : 냉매
    
    Returns: α_2ph [W/m²K]
    """
    if x_avg <= 0 or x_avg >= 1:
        # 단상이면 Dittus-Boelter
        return _liquid_DB(P_Pa, m_dot, D_i, fluid)

    try:
        # Liquid properties (포화액)
        rho_l = CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid)
        mu_l  = CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid)
        k_l   = CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid)
        cp_l  = CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid)
        h_lv  = CP.PropsSI('H', 'P', P_Pa, 'Q', 1, fluid) - \
                CP.PropsSI('H', 'P', P_Pa, 'Q', 0, fluid)
        rho_v = CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid)
        T_sat = CP.PropsSI('T', 'P', P_Pa, 'Q', 0.5, fluid)
        # Critical pressure for reduced pressure
        P_crit = CP.PropsSI('Pcrit', fluid)
    except Exception:
        return _liquid_DB(P_Pa, m_dot, D_i, fluid)

    # Mass flux
    A_cross = math.pi * (D_i ** 2) / 4.0
    G = m_dot / max(A_cross, 1e-9)  # kg/m²s

    # Liquid-only Reynolds & Prandtl
    Re_l = G * (1 - x_avg) * D_i / mu_l if mu_l > 0 else 1e4
    Re_l = max(Re_l, 100.0)  # floor
    Pr_l = mu_l * cp_l / k_l if k_l > 0 else 3.0

    # Liquid HTC (Dittus-Boelter, heating)
    alpha_l = 0.023 * (Re_l ** 0.8) * (Pr_l ** 0.4) * k_l / D_i

    # Convection number Co (Shah)
    Co = ((1 - x_avg) / x_avg) ** 0.8 * (rho_v / rho_l) ** 0.5

    # Boiling number Bo
    Bo = q_flux / (G * h_lv) if (G * h_lv) > 0 else 0.0

    # Froude number Fr (수평 튜브 가정)
    Fr = G ** 2 / (rho_l ** 2 * 9.81 * D_i) if rho_l > 0 else 1.0

    # Constants
    if Fr >= 0.04:
        N = Co
    else:
        # 수평이고 Fr 작으면 stratified — Shah 보정
        N = 0.38 * (Fr ** -0.3) * Co

    # Nucleate boiling factor
    if Bo > 1.9e-5:
        F = 14.7  # high Bo
    else:
        F = 15.43

    psi_nb = F * (Bo ** 0.5) * math.exp(2.74 * (N ** -0.1)) if N > 0 else 0.0

    # Convective boiling
    if N > 1.0:
        psi_cb = 1.8 / (N ** 0.8)
    elif N >= 0.1:
        psi_cb = 1.8 / (N ** 0.8)
    else:
        psi_cb = 1.8 / (N ** 0.8) if N > 0 else 1.0

    psi = max(psi_nb, psi_cb, 1.0)
    alpha_2ph = alpha_l * psi
    return max(alpha_2ph, 100.0)  # floor


def _liquid_DB(P_Pa, m_dot, D_i, fluid):
    """Fallback: liquid-only Dittus-Boelter."""
    try:
        mu = CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid)
        k  = CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid)
        cp = CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid)
    except Exception:
        return 1000.0
    A_cross = math.pi * (D_i ** 2) / 4.0
    G = m_dot / max(A_cross, 1e-9)
    Re = G * D_i / mu if mu > 0 else 1e4
    Pr = mu * cp / k if k > 0 else 3.0
    return 0.023 * (Re ** 0.8) * (Pr ** 0.4) * k / D_i


# ════════ Registry — Commit 2에서 더 추가됨 ════════
CORR_REGISTRY = {
    'Shah': shah,
    # Commit 2: 'Wang-Chang-Chi', 'Kandlikar', 'Gungor-Winterton', 'Cooper'
}

DEFAULT = 'Shah'


def evaluate(name, **kwargs):
    """이름으로 correlation 호출. 없으면 default 사용."""
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
