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
from components.correlations import pressure_drop as _pd

# 2상 마찰 ΔP 상관식 dispatch (HX와 동일 라인업)
_DP2PH = {
    'Friedel':             _pd.friedel_2phase,
    'MSH':                 _pd.msh_2phase,
    'Lockhart-Martinelli': _pd.lockhart_martinelli_2phase,
    'Chisholm':            _pd.chisholm_2phase,
}


def pipe_segment(fluid, L_mm, di_mm, P_bar, h_kJ, m_dot=None,
                 bends=0, K_bend=0.75, eps_over_D=0.0,
                 void_model=None, dp_corr_2ph='Friedel'):
    """연결선(냉매배관) 1구간: charge holdup + 압력강하.

    형상(L, di)으로 charge(체적 효과)와 ΔP(마찰+벤드)를 함께 산출한다.
    배관은 짧고 상변화가 거의 없어 입구 상태(상류 노드 출구 P, h)로 균일 가정.
    열손실·hydrostatic(액주)은 제외 — 수평·단열 가정 (HX와 동일 관례).

    Args:
        fluid:       냉매 (예: 'R290')
        L_mm:        배관 길이 [mm]  (연결선 lineParams.L)
        di_mm:       배관 내경 [mm]  (연결선 lineParams.di)
        P_bar:       배관 내 압력 [bar]      (상류 노드 출구 P_ref_out)
        h_kJ:        배관 내 비엔탈피 [kJ/kg] (상류 노드 출구 h_ref_out)
        m_dot:       냉매 질량유량 [kg/s] — ΔP 계산에 필수. None이면 ΔP=None (charge만).
        bends:       벤드 수 (연결선 lineParams.bends) — minor loss용
        K_bend:      벤드 1개 손실계수 (Idelchik, default 0.75)
        eps_over_D:  관 내면 조도/내경 (단상 마찰)
        void_model:  void fraction 모델명 (default Premoli)
        dp_corr_2ph: 2상 마찰 상관식 ('Friedel'/'MSH'/'Lockhart-Martinelli'/'Chisholm')

    Returns:
        dict:
          M           [kg]    배관 charge holdup
          rho         [kg/m³] 대표 밀도 (단상=ρ(P,h), 2상=ρ_tp)
          V           [m³]    배관 내부 체적
          x           [-]     quality (단상이면 <0=액, >1=증기 마커)
          phase       [str]   'liquid' / 'vapor' / 'two-phase'
          dP_friction [Pa]    관 마찰 압력강하 (m_dot 없으면 None)
          dP_bend     [Pa]    벤드 minor loss (m_dot 없으면 None)
          dP_total    [Pa]    합계 (m_dot 없으면 None)
          P_out       [bar]   하류 입구 압력 = P_bar − dP_total
    """
    P_Pa = P_bar * 1e5
    h_J = h_kJ * 1000.0
    di_m = di_mm / 1000.0
    L_m = L_mm / 1000.0
    A = math.pi * (di_m ** 2) / 4.0
    V = A * L_m  # 내부 체적 [m³]

    # ── 상 판정: 포화 엔탈피 비교 (HX Semi와 동일한 경로) ──
    h_l = CP.PropsSI('H', 'P', P_Pa, 'Q', 0, fluid)
    h_v = CP.PropsSI('H', 'P', P_Pa, 'Q', 1, fluid)

    if h_J <= h_l:            # 과냉액 (단상)
        rho = CP.PropsSI('D', 'P', P_Pa, 'H', h_J, fluid)
        T_K = CP.PropsSI('T', 'P', P_Pa, 'H', h_J, fluid)
        x, phase, is_liq = -1.0, 'liquid', True
    elif h_J >= h_v:          # 과열증기 (단상)
        rho = CP.PropsSI('D', 'P', P_Pa, 'H', h_J, fluid)
        T_K = CP.PropsSI('T', 'P', P_Pa, 'H', h_J, fluid)
        x, phase, is_liq = 2.0, 'vapor', False
    else:                     # 2상
        x = (h_J - h_l) / (h_v - h_l)
        vm = void_model or _vf.DEFAULT
        alpha = _vf.evaluate(vm, x=x, P_Pa=P_Pa,
                             m_dot=(m_dot if m_dot else 0.005),
                             D_i=di_m, fluid=fluid)
        rho = _vf.mean_density(alpha, P_Pa, fluid)
        T_K = CP.PropsSI('T', 'P', P_Pa, 'Q', 0.5, fluid)
        phase, is_liq = 'two-phase', False

    M = rho * V

    # ── 압력강하 (m_dot 주어질 때만) ──
    dP_friction = dP_bend = dP_total = None
    P_out = P_bar
    if m_dot:
        G = m_dot / A  # mass flux [kg/m²s]
        if phase == 'two-phase':
            dp_fn = _DP2PH.get(dp_corr_2ph, _pd.friedel_2phase)
            # 균일 가정: x_in = x_out = x → 가속항 0, 마찰만
            dP_friction = dp_fn(P_Pa, x, x, m_dot, di_m, L_m, fluid)
        else:
            dP_friction = _pd.single_phase_dp(P_Pa, T_K, m_dot, di_m, L_m,
                                              fluid, is_liquid=is_liq,
                                              eps_over_D=eps_over_D)
        # 벤드 minor loss: ΔP = N · K · ρv²/2 = N · K · G²/(2ρ)
        dP_bend = bends * K_bend * (G ** 2) / (2.0 * rho)
        dP_total = dP_friction + dP_bend
        P_out = P_bar - dP_total / 1e5

    return {'M': M, 'rho': rho, 'V': V, 'x': x, 'phase': phase,
            'dP_friction': dP_friction, 'dP_bend': dP_bend,
            'dP_total': dP_total, 'P_out': P_out}


# 하위호환: charge만 필요한 호출용 얇은 wrapper
def pipe_charge(fluid, L_mm, di_mm, P_bar, h_kJ, m_dot=None, void_model=None):
    """pipe_segment의 charge 부분만 반환 (하위호환 wrapper)."""
    return pipe_segment(fluid, L_mm, di_mm, P_bar, h_kJ,
                        m_dot=m_dot, void_model=void_model)
