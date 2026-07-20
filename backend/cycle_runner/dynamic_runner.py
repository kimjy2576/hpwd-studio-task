"""
dynamic_runner.py — 동적 시뮬레이션 (콜드스타트 + 건조 과정)

하이브리드 방식:
  · 냉매측: 빠른 동역학 → 매 스텝 준정적 수렴 (coupled_solver 재사용)
  · drum: 느린 동역학 → 오일러 시간적분 (건조 진행, m_w/T_cl 상태)
  · 압축기 N ramp가 기동 구동 (정지 N=0 → 목표 rpm)

근거 (OMC 대비 Python 콜드스타트 이점):
  OMC DAE는 t=0 초기 연립(폐루프 순환의존)이 발산 → 초기화 난제.
  Python은 초기상태 지정(P_equalize, T_amb, N=0) 후 시간전진 → 연립 불필요.
  압력 분리 과도는 강성이 심해 준정적 근사; 건조(느린)는 시간적분으로 정확.

궤적 산출: 시간별 P_evap, P_cond, m_dot, Q, 건조율 X, SMER 등.
"""

from .coupled_solver import solve as coupled_solve


def n_ramp(t, N_target, ramp_time):
    """압축기 rpm ramp: 0 → N_target (ramp_time 동안 선형)."""
    if t <= 0:
        return 0.0
    if t >= ramp_time:
        return N_target
    return N_target * t / ramp_time


