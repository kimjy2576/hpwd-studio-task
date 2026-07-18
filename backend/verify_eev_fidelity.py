#!/usr/bin/env python3
"""
verify_eev_fidelity.py — EEV 3급 Python GT ↔ OMC 검증

냉매측 검증 (EEV 편). verify_comp_fidelity.py와 같은 방식.
각 급의 Python step()을 OMC CmpParts.Eev_L{1,2,3}과 동일 BC서 대조.

매핑:
  Eev_L1 → EEV_Orifice_ctrl (Cycle.mo)  ↔ eev_off_design.py
  Eev_L2 → EEV_MB           (EevMB.mo)  ↔ eev_moving_boundary.py
  Eev_L3 → EEV_On           (HPWDon.mo) ↔ eev_on_design.py

동일 BC (CmpParts 정착점):
  opening=23.586%, P_in=9.8762 bar, P_out=5.0889 bar, h_in=363.087 kJ/kg

✅ L1 Python φ 버그 수정됨 (커밋 시점):
  EEV_Orifice_ctrl(OMC)은 φ를 needle-cone 물리로 통일(A_cone/A_max)했으나
  eev_off_design.py(Python)은 근거불명 큐빅(c0~c3) 그대로 방치였음.
  → opening 50%서 φ 0.35(큐빅) vs 1.00(cone)로 완전히 다른 곡선.
  eev_off_design.py의 _phi를 needle-cone(_phi_needle)으로 교체 → m_dot Δ0.01%.

L2/L3는 cf_A(면적보정)가 OMC서 L3 needle-cone에 피팅된 상태로 Python도 동일값.

사용: python3 verify_eev_fidelity.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'components'))
import eev_off_design as eev_L1
import eev_moving_boundary as eev_L2
import eev_on_design as eev_L3

BC = {'P_in': 9.8762, 'h_in': 363.087, 'P_out': 5.0889, 'opening': 23.586}

OMC = {
    'L1': {'m_dot': 0.00209647, 'phi': 0.471718, 'rho_in': 68.2514},
    'L2': {'m_dot': 0.00207977, 'Cd_eff': 0.619758, 'is_choked': 1},
    'L3': {'m_dot': 0.00207765, 'Cd_eff': 0.693718, 'rho_in': 68.2514},
}
TOL = 1.0  # %


def verify_L1():
    print("── L1 (off_design = EEV_Orifice_ctrl) ──  φ needle-cone 수정 적용")
    par = {'A_orifice': 0.7854, 'Cv_rated': 0.7, 'mode': 'control', 'fluid': 'R290'}
    o = eev_L1.step(BC, par, {}, 0)['outputs']
    ok = True
    for pk, ok_key in [('m_dot_ref', 'm_dot'), ('phi_op', 'phi'), ('rho_in', 'rho_in')]:
        pv, ov = o[pk], OMC['L1'][ok_key]
        d = abs(pv - ov) / ov * 100
        p = d < TOL
        ok &= p
        print(f"  {ok_key:<8} Py={pv:.6f}  OMC={ov:.6f}  Δ={d:.2f}%  {'✅' if p else '❌'}")
    return ok


def verify_L2():
    print("── L2 (moving_boundary = EEV_MB) ──  cf_A=2.327 (L3 정합)")
    par = {'A_orifice': 0.785, 'Cd_0': 0.70, 'Re_c': 5000.0, 'k_sub': 0.05,
           'k_op': 0.15, 'Y_crit': 0.55, 'cf_A': 2.327, 'use_choke': 'on', 'fluid': 'R290'}
    o = eev_L2.step(BC, par, {}, 0)['outputs']
    ok = True
    for pk, ok_key in [('m_dot_ref', 'm_dot'), ('Cd_eff', 'Cd_eff'), ('is_choked', 'is_choked')]:
        pv, ov = o[pk], OMC['L2'][ok_key]
        d = abs(pv - ov) / (abs(ov) if ov else 1) * 100
        p = d < TOL
        ok &= p
        print(f"  {ok_key:<10} Py={pv:.5f}  OMC={ov:.5f}  Δ={d:.2f}%  {'✅' if p else '❌'}")
    print("  (Re는 D_h 정의차로 다르나 f_Re가 이미 1 포화 → Cd 무영향)")
    return ok


def verify_L3():
    print("── L3 (on_design = EEV_On) ──  needle-cone geometry")
    par = {'D_seat': 1.0e-3, 'stroke_max': 1.0e-3, 'needle_angle': 30.0, 'cf_A': 1.0,
           'Cd_base': 0.70, 'Re_transition': 1000.0, 'needle_profile': 'cone', 'fluid': 'R290'}
    o = eev_L3.step(BC, par, {}, 0)['outputs']
    # A_throat은 mm² 단위 출력 → SI 변환, m_dot은 이미 kg/s
    m_dot = o['m_dot_ref']
    ok = True
    checks = [('m_dot', m_dot, OMC['L3']['m_dot']),
              ('Cd_eff', o['Cd_eff'], OMC['L3']['Cd_eff']),
              ('rho_in', o['rho_in'], OMC['L3']['rho_in'])]
    for lbl, pv, ov in checks:
        d = abs(pv - ov) / (abs(ov) if ov else 1) * 100
        p = d < TOL
        ok &= p
        print(f"  {lbl:<8} Py={pv:.6f}  OMC={ov:.6f}  Δ={d:.2f}%  {'✅' if p else '❌'}")
    return ok


if __name__ == '__main__':
    print("=" * 58)
    print("EEV 3급 Python GT ↔ OMC 검증")
    print(f"BC: opening={BC['opening']}% P_in={BC['P_in']}bar P_out={BC['P_out']}bar")
    print("=" * 58)
    r1 = verify_L1(); print()
    r2 = verify_L2(); print()
    r3 = verify_L3(); print()
    print("=" * 58)
    print(f"L1={'✅' if r1 else '❌'}  L2={'✅' if r2 else '❌'}  L3={'✅' if r3 else '❌'}")
    sys.exit(0 if (r1 and r2 and r3) else 1)
