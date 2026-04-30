"""
Pressure drop correlations
═══════════════════════════════════════════════════════════════════════
Total dP = dP_friction + dP_acceleration  (Hydrostatic 제외 — 수평 가정)

Available — 2-phase friction:
  - MSH (Müller-Steinhagen-Heck, 1986)  — 학계 표준, 단순+정확
  - Friedel (1979)                       — 가장 정확 (4 dim.number)
  - Lockhart-Martinelli (1949)           — 시초, 단순
  - Chisholm (1973)                      — 단순, parameter B 기반

Single-phase friction:
  - Churchill (1977) — laminar/transition/turbulent 자동 (전 범위)

Acceleration:
  - dP_a = G² × (1/ρ_h_out - 1/ρ_h_in)  (homogeneous density 기반)

Reference:
  Müller-Steinhagen H., Heck K., Chem. Eng. Process. 20 (1986) 297-308.
  Friedel L., European Two-Phase Flow Group Meeting (1979).
  Lockhart R.W., Martinelli R.C., Chem. Eng. Prog. 45 (1949) 39-48.
  Chisholm D., Int. J. Heat Mass Transfer 16 (1973) 347-358.
  Churchill S.W., Chem. Eng. (Nov 1977) 91-92.
"""

import math
import CoolProp.CoolProp as CP


def _liquid_props(P_Pa, fluid):
    return {
        'rho_l': CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid),
        'mu_l':  CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid),
        'rho_v': CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid),
        'mu_v':  CP.PropsSI('V', 'P', P_Pa, 'Q', 1, fluid),
    }


def _G_from_mdot(m_dot, D_i):
    A_cross = math.pi * (D_i ** 2) / 4.0
    return m_dot / max(A_cross, 1e-12)


# ════════════════════════════════════════════════════════════════════
# Churchill (1977) — Single-phase friction factor
# ════════════════════════════════════════════════════════════════════
def churchill_friction(Re, eps_over_D=0.0):
    """Churchill (1977) — laminar/transition/turbulent 전 범위 자동.
    
    f = 8 × ((8/Re)^12 + 1/(A+B)^1.5)^(1/12)
    A = (-2.457 ln((7/Re)^0.9 + 0.27 eps/D))^16
    B = (37530/Re)^16
    
    Returns: Fanning friction factor (Darcy/4).
    """
    if Re < 1:
        return 0.5  # avoid division
    Re_safe = max(Re, 1.0)
    
    A = (-2.457 * math.log((7.0/Re_safe)**0.9 + 0.27*eps_over_D)) ** 16
    B = (37530.0 / Re_safe) ** 16
    
    f_darcy = 8.0 * ((8.0/Re_safe)**12 + 1.0/(A + B)**1.5) ** (1.0/12.0)
    f_fanning = f_darcy / 4.0
    return max(f_fanning, 1e-5)


def single_phase_dp(P_Pa, T_K, m_dot, D_i, L, fluid='R290', is_liquid=False, eps_over_D=0.0):
    """Single-phase frictional pressure drop using Churchill.
    
    Returns: dP [Pa] (positive = pressure loss)
    """
    try:
        if is_liquid:
            rho = CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid)
            mu = CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid)
        else:
            rho = CP.PropsSI('D', 'P', P_Pa, 'T', T_K, fluid)
            mu = CP.PropsSI('V', 'P', P_Pa, 'T', T_K, fluid)
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / mu if mu > 0 else 1.0
    f = churchill_friction(Re, eps_over_D)
    
    # ΔP_f = 4 × f_F × (L/D) × G² / (2 × ρ)
    dP = 4 * f * (L / D_i) * (G ** 2) / (2 * rho)
    return max(dP, 0.0)


