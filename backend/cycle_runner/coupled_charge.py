"""coupled_charge — 완전 연성 정상해 (냉매 오일·어큐·충전량 + 공기 드럼루프).

기존 두 계층을 합친다.
  charge_closure.solve_forward : 오일·어큐·충전량 구속 (공기는 고정 BC)
  coupled_solver.solve         : 냉매 <-> 공기 교대 수렴 (오일·어큐·충전량 없음)

구조 (충전량 구속을 안쪽에 둔다)
  외부 루프: 공기 BC 교대 수렴 (drum -> filter -> evaporator -> condenser)
    내부   : solve_forward 로 충전량을 만족하는 냉매 정상해
    갱신   : air_loop.one_pass 로 새 HX 공기입구 산출, under-relaxation

  왜 충전량이 안쪽인가: 바깥에 두면 공기 반복마다 충전량이 흔들려 수렴이 어렵다.
  공기 BC 가 바뀔 때마다 냉매가 충전량을 다시 만족시키는 편이 안정적이다.

공기 순환 순서는 AIR_CORE = ['drum','filter','evaporator','condenser'].
팬은 fan_position 으로 임의 지점에 삽입한다(발열 위치가 성능에 영향).
"""
from .air_loop import one_pass as air_pass, AIR_CORE
from .charge_closure import solve_forward


def _rh_from_TW(T_C, W, P_atm=101325.0):
    """온도·습도비에서 상대습도 [%]"""
    from .air_loop import _rh_from_TW as f
    return f(T_C, W, P_atm)


def solve(ref_fidelity, air_fidelity, operating, air_inlet,
          M_charge, geom, oil_cfg=None, fan_position=None,
          params_override=None, air_states=None,
          max_outer=20, tol_air=0.05, alpha_air=0.6,
          dry_accumulator=True, verbose=False):
    """완전 연성 정상해.

    Args:
      ref_fidelity : {'compressor','condenser','eev','evaporator'} 각 1/2/3
      air_fidelity : {'drum','filter','fan','evaporator','condenser'}
      operating    : {'P_evap','P_cond','N','opening','h_suc','T_amb'} 초기추정
      air_inlet    : 드럼 입구 공기 {'T','RH','V_air_CMM'}
      M_charge     : 냉매 충전량 [kg]
      geom         : {'V_n1','V_n2','V_n3','V_acc','V_oil_cc','V_shell'}
      fan_position : 팬 삽입 위치 (0~4). None 이면 팬 없음.
      air_states   : 드럼 등 동적 상태 (동적해에서 스텝 간 전달용)

    Returns:
      dict: converged, outer_iter, refrigerant(solve_forward 결과), air, air_bc
    """
    # 초기 air_bc: 드럼 입구를 양 HX 에 동일 적용
    air_bc = {
        'condenser':  {'T_air_in': air_inlet['T'], 'RH_air_in': air_inlet.get('RH', 50.0),
                       'V_air_CMM': air_inlet['V_air_CMM']},
        'evaporator': {'T_air_in': air_inlet['T'], 'RH_air_in': air_inlet.get('RH', 50.0),
                       'V_air_CMM': air_inlet['V_air_CMM']},
    }
    op_ws = dict(operating)
    converged = False
    ref_res = None
    air_res = None
    hist = []

    for outer in range(max_outer):
        # ── 냉매: 충전량 구속 정상해 ──
        ref_res = solve_forward(ref_fidelity, op_ws, air_bc, M_charge, geom,
                                oil_cfg=oil_cfg, dry_accumulator=dry_accumulator)
        st = ref_res['state']

        # warm start: 수렴값을 다음 outer 초기추정으로
        op_ws = dict(op_ws)
        op_ws['P_evap'] = ref_res['P_evap']
        op_ws['P_cond'] = ref_res['P_cond']
        op_ws['h_suc']  = ref_res['h_suc']

        # ── 공기: 드럼 루프 1-pass ──
        hx_ref = {
            'evaporator': {'P_evap': ref_res['P_evap'],
                           'h_in':   st['eev']['h_out'] if 'eev' in st else None,
                           'm_dot_ref': st['compressor']['m_dot']},
            'condenser':  {'P_cond': ref_res['P_cond'],
                           'h_in':   st['compressor']['h_dis'],
                           'm_dot_ref': st['compressor']['m_dot']},
        }
        air_res = air_pass(air_fidelity, air_inlet, air_states or {}, hx_ref,
                           fan_position=fan_position,
                           params_override=params_override)

        # ── 새 공기 BC 추출 + under-relaxation ──
        # air_res['path'] 는 실행 순서, trajectory[i] 는 path[i] 직전 공기 상태.
        # HX 이름을 path 에서 찾아 그 앞 상태를 새 BC 로 쓴다.
        path = air_res['path']; traj = air_res['trajectory']
        new_bc = {}
        for comp in ('evaporator', 'condenser'):
            idx = path.index(comp) if comp in path else None
            if idx is None or idx >= len(traj):
                new_bc[comp] = dict(air_bc[comp])
            else:
                cin = traj[idx]
                new_bc[comp] = {
                    'T_air_in': cin['T'],
                    'RH_air_in': cin.get('RH') if cin.get('RH') is not None
                                 else _rh_from_TW(cin['T'], cin.get('W', 0.0)),
                    'V_air_CMM': air_bc[comp]['V_air_CMM']}

        dT_e = abs(new_bc['evaporator']['T_air_in'] - air_bc['evaporator']['T_air_in'])
        dT_c = abs(new_bc['condenser']['T_air_in'] - air_bc['condenser']['T_air_in'])
        hist.append({'outer': outer, 'dT_evap': dT_e, 'dT_cond': dT_c,
                     'Pc': ref_res['P_cond'], 'Pe': ref_res['P_evap'],
                     'ok': ref_res['success']})
        if verbose:
            print(f"  outer{outer}: dT_e={dT_e:.3f} dT_c={dT_c:.3f} "
                  f"Pc={ref_res['P_cond']:.4f} Pe={ref_res['P_evap']:.4f} ok={ref_res['success']}")

        if dT_e < tol_air and dT_c < tol_air:
            converged = True
            break

        for comp in ('evaporator', 'condenser'):
            for k in ('T_air_in', 'RH_air_in'):
                air_bc[comp][k] = ((1 - alpha_air) * air_bc[comp][k]
                                   + alpha_air * new_bc[comp][k])

    return {'converged': converged, 'outer_iter': outer + 1,
            'refrigerant': ref_res, 'air': air_res, 'air_bc': air_bc,
            'history': hist}
