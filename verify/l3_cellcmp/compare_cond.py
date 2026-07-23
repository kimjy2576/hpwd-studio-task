#!/usr/bin/env python3
"""L3 셀 대조 — 응축기: Python GT vs OMC Cond_On_Dyn 정착값.

정렬:
  Python: circuit_paths[0] 순서 (240셀 직렬 여부는 측정으로 확인됨)
  OMC:    path k=1..M (M=Nr*Nseg=60/컬럼), pathRow/pathSeg 재현으로 (p,s) 매핑
  경로분율 xi=(j-0.5)/N 로 정규화해 병렬 비교 + x(건도) 구간별 h_i 통계

사용: python3 compare_cond.py <omc_res.csv>
"""
import sys, json, csv, math

PY_JSON = '/tmp/py_cond_cells.json'
Nr_M, Nseg_M = 6, 10          # Modelica Cond_On_Dyn
M = Nr_M * Nseg_M

def path_row(k0):  # Modelica pathRow 재현 (1-based p)
    return Nr_M - k0 // Nseg_M

def path_seg(k0):
    pp, j = divmod(k0, Nseg_M)
    return j + 1 if pp % 2 == 0 else Nseg_M - j

# ── OMC mat (dymola v1.1): name/dataInfo/data_1(param)/data_2(시계열) ──
from scipy.io import loadmat
m = loadmat(sys.argv[1], matlab_compatible=True)
names = [''.join(m['name'][:, i]).strip() for i in range(m['name'].shape[1])]
di = m['dataInfo']            # [2 x nvar]: row0=which data block, row1=col(1-based, 부호=방향)
d1, d2 = m['data_1'], m['data_2']

def val(nm, at=-1):
    i = names.index(nm)
    blk, col = int(di[0, i]), int(di[1, i])
    sgn = 1.0 if col > 0 else -1.0
    c = abs(col) - 1
    if blk == 1:
        return sgn * d1[c, 0]      # parameter: 상수
    return sgn * d2[c, at]         # 시계열: at 시점

class _V:
    def __getitem__(self, k): return val(k)
    def get(self, k, dflt=float('nan')):
        return val(k) if k in names else dflt

class _Vp:
    def __getitem__(self, k): return val(k, at=-2)

V, Vp = _V(), _Vp()

def arr(base, n):
    return [V.get(f'{base}[{k}]', float('nan')) for k in range(1, n + 1)]

o_hi   = arr('cond.h_i', M)
o_Tref = arr('cond.T_ref', M)
o_xq   = arr('cond.xq', M)
o_Qref = arr('cond.Q_ref', M)
o_Qair = arr('cond.Q_air', M)
o_Tw   = arr('cond.T_w', M)
o_href = arr('cond.h_ref', M)

# 정착 확인 (마지막 두 출력점 Q_total 변화)
q_now, q_prev = V['cond.Q_total'], Vp['cond.Q_total']
settle = abs(q_now - q_prev) / max(abs(q_now), 1e-9) * 100

o = dict(
    Q_total=V['cond.Q_total'], h_out=V['cond.h_out'] / 1e3, x_out=V['cond.x_out'],
    T_air_out=V['cond.T_air_out'], h_o=V['cond.h_o'], eta_o=V['cond.eta_o_dry'],
    A_i_seg=V['cond.A_i_seg'], A_o_seg=V['cond.A_o_seg'],
    G_ref=V['cond.G_ref'], m_ref_col=V['cond.m_ref_col'],
    EF_2ph=V.get('cond.EF_2ph', float('nan')), EF_sgl=V.get('cond.EF_sgl', float('nan')),
)

# T_air(셀 진입) — path k → (p,s) → T_aen[p,s]
o_Tair = [V.get(f'cond.T_aen[{path_row(k)},{path_seg(k)}]', float('nan')) for k in range(M)]

# OMC UA 합성 (진단용, dry): 1/(1/(eta*ho*Ao) + 1/(hi*Ai))
o_UA = [1.0 / (1.0 / (o['eta_o'] * o['h_o'] * o['A_o_seg']) + 1.0 / (h * o['A_i_seg']))
        if h > 0 else 0.0 for h in o_hi]

# ── Python ──
d = json.load(open(PY_JSON))
pseg = {(s['row'], s['tube'], s['seg']): s for s in d['segments']}
path = d['circuit_paths'][0]              # [[tube,row,seg],...]
p_cells = [pseg[(r, t, s)] for (t, r, s) in path]
Np = len(p_cells)
pg = d['geom']

