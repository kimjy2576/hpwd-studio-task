"""find_operating_point — 공기 직렬 결합 하에서 SH 목표를 만족하는 정상 운전점 탐색.

목적 (2026-07-25, A단계):
  Modelica 사이클 콜드스타트가 Pc 26bar / SH=0 의 '응축기 액범람' 해로 수렴하는데,
  이것이 유일해인지 확인하기 위해 Python 정상상태로 SH=6K 해의 존재를 검증.
  결과: 존재함. 시스템에 정상해가 최소 둘 있고 콜드스타트가 나쁜 쪽으로 간 것.

구조:
  실물 HPWD 는 공기가 직렬임 (증발기 제습 -> 응축기 재가열 -> 드럼 -> 증발기).
  따라서 응축기 공기입구 = 증발기 공기출구. 이를 바깥 fixed-point 로 감싸고,
  안쪽은 역방향 solver(SH_target 지정 -> P_evap/P_cond/h_suc 해)를 돌린다.

  ※ 드럼은 아직 미연결이라 증발기 공기입구는 고정 BC 로 둔다.
    드럼 연결 시에는 cycle_runner.coupled_solver 를 쓸 것.

주의:
  역방향 solver 는 SH 를 구속하고 충전량은 자유. 따라서 해가 나온 뒤
  반드시 charge_check() 로 실제 충전량(100g)과 양립하는지 확인해야 한다.
  어큐뮬레이터가 잉여 냉매를 흡수하므로 시스템이 담을 수 있는 총량에는
  폭이 있고, 그 안에 들어와야 물리적으로 성립한다.
"""

import CoolProp.CoolProp as CP

from .solver import solve as reverse_solve

FLUID = 'R290'

# 실물 내용적 [m^3] (CYCLE_ANALYSIS_CHECKLIST 조치2 기준)
V_N1 = 1.832e-5   # 압축기 -> 응축기 (1/4" 동관 1.0m)
V_N2 = 9.99e-6    # 응축기 -> EEV (0.2m + 응축기 리턴밴드)
V_N3 = 3.66e-6    # EEV -> 증발기 (0.2m)
V_N4 = 2.226e-4   # 증발기 -> 압축기 (1.0m + 어큐 200cc + 증발기 밴드)


def find(N=1800.0, opening=23.586, SH_target=6.0,
         evap_air=None, cond_air_guess=(12.7, 99.0),
         V_air_CMM=2.42, T_amb=20.0,
         outer_iter=10, relax=0.5, fidelity=None, verbose=False):
    """공기 직렬 결합 + SH 구속으로 정상 운전점을 찾는다.

    Returns: (result, air_cond) — result 는 reverse_solve 반환, air_cond 는 (T,RH)
    """
    fid = fidelity or {'compressor': 3, 'condenser': 3, 'eev': 3, 'evaporator': 3}
    evap_air = evap_air or {'T_air_in': 20.0, 'RH_air_in': 80.0, 'V_air_CMM': V_air_CMM}
    Tc, RHc = cond_air_guess

    op = {'P_evap': 6.04, 'P_cond': 10.45, 'N': N, 'opening': opening,
          'h_suc': 587.31, 'T_amb': T_amb}
    r = None
    for k in range(outer_iter):
        air = {'condenser': {'T_air_in': Tc, 'RH_air_in': RHc, 'V_air_CMM': V_air_CMM},
               'evaporator': dict(evap_air)}
        r = reverse_solve(fid, op, air, SH_target=SH_target, max_iter=150)
        ev = r['state']['evaporator']
        # 응축기 공기입구 <- 증발기 공기출구 (under-relaxation)
        Tc += relax * (ev['T_air_out'] - Tc)
        RHc += relax * (min(ev['RH_air_out'], 99.0) - RHc)
        op = {**op, 'P_evap': r['P_evap'], 'P_cond': r['P_cond'], 'h_suc': r['h_suc']}
        if verbose:
            print(f"  outer{k}: conv={r['converged']} Pe={r['P_evap']:.4f} "
                  f"Pc={r['P_cond']:.4f} SH={r['state']['SH_evap']:.3f} "
                  f"cond_air={Tc:.2f}C/{RHc:.1f}%")
    return r, (Tc, RHc)


