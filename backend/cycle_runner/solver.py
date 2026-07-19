"""
solver.py — 냉매 사이클 수렴 solver (fixed-point)

refrigerant_loop.one_pass를 반복 호출해 사이클 상태점을 수렴.

미지수 3개 → 조건 3개:
  P_evap  ← 증발기 과열도 SH를 목표값에 맞춤
  P_cond  ← 질량 보존 (압축기 m_dot = EEV m_dot)
  h_suc   ← 증발기 출구 h (순환 닫힘, 직접 대입 + under-relaxation)

안정화: under-relaxation(h_suc), 작은 게인(P), 압력 클램프.
(직접 동시 흔들면 압력이 음수로 발산 → CoolProp 실패. 완화 필수.)

검증: 12칸 BC(P_evap=5.09, P_cond=9.88)를 정답으로 재현.
"""

from .refrigerant_loop import one_pass


def solve(fidelity, operating, air_bc, SH_target=None,
          params_override=None, max_iter=100, tol_mass=1e-6,
          tol_enthalpy=0.5, tol_SH=0.05,
          alpha_h=0.5, gain_pcond=200.0, gain_pevap=0.01,
          P_evap_bounds=(3.0, 8.0), P_cond_bounds=(6.0, 20.0),
          verbose=False):
    """냉매 사이클 수렴.

    Args:
      fidelity: {'compressor','condenser','eev','evaporator'} 각 1/2/3
      operating: 초기 {'P_evap','P_cond','N','opening','h_suc','T_amb'}
      air_bc: {'condenser':{...}, 'evaporator':{...}}
      SH_target: 목표 과열도 [K]. None이면 초기 1-pass의 SH 사용.

    Returns:
      dict: {'converged','iterations','P_evap','P_cond','h_suc','state'(마지막 one_pass)}
    """
    P_evap = operating['P_evap']
    P_cond = operating['P_cond']
    h_suc = operating['h_suc']
    N = operating['N']
    opening = operating['opening']
    T_amb = operating.get('T_amb', 35.0)

    def _op(pe, pc, hs):
        return {'P_evap': pe, 'P_cond': pc, 'N': N,
                'opening': opening, 'h_suc': hs, 'T_amb': T_amb}

    # SH_target 미지정 시 초기 1-pass에서 결정
    if SH_target is None:
        r0 = one_pass(fidelity, _op(P_evap, P_cond, h_suc), air_bc, params_override)
        SH_target = r0['SH_evap']

    converged = False
    it = 0
    r = None
    # 적응적 게인: 잔차가 느리게 줄면 게인 증가 (조합 무관 수렴)
    gp_evap = gain_pevap
    prev_rSH = None
    for it in range(max_iter):
        r = one_pass(fidelity, _op(P_evap, P_cond, h_suc), air_bc, params_override)
        rm = r['residual']['mass']
        re = r['residual']['enthalpy']
        rSH = r['SH_evap'] - SH_target

        if abs(rm) < tol_mass and abs(re) < tol_enthalpy and abs(rSH) < tol_SH:
            converged = True
            break

        # 적응적 게인: SH 잔차가 같은 부호로 느리게 줄면 게인 증가
        if prev_rSH is not None and abs(rSH) > 0.7 * abs(prev_rSH) and rSH * prev_rSH > 0:
            gp_evap = min(gp_evap * 1.3, 0.1)   # 상한 0.1 (안정성)
        prev_rSH = rSH

        # 갱신 (완화 + 클램프)
        h_suc = h_suc + alpha_h * (r['h_evap_out'] - h_suc)
        P_cond = min(P_cond_bounds[1], max(P_cond_bounds[0], P_cond + rm * gain_pcond))
        P_evap = min(P_evap_bounds[1], max(P_evap_bounds[0], P_evap + rSH * gp_evap))

        if verbose and it % 10 == 0:
            print(f"  it{it}: P_evap={P_evap:.4f} P_cond={P_cond:.4f} "
                  f"질량={rm:+.6f} 엔탈피={re:+.2f} SH잔차={rSH:+.3f} gp={gp_evap:.4f}")

    return {
        'converged': converged, 'iterations': it + 1,
        'P_evap': P_evap, 'P_cond': P_cond, 'h_suc': h_suc,
        'SH_target': SH_target, 'state': r,
    }


if __name__ == '__main__':
    air = {'condenser': {'T_air_in': 14.474, 'RH_air_in': 99.0, 'V_air_CMM': 2.42},
           'evaporator': {'T_air_in': 20.0, 'RH_air_in': 80.0, 'V_air_CMM': 2.42}}
    op = {'P_evap': 5.0889, 'P_cond': 9.8762, 'N': 1800,
          'opening': 23.586, 'h_suc': 587.309, 'T_amb': 35.0}

    for label, fid in [('전부 L1', {'compressor': 1, 'condenser': 1, 'eev': 1, 'evaporator': 1}),
                       ('전부 L3', {'compressor': 3, 'condenser': 3, 'eev': 3, 'evaporator': 3})]:
        res = solve(fid, op, air)
        s = res['state']
        print(f"\n═══ {label} ═══")
        print(f"  수렴: {res['converged']} ({res['iterations']}회)")
        print(f"  P_evap={res['P_evap']:.4f} (BC 5.0889), P_cond={res['P_cond']:.4f} (BC 9.8762)")
        print(f"  m_dot={s['m_dot']:.6f}, Q_cond={s['Q_cond']:.1f}, Q_evap={s['Q_evap']:.1f}, SH={s['SH_evap']:.2f}")
