"""charge_closure — 전체 시스템 냉매 충전량 수지.

배경 (2026-07-25, P1):
  기존 solver_forward 의 충전량 닫힘식은 HX 홀드업 합만 썼음
  (docstring: "배관·오일 용해 제외"). 그런데 실측해보니

    HX 홀드업          ~10 g
    배관+어큐          ~90 g  (어큐 200cc 가 전체 425cc 의 절반)
    오일 용해          21~85 g  (섬프 온도에 따라)

  오일 용해량이 전체 충전량(100 g)과 같은 자릿수라, 이걸 빼놓으면
  충전량 수지가 애초에 닫히지 않음. 즉 '이 시스템에 SH 해가 있는가'를
  판정할 수 없었음.

구성 요소:
  1) HX 홀드업      — 컴포넌트가 반환하는 M_holdup 사용
  2) 배관 홀드업     — charge_inventory.pipe_charge (Premoli void fraction)
  3) 어큐뮬레이터    — 엔탈피 중립 + 충전량 버퍼 (아래 참조)
  4) 오일 용해       — oil_solubility.dissolved_mass + 유효범위 가드

어큐뮬레이터 모델링 근거:
  정상상태에서 질량 ṁ_in=ṁ_out, 에너지 ṁ·h_in=ṁ·h_out → h_out=h_in.
  즉 어큐는 엔탈피 중립이고, 실제 역할은 '순환하지 않는 냉매의 저장소'임.
  액위는 충전량 수지가 결정하는 자유도이며, 물리적 한계는
    M_min = rho_v·V  (전부 증기)  ~  M_max = rho_l·V  (전부 액체)
  M_target 이 이 범위를 벗어나면 과충전/부족충전으로 판정한다.

  ※ 실물 어큐는 U-tube 하단 블리드홀로 액+오일을 계량 회수하므로 액이
    있어도 정상상태가 성립한다. 블리드 특성을 모델링하지 않는 대신
    액위를 충전량으로부터 역산하는 방식(정상 사이클 해석의 표준 가정).
"""

import math

import CoolProp.CoolProp as CP

from .oil_solubility import (OIL_5GSD, dissolved_mass, oil_mass_from_volume,
                             oil_sump_temperature, solubility)

FLUID = 'R290'


# ─── 오일 용해 유효범위 가드 ────────────────────────────────────────
def oil_validity(P_bar, T_oil_C, oil=OIL_5GSD):
    """오일 용해 상관식의 유효범위 점검.

    raoult_fit 은 P = gamma(T,x1)*x1*P1s 를 x1 에 대해 푸는데,
    P_bar 가 그 온도의 R290 포화압 P1s 에 근접/초과하면 x1 이 1 로 몰려
    w/(1-w) 가 발산한다 (실측: P=26bar, 섬프 31.7C 에서 2114 g — 총
    충전량의 21배로 명백한 파탄).

    물리적으로 P >= P1s 는 섬프에서 냉매가 응축하는 조건이라 '오일에 녹은
    냉매'가 아니라 '냉매 액에 녹은 오일'이 되어 상관식의 전제가 깨진다.

    Returns: dict(P_sat_bar, P_ratio, x1, w, valid, reason)
    """
    T = T_oil_C + 273.15
    Tcrit = CP.PropsSI('Tcrit', FLUID)
    if T >= Tcrit:
        return {'P_sat_bar': None, 'P_ratio': None, 'x1': 0.0, 'w': 0.0,
                'valid': True, 'reason': '초임계 — 용해 없음'}
    P1s = CP.PropsSI('P', 'T', T, 'Q', 1, FLUID) / 1e5
    ratio = P_bar / P1s
    w = solubility(P_bar, T_oil_C, 'raoult_fit', oil)
    x1 = w / oil['M_molar'] / (w / oil['M_molar'] + (1 - w) / 44.1) if w < 1 else 1.0

    valid, reason = True, 'ok'
    if ratio >= 1.0:
        valid, reason = False, f'섬프 압력이 포화압 초과 (P/Psat={ratio:.3f}) — 상관식 전제 파탄'
    elif ratio > 0.92:
        valid, reason = False, f'포화선 근접 (P/Psat={ratio:.3f}) — x1 발산 영역'
    elif w > 0.60:
        valid, reason = False, f'질량분율 {w*100:.1f}% — Wang 2020 회귀 범위 밖 추정'
    return {'P_sat_bar': P1s, 'P_ratio': ratio, 'x1': x1, 'w': w,
            'valid': valid, 'reason': reason}


def oil_charge(M_oil_kg, P_bar, T_oil_C, oil=OIL_5GSD, strict=True):
    """오일 용해 냉매 [kg] + 유효성. strict=True 면 범위 밖일 때 예외."""
    v = oil_validity(P_bar, T_oil_C, oil)
    if not v['valid']:
        if strict:
            raise ValueError(f"오일 용해 상관식 유효범위 밖: {v['reason']} "
                             f"(P={P_bar:.2f}bar, T_oil={T_oil_C:.1f}C)")
        return None, v
    return dissolved_mass(M_oil_kg, P_bar, T_oil_C, 'raoult_fit', oil), v