# ════════════════════════════════════════════════════════════════════
# 1. Müller-Steinhagen-Heck (MSH, 1986)
# ════════════════════════════════════════════════════════════════════
def msh_2phase(P_Pa, x_in, x_out, m_dot, D_i, L, fluid='R290', N_sub=10):
    """MSH 2-phase frictional pressure drop.
    
    (dP/dz)_2ph = G_M × (1-x)^(1/3) + B × x³
      G_M = A + 2(B-A) × x
      A = liquid-only frictional gradient
      B = vapor-only frictional gradient
    
    Integration: trapezoidal, N_sub subsections.
    """
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    
    # Liquid-only friction gradient (A) — assume all flow as liquid
    Re_lo = G * D_i / p['mu_l'] if p['mu_l'] > 0 else 1.0
    f_lo = churchill_friction(Re_lo)
    A = 4 * f_lo * (G ** 2) / (2 * p['rho_l'] * D_i)  # Pa/m
    
    # Vapor-only friction gradient (B) — assume all flow as vapor
    Re_vo = G * D_i / p['mu_v'] if p['mu_v'] > 0 else 1.0
    f_vo = churchill_friction(Re_vo)
    B = 4 * f_vo * (G ** 2) / (2 * p['rho_v'] * D_i)  # Pa/m
    
    # Integrate (dP/dz)_2ph along x_in → x_out (uniformly distributed)
    dP_total = 0.0
    L_per_sub = L / N_sub
    for i in range(N_sub):
        x_lo = x_in + (x_out - x_in) * i / N_sub
        x_hi = x_in + (x_out - x_in) * (i + 1) / N_sub
        x_mid = (x_lo + x_hi) / 2
        x_mid = max(0.0, min(1.0, x_mid))
        
        G_M = A + 2 * (B - A) * x_mid
        dpdz = G_M * (1 - x_mid)**(1.0/3.0) + B * (x_mid**3)
        dP_total += dpdz * L_per_sub
    
    return max(dP_total, 0.0)


# ════════════════════════════════════════════════════════════════════
# 2. Friedel (1979)
# ════════════════════════════════════════════════════════════════════
def friedel_2phase(P_Pa, x_in, x_out, m_dot, D_i, L, fluid='R290', N_sub=10):
    """Friedel correlation — 가장 정확한 학계 표준.
    
    Φ²_LO = E + 3.24 × F × H / (Fr_h^0.045 × We^0.035)
      E = (1-x)² + x² × (ρ_l × f_vo) / (ρ_v × f_lo)
      F = x^0.78 × (1-x)^0.224
      H = (ρ_l/ρ_v)^0.91 × (μ_v/μ_l)^0.19 × (1 - μ_v/μ_l)^0.7
      Fr_h = G² / (g × D × ρ_h²)  (Froude)
      We = G² × D / (ρ_h × σ)  (Weber)
      ρ_h = (x/ρ_v + (1-x)/ρ_l)^-1
    
    dP_2ph = Φ²_LO × dP_LO
    """
    try:
        p = _liquid_props(P_Pa, fluid)
        sigma = CP.PropsSI('I', 'P', P_Pa, 'Q', 0, fluid)  # surface tension
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    
    # Friction factors
    Re_lo = G * D_i / p['mu_l'] if p['mu_l'] > 0 else 1.0
    f_lo = churchill_friction(Re_lo)
    Re_vo = G * D_i / p['mu_v'] if p['mu_v'] > 0 else 1.0
    f_vo = churchill_friction(Re_vo)
    
    # LO pressure drop gradient
    dpdz_lo = 4 * f_lo * (G ** 2) / (2 * p['rho_l'] * D_i)
    
    dP_total = 0.0
    L_per_sub = L / N_sub
    
    for i in range(N_sub):
        x_lo = x_in + (x_out - x_in) * i / N_sub
        x_hi = x_in + (x_out - x_in) * (i + 1) / N_sub
        x_mid = max(1e-6, min(1.0 - 1e-6, (x_lo + x_hi) / 2))
        
        # Homogeneous density
        rho_h = 1.0 / (x_mid / p['rho_v'] + (1 - x_mid) / p['rho_l'])
        
        # Dimensionless numbers
        Fr_h = (G ** 2) / (9.81 * D_i * (rho_h ** 2)) if rho_h > 0 else 1.0
        We = (G ** 2) * D_i / (rho_h * sigma) if (rho_h * sigma) > 0 else 1.0
        Fr_h = max(Fr_h, 1e-6)
        We = max(We, 1e-6)
        
        # Friedel multiplier
        E = (1 - x_mid)**2 + (x_mid**2) * (p['rho_l'] * f_vo) / (p['rho_v'] * f_lo)
        F = (x_mid**0.78) * ((1 - x_mid)**0.224)
        mu_ratio = p['mu_v'] / p['mu_l'] if p['mu_l'] > 0 else 0.01
        mu_ratio = max(min(mu_ratio, 0.99), 1e-6)
        H = ((p['rho_l']/p['rho_v'])**0.91) * (mu_ratio**0.19) * ((1 - mu_ratio)**0.7)
        
        Phi2_lo = E + 3.24 * F * H / ((Fr_h**0.045) * (We**0.035))
        
        dpdz_2ph = Phi2_lo * dpdz_lo
        dP_total += dpdz_2ph * L_per_sub
    
    return max(dP_total, 0.0)


