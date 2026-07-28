"""dynamic_charge — 완전 연성 동적해 (충전량 구속 + SH 제어 + 드럼 건조).

기존 dynamic_runner 는 coupled_solver(오일·어큐·충전량 없음)를 썼다.
이 모듈은 coupled_charge 를 써서 매 시간 스텝마다
  오일 용해 + 어큐 + 충전량 보존 + SH 제어
를 만족하는 준정적 해를 구하고, 드럼 건조만 시간적분한다.

기동 구간 처리 (방침 A)
  저rpm 에는 충전량 구속을 만족하는 정상해가 존재하지 않는다
  (실측: N=500 에서 Pe 가 하한 2.0bar 에 고착, SH 45.5, ok=False).
  따라서 N < N_charge_min 구간은 coupled_solver(충전량 없음)로 통과시키고,
  정상 rpm 도달 후 coupled_charge 로 전환한다.

warm start
  이전 스텝의 (P_evap, P_cond, h_suc, opening) 과 공기 BC 를 이월한다.
  정상해 1점이 32초이나 warm start 로 outer 반복이 2~3회로 줄어든다.
"""
from .coupled_solver import solve as coupled_solve
from .coupled_charge import solve as charge_solve


def n_ramp(t, N_target, ramp_time):
    """압축기 rpm ramp: 0 -> N_target (ramp_time 동안 선형)."""
    if t <= 0:
        return 0.0
    if t >= ramp_time:
        return N_target
    return N_target * t / ramp_time


def run(ref_fidelity, air_fidelity, operating, air_inlet,
        M_charge, geom, oil_cfg=None, fan_position=None,
        SH_target=None, t_end=1800.0, dt=60.0,
        N_target=1800.0, ramp_time=120.0, N_charge_min=1200.0,
        max_outer=6, method='hybr', verbose=False):
    """완전 연성 동적 해석.

    Returns:
      dict: trajectory, converged_steps, total_steps, phase_switch_t
    """
    traj = []
    persistent_drum = None
    op_ws = dict(operating)
    conv = 0
    switch_t = None
    n_steps = int(t_end / dt) + 1

    for k in range(n_steps):
        t = k * dt
        N = n_ramp(t, N_target, ramp_time)
        if N <= 0.0:
            traj.append({'t': t, 'N': 0.0, 'phase': 'stopped'})
            continue

        op_ws['N'] = N
        air_st = {'drum': persistent_drum} if persistent_drum else {}
        use_charge = (N >= N_charge_min)
        if use_charge and switch_t is None:
            switch_t = t

        try:
            if use_charge:
                r = charge_solve(ref_fidelity, air_fidelity, op_ws, air_inlet,
                                 M_charge, geom, oil_cfg=oil_cfg,
                                 fan_position=fan_position, SH_target=SH_target,
                                 air_states=air_st, dt=dt, max_outer=max_outer,
                                 # warm start 가 있으면 공기 BC 가 이미 가까우므로
                                 # SH 구속을 일찍 켠다. sh_warmup 기본 3 은
                                 # max_outer=6 에서 SH 반복을 3회로 제한해
                                 # t>=180 부터 SH 가 0 으로 밀렸다.
                                 # sh_warmup: warm start 가 있어도 첫 회부터 SH 를
                                 # 걸면 개도가 상한(100%)에 붙는다(실측 t=120 발산).
                                 # 공기 BC 를 1회 안정시킨 뒤 켜는 것이 안전하다.
                                 method=method,
                                 sh_warmup=(1 if k > 0 else 3))
                rr = r['refrigerant']
                rec = {'t': t, 'N': N, 'phase': 'charge',
                       'Pc': rr['P_cond'], 'Pe': rr['P_evap'],
                       'SH': rr['SH_evap'], 'opening': rr.get('opening'),
                       'ok': bool(rr['success']), 'outer': r['outer_iter']}
                op_ws['P_evap'] = rr['P_evap']
                op_ws['P_cond'] = rr['P_cond']
                op_ws['h_suc'] = rr['h_suc']
                if rr.get('opening') is not None:
                    op_ws['opening'] = rr['opening']
                air_res = r.get('air')
            else:
                # 기동 구간은 SH 구속을 끈다.
                #   저rpm 에서는 개도를 최대로 열어도 SH 목표를 만들 수 없어
                #   흡입이 포화선에 붙고 CoolProp (P,T) flash 가 실패한다
                #   (실측 N=900: Psat[794000Pa] 가 T[291.186K] 와 일치).
                #   SH 없이 풀면 정상 수렴한다 (Pe 6.09, Pc 10.03).
                r = coupled_solve(ref_fidelity, air_fidelity, op_ws, air_inlet,
                                  fan_position=fan_position, air_states=air_st,
                                  SH_target=None, max_outer=max_outer)
                s = r['refrigerant']
                rec = {'t': t, 'N': N, 'phase': 'startup',
                       'Pc': s.get('P_cond'), 'Pe': s.get('P_evap'),
                       'SH': s.get('SH_evap'), 'ok': bool(r['converged']),
                       'outer': r['outer_iter']}
                for kk in ('P_evap', 'P_cond', 'h_suc'):
                    if s.get(kk) is not None:
                        op_ws[kk] = s[kk]
                air_res = r.get('air')

            # 드럼 상태 이월 (건조 진행)
            if air_res and air_res.get('new_states'):
                persistent_drum = air_res['new_states'].get('drum', persistent_drum)
            dr = air_res['results'].get('drum') if (air_res and air_res.get('results')) else None
            if dr:
                rec['X_dry'] = dr.get('X') or dr.get('X_dry')
                rec['m_w'] = dr.get('m_w')
            if rec.get('ok'):
                conv += 1
        except Exception as e:
            rec = {'t': t, 'N': N, 'phase': 'error', 'error': str(e)[:80]}

        traj.append(rec)
        if verbose:
            print(f"  t={t:6.0f} N={N:6.0f} {rec.get('phase')} "
                  f"Pc={rec.get('Pc')} Pe={rec.get('Pe')} X={rec.get('X_dry')}")

    return {'trajectory': traj, 'converged_steps': conv,
            'total_steps': n_steps, 'phase_switch_t': switch_t}
