"""
air_loop.py — 공기 루프 1-pass 배관 (팬 가변 위치)

고정 코어 위상: 드럼 → 필터 → 증발기 → 응축기 → (드럼)
팬은 임의 위치 삽입: air_path.insert(fan_position, fan)

각 컴포넌트가 공기 상태를 다르게 출력(drum:T_air_out/omega_out, filter:보존,
fan:T_out/omega_out, HX:T_air_out/W_air_out)하므로 통일 어댑터로 (T,W,유량)
표준화해서 다음 컴포넌트로 전달.

HX(증발기/응축기)는 냉매측도 필요 → coupled_solver에서 냉매 상태 받아 호출.
여기(air_loop 단독)서는 HX 냉매측을 고정 BC로 처리 (3단계 검증용).

단위: T [°C], RH [%], W [kg/kg], V_air_CMM [m³/min].
"""

import CoolProp.CoolProp as CP

from .registry import get_component, default_params

# 공기 루프 고정 코어 순서 (팬 제외)
AIR_CORE = ['drum', 'filter', 'evaporator', 'condenser']


def _air_out_state(comp_kind, inp_state, outputs):
    """컴포넌트 출력에서 통일 공기 상태 (T, W, RH, V_air_CMM) 추출.

    컴포넌트마다 출구 키가 다르므로 통일. 없으면 입구값 보존.
    - drum/HX: T,W를 바꿈 (출력 키 사용)
    - filter: T,W 보존 (압력강하만) → 입구값 유지
    - fan(L3): T_out만 (W 보존); fan(L1): 아무것도 안 바꿈
    """
    T = outputs.get('T_air_out', outputs.get('T_out'))
    if T is None:
        T = inp_state['T']            # filter, fan-L1 등: 온도 보존
    W = outputs.get('W_air_out', outputs.get('omega_out'))
    if W is None:
        W = inp_state.get('W')        # W 미출력 시 입구 보존
    RH = outputs.get('RH_air_out', inp_state.get('RH'))
    return {'T': T, 'W': W, 'RH': RH, 'V_air_CMM': inp_state['V_air_CMM']}


def _cin_for(comp, air, m_dot_air, P_air=101325.0):
    """컴포넌트별 입력 키 규약 변환.

    냉매측 HX는 T_air_in / RH_air_in / V_air_CMM 를 쓰지만, 공기 3종은 규약이 다르다:
      drum   : T_in[°C] 또는 T_in_K, W_in[kg/kg], m_flow_da[kg/s 건공기]
               (L3 경로는 T_air_in / RH_air_in / W_in 도 읽음)
      filter : T_in[°C], omega[kg/kg], m_dot_da[kg/s 건공기], P_in[Pa]
      fan    : T_in[°C], omega[kg/kg], m_dot_da 또는 V_dot[m³/s], P_in[Pa]

    ⚠ fan/filter의 'omega'는 회전속도가 아니라 **절대습도**다 (기본값 0.008~0.010).
    ⚠ m_dot_da 는 **건공기** 유량 — 습공기 유량에서 1/(1+W) 로 환산.

    2026-07-24 이전에는 HX용 키(T_air_in 등)를 그대로 넘겨 drum 일부를 빼고
    전부 기본값으로 동작했음. 실측: fan dp가 599.71 로 고정(공기온도 20/40/60°C
    무관), filter V_dot 이 실제 0.0403 대신 기본값 0.03.
    """
    if comp in ('evaporator', 'condenser'):
        return {'T_air_in': air['T'], 'RH_air_in': air['RH'],
                'V_air_CMM': air['V_air_CMM'], 'm_dot_air': m_dot_air}
    W = air.get('W')
    if W is None:
        W = CP.HAPropsSI('W', 'T', air['T'] + 273.15, 'R',
                         max(min(air['RH'] / 100.0, 1.0), 1e-4), 'P', P_air)
    m_da = m_dot_air / (1.0 + W)
    if comp == 'drum':
        return {'T_in': air['T'], 'W_in': W, 'm_flow_da': m_da,
                'm_dot_air': m_dot_air, 'T_air_in': air['T'], 'RH_air_in': air['RH']}
    # filter / fan — 'omega' = 절대습도
    return {'T_in': air['T'], 'omega': W, 'm_dot_da': m_da,
            'P_in': P_air, 'RH_in': air['RH'],
            'V_dot': m_da * (1.0 + W) / 1.2}


