#!/usr/bin/env python3
"""run_dynamic — 완전 연성 동적해 실행 스크립트 (워크스테이션용).

컨테이너(nproc=1)에서는 스텝당 45초라 30분 건조(90스텝)를 돌릴 수 없어
실제 워크스테이션에서 실행하도록 분리했다.

사용법
    cd backend
    python -m cycle_runner.run_dynamic                    # 기본: 30분 건조
    python -m cycle_runner.run_dynamic --t_end 300 --dt 20 --quick
    python -m cycle_runner.run_dynamic --solver broyden1  # quasi-Newton 시험

출력
    stdout 에 스텝별 진행상황
    --out 으로 지정한 JSON 파일에 전체 궤적 (기본 dynamic_result.json)

확인 포인트
    1) ok=True 비율 — 모든 스텝이 수렴하는가
    2) SH — 목표(기본 6.0)를 유지하는가
    3) m_w — 단조 감소하며 건조가 진행되는가
    4) Pc/Pe — 물리적으로 매끄러운가 (튀는 스텝이 없는가)
    5) wall/step — 스텝당 소요시간 (야코비안 비용 확인)

알려진 이슈
    - dt=60 에서 중간 스텝 실패: 개도가 21->9.5 로 크게 이동해야 하는
      구간에서 warm start 가 갇힌다. dt=20 이하 권장.
    - 저rpm 구간은 SH 구속을 만족하는 해가 없어 자동으로 SH 를 끈다.
    - 스텝당 비용은 뉴턴의 수치 야코비안이 지배한다
      (미지수 4개 -> 야코비안 1회에 함수평가 4~5회, 잔차 1회 0.55초).
      --solver broyden1 로 quasi-Newton 을 시험할 수 있다.
"""
import argparse
import json
import sys
import time


DEFAULT_GEOM = {
    'V_n1': 1.832e-5,   # 압축기->응축기 배관 [m3]
    'V_n2': 9.99e-6,    # 응축기->EEV
    'V_n3': 3.66e-6,    # EEV->증발기
    'V_acc': 2.226e-4,  # 어큐뮬레이터 200cc
    'V_oil_cc': 160.0,  # 오일 160cc (SUNISO 5GSD)
    'V_shell': 4.0e-4,  # 압축기 쉘 400cc
}

REF_FID = {'compressor': 3, 'condenser': 3, 'eev': 3, 'evaporator': 3}
AIR_FID = {'drum': 1, 'filter': 1, 'fan': 1, 'evaporator': 3, 'condenser': 3}