def charge_check(r, M_charge=0.100):
    """해가 목표 충전량과 양립하는지. 어큐 quality 를 자유도로 본다.

    HX 홀드업 + 노드1~3 은 상태로부터 결정되고, 어큐(vol4)만 액/증기 비율이
    자유롭다. 따라서 시스템이 담을 수 있는 총량에 [최소, 최대] 폭이 생기며
    M_charge 가 그 안에 들어와야 물리적으로 성립한다.
    """
    s = r['state']
    Pe_Pa = r['P_evap'] * 1e5
    rl = CP.PropsSI('D', 'P', Pe_Pa, 'Q', 0, FLUID)
    rv = CP.PropsSI('D', 'P', Pe_Pa, 'Q', 1, FLUID)

    M_hx = (s['condenser'].get('M_holdup') or 0.0) + (s['evaporator'].get('M_holdup') or 0.0)

    # 노드1~3 (어큐 제외)
    rho1 = CP.PropsSI('D', 'P', r['P_cond'] * 1e5, 'H', s['compressor']['h_dis'] * 1e3, FLUID)
    rho2 = CP.PropsSI('D', 'P', s['condenser']['P_ref_out'] * 1e5,
                      'H', s['condenser']['h_ref_out'] * 1e3, FLUID)
    rho3 = CP.PropsSI('D', 'P', Pe_Pa, 'H', s['eev']['h_out'] * 1e3, FLUID)
    M_123 = rho1 * V_N1 + rho2 * V_N2 + rho3 * V_N3

    M_min = M_hx + M_123 + rv * V_N4
    M_max = M_hx + M_123 + rl * V_N4
    ok = M_min <= M_charge <= M_max

    out = {'M_hx': M_hx, 'M_nodes123': M_123,
           'M_sys_min': M_min, 'M_sys_max': M_max,
           'compatible': ok, 'rho_l': rl, 'rho_v': rv}
    if ok:
        rho_acc = (M_charge - M_hx - M_123) / V_N4
        out['M_acc'] = rho_acc * V_N4
        out['rho_acc'] = rho_acc
        out['liquid_frac'] = (rho_acc - rv) / (rl - rv)
        out['x_acc'] = (1.0 / rho_acc - 1.0 / rl) / (1.0 / rv - 1.0 / rl)
        hl = CP.PropsSI('H', 'P', Pe_Pa, 'Q', 0, FLUID)
        hv = CP.PropsSI('H', 'P', Pe_Pa, 'Q', 1, FLUID)
        out['h_acc'] = hl + out['x_acc'] * (hv - hl)
    return out


def modelica_init(r, air_cond, chk):
    """Modelica Cycle_L3 초기값 묶음 (p_start/h_start 주입용)."""
    s = r['state']
    return {
        'p_cond_Pa': r['P_cond'] * 1e5,
        'p_evap_Pa': r['P_evap'] * 1e5,
        'vol1': {'p': r['P_cond'] * 1e5, 'h': s['compressor']['h_dis'] * 1e3},
        'vol2': {'p': s['condenser']['P_ref_out'] * 1e5, 'h': s['condenser']['h_ref_out'] * 1e3},
        'vol3': {'p': r['P_evap'] * 1e5, 'h': s['eev']['h_out'] * 1e3},
        'vol4': {'p': r['P_evap'] * 1e5, 'h': chk.get('h_acc')},
        'h_suc': r['h_suc'] * 1e3,
        'T_air_cond': air_cond[0], 'RH_air_cond': air_cond[1],
    }


if __name__ == '__main__':
    r, air_cond = find(verbose=True)
    s = r['state']
    print(f"\n수렴={r['converged']}  Pe={r['P_evap']:.4f} bar  Pc={r['P_cond']:.4f} bar")
    print(f"SH={s['SH_evap']:.3f} K  mdot={s['compressor']['m_dot']:.6f} kg/s")
    print(f"Q_evap={s['evaporator']['Q_total']:.1f} W  Q_cond={s['condenser']['Q_total']:.1f} W")
    print(f"cond.x_out={s['condenser']['quality_out']:.4f}")

    chk = charge_check(r)
    print(f"\nHX 홀드업 {chk['M_hx']*1000:.2f} g + 노드1~3 {chk['M_nodes123']*1000:.2f} g")
    print(f"시스템 수용범위 {chk['M_sys_min']*1000:.1f} ~ {chk['M_sys_max']*1000:.1f} g")
    print(f"100 g 양립={chk['compatible']}")
    if chk['compatible']:
        print(f"  어큐 {chk['M_acc']*1000:.1f} g  rho={chk['rho_acc']:.0f}  "
              f"액 체적분율 {chk['liquid_frac']*100:.0f}%  x={chk['x_acc']:.4f}")

    print("\n=== Modelica 초기값 ===")
    for k, v in modelica_init(r, air_cond, chk).items():
        print(f"  {k}: {v}")