print('=' * 100)
print('전역 대조 — 응축기 (BC: P_c 9.8762 bar / h_in 651.26 kJ/kg / mdot 2.06593 g/s / 공기 14.474C RH99 2.42CMM)')
print('=' * 100)
py_o = d['outputs']
rows_g = [
    ('Q_total [W]',  py_o['Q_total'], o['Q_total']),
    ('h_out [kJ/kg]', py_o['h_ref_out'], o['h_out']),
    ('x_out [-]',    py_o['quality_out'], o['x_out']),
    ('T_air_out [C]', py_o['T_air_out'], o['T_air_out']),
    ('A_i_seg [m2]', pg['A_i_seg'], o['A_i_seg']),
    ('A_o_seg [m2]', pg['A_o_seg'], o['A_o_seg']),
    ('A_o_total[m2]', pg['A_o_total'], o['A_o_seg'] * M * 4),
    ('h_o [W/m2K]',  p_cells[0]['h_o'], o['h_o']),
    ('eta_o [-]',    p_cells[0]['eta_o'], o['eta_o']),
    ('G_ref[kg/m2s]', 0.00206593 / (math.pi * 0.0046 ** 2 / 4) / len(d['circuit_paths']), o['G_ref']),
]
print(f"{'항목':<15}{'Python GT':>14}{'OMC':>14}{'OMC/Py':>9}")
for name, pv, ov in rows_g:
    r = ov / pv if pv else float('nan')
    print(f"{name:<15}{pv:>14.5g}{ov:>14.5g}{r:>9.3f}")
print(f"\nOMC 정착도: 마지막 두 출력점 Q_total 변화 {settle:.3f}%  (t_end Q={q_now:.1f} W)")
print(f"Python 회로: {len(d['circuit_paths'])}개 직렬경로 x {Np}셀  | OMC: 4병렬 x {M}셀")

# ── 경로분율 병렬 테이블 ──
print()
print('=' * 100)
print('경로분율 xi별 셀값 (Py: 240셀 직렬 / OMC: 60셀·컬럼)  [T:degC, Q:W/셀]')
print('=' * 100)
print(f"{'xi':>5} | {'x_Py':>6}{'x_OM':>7} | {'hi_Py':>8}{'hi_OM':>8}{'비':>6} | "
      f"{'UA_Py':>7}{'UA_OM':>7}{'비':>6} | {'Tref_Py':>8}{'Tref_OM':>8} | "
      f"{'Tair_Py':>8}{'Tair_OM':>8} | {'Q_Py':>6}{'Q_OM':>7}")

def pick(cells, xi):
    j = min(int(xi * len(cells)), len(cells) - 1)
    return cells[j], j

for xi100 in range(2, 100, 7):
    xi = xi100 / 100.0
    pc, _ = pick(p_cells, xi)
    ko = min(int(xi * M), M - 1)
    hi_r = o_hi[ko] / pc['h_i'] if pc['h_i'] else float('nan')
    ua_r = o_UA[ko] / pc['UA'] if pc['UA'] else float('nan')
    print(f"{xi:>5.2f} | {pc['x']:>6.3f}{o_xq[ko]:>7.3f} | "
          f"{pc['h_i']:>8.1f}{o_hi[ko]:>8.1f}{hi_r:>6.2f} | "
          f"{pc['UA']:>7.3f}{o_UA[ko]:>7.3f}{ua_r:>6.2f} | "
          f"{pc['T_ref']:>8.2f}{o_Tref[ko]:>8.2f} | "
          f"{pc['T_air']:>8.2f}{o_Tair[ko]:>8.2f} | "
          f"{pc['Q']:>6.2f}{o_Qref[ko]:>7.2f}")

# ── x 구간별 h_i 통계 (경로 정렬 무관 비교) ──
print()
print('=' * 100)
print('건도 구간별 h_i 평균 [W/m2K] — 경로/셀수 정렬과 무관한 상태공간 비교')
print('=' * 100)
bins = [('SH  x>=1', lambda x: x >= 1.0),
        ('2ph 0.66-1', lambda x: 0.66 <= x < 1.0),
        ('2ph 0.33-0.66', lambda x: 0.33 <= x < 0.66),
        ('2ph 0-0.33', lambda x: 0.0 < x < 0.33),
        ('SC  x<=0', lambda x: x <= 0.0)]
print(f"{'구간':<15}{'n_Py':>6}{'hi_Py':>10}{'n_OM':>6}{'hi_OM':>10}{'OM/Py':>8}")
for name, cond_f in bins:
    ps = [c['h_i'] for c in p_cells if cond_f(c['x'])]
    os_ = [h for h, x in zip(o_hi, o_xq) if cond_f(x)]
    mp = sum(ps) / len(ps) if ps else float('nan')
    mo = sum(os_) / len(os_) if os_ else float('nan')
    r = mo / mp if ps and os_ else float('nan')
    print(f"{name:<15}{len(ps):>6}{mp:>10.1f}{len(os_):>6}{mo:>10.1f}{r:>8.2f}")

# 셀당 면적·전열 스택 요약
print()
print('스택 확인:  UA·(T_ref-T_air) 합 vs Q_total')
q_py_sum = sum(c['Q'] for c in p_cells)
q_om_sum = sum(o_Qref) * 4
print(f"  Py  sum(Q_seg)={q_py_sum:.1f} W  (result {py_o['Q_total']:.1f})")
print(f"  OMC 4*sum(Q_ref)={q_om_sum:.1f} W  (Q_total {o['Q_total']:.1f})")
