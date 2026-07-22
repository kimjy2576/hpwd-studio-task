"""oil_solubility — R290-미네랄오일 용해 냉매 + 충전량 분배.

배경:
  R290 충전량의 상당분이 압축기 오일에 용해. 정방향 solver의 충전량
  보존식(ΣM = M_charge)에서 이를 빼면 절대 충전량이 안 맞음.
  본 시스템 오일: SUNISO 5GSD (나프텐계 MO). R290은 극성 문제로
  POE/PAG가 아닌 MO/AB를 사용.

용해도 모델 (model= 로 선택):
  'raoult'      P = x1·P1s               (평균오차 10.1%)
  'raoult_fit'  P = γ(T,x1)·x1·P1s       (평균오차 3.98%)  ← 기본
                γ = exp(a + b/T + c·x1), Wang 2020 4GS 실측 37점 회귀
  'nrtl'        Wang 2020 NRTL (미구현 — 계수는 NRTL_COEFFS에 보관)

검증 기준: Wang X., Jia X., Wang D., "Experimental investigation on the
  solubility of R290 in two mineral oils", Int. J. Refrig. 124 (2021) 13-19.
  Table 3 (4GS, 253~333K) 전 데이터 대조. 논문 NRTL 자체 ARD는 1.79%.

⚠️ 5GSD 전용 실측 데이터는 없음. 같은 SUNISO 나프텐계인 4GS(VG56)
   계수를 사용 (5GSD는 VG100이라 4GS보다 무거움 — 근사).
"""
import math

import CoolProp.CoolProp as CP

R290_M = 44.1  # g/mol


# ─── 오일 물성 ────────────────────────────────────────────────────
OIL_5GSD = {
    'name': 'SUNISO 5GSD',
    'type': 'mineral (naphthenic)',
    'rho_15C': 920.0,     # kg/m³ (비중 0.92, 제조사 물성표)
    'drho_dT': -0.628,    # kg/m³/K (Wang 2020 4GS 상관식 기울기 @300K)
    'M_molar': 302.87,    # g/mol — 4GS 값. 5GSD 실측 미상.
                          #   γ 회귀가 이 값 기준이라 일관성 위해 동일 사용.
    'ISO_VG': 100.0,
}


def oil_density(T_C, oil=OIL_5GSD):
    """오일 밀도 [kg/m³]."""
    return oil['rho_15C'] + oil['drho_dT'] * (T_C - 15.0)


def oil_mass_from_volume(V_cc, T_C=20.0, oil=OIL_5GSD):
    """오일 주입 체적 [cc] → 질량 [kg]."""
    return V_cc * 1e-6 * oil_density(T_C, oil)


# ─── 용해도 상관 ──────────────────────────────────────────────────
# γ = exp(a + b/T + c·x1), Wang 2020 4GS Table 3 37점 최소자승
GAMMA_FIT = {'a': -0.68127, 'b': 151.00569, 'c': 0.42058}

# Wang 2020 Table 4 — NRTL 계수 (model='nrtl' 구현 시 사용)
#   τ12 = τ12_0 + τ12_1/T,  τ21 = τ21_0 + τ21_1/T
NRTL_COEFFS = {
    '3GS': {'alpha': 0.5981, 'tau12_0': 21.798, 'tau12_1': -4468.8,
            'tau21_0': 0.24449, 'tau21_1': 155.04, 'M_molar': 318.62},
    '4GS': {'alpha': 0.1194, 'tau12_0': 1.3593, 'tau12_1': 1052.6,
            'tau21_0': 2.5775, 'tau21_1': 132.01, 'M_molar': 302.87},
}


def _x_to_w(x1, M2):
    """냉매 몰분율 → 질량분율."""
    return x1 * R290_M / (x1 * R290_M + (1.0 - x1) * M2)


def _gamma(T_K, x1, fit=GAMMA_FIT):
    return math.exp(fit['a'] + fit['b'] / T_K + fit['c'] * x1)


def solubility(P_bar, T_oil_C, model='raoult_fit', oil=OIL_5GSD):
    """오일에 용해된 R290 질량분율 w1 [-].

    Args:
      P_bar: 오일 sump가 노출된 냉매 압력 [bar]
             (고압쉘 회전압축기면 토출압, 저압쉘이면 흡입압)
      T_oil_C: 오일 sump 온도 [°C]
      model: 'raoult' | 'raoult_fit' | 'nrtl'

    Returns:
      w1: 질량분율 [-] (0~1)
    """
    T = T_oil_C + 273.15
    if T >= CP.PropsSI('Tcrit', 'R290'):
        return 0.0
    P1s = CP.PropsSI('P', 'T', T, 'Q', 1, 'R290') / 1e5  # bar
    M2 = oil['M_molar']

    if model == 'nrtl':
        raise NotImplementedError(
            "NRTL 미구현. 계수는 NRTL_COEFFS 참조. "
            "현재는 'raoult_fit'(평균오차 3.98%) 사용.")

    if model == 'raoult':
        x1 = min(0.99, P_bar / P1s)
        return _x_to_w(x1, M2)

    if model == 'raoult_fit':
        # P = γ(T,x1)·x1·P1s → x1 음함수. 고정점 반복(γ가 x1에 약의존).
        x1 = min(0.99, P_bar / P1s)
        for _ in range(30):
            x_new = min(0.99, P_bar / (_gamma(T, x1) * P1s))
            if abs(x_new - x1) < 1e-10:
                x1 = x_new
                break
            x1 = 0.5 * x1 + 0.5 * x_new
        return _x_to_w(x1, M2)

    raise ValueError(f"unknown model: {model}")


