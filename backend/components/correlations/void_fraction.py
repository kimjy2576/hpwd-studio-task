"""
Void fraction correlations (2-phase) — 냉매 charge inventory 계산용
═══════════════════════════════════════════════════════════════════════
void fraction α = 2상 유동에서 증기가 점유하는 단면적 분율.
2상 구간 평균 밀도 ρ_tp = α·ρ_v + (1-α)·ρ_l 로 charge holdup 계산.

⚠️ 이 모듈은 charge inventory 전용. 열전달/압력강하 correlation 내부의
   void fraction(예: Dobson-Chato)과는 별개 (목적·정밀도 기준 다름).

Available (위계 없는 동등 모델 선택, fitting parameter 없음):
  - Homogeneous          — no-slip (S=1), 가장 단순, 액 holdup 과소
  - Zivi (1964)          — slip ratio S=(ρ_l/ρ_v)^(1/3), 운동E 최소화
  - Rigot                — slip ratio S=2 고정 (단순 상수)
  - Hughmark (1962)      — homogeneous에 보정계수 K_H(Z), mass-flux 의존
  - Premoli (1970)       — slip-ratio + Re·We, 액밀도 오차 최소화 (charge 표준)
  - Rouhani-Axelsson     — drift-flux (Steiner horizontal), transient 표준

charge 예측 정확도: Hughmark·Premoli·Tandon이 측정값에 근접 (Rice/ORNL).
Premoli가 액밀도 최적화라 charge ground truth로 적합 → DEFAULT.

참고문헌:
  Zivi (1964), Rigot (1973), Hughmark (1962), Premoli et al. (1970),
  Rouhani-Axelsson (1970) / Steiner (1993) horizontal modification.
"""

import math
import CoolProp.CoolProp as CP

GRAV = 9.81


# ════════════════════════════════════════════════════════════════════
# 헬퍼: 물성 + 질량유속
# ════════════════════════════════════════════════════════════════════
def _props(P_Pa, fluid):
    """포화 액·기 물성 (charge 계산에 필요한 것만)."""
    return {
        'rho_l': CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid),
        'rho_v': CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid),
        'mu_l':  CP.PropsSI('V', 'P', P_Pa, 'Q', 0, fluid),
        'mu_v':  CP.PropsSI('V', 'P', P_Pa, 'Q', 1, fluid),
        'sigma': CP.PropsSI('I', 'P', P_Pa, 'Q', 0, fluid),  # 표면장력
    }


def _G_from_mdot(m_dot, D_i):
    """질량유속 G = ṁ / A_cross [kg/m²s]."""
    A = math.pi * (D_i ** 2) / 4.0
    return m_dot / max(A, 1e-12)


def _homogeneous_void(x, rho_l, rho_v):
    """homogeneous void fraction β (slip ratio S=1)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1.0 / (1.0 + (1 - x) / x * (rho_v / rho_l))


def _slip_void(x, rho_l, rho_v, S):
    """slip-ratio 기반 void fraction: α = 1/(1 + S·(1-x)/x·ρ_v/ρ_l)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1.0 / (1.0 + S * (1 - x) / x * (rho_v / rho_l))