# ════════════════════════════════════════════════════════════════════
# 3. Lockhart-Martinelli (1949)
# ════════════════════════════════════════════════════════════════════
def lockhart_martinelli_2phase(P_Pa, x_in, x_out, m_dot, D_i, L, fluid='R290', N_sub=10):
    """Lockhart-Martinelli — 시초의 2-phase correlation.
    
    Φ²_l = 1 + C/X + 1/X²
    X² = (dP/dz)_l / (dP/dz)_v   (Martinelli parameter)
    C = constant depending on flow regime (default C=20 for tt)
    
    dP_2ph = Φ²_l × dP_l (단상 액체 가정의 dP)
    """
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    C = 20.0  # turbulent-turbulent (most common)
    
    dP_total = 0.0
    L_per_sub = L / N_sub
    
    for i in range(N_sub):
        x_lo = x_in + (x_out - x_in) * i / N_sub
        x_hi = x_in + (x_out - x_in) * (i + 1) / N_sub
        x_mid = max(1e-6, min(1.0 - 1e-6, (x_lo + x_hi) / 2))
        
        # Liquid-phase only (just (1-x) of total flow)
        Re_l = G * (1 - x_mid) * D_i / p['mu_l'] if p['mu_l'] > 0 else 1.0
        f_l = churchill_friction(Re_l)
        dpdz_l = 4 * f_l * ((G * (1 - x_mid))**2) / (2 * p['rho_l'] * D_i)
        
        # Vapor-phase only
        Re_v = G * x_mid * D_i / p['mu_v'] if p['mu_v'] > 0 else 1.0
        f_v = churchill_friction(Re_v)
        dpdz_v = 4 * f_v * ((G * x_mid)**2) / (2 * p['rho_v'] * D_i)
        
        # Martinelli parameter
        X2 = dpdz_l / dpdz_v if dpdz_v > 0 else 1.0
        X = math.sqrt(max(X2, 1e-9))
        
        # Two-phase multiplier (liquid base)
        Phi2_l = 1 + C/X + 1.0/(X**2)
        
        dpdz_2ph = Phi2_l * dpdz_l
        dP_total += dpdz_2ph * L_per_sub
    
    return max(dP_total, 0.0)


