#!/usr/bin/env python3
"""L3 셀 대조 하네스 — Python GT(HX-Sim) 응축기 셀별 덤프.

GT 코드 무수정: HXSolver.solve 를 monkey-patch 래핑해 SimulationResult /
solver 객체를 캡처. wrapper(condenser_on_design.step) 경유라 입력 조립
로직 drift 없음.

BC: CmpParts.mo 응축기 조건
  P_c=9.8762 bar, h_in=651.260 kJ/kg, mdot=2.06593 g/s
  공기 14.474 degC / RH 0.99 / 2.42 CMM

출력: /tmp/py_cond_cells.json (stderr 로 요약)
"""
import sys, os, json, io
from contextlib import redirect_stdout

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, '..', '..', 'backend'))

import _vendor.hx_sim.solver as hxs

_captured = {}
_orig_solve = hxs.HXSolver.solve

def _patched_solve(self):
    r = _orig_solve(self)
    _captured['result'] = r
    _captured['solver'] = self
    return r

hxs.HXSolver.solve = _patched_solve

buf = io.StringIO()
with redirect_stdout(buf):
    from components import condenser_on_design as cond

    inp = dict(
        P_cond=9.8762,        # bar
        h_in=651.260,         # kJ/kg
        m_dot_ref=0.00206593, # kg/s
        T_air_in=14.474,      # degC
        RH_air_in=99.0,       # %
        V_air_CMM=2.42,
    )
    out = cond.step(inp, {}, {}, 0.0)

res = _captured['result']
solver = _captured['solver']
geo = solver.geo

Nr, Nt, Nseg = solver.Nr, solver.Nt, solver.N_seg
A_i_seg = geo.A_i_seg
A_o_seg = geo.A_total / (Nr * Nt * Nseg)

segs = []
for s in res.segments:
    ua = 0.0
    if s.h_i > 0 and s.h_o > 0 and s.eta_o > 0:
        ua = 1.0 / (1.0 / (s.eta_o * s.h_o * A_o_seg) + 1.0 / (s.h_i * A_i_seg))
    segs.append(dict(
        row=s.row, tube=s.tube, seg=s.seg,
        Q=s.Q, T_wall=s.T_wall - 273.15,
        T_air=s.T_air_local - 273.15, T_ref=s.T_ref - 273.15,
        x=s.x_ref, h_i=s.h_i, h_o=s.h_o, eta_o=s.eta_o,
        UA=ua, P_local=s.P_local, is_wet=bool(s.is_wet),
    ))

dump = dict(
    bc=inp,
    outputs=out['outputs'],
    geom=dict(Nr=Nr, Nt=Nt, Nseg=Nseg,
              A_i_seg=A_i_seg, A_o_seg=A_o_seg,
              A_i_total=geo.A_i, A_o_total=geo.A_total),
    n_segments=len(segs),
    segments=segs,
    circuit_paths=getattr(res, 'circuit_paths', []),
)

with open('/tmp/py_cond_cells.json', 'w') as f:
    json.dump(dump, f, indent=1)

print(f"Q_total={out['outputs']['Q_total']:.1f} W  "
      f"h_out={out['outputs']['h_ref_out']:.2f} kJ/kg  "
      f"x_out={out['outputs']['quality_out']:.4f}", file=sys.stderr)
print(f"segments={len(segs)}  Nr={Nr} Nt={Nt} Nseg={Nseg}  "
      f"A_i_seg={A_i_seg:.10f}  A_o_seg={A_o_seg:.10f}", file=sys.stderr)
print(f"h_i range: {min(s['h_i'] for s in segs):.1f} ~ {max(s['h_i'] for s in segs):.1f}  "
      f"h_o={segs[0]['h_o']:.2f}  eta_o={segs[0]['eta_o']:.4f}", file=sys.stderr)
