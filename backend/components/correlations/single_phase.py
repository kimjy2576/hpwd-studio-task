"""
Refrigerant-side single-phase (superheat) correlations
═══════════════════════════════════════════════════════════════════════
Internal turbulent flow, gas phase.

Commit 1: Dittus-Boelter only (default)
Commit 2 추가 예정: Gnielinski, Petukhov
"""

import math
import CoolProp.CoolProp as CP


def dittus_boelter(P_Pa, T_avg_K, m_dot, D_i, fluid='R290', heating=True):
    """Dittus-Boelter (1930) — 학계 default for turbulent flow.
    
    Nu = 0.023 × Re^0.8 × Pr^n
      n = 0.4 (heating, fluid being heated)
      n = 0.3 (cooling)
    
    Validity: Re > 10000, 0.7 < Pr < 160. SH 영역에선 보통 만족.
    """
    try:
        rho = CP.PropsSI('D', 'P', P_Pa, 'T', T_avg_K, fluid)
        mu  = CP.PropsSI('V', 'P', P_Pa, 'T', T_avg_K, fluid)
        k   = CP.PropsSI('L', 'P', P_Pa, 'T', T_avg_K, fluid)
        cp  = CP.PropsSI('C', 'P', P_Pa, 'T', T_avg_K, fluid)
    except Exception:
        return 100.0  # fallback for SH gas (낮음)

    A_cross = math.pi * (D_i ** 2) / 4.0
    G = m_dot / max(A_cross, 1e-9)
    Re = G * D_i / mu if mu > 0 else 1e4
    Pr = mu * cp / k if k > 0 else 1.0
    n = 0.4 if heating else 0.3
    Nu = 0.023 * (Re ** 0.8) * (Pr ** n)
    alpha = Nu * k / D_i
    return max(alpha, 50.0)


CORR_REGISTRY = {
    'Dittus-Boelter': dittus_boelter,
    # Commit 2: 'Gnielinski', 'Petukhov'
}

DEFAULT = 'Dittus-Boelter'


def evaluate(name, **kwargs):
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)
