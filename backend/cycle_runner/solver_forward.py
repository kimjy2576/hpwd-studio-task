"""solver_forward — 정방향 플랜트 solver (프로토타입, L3 우선).

역방향 solver.py는 SH_target을 지정해 P_evap을 역산 (정상상태 A-2용).
이 정방향 solver는 개도(opening)를 입력으로, SH를 출력으로 계산.
세 번째 닫힘 조건은 충전량 보존 (ΣM_holdup = M_charge).

  입력:  N, opening, 공기BC, M_charge
  미지수: P_evap, P_cond, h_suc
  방정식:
    (1) 질량연속:   m_comp = m_eev       → P_evap 갱신
    (2) 충전량보존: ΣM_holdup = M_charge  → P_cond 갱신
    (3) 엔탈피폐합: h_suc = h_evap_out     → h_suc 갱신
  출력: SH, SC (강제 안 함 — 결과로 나옴)

⚠️ 프로토타입: M_charge = HX holdup 합만 (배관·오일 용해 제외).
   절대 충전량(R290 100g) 정합은 오일 용해 모델 후 (별도).
   여기선 정방향 수렴 + 개도→SH 반응 + 역방향 정합 검증이 목적.

L2/L3만 (L1은 M_holdup 없음 → SC 대체 예정, 보류).
"""
import io
import contextlib

from .refrigerant_loop import one_pass


def _total_holdup(r):
    """one_pass 결과에서 ΣM_holdup [kg] (응축기+증발기)."""
    mc = r['condenser'].get('M_holdup') or 0.0
    me = r['evaporator'].get('M_holdup') or 0.0
    return mc + me


def solve(fidelity, operating, air_bc, M_charge,
          max_iter=200,
          tol_mass=1e-5, tol_charge=1e-5, tol_enthalpy=0.5,
          P_evap_bounds=(3.5, 6.2), P_cond_bounds=(6.0, 20.0),
          gain_pevap=0.05, gain_pcond=0.3, alpha_h=0.5,
          verbose=False):
    """정방향 수렴. 개도는 operating['opening']에 (입력).

    Args:
      fidelity: {'compressor','condenser','eev','evaporator'} 각 2/3 (L1 미지원)
      operating: {'P_evap','P_cond','N','opening','h_suc','T_amb'} (초기추정+입력)
      air_bc: {'condenser':{...}, 'evaporator':{...}}
      M_charge: 목표 충전량 [kg] (ΣM_holdup 목표)
      P_evap_bounds: P_evap 범위 [bar] — 상한 넘으면 holdup 폭증 주의

    Returns:
      dict: {'converged','iterations','P_evap','P_cond','h_suc',
             'SH_evap','SC_cond','M_total','state'}
    """
    P_evap = operating['P_evap']
    P_cond = operating['P_cond']
    N = operating['N']
    opening = operating['opening']
    h_suc = operating['h_suc']
    T_amb = operating['T_amb']

    def _op(pe, pc, hs):
        return {'P_evap': pe, 'P_cond': pc, 'N': N,
                'opening': opening, 'h_suc': hs, 'T_amb': T_amb}

    converged = False
    it = 0
    r = None
    for it in range(max_iter):
        r = one_pass(fidelity, _op(P_evap, P_cond, h_suc), air_bc, None)
        rm = r['residual']['mass']              # m_comp - m_eev
        re = r['residual']['enthalpy']          # h_evap_out - h_suc
        M_tot = _total_holdup(r)
        rc = M_tot - M_charge                    # 충전량 잔차

        if abs(rm) < tol_mass and abs(rc) < tol_charge and abs(re) < tol_enthalpy:
            converged = True
            break

        # ── 갱신 (짝짓기) ──
        # 엔탈피폐합 → h_suc
        h_suc = h_suc + alpha_h * (r['h_evap_out'] - h_suc)
        # 질량연속 → P_evap
        #   rm = m_comp - m_eev. m_eev는 개도·P_cond·P_evap 함수.
        #   P_evap↑ → 압축기 흡입밀도↑ → m_comp↑, 동시에 EEV ΔP↓ → m_eev↓
        #   경험상 rm>0(comp>eev)면 P_evap 낮춰 comp 줄이거나 eev 늘림
        P_evap = P_evap - rm * gain_pevap * 1000.0   # 스케일 (rm ~1e-3)
        P_evap = min(P_evap_bounds[1], max(P_evap_bounds[0], P_evap))
        # 충전량보존 → P_cond
        #   rc>0 (holdup 과다) → P_cond 낮춰 응축액 줄임
        P_cond = P_cond - rc * gain_pcond * 1000.0   # 스케일
        P_cond = min(P_cond_bounds[1], max(P_cond_bounds[0], P_cond))

        if verbose and it % 10 == 0:
            print(f"  it{it}: P_evap={P_evap:.4f} P_cond={P_cond:.4f} "
                  f"질량={rm:+.6f} 충전={rc*1000:+.3f}g 엔탈피={re:+.2f} "
                  f"SH={r['SH_evap']:.2f} ΣM={M_tot*1000:.2f}g")

    # 과냉 SC (응축기 출구) — 결과
    SC = r['condenser'].get('SC_out', r['condenser'].get('subcool'))
    return {
        'converged': converged, 'iterations': it + 1,
        'P_evap': P_evap, 'P_cond': P_cond, 'h_suc': h_suc,
        'SH_evap': r['SH_evap'], 'SC_cond': SC,
        'M_total': _total_holdup(r),
        'state': r,
    }