def run(ref_fidelity, air_fidelity, operating, air_inlet,
        fan_position=None, params_override=None,
        t_end=1800.0, dt=60.0, N_target=1800.0, ramp_time=120.0,
        P_equalize=7.0, verbose=False):
    """콜드스타트 동적 시뮬레이션.

    Args:
      ref_fidelity/air_fidelity: 컴포넌트 fidelity
      operating: {'opening','h_suc','T_amb'} (N은 ramp로 대체)
      air_inlet: 드럼 입구 공기
      t_end: 총 시뮬 시간 [s]
      dt: 시간 스텝 [s] (건조는 느려 큰 dt 가능)
      N_target: 목표 압축기 rpm
      ramp_time: N ramp 시간 [s]
      P_equalize: 초기 균일압력 [bar]

    Returns:
      dict: {'trajectory': [시간별 상태], 'converged_steps', 'total_steps'}
    """
    # ── 초기 상태 (지정, 연립 불필요) ──
    # 냉매: 물리적으로 정지 시 균일압력이나, solver는 분리된 압력서 시작해야
    # 수렴 (균일압력=압축비1에서 solver 발산). warm-start 전략:
    #   solver에 넘기는 초기추정 P는 분리값(정상 운전점 근처)으로 두되,
    #   실제 기동 과도(압력 분리)는 N ramp가 표현. 균일→분리는 물리적으로
    #   수 초 내 완료되므로 dt(수십초) 스케일에선 이미 분리 상태로 근사.
    drum_state = None
    # solver 초기추정 압력 (분리값 — 수렴 영역 보장)
    P_evap = 5.0889
    P_cond = 9.8762
    h_suc = operating.get('h_suc', 587.309)
    opening = operating.get('opening', 23.586)
    T_amb = operating.get('T_amb', 35.0)

    trajectory = []
    converged_steps = 0
    n_steps = int(t_end / dt) + 1

    # drum 동적 상태를 스텝 간 유지 (건조 진행)
    persistent_drum = None

    for step in range(n_steps):
        t = step * dt
        N = n_ramp(t, N_target, ramp_time)

        if N < 1.0:
            # 정지 (N≈0): 압력 균일, m_dot≈0, 건조 없음
            trajectory.append({
                't': t, 'N': N, 'P_evap': P_evap, 'P_cond': P_cond,
                'm_dot': 0.0, 'Q_cond': 0.0, 'Q_evap': 0.0,
                'X_dry': None, 'phase': 'stopped',
            })
            continue

        # ── 냉매-공기 연성 준정적 수렴 (현재 N) ──
        # drum 상태를 스텝 간 전달 (건조 진행). 연성 내부 drum은 dt로 갱신되나
        # 준정적 근사상 스텝당 최종 newState만 채택 (연성 반복은 냉매-공기 정합용).
        op = {'P_evap': P_evap, 'P_cond': P_cond, 'N': N,
              'opening': opening, 'h_suc': h_suc, 'T_amb': T_amb}
        air_st = {'drum': persistent_drum} if persistent_drum else {}
        try:
            cr = coupled_solve(ref_fidelity, air_fidelity, op, air_inlet,
                               fan_position=fan_position,
                               params_override=params_override,
                               air_states=air_st, max_outer=20)
        except Exception as e:
            trajectory.append({'t': t, 'N': N, 'phase': 'error', 'error': str(e)[:60]})
            continue

        rf = cr['refrigerant']
        s = rf['state']
        if rf['converged']:
            converged_steps += 1
        # 다음 스텝 초기추정 = 현재 수렴값 (warm start, 수렴 가속)
        P_evap = rf['P_evap']
        P_cond = rf['P_cond']
        h_suc = rf['h_suc']

        # drum 건조 상태 (연성 air 결과에서)
        drum_out = cr['air']['results'].get('drum', {})
        X_dry = drum_out.get('X')
        persistent_drum = cr['air']['new_states'].get('drum', persistent_drum)

        trajectory.append({
            't': t, 'N': N, 'P_evap': P_evap, 'P_cond': P_cond,
            'm_dot': s['m_dot'], 'Q_cond': s['Q_cond'], 'Q_evap': s['Q_evap'],
            'SH_evap': s['SH_evap'], 'X_dry': X_dry,
            'outer_iter': cr['outer_iter'], 'ref_converged': rf['converged'],
            'phase': 'ramp' if t < ramp_time else 'running',
        })

        if verbose and step % max(1, n_steps // 10) == 0:
            print(f"  t={t:.0f}s N={N:.0f} P_evap={P_evap:.3f} P_cond={P_cond:.3f} "
                  f"m_dot={s['m_dot']:.6f} Q_cond={s['Q_cond']:.1f} phase={trajectory[-1]['phase']}")

    return {
        'trajectory': trajectory,
        'converged_steps': converged_steps,
        'total_steps': n_steps,
    }


if __name__ == '__main__':
    ref_fid = {'compressor': 1, 'condenser': 1, 'eev': 1, 'evaporator': 1}
    air_fid = {'drum': 1, 'filter': 1, 'fan': 3, 'evaporator': 1, 'condenser': 1}
    op = {'opening': 23.586, 'h_suc': 587.309, 'T_amb': 35.0}
    air_in = {'T': 30.0, 'RH': 40.0, 'W': 0.0107, 'V_air_CMM': 2.42, 'm_dot_air': 0.048}

    # 짧은 시뮬 (콜드스타트 초반 + 몇 스텝). ramp 짧게 (저속 미수렴 구간 빨리 통과)
    print("콜드스타트 동적 (t_end=300s, dt=60s, ramp=60s):")
    r = run(ref_fid, air_fid, op, air_in, t_end=300.0, dt=60.0,
            N_target=1800.0, ramp_time=60.0, verbose=True)
    print(f"\n수렴 스텝: {r['converged_steps']}/{r['total_steps']}")
    print("\n시간별 궤적:")
    for pt in r['trajectory']:
        if pt['phase'] == 'stopped':
            print(f"  t={pt['t']:.0f}s N={pt['N']:.0f} [정지] P={pt['P_evap']:.1f}bar")
        elif pt['phase'] in ('ramp', 'running'):
            cv = '✓' if pt.get('ref_converged') else '~'
            print(f"  t={pt['t']:.0f}s N={pt['N']:.0f} P_evap={pt['P_evap']:.3f} "
                  f"P_cond={pt['P_cond']:.3f} m_dot={pt['m_dot']:.6f} "
                  f"Q_cond={pt['Q_cond']:.1f} [{pt['phase']}{cv}]")
