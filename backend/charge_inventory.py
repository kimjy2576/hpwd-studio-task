"""
charge_inventory.py — 시스템 냉매 충전량(charge) 산출 유틸
═══════════════════════════════════════════════════════════════════════
컴포넌트(노드) holdup과 연결선(배관) holdup을 합산해 시스템 total charge를 구함.

[설계 원칙]
- 배관은 별도 노드(컴포넌트)가 아니라 HPWD Studio 캔버스의 연결선(edge) 속성이다.
  연결선 kind='refrigerant'인 경우 lineParams(L, di)로 charge를 계산한다.
  (LINE_KINDS.refrigerant: L[mm], di[mm], ... — 프론트가 이미 보유)
- 노드 holdup은 각 컴포넌트(증발기/응축기 Semi·On)가 출력하는 M_holdup을 그대로 쓴다.
  Off는 형상(V_internal)이 없어 holdup 미지원(성능 전용).
- charge balance는 닫힌 냉매 control volume에만 성립 → 합산은 냉매 도메인 한정.

[배관 charge]
연결선은 짧고 상변화가 거의 없어 입구 상태(상류 노드 출구 P, h)로 균일 가정.
  V = π·(di/2)²·L
  단상(과냉액·과열증기): ρ = ρ(P, h) 직접
  2상(EEV→증발기 등):    void fraction(Premoli) → ρ_tp = α·ρ_v + (1−α)·ρ_l
  M = ρ × V

HX Semi의 holdup 계산(2상 void 적분 + 단상 ρ 직접)과 동일한 물성 경로를 쓴다.
"""

import math
import CoolProp.CoolProp as CP
from components.correlations import void_fraction as _vf


def pipe_charge(fluid, L_mm, di_mm, P_bar, h_kJ, m_dot=None, void_model=None):
    """단일 연결선(냉매배관)의 charge holdup [kg].

    Args:
        fluid:      냉매 (예: 'R290')
        L_mm:       배관 길이 [mm]  (연결선 lineParams.L)
        di_mm:      배관 내경 [mm]  (연결선 lineParams.di)
        P_bar:      배관 내 압력 [bar]      (상류 노드 출구 P_ref_out)
        h_kJ:       배관 내 비엔탈피 [kJ/kg] (상류 노드 출구 h_ref_out)
        m_dot:      냉매 질량유량 [kg/s] — 2상 void 계산에만 사용 (단상이면 무시)
        void_model: void fraction 모델명 (default Premoli)

    Returns:
        dict:
          M     [kg]      배관 charge holdup
          rho   [kg/m³]   대표 밀도 (단상=ρ(P,h), 2상=ρ_tp)
          V     [m³]      배관 내부 체적
          x     [-]       quality (단상이면 <0=액, >1=증기 마커)
          phase [str]     'liquid' / 'vapor' / 'two-phase'
    """
    P_Pa = P_bar * 1e5
    h_J = h_kJ * 1000.0
    di_m = di_mm / 1000.0
    L_m = L_mm / 1000.0
    V = math.pi * (di_m ** 2) / 4.0 * L_m  # 내부 체적 [m³]

    # 상 판정: 포화 엔탈피 비교 (HX Semi와 동일한 경로)
    h_l = CP.PropsSI('H', 'P', P_Pa, 'Q', 0, fluid)
    h_v = CP.PropsSI('H', 'P', P_Pa, 'Q', 1, fluid)

    if h_J <= h_l:            # 과냉액 (단상)
        rho = CP.PropsSI('D', 'P', P_Pa, 'H', h_J, fluid)
        x, phase = -1.0, 'liquid'
    elif h_J >= h_v:          # 과열증기 (단상)
        rho = CP.PropsSI('D', 'P', P_Pa, 'H', h_J, fluid)
        x, phase = 2.0, 'vapor'
    else:                     # 2상
        x = (h_J - h_l) / (h_v - h_l)
        vm = void_model or _vf.DEFAULT
        alpha = _vf.evaluate(vm, x=x, P_Pa=P_Pa,
                             m_dot=(m_dot if m_dot else 0.005),
                             D_i=di_m, fluid=fluid)
        rho = _vf.mean_density(alpha, P_Pa, fluid)
        phase = 'two-phase'

    M = rho * V
    return {'M': M, 'rho': rho, 'V': V, 'x': x, 'phase': phase}
