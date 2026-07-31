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
from .cancel import Cancelled
from .air_loop import one_pass as air_pass, AIR_CORE
from .charge_closure import solve_forward


def _rh_from_TW(T_C, W, P_atm=101325.0):
    """온도·습도비에서 상대습도 [%]"""
    from .air_loop import _rh_from_TW as f
    return f(T_C, W, P_atm)


def _try_solve(fid, op, air_bc, M_charge, geom, oil_cfg, sh, x0, xtol, dry_acc,
               use_broyden=False):
    """broyden1 우선, 실패 시 hybr 재시도.

    broyden1 은 야코비안을 재사용해 warm start 에서 5.6배 빠르나
    범위 밖으로 벗어나면 CoolProp 예외가 난다. 그때는 견고한 hybr 로 되돌린다.
    """
    # 2026-07-27: broyden1 은 지금 조건에서 거의 매번 실패해
    #   hybr 재시도로 이어져 같은 문제를 두 번 푼다(실측: 전체 59.8s 중
    #   solve_forward 12.1s 외 47.1s 가 실패한 broyden1 에 소모).
    #   use_broyden 로 명시적으로 켤 때만 시도한다.
    if x0 is not None and use_broyden:
        try:
            r = solve_forward(fid, op, air_bc, M_charge, geom, oil_cfg=oil_cfg,
                              SH_target=sh, x0=x0, xtol=xtol,
                              method='broyden1', dry_accumulator=dry_acc)
            if r['success']:
                return r
        except Exception:
            pass
    return solve_forward(fid, op, air_bc, M_charge, geom, oil_cfg=oil_cfg,
                         SH_target=sh, x0=x0, xtol=xtol,
                         method='hybr', dry_accumulator=dry_acc)


