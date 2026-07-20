"""
coupled_solver.py — 냉매-공기 연성 solver

HX(증발기·응축기)가 냉매 루프와 공기 루프 양쪽에 걸침. 두 루프를 외부
fixed-point로 연결:

  air_bc = 초기추정 (드럼 입구 공기로부터)
  repeat:
    냉매 solve(air_bc) → 냉매사이클 수렴, HX 냉매입구 추출
    공기 loop(hx_ref) → 공기상태, HX 공기입구 추출
    수렴판정 (air_bc의 HX 공기입구가 안정되나)
    air_bc ← 새 HX 공기입구 (under-relaxation)

수렴 시: 양 루프가 각자 정합 + 공유 Q(HX 열전달)가 일치.

핵심 데이터 흐름:
  냉매→공기: 응축기 냉매입구={P_cond,h_dis,m_dot}, 증발기={P_evap,h_eev_out,m_dot}
  공기→냉매: 증발기 공기입구=traj[evap_idx], 응축기 공기입구=traj[cond_idx]
"""

from .solver import solve as refrigerant_solve
from .air_loop import one_pass as air_pass, AIR_CORE

import CoolProp.CoolProp as CP


def _rh_from_TW(T_C, W, P=101325.0):
    """온도(°C)·습도비 W에서 RH(%) 계산 (HX가 RH 입력 필요)."""
    if W is None:
        return None
    try:
        # W = 0.622·p_w/(P-p_w) → p_w = W·P/(0.622+W)
        p_w = W * P / (0.622 + W)
        p_sat = CP.PropsSI('P', 'T', T_C + 273.15, 'Q', 1, 'Water')
        return max(0.0, min(100.0, 100.0 * p_w / p_sat))
    except Exception:
        return None


