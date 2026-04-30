"""
Refrigerant-side single-phase (superheat) correlations
═══════════════════════════════════════════════════════════════════════
Internal turbulent flow, gas phase.

Available:
  - Dittus-Boelter (1930) — 학계 default, 가장 단순
  - Gnielinski (1976)     — 더 정확, transition + turbulent
  - Petukhov (1970)       — fully developed turbulent, 매우 정확
"""

import math
import CoolProp.CoolProp as CP


def _gas_props(P_Pa, T_K, fluid):
    """Gas properties at given P, T."""
    try:
        return {
            'rho': CP.PropsSI('D', 'P', P_Pa, 'T', T_K, fluid),
            'mu':  CP.PropsSI('V', 'P', P_Pa, 'T', T_K, fluid),
            'k':   CP.PropsSI('L', 'P', P_Pa, 'T', T_K, fluid),
            'cp':  CP.PropsSI('C', 'P', P_Pa, 'T', T_K, fluid),
        }
    except Exception:
        return None


def _G_from_mdot(m_dot, D_i):
    A_cross = math.pi * (D_i ** 2) / 4.0
    return m_dot / max(A_cross, 1e-12)


# ════════════════════════════════════════════════════════════════════
# 1. Dittus-Boelter (1930)
# ════════════════════════════════════════════════════════════════════
def dittus_boelter(P_Pa, T_avg_K, m_dot, D_i, fluid='R290', heating=True):
    """Dittus-Boelter — 학계 default for turbulent flow.
    Nu = 0.023 × Re^0.8 × Pr^n  (n=0.4 heating, 0.3 cooling)
    """
    p = _gas_props(P_Pa, T_avg_K, fluid)
    if p is None:
        return 100.0
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / p['mu'] if p['mu'] > 0 else 1e4
    Pr = p['mu'] * p['cp'] / p['k'] if p['k'] > 0 else 1.0
    n = 0.4 if heating else 0.3
    Nu = 0.023 * (Re ** 0.8) * (Pr ** n)
    return max(Nu * p['k'] / D_i, 50.0)


# ════════════════════════════════════════════════════════════════════
# 2. Gnielinski (1976)
# ════════════════════════════════════════════════════════════════════
def gnielinski(P_Pa, T_avg_K, m_dot, D_i, fluid='R290', heating=True):
    """Gnielinski (1976) — 더 정확한 turbulent flow correlation.
    
    Nu = (f/8)(Re - 1000) Pr / (1 + 12.7 sqrt(f/8) (Pr^(2/3) - 1))
    f = (0.79 ln(Re) - 1.64)^-2  (Petukhov friction factor)
    
    Validity: 3000 < Re < 5e6, 0.5 < Pr < 2000.
    Transition + fully turbulent 모두 정확.
    """
    p = _gas_props(P_Pa, T_avg_K, fluid)
    if p is None:
        return 100.0
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / p['mu'] if p['mu'] > 0 else 1e4
    Pr = p['mu'] * p['cp'] / p['k'] if p['k'] > 0 else 1.0

    if Re < 2300:
        # Laminar — fallback to Nu = 4.36 (constant heat flux)
        Nu = 4.36
    else:
        # Petukhov friction factor
        Re_safe = max(Re, 2300)
        f = (0.79 * math.log(Re_safe) - 1.64) ** -2

        Pr_term = Pr ** (2.0/3.0) - 1
        denom = 1 + 12.7 * math.sqrt(f / 8.0) * Pr_term
        Nu = (f / 8.0) * (Re_safe - 1000) * Pr / max(denom, 1e-6)

    return max(Nu * p['k'] / D_i, 50.0)


# ════════════════════════════════════════════════════════════════════
# 3. Petukhov (1970)
# ════════════════════════════════════════════════════════════════════
def petukhov(P_Pa, T_avg_K, m_dot, D_i, fluid='R290', heating=True):
    """Petukhov (1970) — fully developed turbulent.
    
    Nu = (f/8) Re Pr / (1.07 + 12.7 sqrt(f/8) (Pr^(2/3) - 1))
    
    Gnielinski의 origin. Re > 1e4 fully turbulent에서 매우 정확.
    범위: 1e4 < Re < 5e6, 0.5 < Pr < 2000.
    """
    p = _gas_props(P_Pa, T_avg_K, fluid)
    if p is None:
        return 100.0
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / p['mu'] if p['mu'] > 0 else 1e4
    Pr = p['mu'] * p['cp'] / p['k'] if p['k'] > 0 else 1.0

    if Re < 2300:
        Nu = 4.36
    else:
        Re_safe = max(Re, 2300)
        f = (0.79 * math.log(Re_safe) - 1.64) ** -2

        Pr_term = Pr ** (2.0/3.0) - 1
        denom = 1.07 + 12.7 * math.sqrt(f / 8.0) * Pr_term
        Nu = (f / 8.0) * Re_safe * Pr / max(denom, 1e-6)

    return max(Nu * p['k'] / D_i, 50.0)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
CORR_REGISTRY = {
    'Dittus-Boelter': dittus_boelter,
    'Gnielinski':     gnielinski,
    'Petukhov':       petukhov,
}

DEFAULT = 'Dittus-Boelter'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
