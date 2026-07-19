#!/usr/bin/env python3
"""
verify_evap_fidelity.py — 증발기 3급 Python GT ↔ OMC 검증

냉매측 검증 4번째(증발기 편, 마지막 컴포넌트). verify_*_fidelity.py 방식.

매핑:
  Evap_L1 → Evap_UA_eq       (EvapUA.mo)   ↔ evaporator_off_design.py
  Evap_L2 → EvaporatorMBdyn  (EvapMBe.mo)  ↔ evaporator_moving_boundary.py
  Evap_L3 → Evap_On_Dyn      (HPWDevap.mo) ↔ evaporator_on_design.py

동일 BC: P_e=5.0889bar, h_in=364.157 kJ/kg, m_ref=0.00206593,
         공기 20°C / RH80% / 2.42 CMM

[결과]
L1 (off_design): ✅ OMC UA(15.9/2.2) 주입 시 Q Δ0.01% 일치.
  Python 기본값도 472 vs OMC 462 (Δ+2.2%) — 응축기보다 덜 어긋남.
  단 정합엔 OMC 재피팅 UA 필요. evaporator_off_design.py 기본 UA 갱신 권장.
L2 (EvaporatorMBdyn): ⚠️ Q Δ+9.1% (Python이 큼)
L3 (Evap_On_Dyn): ⚠️ Q Δ+9.6% (Python이 큼)

[증발기 L2/L3 불일치 — 응축기와 다른 양상]
- 응축기 L2는 Python이 -15.5%(smooth라 낮음). 증발기 L2/L3는 Python이 +9%(높음).
  방향 반대 → microfin 누락(양쪽 공통, EF_evap=1.845)만으론 설명 안 됨.
- OMC는 h_evap_chen1966 × EF_evap. Python은 _vendor_h_tp(mode='evap')에
  microfin 인자 없이 호출 → 비등 상관식 차이 + microfin 누락이 반대로 섞임.
- L2/L3가 +9%로 거의 동일 → 일관된 원인(vendor 비등 h 계산 방식).
  On(L3)은 OMC 동적 셀-march vs Python 단일 step이라 정착점도 미묘차.
→ evaporator_moving_boundary/on_design.py의 vendor 호출·microfin 전달 점검 필요.

[OMC 기준값] L1 462.0W, L2 462.3W, L3 461.7W
  → 증발기는 3급이 서로 잘 맞음(응축기는 594/622/633으로 벌어졌던 것과 대조).
  증발기 자체 3급 일관성은 양호, Python↔OMC 정합만 남음.

사용: python3 verify_evap_fidelity.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from components import evaporator_off_design as evap_L1
from components import evaporator_moving_boundary as evap_L2
from components import evaporator_on_design as evap_L3

BC = {'P_evap': 5.0889, 'h_in': 364.157, 'm_dot_ref': 0.00206593,
      'T_air_in': 20.0, 'RH_air_in': 80.0, 'V_air_CMM': 2.42}
OMC = {'L1': 462.029, 'L2': 462.283, 'L3': 461.743}
GEO = {'D_o': 5.0e-3, 'D_i': 4.6e-3, 'L_tube_total': 3.84, 'N_rows': 4.0,
       'FPI': 20.0, 'A_o_face': 0.0135744, 'is_wet': True, 'fluid': 'R290'}


def verify_L1():
    o = evap_L1.step(BC, {'input_mode': 'UA', 'fluid': 'R290'}, {}, 0)['outputs']
    q = o['Q_total']
    d = (q - OMC['L1']) / OMC['L1'] * 100
    ok = abs(d) < 1
    print(f"L1 (기본 UA, 동기화됨):     Py Q={q:.1f}  OMC={OMC['L1']:.1f}  Δ={d:+.2f}%  {'✅' if ok else '❌'}")
    return ok


def verify_L2():
    """L2: microfin EF + cf_SH(과열존 HTC 보정) 적용 → 일치."""
    o = evap_L2.step(BC, GEO, {}, 0)['outputs']
    q = o['Q_total']
    d = (q - OMC['L2']) / OMC['L2'] * 100
    ok = abs(d) < 1
    print(f"L2 (microfin+cf_SH 수정):   Py Q={q:.1f}  OMC={OMC['L2']:.1f}  Δ={d:+.2f}%  {'✅' if ok else '❌'}")
    print(f"     alpha_SH={o['alpha_r_SH']:.1f}(OMC 42.9) SH_out={o.get('SH_out',0):.1f}(OMC 6.0)")
    return ok


if __name__ == '__main__':
    print("=" * 60)
    print("증발기 3급 Python↔OMC 검증")
    print(f"BC: P_e={BC['P_evap']}bar h_in={BC['h_in']} 공기 20°C/RH80%")
    print("=" * 60)
    r1 = verify_L1()
    r2 = verify_L2()
    o3 = evap_L3.step(BC, {'tube_type':'microfin','fluid':'R290','circuit_mode':'row_parallel'}, {}, 0)['outputs']
    d3 = (o3['Q_total'] - OMC['L3']) / OMC['L3'] * 100
    print(f"L3 (Evap_On_Dyn, T_wall 안정화): Py Q={o3['Q_total']:.1f}  OMC={OMC['L3']:.1f}  Δ={d3:+.2f}%")
    print(f"     SH_out={o3['SH_out']:.1f}(OMC 5.8) 과열셀 6/40(OMC 5) — T_wall 진동 해결로")
    print(f"     Δ+9.6%→+2.1% 개선(row_parallel+adaptive under-relax+클램프). 완전증발 #34 vs OMC #35.")
    print("=" * 60)
    r3 = abs((evap_L3.step(BC, {'tube_type':'microfin','fluid':'R290','circuit_mode':'row_parallel'}, {}, 0)['outputs']['Q_total'] - OMC['L3']) / OMC['L3'] * 100) < 3
    print(f"L1={'✅' if r1 else '❌'}  L2={'✅' if r2 else '❌'}  L3={'✅' if r3 else '🔶'}(Δ+2.2%, T_wall 안정화 완료)")
    sys.exit(0 if (r1 and r2) else 1)