def solve(ref_fidelity, air_fidelity, operating, air_inlet,
          fan_position=None, params_override=None, air_states=None,
          max_outer=30, tol_air=0.05, alpha_air=0.6, verbose=False):
    """냉매-공기 연성 수렴.

    Args:
      ref_fidelity: 냉매 {'compressor','condenser','eev','evaporator'} 각 1/2/3
      air_fidelity: 공기 {'drum','filter','fan','evaporator','condenser'}
      operating: 냉매 초기 {'P_evap','P_cond','N','opening','h_suc','T_amb'}
      air_inlet: 드럼 입구 공기 {'T','RH','W','V_air_CMM','m_dot_air'}
      fan_position: 팬 위치 (None=없음)
      air_states: 공기 컴포넌트 상태 {'drum': drum_state} (동적 건조 진행용).
                  None이면 매번 init (정상상태). dynamic_runner가 스텝 간 전달.

    Returns:
      dict: {'converged','outer_iter','refrigerant','air','air_bc'}
    """
    air_states = air_states or {}
    # 초기 air_bc: 드럼 입구 공기를 양 HX에 동일 적용 (첫 추정)
    air_bc = {
        'condenser': {'T_air_in': air_inlet['T'], 'RH_air_in': air_inlet['RH'],
                      'V_air_CMM': air_inlet['V_air_CMM']},
        'evaporator': {'T_air_in': air_inlet['T'], 'RH_air_in': air_inlet['RH'],
                       'V_air_CMM': air_inlet['V_air_CMM']},
    }

    converged = False
    ref_res = None
    air_res = None
    # warm start: operating을 복사해 매 outer 후 수렴값으로 갱신
    #   (냉매 사이클을 매번 초기값에서 재수렴하지 않고 이전 outer 결과에서 이어감)
    #   max_iter는 충분히 유지 — warm start로 실제 iteration은 자연히 줄어듦
    op_ws = dict(operating)
    for outer in range(max_outer):
        # ── 냉매 사이클 수렴 (현재 air_bc + warm-started operating) ──
        ref_res = refrigerant_solve(ref_fidelity, op_ws, air_bc,
                                    params_override=params_override, max_iter=100,
                                    tol_mass=1e-5, tol_enthalpy=1.0, tol_SH=0.1)
        s = ref_res['state']

        # 다음 outer용 warm start: 수렴된 냉매 상태를 operating에 반영
        op_ws = dict(op_ws)
        op_ws['P_evap'] = ref_res['P_evap']
        op_ws['P_cond'] = ref_res['P_cond']
        op_ws['h_suc'] = ref_res['h_suc']

        # HX 냉매입구 추출 → 공기 loop용
        hx_ref = {
            'condenser': {'P_cond': ref_res['P_cond'], 'h_in': s['h_dis'],
                          'm_dot_ref': s['m_dot']},
            'evaporator': {'P_evap': ref_res['P_evap'], 'h_in': s['h_eev_out'],
                           'm_dot_ref': s['m_dot']},
        }

        # ── 공기 loop (현재 냉매입구로) ──
        air_res = air_pass(air_fidelity, air_inlet, air_states, hx_ref,
                           fan_position=fan_position, params_override=params_override)
        path = air_res['path']
        traj = air_res['trajectory']

        # HX 공기입구 추출 (trajectory[i] = 컴포넌트 i 입구)
        new_air_bc = {}
        for i, comp in enumerate(path):
            if comp in ('evaporator', 'condenser'):
                tin = traj[i]
                rh = tin['RH'] if tin['RH'] is not None else _rh_from_TW(tin['T'], tin['W'])
                new_air_bc[comp] = {
                    'T_air_in': tin['T'],
                    'RH_air_in': rh if rh is not None else 50.0,
                    'V_air_CMM': tin['V_air_CMM'],
                }

        # ── 수렴 판정 (HX 공기입구 T 변화) ──
        dT_cond = abs(new_air_bc['condenser']['T_air_in'] - air_bc['condenser']['T_air_in'])
        dT_evap = abs(new_air_bc['evaporator']['T_air_in'] - air_bc['evaporator']['T_air_in'])
        max_dT = max(dT_cond, dT_evap)

        if verbose:
            print(f"  outer{outer}: evap공기입구={new_air_bc['evaporator']['T_air_in']:.2f} "
                  f"cond공기입구={new_air_bc['condenser']['T_air_in']:.2f} "
                  f"maxΔT={max_dT:.3f} (냉매 {ref_res['iterations']}회)")

        if max_dT < tol_air and ref_res['converged']:
            converged = True
            break

        # air_bc 갱신 (under-relaxation)
        for hx in ('condenser', 'evaporator'):
            for k in ('T_air_in', 'RH_air_in'):
                old = air_bc[hx][k]
                new = new_air_bc[hx][k]
                air_bc[hx][k] = old + alpha_air * (new - old)
            air_bc[hx]['V_air_CMM'] = new_air_bc[hx]['V_air_CMM']

    return {
        'converged': converged, 'outer_iter': outer + 1,
        'refrigerant': ref_res, 'air': air_res, 'air_bc': air_bc,
    }


if __name__ == '__main__':
    ref_fid = {'compressor': 1, 'condenser': 1, 'eev': 1, 'evaporator': 1}
    air_fid = {'drum': 1, 'filter': 1, 'fan': 3, 'evaporator': 1, 'condenser': 1}
    op = {'P_evap': 5.0889, 'P_cond': 9.8762, 'N': 1800,
          'opening': 23.586, 'h_suc': 587.309, 'T_amb': 35.0}
    air_in = {'T': 30.0, 'RH': 40.0, 'W': 0.0107, 'V_air_CMM': 2.42, 'm_dot_air': 0.048}

    r = solve(ref_fid, air_fid, op, air_in, fan_position=None, verbose=True)
    print(f"\n연성 수렴: {r['converged']} ({r['outer_iter']} outer)")
    rf = r['refrigerant']
    print(f"  냉매: P_evap={rf['P_evap']:.4f} P_cond={rf['P_cond']:.4f} "
          f"m_dot={rf['state']['m_dot']:.6f}")
    print(f"  Q_cond={rf['state']['Q_cond']:.1f} Q_evap={rf['state']['Q_evap']:.1f}")
    print(f"  HX 공기입구: evap={r['air_bc']['evaporator']['T_air_in']:.2f}°C "
          f"cond={r['air_bc']['condenser']['T_air_in']:.2f}°C")
