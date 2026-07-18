#!/usr/bin/env python3
"""
verify_air_fidelity.py — 공기측 3컴포넌트 × 3급 GT↔Modelica 검증 (Python GT 측)

각 컴포넌트(Fan/Drum/Filter)의 L1/L2/L3 Python ground truth를 동일 BC에서
실행하고 기준값을 출력. Modelica 측 값은 CmpAirParts 하네스로 별도 시뮬해
대조(주석에 기록). 모델 수정 시 회귀 테스트로 사용.

동일 BC:
  Fan:    RPM=3000, m=+0.05, 20°C, W=0.008
          통일기하 D2=0.175/b2=0.050/D1=0.120/b1=0.060/Z=36/β2=145/β1=30
          (= Fan_L3 기본값 = fan-sim 검증 레퍼런스)
  Drum:   60°C, W=0.010, m=0.035, 면3kg, X0=0.6 (동적, 궤적)
  Filter: m=0.05, 50°C, W=0.010, A_face=0.05

⚠️ Fan 부호: outlet BoundaryAir_mflow는 +m이 정방향. -m은 역류(eta=0).
   드럼은 inlet이 mflow라 -m이 정방향 — 반대이니 주의.
⚠️ Fan 기하: N만 통일하면 각 급 기본값이 달라 서로 다른 팬 비교가 됨.
⚠️ Drum: der 연속 vs 오일러 → ΔX~0.001-0.003 잔여차 정상.

사용: python3 verify_air_fidelity.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'components'))
import fan_on, drum_on, filter_on

# Modelica 기준값 (CmpAirParts 하네스 시뮬 결과, 동일 BC)
MODELICA_REF = {
    'fan_L1': 727.091, 'fan_L2': 842.919,   # dp [Pa] @ 통일기하·정방향
    'filter_L1': 17.3051, 'filter_L2': 16.8799, 'filter_L3': 14.1133,  # dp [Pa]
    # Drum: (t, X) 궤적 점
    'drum_L1': {600: 0.514599, 1800: 0.337214, 3000: 0.159829},
    'drum_L2': {600: 0.514598, 2400: 0.248515, 4800: 0.00182415},
    'drum_L3': {600: 0.312494},  # 4경로, t600 mev/Tfab 검증은 36cebae
}

TOL_DP = 0.5     # Pa
TOL_X = 0.005    # 함수율 (der vs 오일러 허용)


def verify_fan():
    print("── Fan (정적, dp [Pa]) ──")
    # ⚠️ 통일 기하 (CmpAirParts 공통상수 = Fan_L3 기본값, fan-sim 레퍼런스).
    #    이전엔 N만 통일하고 기하는 각자 기본값 → 서로 다른 팬 비교 오류.
    base = {'D2':0.175,'b2':0.050,'D1':0.120,'b1':0.060,'Z':36,
            'beta2':145,'beta1':30,'N':3000,
            'eta_h':0.78,'eta_mech':0.95,'f_inc':0.6,'f_fric':0.8}
    # ⚠️ 정방향(+) 유량. 하네스 outlet mflow는 +가 정방향 — 이전 -0.05는
    #    역류(Fan_L3 eta=0)였고 Python도 -로 맞춰 "일치"시킨 오류였음.
    inp = {'T_in':20.0,'omega':0.008,'m_dot_da':0.05}
    results = []
    for lv in ['L1','L2']:
        o = fan_on.step(inp, {**base,'fidelity':lv}, {}, 0)['outputs']
        ref = MODELICA_REF[f'fan_{lv}']
        ok = abs(o['dp'] - ref) < TOL_DP
        results.append(ok)
        print(f"  {lv}: Py={o['dp']:.3f}  Mod={ref:.3f}  Δ={abs(o['dp']-ref):.4f}  {'✅' if ok else '❌'}")
    print("  L3: fan-sim 단위(mm) 별도 BC, 5c6aac6서 Ps 668.23↔668.24 검증")
    print("      (통일기하 CmpAirParts: Ps=662.61, Pt_fan=715.39, eta=0.6515)")
    return all(results)


def verify_filter():
    print("── Filter (정적, dp [Pa]) ──")
    inp = {'T_in':50.0,'omega':0.010,'m_dot_da':0.05}
    base = {'A_face':0.05,'r_pleat':1.0,'theta_face':0.0,'K':20}
    results = []
    for lv in ['L1','L2','L3']:
        o = filter_on.step(inp, {**base,'fidelity':lv}, {}, 0)['outputs']
        ref = MODELICA_REF[f'filter_{lv}']
        ok = abs(o['dp'] - ref) < TOL_DP
        results.append(ok)
        print(f"  {lv}: Py={o['dp']:.4f}  Mod={ref:.4f}  Δ={abs(o['dp']-ref):.4f}  {'✅' if ok else '❌'}")
    return all(results)


def verify_drum():
    print("── Drum (동적, 궤적 X) ──")
    base = {'m_cl_dry':3.0,'c_p_cl':1500,'A_eff':10,'h_a':50,'A_drum':0.15,
            'K_drum':30,'X0':0.6,'Tcl0':298.15,'UA_amb':0.0,
            'X_cr':0.2,'a_sorp':0.25,'n_sorp':2.0}
    inp = {'T_in_K':333.15,'W_in':0.010,'m_flow_da':0.035}
    results = []
    for lv in ['L1','L2']:
        init = drum_on.init_state_L1(base) if lv=='L1' else drum_on.init_state_L2(base)
        state = init
        saved = {}
        t = 0
        for i in range(600):
            out = drum_on.step(inp, {**base,'fidelity':lv}, state, 10.0)
            state = out['newState']; t += 10
            saved[t] = out['outputs']['X']
        ref = MODELICA_REF[f'drum_{lv}']
        for ts, Xref in ref.items():
            if ts in saved:
                ok = abs(saved[ts] - Xref) < TOL_X
                results.append(ok)
                print(f"  {lv} t{ts}: Py X={saved[ts]:.5f}  Mod={Xref:.5f}  Δ={abs(saved[ts]-Xref):.5f}  {'✅' if ok else '❌'}")
    print("  L3: 4경로 동적, 36cebae서 ΔX=0.0035 검증")
    return all(results)


def sweep_fan():
    """팬 3급 유량 스윕 (분석용, 회귀 아님). 전압 기준 통일 비교.
    L1/L2 dp는 전압, L3는 dP_total(=Pt_fan) 전압 / dP_static(=Ps) 정압.
    ⚠️ L1/L2는 SI(m), L3는 fan-sim(mm) 단위 — 기하는 같은 팬."""
    import math
    g_si = {'D2':0.175,'b2':0.050,'D1':0.120,'b1':0.060,'Z':36,'beta2':145,
            'beta1':30,'N':3000,'eta_h':0.78,'eta_mech':0.95,'f_inc':0.6,'f_fric':0.8}
    g_mm = {'D2':175.0,'b2':50.0,'D1':120.0,'b1':60.0,'Z':36,'beta2':145,
            'beta1':30,'RPM':3000.0}
    D2, b2, N, rho = 0.175, 0.050, 3000, 1.2
    U2 = math.pi * D2 * N / 60

    print("── Fan 유량 스윕 (전압 기준, N=3000) ──")
    print(f"{'m[kg/s]':>8} {'φ':>6} | {'Euler':>7} {'L1':>7} {'L2':>7} {'L3 Pt':>7} {'L3 Ps':>7}"
          f" | {'L1err':>7} {'L2err':>7} | {'eta':>5}")
    for m in [0.03, 0.05, 0.08, 0.10, 0.125, 0.15, 0.16, 0.18, 0.20]:
        inp = {'T_in':20.0, 'omega':0.008, 'm_dot_da':m}
        o1 = fan_on.step(inp, {**g_si,'fidelity':'L1'}, {}, 0)['outputs']
        o2 = fan_on.step(inp, {**g_si,'fidelity':'L2'}, {}, 0)['outputs']
        o3 = fan_on.step(inp, {**g_mm,'fidelity':'L3'}, {}, 0)['outputs']
        phi = (m/rho) / (math.pi * D2 * b2 * U2)
        L3t, L3s = o3['dP_total'], o3['dP_static']
        e1 = (o1['dp']-L3t)/L3t*100
        e2 = (o2['dp']-L3t)/L3t*100
        print(f"{m:>8.3f} {phi:>6.3f} | {o1['dp_t']:>7.1f} {o1['dp']:>7.1f} {o2['dp']:>7.1f}"
              f" {L3t:>7.1f} {L3s:>7.1f} | {e1:>+6.1f}% {e2:>+6.1f}% | {o3['eta']:>5.3f}")
    print("  → L3 eta가 φ 전범위 평탄(0.63~0.67) → fidelity 격차도 안정")
    print("     L1 오차 +2.5~-2.1% (η_h=0.78 일괄이 실제 총손실 ~21%와 근접)")
    print("     L2 오차 +16~+19.5% (입사+마찰만=2.1%, 지배적 스크롤손실 70% 누락)")
    print("  ⚠️ L2 > L1 오차 — fidelity 사다리 비단조. 중간급이 지배물리를")
    print("     빠뜨리면 잘 보정된 일괄모델보다 나쁠 수 있음.")


if __name__ == '__main__':
    print("=" * 60)
    print("공기측 3컴포넌트 × 3급 GT↔Modelica 검증")
    print("=" * 60)
    fan_ok = verify_fan()
    print()
    drum_ok = verify_drum()
    print()
    filt_ok = verify_filter()
    print()
    if '--sweep' in sys.argv:
        sweep_fan()
        print()
    print("=" * 60)
    allok = fan_ok and drum_ok and filt_ok
    print(f"종합: {'✅ 전부 통과' if allok else '❌ 실패 항목 있음'}")
    print(f"  Fan={fan_ok}  Drum={drum_ok}  Filter={filt_ok}")
    sys.exit(0 if allok else 1)
