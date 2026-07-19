"""
refrigerant_loop.py — 냉매 사이클 1-pass 배관 (수렴 전 단계)

고정 위상: 압축기 → 응축기 → EEV → 증발기 → (압축기)
registry로 각 컴포넌트를 fidelity별 조회해 순서대로 연결.

1단계 (a): 수렴 없이 1-pass만. 주어진 (P_evap, P_cond, N, opening, h_suc)로
컴포넌트를 한 바퀴 돌려 배관 닫힘 잔차를 반환. 수렴 루프는 (b)에서 추가.

배관 매핑 (검증됨):
  압축기.h_dis   → 응축기.h_in
  압축기.m_dot   → 응축기/증발기.m_dot_ref
  응축기.h_ref_out → EEV.h_in ;  P_cond → EEV.P_in
  EEV.h_out      → 증발기.h_in
  증발기.h_ref_out → 압축기.h_suc  (닫힘 조건)

단위: P는 bar, h는 kJ/kg (컴포넌트가 그대로 받음).
"""

from .registry import get_component, default_params


def one_pass(fidelity, operating, air_bc, params_override=None):
    """냉매 사이클 1-pass.

    Args:
      fidelity: {'compressor':1/2/3, 'condenser':.., 'eev':.., 'evaporator':..}
      operating: {'P_evap','P_cond','N','opening','h_suc','T_amb'} (bar, kJ/kg, rpm, %)
      air_bc: {'condenser':{T_air_in,RH_air_in,V_air_CMM}, 'evaporator':{...}}
      params_override: 컴포넌트별 추가 params (선택)

    Returns:
      dict: 각 컴포넌트 결과 + 닫힘 잔차
    """
    po = params_override or {}

    def _params(comp):
        p = default_params(comp, fidelity[comp])
        p.update(po.get(comp, {}))
        return p

    P_evap = operating['P_evap']
    P_cond = operating['P_cond']
    N = operating['N']
    opening = operating['opening']
    h_suc = operating['h_suc']
    T_amb = operating.get('T_amb', 35.0)

    # ── 1. 압축기 (P_suc=P_evap, P_dis=P_cond, h_suc) ──
    comp_mod = get_component('refrigerant', 'compressor', fidelity['compressor'])
    r_comp = comp_mod.step(
        {'P_suc': P_evap, 'P_dis': P_cond, 'h_suc': h_suc, 'N': N, 'T_amb': T_amb},
        _params('compressor'), {}, 0)['outputs']
    m_dot = r_comp['m_dot']
    h_dis = r_comp['h_dis']

    # ── 2. 응축기 (P_cond, h_dis, m_dot, 공기) ──
    cond_mod = get_component('refrigerant', 'condenser', fidelity['condenser'])
    r_cond = cond_mod.step(
        {'P_cond': P_cond, 'h_in': h_dis, 'm_dot_ref': m_dot, **air_bc['condenser']},
        _params('condenser'), {}, 0)['outputs']
    h_cond_out = r_cond['h_ref_out']

    # ── 3. EEV (P_cond, h_cond_out, P_evap, opening) ──
    eev_mod = get_component('refrigerant', 'eev', fidelity['eev'])
    r_eev = eev_mod.step(
        {'P_in': P_cond, 'h_in': h_cond_out, 'P_out': P_evap, 'opening': opening},
        _params('eev'), {}, 0)['outputs']
    m_eev = r_eev['m_dot_ref']
    h_eev_out = r_eev['h_out']

    # ── 4. 증발기 (P_evap, h_eev_out, m_dot, 공기) ──
    evap_mod = get_component('refrigerant', 'evaporator', fidelity['evaporator'])
    r_evap = evap_mod.step(
        {'P_evap': P_evap, 'h_in': h_eev_out, 'm_dot_ref': m_dot, **air_bc['evaporator']},
        _params('evaporator'), {}, 0)['outputs']
    h_evap_out = r_evap['h_ref_out']

    # ── 닫힘 잔차 ──
    resid_enthalpy = h_evap_out - h_suc      # 증발기 출구 = 압축기 입구 (순환)
    resid_mass = m_dot - m_eev               # 압축기 = EEV (질량 보존)

    return {
        'compressor': r_comp, 'condenser': r_cond, 'eev': r_eev, 'evaporator': r_evap,
        'm_dot': m_dot, 'm_eev': m_eev,
        'h_dis': h_dis, 'h_cond_out': h_cond_out, 'h_eev_out': h_eev_out,
        'h_evap_out': h_evap_out,
        'residual': {'enthalpy': resid_enthalpy, 'mass': resid_mass},
        'Q_cond': r_cond['Q_total'], 'Q_evap': r_evap['Q_total'],
        'SH_evap': r_evap['SH_out'],
    }


if __name__ == '__main__':
    # 12칸 검증 BC로 1-pass 실행 (배관 닫힘 sanity)
    fid = {'compressor': 3, 'condenser': 3, 'eev': 3, 'evaporator': 3}
    op = {'P_evap': 5.0889, 'P_cond': 9.8762, 'N': 1800,
          'opening': 23.586, 'h_suc': 587.309, 'T_amb': 35.0}
    air = {'condenser': {'T_air_in': 14.474, 'RH_air_in': 99.0, 'V_air_CMM': 2.42},
           'evaporator': {'T_air_in': 20.0, 'RH_air_in': 80.0, 'V_air_CMM': 2.42}}
    r = one_pass(fid, op, air)
    print(f"압축기: m_dot={r['m_dot']:.6f} h_dis={r['h_dis']:.1f}")
    print(f"응축기: h_out={r['h_cond_out']:.1f} Q={r['Q_cond']:.1f}")
    print(f"EEV:    m_dot={r['m_eev']:.6f} h_out={r['h_eev_out']:.1f}")
    print(f"증발기: h_out={r['h_evap_out']:.1f} Q={r['Q_evap']:.1f} SH={r['SH_evap']:.1f}")
    print(f"닫힘 잔차: 엔탈피={r['residual']['enthalpy']:+.1f} kJ/kg, "
          f"질량={r['residual']['mass']:+.6f}")