def main():
    ap = argparse.ArgumentParser(description='완전 연성 동적해 실행')
    ap.add_argument('--t_end', type=float, default=1800.0, help='해석 종료 시각 [s]')
    ap.add_argument('--dt', type=float, default=20.0, help='시간 스텝 [s]')
    ap.add_argument('--N', type=float, default=1800.0, help='목표 압축기 rpm')
    ap.add_argument('--ramp', type=float, default=120.0, help='rpm ramp 시간 [s]')
    ap.add_argument('--charge', type=float, default=0.100, help='냉매 충전량 [kg]')
    ap.add_argument('--SH', type=float, default=6.0, help='과열도 목표 [K] (0 이면 제어 안 함)')
    ap.add_argument('--fan_pos', type=int, default=4,
                    help='팬 위치 0~4 (AIR_CORE=drum,filter,evaporator,condenser)')
    ap.add_argument('--T_air', type=float, default=30.0, help='드럼 입구 공기 온도 [C]')
    ap.add_argument('--RH', type=float, default=40.0, help='드럼 입구 상대습도 [%]')
    ap.add_argument('--V_air', type=float, default=2.42, help='풍량 [CMM]')
    ap.add_argument('--T_amb', type=float, default=35.0, help='주위 온도 [C]')
    ap.add_argument('--max_outer', type=int, default=8, help='공기 연성 외부 반복 상한')
    ap.add_argument('--pulse', action='store_true',
                    help='EEV 스텝모터 펄스 제어 (과도구간 SH 진동 재현)')
    ap.add_argument('--pps', type=float, default=30.0, help='초당 최대 펄스 [step/s]')
    ap.add_argument('--nstep', type=int, default=500, help='EEV 전체 스텝수')
    ap.add_argument('--solver', default='hybr',
                    help="scipy.root method (hybr/broyden1/krylov/df-sane)")
    ap.add_argument('--out', default='dynamic_result.json', help='결과 JSON 경로')
    ap.add_argument('--quick', action='store_true', help='짧은 시험 (t_end=300, dt=20)')
    args = ap.parse_args()

    if args.quick:
        args.t_end, args.dt = 300.0, 20.0

    sys.path.insert(0, '.')
    from cycle_runner import dynamic_charge as dc

    air_inlet = {'T': args.T_air, 'RH': args.RH, 'V_air_CMM': args.V_air}
    operating = {'P_evap': 6.09, 'P_cond': 10.46, 'N': args.N,
                 'opening': 23.586, 'h_suc': 595.4, 'T_amb': args.T_amb}
    sh = args.SH if args.SH > 0 else None

    print('=' * 72)
    print(f"완전 연성 동적해  t_end={args.t_end:.0f}s  dt={args.dt:.0f}s  "
          f"({int(args.t_end/args.dt)+1} 스텝)")
    print(f"  N={args.N:.0f}rpm (ramp {args.ramp:.0f}s)  충전={args.charge*1000:.0f}g  "
          f"SH={sh}  fan_pos={args.fan_pos}")
    print(f"  공기입구 {args.T_air:.1f}C/{args.RH:.0f}%  {args.V_air:.2f}CMM  "
          f"T_amb={args.T_amb:.1f}C  solver={args.solver}")
    print('=' * 72)

    t0 = time.time()
    res = dc.run(REF_FID, AIR_FID, operating, air_inlet,
                 args.charge, DEFAULT_GEOM,
                 fan_position=args.fan_pos, SH_target=sh,
                 t_end=args.t_end, dt=args.dt,
                 N_target=args.N, ramp_time=args.ramp,
                 max_outer=args.max_outer, method=args.solver,
                 use_pulse=args.pulse,
                 eev_cfg={'pps_max': args.pps, 'n_max': args.nstep},
                 verbose=False)
    wall = time.time() - t0

    print(f"\n{'t[s]':>7} {'N':>6} {'phase':>8} {'Pc':>8} {'Pe':>8} "
          f"{'SH':>7} {'open':>7} {'m_w':>8} {'ok':>5}")
    print('-' * 72)
    for x in res['trajectory']:
        f = lambda v, n=3: ('-' if v is None else f'{v:.{n}f}')
        print(f"{x['t']:7.0f} {x.get('N', 0):6.0f} {str(x.get('phase'))[:8]:>8} "
              f"{f(x.get('Pc')):>8} {f(x.get('Pe')):>8} {f(x.get('SH'), 2):>7} "
              f"{f(x.get('opening'), 2):>7} {f(x.get('m_w'), 4):>8} "
              f"{str(x.get('ok', '-')):>5}")

    n_ok = res['converged_steps']
    n_tot = res['total_steps']
    print('-' * 72)
    print(f"수렴 {n_ok}/{n_tot} ({n_ok/max(n_tot,1)*100:.0f}%)   "
          f"전체 {wall:.0f}s   스텝당 {wall/max(n_tot,1):.1f}s   "
          f"phase 전환 t={res['phase_switch_t']}")

    mw = [x['m_w'] for x in res['trajectory'] if x.get('m_w') is not None]
    if len(mw) >= 2:
        print(f"건조: m_w {mw[0]:.4f} -> {mw[-1]:.4f} kg "
              f"({(mw[0]-mw[-1])*1000:.1f}g 제거)")
        mono = all(mw[i] >= mw[i+1] - 1e-9 for i in range(len(mw)-1))
        print(f"단조감소: {'OK' if mono else '위반 — 확인 필요'}")

    shv = [x['SH'] for x in res['trajectory']
           if x.get('SH') is not None and x.get('ok')]
    if shv and sh:
        err = max(abs(v - sh) for v in shv)
        print(f"SH 제어: 수렴 스텝 {len(shv)}개, 목표 대비 최대오차 {err:.4f} K")

    with open(args.out, 'w', encoding='utf-8') as fp:
        json.dump({'args': vars(args), 'wall': wall, **res}, fp,
                  ensure_ascii=False, indent=1, default=str)
    print(f"\n결과 저장: {args.out}")


if __name__ == '__main__':
    main()
