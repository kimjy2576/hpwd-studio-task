"""
Refrigerant-side condensation heat transfer correlations
═══════════════════════════════════════════════════════════════════════
2-phase 응축 영역 (cond chamber) 내부 튜브 흐름. 각 함수는 운전 조건 +
geometry를 받고 평균 α [W/m²K]를 반환.

Available:
  - Shah (1979)             — 학계 표준, 단순. 거의 모든 냉매에 동작
  - Cavallini-Smith (2006)  — 강제 대류 영역 (regime 분리)
  - Dobson-Chato (1998)     — wavy-stratified vs annular regime
  - Akers (1959)            — 가장 간단, 빠른 추정용

Boiling과 차이점:
  • boiling: vapor가 nucleate하며 chamber 형성 → α가 q_flux dependence
  • condensation: vapor가 wall에서 응축 → α는 q_flux 무관 (보통)
  • condensation α는 보통 boiling α의 1.5~3배 수준 (높음)
"""

import math
import CoolProp.CoolProp as CP


def _saturated_props(P_Pa, fluid):
    """포화 vapor/liquid properties — boiling.py와 동일 helper."""
    return {
        'rho_l': CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid),
        'mu_l':  CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid),
        'k_l':   CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid),
        'cp_l':  CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid),
        'rho_v': CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid),
        'mu_v':  CP.PropsSI('V', 'P', P_Pa, 'Q', 1, fluid),
        'k_v':   CP.PropsSI('L', 'P', P_Pa, 'Q', 1, fluid),
        'cp_v':  CP.PropsSI('C', 'P', P_Pa, 'Q', 1, fluid),
        'h_l':   CP.PropsSI('H', 'P', P_Pa, 'Q', 0, fluid),
        'h_v':   CP.PropsSI('H', 'P', P_Pa, 'Q', 1, fluid),
        'sigma': CP.PropsSI('I', 'P', P_Pa, 'Q', 0, fluid),  # surface tension
    }


def _G_from_mdot(m_dot, D_i):
    A_cross = math.pi * (D_i ** 2) / 4.0
    return m_dot / max(A_cross, 1e-12)


def _alpha_liquid_only_DB(rho_l, mu_l, k_l, cp_l, G, D_i):
    """Liquid-only Dittus-Boelter (전유량이 액체로 흐른다고 가정)."""
    Re_lo = G * D_i / mu_l if mu_l > 0 else 1e4
    Re_lo = max(Re_lo, 100.0)
    Pr_l = mu_l * cp_l / k_l if k_l > 0 else 3.0
    # 응축은 cooling 모드 → exponent 0.3 (heating은 0.4)
    return 0.023 * (Re_lo ** 0.8) * (Pr_l ** 0.3) * k_l / D_i


def _fallback_alpha(P_Pa, m_dot, D_i, fluid):
    """Correlation 실패 시 안전 fallback — liquid-only Dittus-Boelter."""
    try:
        mu = CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid)
        k = CP.PropsSI('L', 'P', P_Pa, 'Q', 0, fluid)
        cp = CP.PropsSI('C', 'P', P_Pa, 'Q', 0, fluid)
    except Exception:
        return 2000.0  # 응축 typical
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / mu if mu > 0 else 1e4
    Pr = mu * cp / k if k > 0 else 3.0
    return 0.023 * (Re ** 0.8) * (Pr ** 0.3) * k / D_i


# ════════════════════════════════════════════════════════════════════
# 1. Shah (1979) — 학계 표준 응축 상관식
# ════════════════════════════════════════════════════════════════════
def shah(P_Pa, x_avg, m_dot, D_i, q_flux=None, fluid='R290'):
    """Shah (1979) condensation correlation.
    
    α/α_lo = (1-x)^0.8 + 3.8 × x^0.76 × (1-x)^0.04 / Pr^0.38
    
    where Pr = P / P_crit
    
    Range: 7 < Re_lo, 0 < x < 1, all common refrigerants.
    """
    if x_avg <= 0 or x_avg >= 1:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    try:
        p = _saturated_props(P_Pa, fluid)
        P_crit = CP.PropsSI('Pcrit', fluid)
    except Exception:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    G = _G_from_mdot(m_dot, D_i)
    alpha_lo = _alpha_liquid_only_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, D_i)
    
    Pr_red = max(P_Pa / P_crit, 0.01)
    
    # Shah enhancement factor
    factor = ((1 - x_avg) ** 0.8 +
              3.8 * (x_avg ** 0.76) * ((1 - x_avg) ** 0.04) / (Pr_red ** 0.38))
    
    alpha = alpha_lo * factor
    return max(alpha, 100.0)