def dissolved_mass(M_oil_kg, P_bar, T_oil_C, model='raoult_fit', oil=OIL_5GSD):
    """오일에 용해된 냉매 질량 [kg].  M_dis = M_oil · w/(1-w)."""
    w = solubility(P_bar, T_oil_C, model, oil)
    w = min(w, 0.95)
    return M_oil_kg * w / (1.0 - w)


def oil_sump_temperature(T_dis_C, dT=15.0):
    """오일 sump 온도 [°C] 추정.

    Shi 2022 (IJR 144, 163-174) 실측: 회전압축기 오일 sump 입구온도는
    토출온도보다 11~20°C 낮음 (주위온도 낮을수록 차이 큼).
    또한 sump 용해도는 균일하고 sump 입구 포화용해도에 가까움.
    """
    return T_dis_C - dT


# ─── 배관 holdup ─────────────────────────────────────────────────
# 구간별 정의. state: 'liquid' | 'vapor' | 'twophase'
#   liquid   → 응축기 출구 과냉액 밀도
#   vapor    → 해당 압력·온도 과열가스 밀도
#   twophase → x_mean 건도의 균질 밀도
def pipe_volume_cc(length_m, ID_mm):
    """배관 내용적 [cc]."""
    return math.pi * (ID_mm * 1e-3 / 2.0) ** 2 * length_m * 1e6


def pipe_holdup(segments, P_cond_bar, P_evap_bar, T_liq_C=None, T_suc_C=None):
    """배관 구간별 냉매 질량 합 [kg].

    Args:
      segments: [{'name','length_m','ID_mm','state','side'}]
                side: 'high'(응축압) | 'low'(증발압)
                state: 'liquid'|'vapor'|'twophase'(+'x' 건도)
    Returns:
      (총질량 kg, [구간별 dict])
    """
    out = []
    total = 0.0
    for s in segments:
        V = pipe_volume_cc(s['length_m'], s['ID_mm']) * 1e-6   # m³
        P = (P_cond_bar if s.get('side', 'high') == 'high' else P_evap_bar) * 1e5
        st = s.get('state', 'vapor')
        if st == 'liquid':
            T = (T_liq_C + 273.15) if T_liq_C is not None else \
                CP.PropsSI('T', 'P', P, 'Q', 0, 'R290') - 3.0
            rho = CP.PropsSI('D', 'P', P, 'T', min(T, CP.PropsSI('T', 'P', P, 'Q', 0, 'R290') - 0.1), 'R290')
        elif st == 'twophase':
            x = s.get('x', 0.5)
            rl = CP.PropsSI('D', 'P', P, 'Q', 0, 'R290')
            rv = CP.PropsSI('D', 'P', P, 'Q', 1, 'R290')
            rho = 1.0 / (x / rv + (1 - x) / rl)
        else:  # vapor
            T = (T_suc_C + 273.15) if T_suc_C is not None else \
                CP.PropsSI('T', 'P', P, 'Q', 1, 'R290') + 5.0
            rho = CP.PropsSI('D', 'P', P, 'T', max(T, CP.PropsSI('T', 'P', P, 'Q', 1, 'R290') + 0.1), 'R290')
        m = rho * V
        total += m
        out.append({'name': s.get('name', '?'), 'V_cc': V * 1e6,
                    'rho': rho, 'm_g': m * 1000})
    return total, out


# ─── 총 충전량 ───────────────────────────────────────────────────
def total_charge(state, M_oil_kg, segments, P_sump_bar, T_dis_C,
                 model='raoult_fit', dT_sump=15.0, oil=OIL_5GSD):
    """총 냉매 충전량 [kg] = HX holdup + 배관 + 오일 용해.

    정방향 solver의 충전량 보존식 좌변.

    Args:
      state: one_pass 결과 (condenser/evaporator의 M_holdup 사용)
      M_oil_kg: 오일 충전 질량
      segments: 배관 구간 정의 (pipe_holdup 참조)
      P_sump_bar: 오일 sump 노출 압력 (고압쉘=P_cond, 저압쉘=P_evap)
      T_dis_C: 압축기 토출온도 [°C]
    """
    M_hx = (state['condenser'].get('M_holdup') or 0.0) \
         + (state['evaporator'].get('M_holdup') or 0.0)
    T_oil = oil_sump_temperature(T_dis_C, dT_sump)
    M_dis = dissolved_mass(M_oil_kg, P_sump_bar, T_oil, model, oil)
    return {
        'total': M_hx + M_dis,   # 배관은 호출측에서 pipe_holdup으로 합산
        'M_HX': M_hx,
        'M_oil_dissolved': M_dis,
        'T_oil_C': T_oil,
        'w_ref': solubility(P_sump_bar, T_oil, model, oil),
    }
