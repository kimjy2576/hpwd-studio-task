#!/usr/bin/env python3
"""냉매 (p,h) 물성표 생성기 — CoolProp → Modelica 패키지(.mo)

목적
  R290Tab.mo 와 동일 구조의 표형 매질 패키지를 임의 냉매에 대해 자동 생성.
  ExternalMedia(CoolProp 런타임 호출)는 정확하지만 9~18배 느림(2026-07-23 실측).
  표 보간은 1배 속도를 유지하면서 냉매 자유도를 얻는 절충.

설계
  함수 32개(보간 로직)는 냉매 무관이므로 **템플릿 .mo에서 그대로 재사용**하고,
  상수 블록(포화 배열 20종 + 2D 표 11종)만 교체한다. 함수를 재작성하지 않으므로
  전사 오류 위험이 없다.

사용
  python3 tools/gen_media_table.py --fluid Propane --package R290Tab \
      --out modelica/R290Tab.mo
  python3 tools/gen_media_table.py --fluid R1234yf --package R1234yfTab \
      --out modelica/R1234yfTab.mo --P1 3.0e6

  검증(기존 파일과 대조, 파일 미기록):
  python3 tools/gen_media_table.py --fluid Propane --package R290Tab \
      --verify modelica/R290Tab.mo

주의
  - P1 은 임계압 미만이어야 한다(포화 배열이 정의되지 않음). 기본은 0.85·Pcrit.
  - 2상 영역에서 T=Tsat, rho는 quality 혼합. 도함수는 중심차분.
  - 기준상태는 CoolProp 기본값. 기존 R290Tab.mo 와 일치함을 확인함(2026-07-23).
"""
import argparse
import math
import re
import sys

import CoolProp.CoolProp as CP

SAT_KEYS = ['Tsat', 'hl', 'hv', 'rhol', 'rhov', 'dTsdp', 'dhldp', 'dhvdp',
            'drholdp', 'drhovdp', 'mul', 'kl', 'cpl', 'muv', 'kv', 'cpv',
            'sl', 'sv', 'cvl', 'cvv']
TBL_KEYS = ['T', 'rho', 'drdp', 'drdh', 'dTdp', 'dTdh', 'mu', 'k', 'cp', 's', 'cv']
# PHg: 상영역 격자 — 1=과냉, 0=2상, 2=과열. bilinC가 상경계를 넘는 코너를
# 포화값으로 대체해 2상 안전 보간을 하는 데 사용.


def _fmt(x, sig=7):
    """Modelica 리터럴 — 기존 파일과 같은 유효숫자(7) 표기."""
    if x != x or math.isinf(x):
        raise ValueError(f"비유한 값: {x}")
    s = f"{x:.{sig}g}"
    return s


def sat_props(fluid, P):
    """포화선 물성 + dp 도함수(중심차분)."""
    g = lambda k, q, p=P: CP.PropsSI(k, 'P', p, 'Q', q, fluid)
    dP = max(P * 1e-4, 1.0)
    Pm, Pp = P - dP, P + dP
    out = {
        'Tsat': g('T', 0), 'hl': g('H', 0), 'hv': g('H', 1),
        'rhol': g('D', 0), 'rhov': g('D', 1),
        'mul': g('V', 0), 'kl': g('L', 0), 'cpl': g('C', 0),
        'muv': g('V', 1), 'kv': g('L', 1), 'cpv': g('C', 1),
        'sl': g('S', 0), 'sv': g('S', 1),
        'cvl': g('O', 0), 'cvv': g('O', 1),
    }
    out['dTsdp'] = (g('T', 0, Pp) - g('T', 0, Pm)) / (2 * dP)
    out['dhldp'] = (g('H', 0, Pp) - g('H', 0, Pm)) / (2 * dP)
    out['dhvdp'] = (g('H', 1, Pp) - g('H', 1, Pm)) / (2 * dP)
    out['drholdp'] = (g('D', 0, Pp) - g('D', 0, Pm)) / (2 * dP)
    out['drhovdp'] = (g('D', 1, Pp) - g('D', 1, Pm)) / (2 * dP)
    return out