def solve(ref_fidelity, air_fidelity, operating, air_inlet,
          M_charge, geom, oil_cfg=None, SH_target=None, fan_position=None,
          params_override=None, air_states=None,
          sh_warmup=3, sh_air_tol=1.0, dt=1.0, method='hybr',
          on_progress=None,   # 2026-07-30: outer 마다 호출 (실시간 진행 표시용)
          max_outer=20, tol_air=0.05,
          # 2026-07-31: alpha_air 0.6 -> 1.0.
          #   0.6 은 초반 4회가 dT_cond 0.18~0.23 에서 정체해 오히려 느렸다.
          #   실측 (fan=4, SH 8.6, tol 0.05)
          #     alpha 0.6  : 8회 55s  0.190 0.179 0.228 0.209 0.152 0.106 0.067 0.047
          #     alpha 0.85 : 6회 35s
          #     alpha 1.0  : 5회 47s  0.190 0.417 0.127 0.105 0.042
          #   1.0 은 2회차에 한 번 튀지만(0.417) 이후 빠르게 내려간다.
          #   팬 위치를 바꿔도 순서가 같아 완화가 이 문제에는 방해였다.
          alpha_air=1.0, inner_xtol=1e-6,
          dry_accumulator=True, verbose=False):
    """완전 연성 정상해.

    Args:
      ref_fidelity : {'compressor','condenser','eev','evaporator'} 각 1/2/3
      air_fidelity : {'drum','filter','fan','evaporator','condenser'}
      operating    : {'P_evap','P_cond','N','opening','h_suc','T_amb'} 초기추정
      air_inlet    : 드럼 입구 공기 {'T','RH','V_air_CMM'}
      M_charge     : 냉매 충전량 [kg]
      SH_target    : 목표 과열도 [K]. 지정 시 개도가 미지수가 되어 SH 를 구속한다.
                     None 이면 operating['opening'] 고정.
      geom         : {'V_n1','V_n2','V_n3','V_acc','V_oil_cc','V_shell'}
      fan_position : 팬 삽입 위치 (0~4). None 이면 팬 없음.
      air_states   : 드럼 등 동적 상태 (동적해에서 스텝 간 전달용)

    Returns:
      dict: converged, outer_iter, refrigerant(solve_forward 결과), air, air_bc
    """
    # 초기 air_bc: 드럼 입구를 양 HX 에 동일 적용
    # 초기 air_bc: 드럼 입구를 양 HX 에 그대로 쓰면 물리적으로 불가능한 조합이
    # 된다(응축기 입구는 증발기 출구여야 하는데 훨씬 뜨겁게 들어감).
    # 실측: 그 상태에서 충전량+SH 구속 해를 못 찾아 첫 outer 가 끝나지 않았다.
    # 증발기는 드럼 입구, 응축기는 증발기에서 냉각·제습된 공기로 추정한다.
    T_in = air_inlet['T']; RH_in = air_inlet.get('RH', 50.0)
    air_bc = {
        'evaporator': {'T_air_in': T_in, 'RH_air_in': RH_in,
                       'V_air_CMM': air_inlet['V_air_CMM']},
        'condenser':  {'T_air_in': max(T_in - 15.0, 5.0), 'RH_air_in': 95.0,
                       'V_air_CMM': air_inlet['V_air_CMM']},
    }

    op_ws = dict(operating)
    x_ws = None   # 이전 outer 해 (warm start)
    _dT_cond_last = 1e9   # 직전 outer 의 응축기 공기입구 변화량 [K]
    converged = False
    ref_res = None
    air_res = None
    hist = []

    for outer in range(max_outer):
        # ── 냉매: 충전량 구속 정상해 ──
        # warm start: 이전 outer 의 해를 x0 로 넘겨 뉴턴이 처음부터 다시
        # 찾지 않게 한다. 이게 없으면 매 outer 가 초기추정에서 재시작해
        # nfev 가 28 회씩 반복된다 (실측 outer 당 39~70초의 주원인).
        # SH 구속은 공기 BC 가 어느 정도 안정된 뒤에 켠다.
        # 첫 반복의 공기 BC 는 실제 운전점과 멀어, 바로 SH 를 구속하면
        # 개도가 상한(100%)에 붙고 Pe 가 발산한다 (실측: Pe 9.09, open 100).
        # 2026-07-27: SH 구속 진입을 '고정 횟수'가 아니라 '공기 수렴 상태' 기준으로.
        #   실제 제품도 기동 초기에는 EEV 를 고정 개도로 두고 일정 조건이
        #   갖춰진 뒤 제어에 진입한다. 공기 BC 가 초기값인 상태에서 SH 를
        #   강제하면 개도가 상한(100%)에 붙는다
        #   (실측: 공기입구 30C 조건의 자연 SH 가 29.9K, 목표 6K 과 괴리).
        #   dT_cond 가 sh_air_tol 이하로 안정되면 그때 SH 구속을 켠다.
        sh_ready = (outer >= sh_warmup) and (_dT_cond_last <= sh_air_tol)
        sh_now = SH_target if (SH_target is not None and sh_ready) else None
        _use_warm = (x_ws is not None
                     and len(x_ws) == (4 if sh_now is not None else 3))
        # broyden1 은 빠르지만(nfev 3, 0.8s vs hybr 8, 4.5s) 범위 밖으로
        # 크게 벗어나 CoolProp 이 터지는 경우가 있다(실측: Pe 가 하한 2bar 로).
        # 실패하면 hybr 로 재시도한다.
        ref_res = _try_solve(ref_fidelity, op_ws, air_bc, M_charge, geom,
                             oil_cfg, sh_now, x_ws if _use_warm else None,
                             inner_xtol, dry_accumulator)
        _unused_solve_forward = (solve_forward,)
        if False:
            ref_res = solve_forward(ref_fidelity, op_ws, air_bc, M_charge, geom,
                                # warm start 는 차원이 맞을 때만 전달.
                                # sh_warmup 경계에서 미지수가 3개<->4개로 바뀌므로
                                # 이전 x_ws 를 그대로 넘기면 unpack 오류가 난다.
                                # 2026-07-27: warm start 유무로 solver 선택.
                                #   hybr     : 수치 야코비안(미지수 4개 -> 4~5평가)
                                #              견고하나 warm 에서도 nfev 8, 4.5s
                                #   broyden1 : quasi-Newton, 야코비안 재사용
                                #              warm 에서 nfev 3, 0.8s (5.6배)
                                #              단 냉해에서는 NaN 으로 발산
                                # -> warm 있으면 broyden1, 없으면 hybr
                                method=method,
                                x0=(x_ws if (x_ws is not None
                                    and len(x_ws) == (4 if sh_now is not None else 3))
                                    else None),
                                xtol=inner_xtol,
                                oil_cfg=oil_cfg, SH_target=sh_now,
                                dry_accumulator=dry_accumulator)
        st = ref_res['state']

        # warm start: 수렴값을 다음 outer 초기추정으로
        op_ws = dict(op_ws)
        op_ws['P_evap'] = ref_res['P_evap']
        op_ws['P_cond'] = ref_res['P_cond']
        op_ws['h_suc']  = ref_res['h_suc']
        # 2026-07-27 버그 수정: 전역 SH_target 이 아니라 이번 outer 에 실제로
        #   쓴 sh_now 로 차원을 정해야 한다. sh_warmup 구간(sh_now=None)에서
        #   4개짜리를 만들면 다음 호출의 차원 가드가 매번 warm start 를 버려
        #   nfev 가 줄지 않았다 (실측: outer3 nfev 12 -> outer4 nfev 21).
        x_ws = ([ref_res['P_evap'], ref_res['P_cond'], ref_res['h_suc'],
                 ref_res.get('opening', op_ws['opening'])] if sh_now is not None
                else [ref_res['P_evap'], ref_res['P_cond'], ref_res['h_suc']])
        if SH_target is not None and 'opening' in ref_res:
            op_ws['opening'] = ref_res['opening']   # SH 제어 시 개도도 warm start

        # ── 공기: 드럼 루프 1-pass ──
        hx_ref = {
            'evaporator': {'P_evap': ref_res['P_evap'],
                           'h_in':   st['eev']['h_out'] if 'eev' in st else None,
                           'm_dot_ref': st['compressor']['m_dot']},
            'condenser':  {'P_cond': ref_res['P_cond'],
                           'h_in':   st['compressor']['h_dis'],
                           'm_dot_ref': st['compressor']['m_dot']},
        }
        # dt 전달 필수: air_loop 기본값이 1.0s 라 드럼이 스텝당 1초만 적분한다.
        # 실측: dt=60 스텝에서 300초 동안 m_w 가 0.001kg 만 감소(1/60 진행).
        air_res = air_pass(air_fidelity, air_inlet, air_states or {}, hx_ref,
                           fan_position=fan_position,
                           params_override=params_override, dt=dt)

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
        _dT_cond_last = dT_c
        hist.append({'outer': outer, 'dT_evap': dT_e, 'dT_cond': dT_c,
                     'Pc': ref_res['P_cond'], 'Pe': ref_res['P_evap'],
                     'SH': ref_res['SH_evap'],
                     'opening': ref_res.get('opening'),
                     'ok': ref_res['success']})
        # 2026-07-30: 실시간 진행 보고. UI 가 수렴 추이를 볼 수 있게 한다.
        #   기존에는 '수렴 중' 메시지만 있어 진행 여부를 알 수 없었다.
        if on_progress:
            try:
                on_progress(hist[-1], outer, max_outer)
            except Cancelled:
                raise      # 취소는 삼키지 않는다
            except Exception:
                pass       # 보고 실패는 계산을 막지 않는다

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