def one_pass(fidelity, air_inlet, states, hx_refrigerant, fan_position=None,
             params_override=None, dt=1.0):
    """공기 루프 1-pass.

    Args:
      fidelity: {'drum':1/2/3, 'filter':.., 'fan':.., 'evaporator':.., 'condenser':..}
      air_inlet: 드럼 입구 공기 {'T','RH','W','V_air_CMM','m_dot_air'}
      states: 동적 컴포넌트 상태 {'drum': drum_state, ...} (drum은 init_state 필요)
      hx_refrigerant: HX 냉매측 고정 BC {'evaporator':{P_evap,h_in,m_dot_ref},
                      'condenser':{P_cond,h_in,m_dot_ref}}
      fan_position: 팬 삽입 위치 (0~len(AIR_CORE)). None이면 팬 없음.
      params_override: 컴포넌트별 추가 params

    Returns:
      dict: 각 컴포넌트 결과 + 공기 상태 궤적 + newStates
    """
    po = params_override or {}

    # 공기 경로 구성 (팬 삽입)
    path = list(AIR_CORE)
    if fan_position is not None:
        path.insert(fan_position, 'fan')

    def _params(comp):
        p = default_params(comp, fidelity.get(comp, 1))
        # 공기 컴포넌트(drum/filter/fan)는 fidelity를 'L1'/'L2'/'L3' 문자열로 받음
        # (냉매 컴포넌트는 숫자 1/2/3). 여기서 변환.
        if comp in ('drum', 'filter', 'fan'):
            p['fidelity'] = f"L{fidelity.get(comp, 1)}"
        else:
            p.setdefault('fidelity', fidelity.get(comp, 1))
        p.update(po.get(comp, {}))
        return p

    # 공기 상태 (통일 dict)
    air = {'T': air_inlet['T'], 'RH': air_inlet['RH'],
           'W': air_inlet.get('W'), 'V_air_CMM': air_inlet['V_air_CMM']}
    m_dot_air = air_inlet.get('m_dot_air', 0.048)

    results = {}
    trajectory = [dict(air)]
    new_states = {}

    for comp in path:
        # 공기측 입력 (통일 상태 → 컴포넌트 입력 키)
        cin = _cin_for(comp, air, m_dot_air)

        if comp in ('evaporator', 'condenser'):
            # HX: 냉매측 BC 병합 (P_cond→응축기, P_evap→증발기)
            cin.update(hx_refrigerant[comp])
            mod = get_component('refrigerant', comp, fidelity[comp])
            state = states.get(comp, {})
        else:
            # drum/filter/fan
            mod = get_component('air', comp, fidelity.get(comp, 1))
            state = states.get(comp, {})
            if comp == 'drum' and not state:
                # drum은 fidelity별 init_state 분리 (init_state_L1/L2, 또는 일반)
                fl = fidelity.get('drum', 1)
                init_fn = getattr(mod, f'init_state_L{fl}', None) or mod.init_state
                state = init_fn({'fidelity': f"L{fl}"})

        r = mod.step(cin, _params(comp), state, dt)
        outs = r['outputs']
        results[comp] = outs
        if 'newState' in r:
            new_states[comp] = r['newState']

        # 공기 상태 갱신 (통일)
        air = _air_out_state(comp, air, outs)
        trajectory.append(dict(air))

    return {
        'results': results, 'trajectory': trajectory,
        'air_out': air, 'new_states': new_states,
        'path': path,
    }


if __name__ == '__main__':
    # 공기 루프 1-pass (팬 위치별 테스트)
    fid = {'drum': 1, 'filter': 1, 'fan': 1, 'evaporator': 3, 'condenser': 3}
    air_in = {'T': 30.0, 'RH': 40.0, 'W': None, 'V_air_CMM': 2.42, 'm_dot_air': 0.048}
    # HX 냉매측 고정 BC (12칸 검증값)
    hx_ref = {
        'evaporator': {'P_evap': 5.0889, 'h_in': 364.157, 'm_dot_ref': 0.00206593},
        'condenser': {'P_cond': 9.8762, 'h_in': 651.260, 'm_dot_ref': 0.00206593},
    }

    for fan_pos in [None, 0, 2]:
        pos_label = '팬없음' if fan_pos is None else f'팬@{fan_pos}'
        try:
            r = one_pass(fid, air_in, {}, hx_ref, fan_position=fan_pos)
            print(f"\n═══ {pos_label} (경로: {'→'.join(r['path'])}) ═══")
            for i, comp in enumerate(r['path']):
                t = r['trajectory'][i + 1]
                print(f"  {comp:10s}: T={t['T']:.2f}°C W={t['W'] if t['W'] else '?'}")
            print(f"  공기 출구: T={r['air_out']['T']:.2f}°C")
        except Exception as e:
            import traceback
            print(f"\n{pos_label}: 에러")
            traceback.print_exc()