def state_ph(fluid, P, h, sat):
    """(P,h) 1점 물성. 2상 내부는 quality 혼합, 외부는 CoolProp 직접."""
    hl, hv = sat['hl'], sat['hv']
    if hl < h < hv:                      # 2상
        x = (h - hl) / (hv - hl)
        rl, rv = sat['rhol'], sat['rhov']
        v = x / rv + (1 - x) / rl
        return {
            'T': sat['Tsat'], 'rho': 1.0 / v,
            'mu': x * sat['muv'] + (1 - x) * sat['mul'],
            'k': x * sat['kv'] + (1 - x) * sat['kl'],
            'cp': x * sat['cpv'] + (1 - x) * sat['cpl'],
            's': x * sat['sv'] + (1 - x) * sat['sl'],
            'cv': x * sat['cvv'] + (1 - x) * sat['cvl'],
        }
    f = lambda k, p=P, hh=h: CP.PropsSI(k, 'P', p, 'H', hh, fluid)
    return {'T': f('T'), 'rho': f('D'), 'mu': f('V'), 'k': f('L'),
            'cp': f('C'), 's': f('S'), 'cv': f('O')}


def derivs_ph(fluid, P, h, sat, dsat):
    """(P,h)에서 dT/dp, dT/dh, drho/dp, drho/dh.

    2상: 해석해 (T=Tsat이므로 dT/dh=0, dT/dp=dTsat/dp;
         rho는 quality 혼합의 해석 미분).
    단상: 중심차분, 단 섭동이 상경계를 넘으면 한쪽차분으로 대체
         (넘으면 물성이 불연속이라 차분이 무의미해짐 —
          레거시 R290Tab의 2상 도함수 손상 원인으로 추정).
    """
    hl, hv = sat['hl'], sat['hv']
    if hl < h < hv:                                  # ── 2상 해석해 ──
        rl, rv, HFG = sat['rhol'], sat['rhov'], hv - hl
        x = (h - hl) / HFG
        v = x / rv + (1 - x) / rl
        rho = 1.0 / v
        dvdh = (1.0 / rv - 1.0 / rl) / HFG
        dxdp = (-dsat['dhldp'] * HFG - (h - hl) * (dsat['dhvdp'] - dsat['dhldp'])) / HFG ** 2
        dvdp = (dxdp * (1.0 / rv - 1.0 / rl)
                - x * dsat['drhovdp'] / rv ** 2
                - (1 - x) * dsat['drholdp'] / rl ** 2)
        return {'dTdp': dsat['dTsdp'], 'dTdh': 0.0,
                'drdp': -rho ** 2 * dvdp, 'drdh': -rho ** 2 * dvdh}

    # ── 단상: 상경계를 넘지 않는 차분 ──
    f = lambda k, p, hh: CP.PropsSI(k, 'P', p, 'H', hh, fluid)
    sub = h <= hl
    eH = max(abs(hv - hl) * 1e-4, 1.0)
    lo, hi = h - eH, h + eH
    if sub and hi >= hl:                 # 위로 넘음 → 후방차분
        lo, hi = h - 2 * eH, h
    elif (not sub) and lo <= hv:         # 아래로 넘음 → 전방차분
        lo, hi = h, h + 2 * eH
    dTdh = (f('T', P, hi) - f('T', P, lo)) / (hi - lo)
    drdh = (f('D', P, hi) - f('D', P, lo)) / (hi - lo)

    eP = max(P * 1e-4, 1.0)
    Pl, Ph = P - eP, P + eP
    sl_, sh_ = sat_props(fluid, Pl), sat_props(fluid, Ph)
    inphase = lambda s: (h <= s['hl']) if sub else (h >= s['hv'])
    if not inphase(sl_):                 # P- 에서 상이 바뀜 → 전방차분
        Pl = P; sl_ = sat
    if not inphase(sh_):                 # P+ 에서 상이 바뀜 → 후방차분
        Ph = P; sh_ = sat
    if Ph == Pl:                         # 양쪽 다 불가 (극히 얇은 영역)
        return {'dTdp': dsat['dTsdp'], 'dTdh': dTdh, 'drdp': 0.0, 'drdh': drdh}
    dTdp = (f('T', Ph, h) - f('T', Pl, h)) / (Ph - Pl)
    drdp = (f('D', Ph, h) - f('D', Pl, h)) / (Ph - Pl)
    return {'dTdp': dTdp, 'dTdh': dTdh, 'drdp': drdp, 'drdh': drdh}