# ════════════════════════════════════════════════════════════════════
# 2. Cavallini-Smith (2006) — regime 분리, 정밀
# ════════════════════════════════════════════════════════════════════
def cavallini_smith(P_Pa, x_avg, m_dot, D_i, q_flux=None, fluid='R290'):
    """Cavallini-Smith-Zecchin (2006) — 단순화된 ΔT-independent 영역만.
    
    실제 Cavallini는 ΔT-dependent regime 분기까지 하지만 ε-NTU 안에서는
    ΔT 모르므로 ΔT-independent (annular) 영역으로 단순화.
    
    α_annular = α_lo × (1 + 1.128 × x^0.817 × (ρ_l/ρ_v)^0.3685 × ...)
    """
    if x_avg <= 0 or x_avg >= 1:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    try:
        p = _saturated_props(P_Pa, fluid)
    except Exception:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    G = _G_from_mdot(m_dot, D_i)
    alpha_lo = _alpha_liquid_only_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, D_i)
    
    rho_ratio = max(p['rho_l'] / p['rho_v'], 1.0) if p['rho_v'] > 0 else 100.0
    mu_ratio = max(p['mu_l'] / p['mu_v'], 1.0) if p['mu_v'] > 0 else 30.0
    
    # ΔT-independent (Cavallini Eq. for annular flow)
    factor = 1.0 + 1.128 * (x_avg ** 0.817) * (rho_ratio ** 0.3685) * (mu_ratio ** 0.2363) * \
             ((1.0 - p['mu_v'] / max(p['mu_l'], 1e-9)) ** 2.144)
    
    alpha = alpha_lo * factor
    return max(min(alpha, 50000.0), 100.0)


# ════════════════════════════════════════════════════════════════════
# 3. Dobson-Chato (1998) — wavy-stratified vs annular
# ════════════════════════════════════════════════════════════════════
def dobson_chato(P_Pa, x_avg, m_dot, D_i, q_flux=None, fluid='R290'):
    """Dobson-Chato (1998) — Annular regime (보통 G > 500 kg/m²s).
    
    G < 500 일 때는 wavy-stratified로 분기되지만 본 cascade 안에서는
    annular 가정으로 단순화 (ε-NTU 안에서 G가 충분히 높음 가정).
    
    α/α_lo = 1 + 2.22/X_tt^0.89
    where X_tt = ((1-x)/x)^0.9 × (ρ_v/ρ_l)^0.5 × (μ_l/μ_v)^0.1
    """
    if x_avg <= 0 or x_avg >= 1:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    try:
        p = _saturated_props(P_Pa, fluid)
    except Exception:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    G = _G_from_mdot(m_dot, D_i)
    alpha_lo = _alpha_liquid_only_DB(p['rho_l'], p['mu_l'], p['k_l'], p['cp_l'], G, D_i)
    
    # Martinelli parameter
    X_tt = (((1 - x_avg) / x_avg) ** 0.9 *
            (p['rho_v'] / p['rho_l']) ** 0.5 *
            (p['mu_l'] / p['mu_v']) ** 0.1) if p['rho_l'] > 0 and p['mu_v'] > 0 else 1.0
    X_tt = max(X_tt, 0.01)
    
    factor = 1.0 + 2.22 / (X_tt ** 0.89)
    alpha = alpha_lo * factor
    return max(min(alpha, 50000.0), 100.0)


# ════════════════════════════════════════════════════════════════════
# 4. Akers (1959) — 단순 추정용, equivalent mass flux
# ════════════════════════════════════════════════════════════════════
def akers(P_Pa, x_avg, m_dot, D_i, q_flux=None, fluid='R290'):
    """Akers et al. (1959) — equivalent Reynolds number method.
    
    G_eq = G × ((1-x) + x × (ρ_l/ρ_v)^0.5)
    Nu = 0.0265 × Re_eq^0.8 × Pr_l^(1/3)   (Re_eq > 5e4)
       = 5.03 × Re_eq^(1/3) × Pr_l^(1/3)   (Re_eq ≤ 5e4)
    """
    if x_avg <= 0 or x_avg >= 1:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    try:
        p = _saturated_props(P_Pa, fluid)
    except Exception:
        return _fallback_alpha(P_Pa, m_dot, D_i, fluid)
    
    G = _G_from_mdot(m_dot, D_i)
    rho_ratio_sqrt = (p['rho_l'] / p['rho_v']) ** 0.5 if p['rho_v'] > 0 else 10.0
    G_eq = G * ((1 - x_avg) + x_avg * rho_ratio_sqrt)
    
    Re_eq = G_eq * D_i / p['mu_l'] if p['mu_l'] > 0 else 1e4
    Pr_l = p['mu_l'] * p['cp_l'] / p['k_l'] if p['k_l'] > 0 else 3.0
    
    if Re_eq > 5e4:
        Nu = 0.0265 * (Re_eq ** 0.8) * (Pr_l ** (1/3))
    else:
        Nu = 5.03 * (Re_eq ** (1/3)) * (Pr_l ** (1/3))
    
    alpha = Nu * p['k_l'] / D_i
    return max(alpha, 100.0)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
CORR_REGISTRY = {
    'Shah':            shah,
    'Cavallini-Smith': cavallini_smith,
    'Dobson-Chato':    dobson_chato,
    'Akers':           akers,
}

DEFAULT = 'Shah'