# ════════════════════════════════════════════════════════════════════
# 1. Homogeneous (no-slip, S=1)
# ════════════════════════════════════════════════════════════════════
def homogeneous(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    return _clamp(_homogeneous_void(x, p['rho_l'], p['rho_v']))


# ════════════════════════════════════════════════════════════════════
# 2. Zivi (1964) — S = (ρ_l/ρ_v)^(1/3)
# ════════════════════════════════════════════════════════════════════
def zivi(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    S = (p['rho_l'] / max(p['rho_v'], 1e-6)) ** (1.0 / 3.0)
    return _clamp(_slip_void(x, p['rho_l'], p['rho_v'], S))


# ════════════════════════════════════════════════════════════════════
# 3. Rigot — S = 2 (상수)
# ════════════════════════════════════════════════════════════════════
def rigot(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    return _clamp(_slip_void(x, p['rho_l'], p['rho_v'], 2.0))


# ════════════════════════════════════════════════════════════════════
# 4. Hughmark (1962) — homogeneous × 보정계수 K_H(Z), mass-flux 의존
#    α = K_H · β,  Z = Re^(1/6)·Fr^(1/8) / (1-β)^(1/4),  K_H = f(Z) 테이블
#    Z가 α에 의존 → fixed-point iteration
# ════════════════════════════════════════════════════════════════════
_HUGHMARK_Z = [1.3, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 40.0, 70.0, 130.0]
_HUGHMARK_K = [0.185, 0.225, 0.325, 0.49, 0.605, 0.675, 0.72, 0.767, 0.78, 0.808, 0.83, 0.88, 0.93, 0.98]


def _hughmark_KH(Z):
    """K_H = f(Z) 선형 보간 (테이블 범위 밖은 끝값 clamp)."""
    if Z <= _HUGHMARK_Z[0]:
        return _HUGHMARK_K[0]
    if Z >= _HUGHMARK_Z[-1]:
        return _HUGHMARK_K[-1]
    for i in range(len(_HUGHMARK_Z) - 1):
        if _HUGHMARK_Z[i] <= Z <= _HUGHMARK_Z[i + 1]:
            f = (Z - _HUGHMARK_Z[i]) / (_HUGHMARK_Z[i + 1] - _HUGHMARK_Z[i])
            return _HUGHMARK_K[i] + f * (_HUGHMARK_K[i + 1] - _HUGHMARK_K[i])
    return _HUGHMARK_K[-1]


def hughmark(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    rho_l, rho_v, mu_l, mu_v = p['rho_l'], p['rho_v'], p['mu_l'], p['mu_v']
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    beta = _homogeneous_void(x, rho_l, rho_v)  # homogeneous void
    G = _G_from_mdot(m_dot, D_i)
    # fixed-point: α 추정 → Z → K_H → α_new = K_H·β
    alpha = beta
    for _ in range(20):
        # 혼합 점도 (mass-weighted)
        mu_mix = mu_l * (1 - x) + mu_v * x
        Re = D_i * G / max(mu_mix, 1e-9)
        # vapor Froude (증기 표면속도 기반)
        j_v = G * x / max(rho_v * alpha, 1e-9)
        Fr = j_v ** 2 / max(GRAV * D_i, 1e-12)
        y_L = max(1.0 - beta, 1e-6)  # liquid volume fraction (homogeneous)
        Z = (Re ** (1.0 / 6.0)) * (Fr ** (1.0 / 8.0)) / (y_L ** (1.0 / 4.0))
        K_H = _hughmark_KH(Z)
        alpha_new = K_H * beta
        if abs(alpha_new - alpha) < 1e-5:
            alpha = alpha_new
            break
        alpha = 0.5 * alpha_new + 0.5 * alpha  # under-relax
    return _clamp(alpha)


# ════════════════════════════════════════════════════════════════════
# 5. Premoli et al. (1970) — slip-ratio + Re·We (charge 표준)
#    S = 1 + E1·[y/(1+y·E2) − y·E2]^0.5,  y = β/(1−β)
#    E1 = 1.578·Re^(−0.19)·(ρ_l/ρ_v)^0.22
#    E2 = 0.0273·We·Re^(−0.51)·(ρ_l/ρ_v)^(−0.08)
# ════════════════════════════════════════════════════════════════════
def premoli(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    rho_l, rho_v, mu_l, sigma = p['rho_l'], p['rho_v'], p['mu_l'], p['sigma']
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    G = _G_from_mdot(m_dot, D_i)
    Re = G * D_i / max(mu_l, 1e-9)               # 전체 G, 액 점성
    We = G ** 2 * D_i / max(sigma * rho_l, 1e-12)  # 액 기준 Weber
    rr = rho_l / max(rho_v, 1e-6)
    E1 = 1.578 * Re ** (-0.19) * rr ** 0.22
    E2 = 0.0273 * We * Re ** (-0.51) * rr ** (-0.08)
    beta = _homogeneous_void(x, rho_l, rho_v)
    y = beta / max(1.0 - beta, 1e-9)
    inner = y / (1.0 + y * E2) - y * E2
    S = 1.0 + E1 * math.sqrt(max(inner, 0.0))
    return _clamp(_slip_void(x, rho_l, rho_v, S))


# ════════════════════════════════════════════════════════════════════
# 6. Rouhani-Axelsson (1970) — drift-flux, Steiner horizontal 수정
#    α = (x/ρ_v) · [ C0·(x/ρ_v + (1−x)/ρ_l)
#                    + 1.18·(1−x)·(g·σ·(ρ_l−ρ_v))^0.25 / (G·ρ_l^0.5) ]^(−1)
#    C0 = 1 + 0.12·(1−x)  (분포계수, drift-flux 모델값)
# ════════════════════════════════════════════════════════════════════
def rouhani_axelsson(x, P_Pa, m_dot, D_i, fluid='R290'):
    p = _props(P_Pa, fluid)
    rho_l, rho_v, sigma = p['rho_l'], p['rho_v'], p['sigma']
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    G = _G_from_mdot(m_dot, D_i)
    C0 = 1.0 + 0.12 * (1 - x)
    drift = 1.18 * (1 - x) * (GRAV * sigma * (rho_l - rho_v)) ** 0.25 / max(G * math.sqrt(rho_l), 1e-9)
    denom = C0 * (x / rho_v + (1 - x) / rho_l) + drift
    alpha = (x / rho_v) / max(denom, 1e-12)
    return _clamp(alpha)


# ════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════
def _clamp(a):
    return max(0.0, min(a, 1.0))


CORR_REGISTRY = {
    'Homogeneous':       homogeneous,
    'Zivi':              zivi,
    'Rigot':             rigot,
    'Hughmark':          hughmark,
    'Premoli':           premoli,
    'Rouhani-Axelsson':  rouhani_axelsson,
}

DEFAULT = 'Premoli'  # 액밀도 최적화 → charge inventory ground truth


def evaluate(name, **kwargs):
    """void fraction α 계산. name으로 모델 선택 (없으면 DEFAULT)."""
    fn = CORR_REGISTRY.get(name) or CORR_REGISTRY[DEFAULT]
    return fn(**kwargs)


def mean_density(alpha, P_Pa, fluid='R290'):
    """2상 평균 밀도 ρ_tp = α·ρ_v + (1−α)·ρ_l [kg/m³] — charge holdup용."""
    rho_l = CP.PropsSI('D', 'P', P_Pa, 'Q', 0, fluid)
    rho_v = CP.PropsSI('D', 'P', P_Pa, 'Q', 1, fluid)
    return alpha * rho_v + (1.0 - alpha) * rho_l


def available():
    """선택 가능한 void fraction 모델 목록."""
    return list(CORR_REGISTRY.keys())