def build_tables(fluid, nP, nH, P0, P1, H0, H1):
    dP = (P1 - P0) / (nP - 1)
    dH = (H1 - H0) / (nH - 1)
    sat = {k: [0.0] * nP for k in SAT_KEYS}
    tbl = {k: [[0.0] * nH for _ in range(nP)] for k in TBL_KEYS}
    phg = [[0] * nH for _ in range(nP)]

    for i in range(nP):
        P = P0 + i * dP
        s = sat_props(fluid, P)
        for k in SAT_KEYS:
            sat[k][i] = s[k]
        for j in range(nH):
            h = H0 + j * dH
            st = state_ph(fluid, P, h, s)
            tbl['T'][i][j] = st['T']
            tbl['rho'][i][j] = st['rho']
            tbl['mu'][i][j] = st['mu']
            tbl['k'][i][j] = st['k']
            tbl['cp'][i][j] = st['cp']
            tbl['s'][i][j] = st['s']
            tbl['cv'][i][j] = st['cv']
            d = derivs_ph(fluid, P, h, s, s)
            for k in ('dTdp', 'dTdh', 'drdp', 'drdh'):
                tbl[k][i][j] = d[k]
            phg[i][j] = 1 if h < s['hl'] else (2 if h > s['hv'] else 0)
        print(f"  P {i+1}/{nP} ({P/1e5:.2f} bar)", end='\r', file=sys.stderr)
    print(file=sys.stderr)
    return sat, tbl, phg


def render_constants(pkg, nP, nH, P0, P1, H0, H1, sat, tbl, phg):
    L = [f"  constant Integer nP={nP};",
         f"  constant Integer nH={nH};",
         f"  constant Real P0={_fmt(P0, 12)};",
         f"  constant Real P1={_fmt(P1, 12)};",
         f"  constant Real H0={_fmt(H0, 12)};",
         f"  constant Real H1={_fmt(H1, 12)};",
         "  constant Real dP=(P1-P0)/(nP-1);",
         "  constant Real dH=(H1-H0)/(nH-1);"]
    for k in SAT_KEYS:
        v = ",".join(_fmt(x) for x in sat[k])
        L.append(f"  constant Real SAT{k}[nP]={{{v}}};")
    for k in TBL_KEYS:
        rows = ",\n".join("{" + ",".join(_fmt(x) for x in row) + "}" for row in tbl[k])
        L.append(f"  constant Real TBL{k}[nP,nH]={{{rows}}};")
    grows = ",\n".join("{" + ",".join(str(x) for x in row) + "}" for row in phg)
    L.append(f"  constant Integer PHg[nP,nH]={{{grows}}};")
    return "\n".join(L)


def split_template(text):
    """템플릿 .mo → (헤더, 함수부). 첫 'function' 앞까지가 상수 블록."""
    m = re.search(r"^  function ", text, re.M)
    if not m:
        raise SystemExit("템플릿에서 function 절을 찾지 못함")
    head, funcs = text[:m.start()], text[m.start():]
    m2 = re.search(r"^(within\s*;\s*\n)?package\s+(\w+)([^\n]*)\n", head)
    if not m2:
        raise SystemExit("템플릿에서 package 선언을 찾지 못함")
    return m2.group(2), m2.group(3), funcs