# ─── 어큐뮬레이터 ──────────────────────────────────────────────────
def accumulator_limits(P_bar, V_m3):
    """어큐가 담을 수 있는 냉매 질량 범위 [kg]. (전부 증기 ~ 전부 액체)"""
    P = P_bar * 1e5
    rho_v = CP.PropsSI('D', 'P', P, 'Q', 1, FLUID)
    rho_l = CP.PropsSI('D', 'P', P, 'Q', 0, FLUID)
    return rho_v * V_m3, rho_l * V_m3, rho_v, rho_l


def accumulator_state(P_bar, V_m3, M_acc_kg):
    """어큐 액위/상태. M_acc 가 범위 밖이면 flag."""
    M_min, M_max, rho_v, rho_l = accumulator_limits(P_bar, V_m3)
    rho = M_acc_kg / V_m3
    out = {'M_min': M_min, 'M_max': M_max, 'rho': rho,
           'rho_v': rho_v, 'rho_l': rho_l}
    if M_acc_kg < M_min:
        out.update(status='undercharge', liquid_frac=0.0, x=1.0)
    elif M_acc_kg > M_max:
        out.update(status='overcharge', liquid_frac=1.0, x=0.0)
    else:
        alpha_l = (rho - rho_v) / (rho_l - rho_v)
        x = (1.0 / rho - 1.0 / rho_l) / (1.0 / rho_v - 1.0 / rho_l)
        out.update(status='ok', liquid_frac=alpha_l, x=x)
    return out


# ─── 배관 ──────────────────────────────────────────────────────────
def pipe_mass(P_bar, h_kJ, V_m3, m_dot=None):
    """배관 구간 냉매 질량 [kg]. 2상이면 Premoli void fraction 사용."""
    from charge_inventory import pipe_segment
    # pipe_segment 은 (L_mm, di_mm) 를 받으므로 등가 치수로 환산
    di_mm = 4.6
    A = math.pi * (di_mm * 1e-3 / 2.0) ** 2
    L_mm = V_m3 / A * 1e3
    r = pipe_segment(FLUID, L_mm, di_mm, P_bar, h_kJ, m_dot=m_dot)
    return r['M'] if isinstance(r, dict) and 'M' in r else r


# ─── 전체 수지 ─────────────────────────────────────────────────────
def system_charge(state, geom, oil_cfg=None, strict_oil=True):
    """운전점 state 에서 시스템 총 냉매량 [kg] 과 내역.

    Args:
      state: {'P_evap','P_cond' [bar], 'h_dis','h_cond_out','h_eev_out',
              'h_evap_out' [kJ/kg], 'T_dis' [C], 'M_hx' [kg], 'm_dot'}
      geom:  {'V_n1','V_n2','V_n3','V_acc' [m3], 'V_oil_cc'}
      oil_cfg: {'shell':'high'|'low', 'dT_sump':15.0}
    """
    oil_cfg = oil_cfg or {}
    shell = oil_cfg.get('shell', 'high')
    dT = oil_cfg.get('dT_sump', 15.0)

    Pe, Pc = state['P_evap'], state['P_cond']
    parts = {}
    parts['HX'] = state.get('M_hx', 0.0)
    parts['pipe_n1'] = pipe_mass(Pc, state['h_dis'], geom['V_n1'], state.get('m_dot'))
    parts['pipe_n2'] = pipe_mass(Pc, state['h_cond_out'], geom['V_n2'], state.get('m_dot'))
    parts['pipe_n3'] = pipe_mass(Pe, state['h_eev_out'], geom['V_n3'], state.get('m_dot'))

    # 오일 — 고압쉘이면 섬프가 토출압
    M_oil = oil_mass_from_volume(geom.get('V_oil_cc', 160.0))
    P_sump = Pc if shell == 'high' else Pe
    T_sump = oil_sump_temperature(state['T_dis'], dT)
    m_oil, oil_info = oil_charge(M_oil, P_sump, T_sump, strict=strict_oil)
    parts['oil'] = m_oil
    parts['_oil_info'] = oil_info
    parts['_M_oil'] = M_oil
    parts['_T_sump'] = T_sump
    parts['_P_sump'] = P_sump

    fixed = sum(v for k, v in parts.items()
                if not k.startswith('_') and k != 'oil' and v is not None)
    if m_oil is not None:
        fixed += m_oil
    parts['_fixed_total'] = fixed

    M_min, M_max, _, _ = accumulator_limits(Pe, geom['V_acc'])
    parts['_acc_range'] = (fixed + M_min, fixed + M_max)
    return parts


def charge_residual(state, geom, M_charge, oil_cfg=None, strict_oil=True):
    """M_charge 와 양립하는지. 어큐가 흡수해야 할 양과 그 가능 여부."""
    p = system_charge(state, geom, oil_cfg, strict_oil)
    need = M_charge - p['_fixed_total']
    acc = accumulator_state(state['P_evap'], geom['V_acc'], need) if need > 0 else \
        {'status': 'undercharge', 'liquid_frac': 0.0}
    lo, hi = p['_acc_range']
    return {'parts': p, 'M_acc_need': need, 'acc': acc,
            'compatible': lo <= M_charge <= hi, 'range': (lo, hi)}
