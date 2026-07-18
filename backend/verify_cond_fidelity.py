#!/usr/bin/env python3
"""
verify_cond_fidelity.py — 응축기 3급 Python GT ↔ OMC 검증 (진행중, 불일치 3건 문서화)

냉매측 검증 3번째(응축기 편). 압축기·EEV와 달리 3급 모두 불일치 발견,
원인이 각각 다름. 이 스크립트는 현 상태를 기록 — 수정은 별도 진행.

매핑:
  Cond_L1 → Cond_UA_eq   (EvapUA.mo)   ↔ condenser_off_design.py
  Cond_L2 → CondenserSS  (CondMBe.mo)  ↔ condenser_moving_boundary.py
  Cond_L3 → Cond_On_Dyn  (HPWDevap.mo) ↔ condenser_on_design.py

동일 BC: P_c=9.8762bar, h_in=651.260 kJ/kg, m_ref=0.00206593,
         공기 14.474°C / RH99% / 2.42 CMM

[불일치 3건 — 원인 규명됨, 수정 대기]
L1 (off_design): ⚠️ 파라미터 동기화 누락
  OMC Cond_UA_eq는 CmpParts BC로 UA 재피팅(UA_deSH=15.5/UA_2ph=280/UA_SC=0.5).
  Python 기본값은 옛 값(8/50/5). → OMC 값 주입 시 Q Δ0.32%로 일치 확인.
  즉 모델 동일, 파라미터만 어긋남. condenser_off_design.py 기본 UA 갱신 필요.
L2 (moving_boundary = CondenserSS): ⚠️ microfin EF 누락
  OMC: alpha = h_cond_shah1979(...) × EF_cond (microfin 강화, EF_cond=1.917,
    EF_single=1.631). Python은 _vendor_h_tp 호출에 tube_type/microfin 인자 없이
    smooth로 계산. → Q Δ-15.5%. condenser_moving_boundary.py가 vendor에
    microfin 전달하도록 수정 필요.
L3 (on_design = Cond_On_Dyn): ⚠️ Q Δ-9.1% + 출력 키 이상
  condenser_on_design.py 출력에 SH_out/T_evap(증발기 변수명) 존재 —
  파일이 증발기 기반으로 만들어졌을 가능성. 별도 정밀 조사 필요.

공통 패턴: OMC 모델은 L3 물리/피팅으로 정비됐으나 Python GT가 그 정비에서
  빠진 채 옛 버전(파라미터/상관식/구조)으로 남음. 압축기 L3 rho_su,
  EEV L1 φ와 동일한 성격의 'Python GT 방치'.

OMC 기준값 (참고):
  L1 Q=594.4W (deSH 101.3 + 2ph 493.1), L2 Q=621.9W, L3 Q=633.0W
  → 급 상승할수록 Q 증가(더 정밀).

사용: python3 verify_cond_fidelity.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from components import condenser_off_design as cond_L1

BC = {'P_cond': 9.8762, 'h_in': 651.260, 'm_dot_ref': 0.00206593,
      'T_air_in': 14.474, 'RH_air_in': 99.0, 'V_air_CMM': 2.42}
OMC = {'L1': 594.404, 'L2': 621.907, 'L3': 633.036}


def verify_L1_with_omc_params():
    """L1은 OMC 재피팅 UA를 주면 일치 — 파라미터 동기화 문제 입증."""
    par = {'input_mode': 'UA', 'UA_deSH': 15.5, 'UA_2ph': 280.0, 'UA_SC': 0.5,
           'dP_ref': 0.03, 'fluid': 'R290'}
    o = cond_L1.step(BC, par, {}, 0)['outputs']
    q = o['Q_total']
    d = (q - OMC['L1']) / OMC['L1'] * 100
    print(f"L1 (OMC UA 주입): Py Q={q:.1f}  OMC={OMC['L1']:.1f}  Δ={d:+.2f}%  "
          f"{'✅ 파라미터 동기화만 필요' if abs(d) < 1 else '❌'}")
    return abs(d) < 1


if __name__ == '__main__':
    print("=" * 60)
    print("응축기 3급 Python↔OMC 검증 (진행중)")
    print(f"BC: P_c={BC['P_cond']}bar h_in={BC['h_in']} 공기 14.474°C/RH99%")
    print("=" * 60)
    verify_L1_with_omc_params()
    print()
    print("L2 (CondenserSS): microfin EF 누락 → Q Δ-15.5% (수정 대기)")
    print("L3 (Cond_On_Dyn): Q Δ-9.1% + 출력 키에 증발기 변수명 (조사 대기)")
    print("=" * 60)
    print("→ 3급 모두 'Python GT 방치' 패턴. L1은 파라미터, L2는 microfin,")
    print("  L3는 구조 의심. 압축기 L3·EEV L1과 동일 성격. 수정은 별도 진행.")