def parse_existing(text, key, is2d):
    pat = rf"constant Real {key}\[nP(?:,nH)?\]=\{{(.*?)\}};"
    m = re.search(pat, text, re.S)
    if not m:
        return None
    body = m.group(1)
    if is2d:
        return [[float(x) for x in r.split(",")]
                for r in re.findall(r"\{([^{}]*)\}", body)]
    return [float(x) for x in body.split(",")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fluid', required=True, help='CoolProp 유체명 (Propane, R1234yf, ...)')
    ap.add_argument('--package', required=True, help='Modelica 패키지명 (R290Tab 등)')
    ap.add_argument('--template', default='modelica/R290Tab.mo', help='함수부를 가져올 템플릿')
    ap.add_argument('--out', help='출력 .mo 경로')
    ap.add_argument('--verify', help='기존 .mo 와 대조만 (파일 미기록)')
    ap.add_argument('--nP', type=int, default=60)
    ap.add_argument('--nH', type=int, default=160)
    ap.add_argument('--P0', type=float, default=150000.0)
    ap.add_argument('--P1', type=float, default=None, help='기본 0.85·Pcrit')
    ap.add_argument('--H0', type=float, default=None,
                    help='기본: hl(P0) − 0.15·h_fg(P0) (과냉 여유)')
    ap.add_argument('--H1', type=float, default=None,
                    help='기본: hv(P0) + 0.40·h_fg(P0) (과열 여유)')
    a = ap.parse_args()

    Pc = CP.PropsSI('Pcrit', a.fluid)
    P1 = a.P1 if a.P1 else 0.85 * Pc
    if P1 >= Pc:
        raise SystemExit(f"P1({P1/1e5:.2f} bar) >= Pcrit({Pc/1e5:.2f} bar)")
    # h 범위 — 냉매마다 기준상태·잠열이 달라 자동 산정 (R290 기본값은 부적합)
    _hl0 = CP.PropsSI('H', 'P', a.P0, 'Q', 0, a.fluid)
    _hv0 = CP.PropsSI('H', 'P', a.P0, 'Q', 1, a.fluid)
    _fg0 = _hv0 - _hl0
    H0 = a.H0 if a.H0 is not None else _hl0 - 0.15 * _fg0
    H1 = a.H1 if a.H1 is not None else _hv0 + 0.40 * _fg0
    print(f"{a.fluid}: Pcrit={Pc/1e5:.3f} bar, 격자 {a.nP}×{a.nH}, "
          f"P {a.P0/1e5:.2f}~{P1/1e5:.2f} bar, h {H0/1e3:.0f}~{H1/1e3:.0f} kJ/kg",
          file=sys.stderr)

    sat, tbl, phg = build_tables(a.fluid, a.nP, a.nH, a.P0, P1, H0, H1)

    if a.verify:
        ref = open(a.verify).read()
        worst = []
        for k in SAT_KEYS:
            r = parse_existing(ref, 'SAT' + k, False)
            if r is None:
                print(f"  SAT{k}: 기존 파일에 없음"); continue
            e = max(abs(x - y) / max(abs(y), 1e-30) for x, y in zip(sat[k], r))
            worst.append((e, 'SAT' + k))
        for k in TBL_KEYS:
            r = parse_existing(ref, 'TBL' + k, True)
            if r is None:
                print(f"  TBL{k}: 기존 파일에 없음"); continue
            e = max(abs(x - y) / max(abs(y), 1e-30)
                    for rowx, rowy in zip(tbl[k], r) for x, y in zip(rowx, rowy))
            worst.append((e, 'TBL' + k))
        worst.sort(reverse=True)
        print("대조 결과 — 상대오차 상위 8개:")
        for e, n in worst[:8]:
            print(f"  {n:<12} {e:.3e}")
        ok = sum(1 for e, _ in worst if e < 1e-4)
        print(f"1e-4 이내: {ok}/{len(worst)}")
        return

    if not a.out:
        raise SystemExit("--out 또는 --verify 필요")
    tmpl = open(a.template).read()
    _, desc, funcs = split_template(tmpl)
    consts = render_constants(a.package, a.nP, a.nH, a.P0, P1, H0, H1, sat, tbl, phg)
    txt = (f'within ;\npackage {a.package} "{a.fluid} tabulated media — (p,h) basis, '
           f'2상 안전, 미분가능 (CoolProp 기준상태)\n'
           f'  tools/gen_media_table.py 자동생성 — 손으로 수정하지 말 것"\n'
           f"{consts}\n{funcs}")
    txt = re.sub(r"end \w+;\s*$", f"end {a.package};\n", txt)
    open(a.out, 'w').write(txt)
    print(f"기록: {a.out} ({len(txt)} bytes)", file=sys.stderr)


if __name__ == '__main__':
    main()