# ════════════════════════════════════════════════════════════════════
# 4. Chisholm (1973)
# ════════════════════════════════════════════════════════════════════
def chisholm_2phase(P_Pa, x_in, x_out, m_dot, D_i, L, fluid='R290', N_sub=10):
    """Chisholm (1973) — 단순 B-coefficient.
    
    Φ²_lo = 1 + (Y² - 1) × (B × x^((2-n)/2) × (1-x)^((2-n)/2) + x^(2-n))
      Y² = (dP/dz)_vo / (dP/dz)_lo
      n = 0.25 (turbulent)
      B = function of Y and G:
        Y < 9.5:        B based on G
        9.5 < Y < 28:   B = 520 / (Y × G^0.5)
        Y > 28:         B = 15000 / (Y² × G^0.5)
    """
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    n = 0.25  # turbulent exponent
    
    # Friction factors (LO and VO)
    Re_lo = G * D_i / p['mu_l'] if p['mu_l'] > 0 else 1.0
    f_lo = churchill_friction(Re_lo)
    dpdz_lo = 4 * f_lo * (G**2) / (2 * p['rho_l'] * D_i)
    
    Re_vo = G * D_i / p['mu_v'] if p['mu_v'] > 0 else 1.0
    f_vo = churchill_friction(Re_vo)
    dpdz_vo = 4 * f_vo * (G**2) / (2 * p['rho_v'] * D_i)
    
    Y2 = dpdz_vo / dpdz_lo if dpdz_lo > 0 else 1.0
    Y = math.sqrt(max(Y2, 1e-9))
    
    # Chisholm B coefficient
    if Y < 9.5:
        if G < 500:
            B = 4.8
        elif G < 1900:
            B = 2400 / G
        else:
            B = 55 / math.sqrt(G)
    elif Y < 28:
        B = 520 / (Y * math.sqrt(G)) if G > 0 else 1.0
    else:
        B = 15000 / ((Y**2) * math.sqrt(G)) if G > 0 else 1.0
    
    dP_total = 0.0
    L_per_sub = L / N_sub
    
    for i in range(N_sub):
        x_lo = x_in + (x_out - x_in) * i / N_sub
        x_hi = x_in + (x_out - x_in) * (i + 1) / N_sub
        x_mid = max(1e-6, min(1.0 - 1e-6, (x_lo + x_hi) / 2))
        
        # Chisholm two-phase multiplier
        Phi2_lo = 1 + (Y2 - 1) * (B * (x_mid**((2-n)/2)) * ((1-x_mid)**((2-n)/2)) + x_mid**(2-n))
        Phi2_lo = max(Phi2_lo, 1.0)
        
        dpdz_2ph = Phi2_lo * dpdz_lo
        dP_total += dpdz_2ph * L_per_sub
    
    return max(dP_total, 0.0)


# ════════════════════════════════════════════════════════════════════
# Acceleration Pressure Drop (homogeneous flow)
# ════════════════════════════════════════════════════════════════════
def acceleration_dp(P_Pa, x_in, x_out, m_dot, D_i, fluid='R290'):
    """Homogeneous flow acceleration ΔP.
    
    ΔP_a = G² × (v_h_out - v_h_in)
    v_h = x/ρ_v + (1-x)/ρ_l   (homogeneous specific volume)
    
    boiling이면 (x_out > x_in) 양수 — 압력 강하.
    condensation이면 음수 — 압력 회복.
    
    Returns: dP [Pa] (positive = pressure loss)
    """
    try:
        p = _liquid_props(P_Pa, fluid)
    except Exception:
        return 0.0
    
    G = _G_from_mdot(m_dot, D_i)
    
    x_in_safe = max(0.0, min(1.0, x_in))
    x_out_safe = max(0.0, min(1.0, x_out))
    
    v_in = x_in_safe / p['rho_v'] + (1 - x_in_safe) / p['rho_l']
    v_out = x_out_safe / p['rho_v'] + (1 - x_out_safe) / p['rho_l']
    
    dP_a = (G**2) * (v_out - v_in)
    return dP_a  # 부호 유지 (boiling +, condensation -)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
TWO_PHASE_REGISTRY = {
    'MSH':                  msh_2phase,
    'Friedel':              friedel_2phase,
    'Lockhart-Martinelli':  lockhart_martinelli_2phase,
    'Chisholm':             chisholm_2phase,
}

DEFAULT_2PH = 'MSH'


def evaluate_2phase(name, **kwargs):
    fn = TWO_PHASE_REGISTRY.get(name) or TWO_PHASE_REGISTRY[DEFAULT_2PH]
    return fn(**kwargs)
