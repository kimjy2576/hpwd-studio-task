#!/usr/bin/env python3
"""컴포넌트 입력 감도 프로브 — 선언된 입력이 실제로 출력에 반영되는지 측정.

배경 (2026-07-24)
  Cycle Runner에서 압축기 T_suc / T_amb 가 조용히 무시되어(기본값 고정)
  사이클 연성이 끊긴 결함이 실측으로 발견됨. 같은 유형(넘겼는데 안 읽음,
  잘못된 경로로 읽음, 하드코딩 잔존)은 수렴이 되기 때문에 코드 독해로는
  놓치기 쉽다. 이 스크립트는 코드를 읽지 않고 **결과를 재서** 판정한다.

방법
  modelDescription()의 causality=='input' 변수를 하나씩 ±섭동하고
  출력 벡터가 유의하게 움직이는지 본다. 불변이면 셋 중 하나:
    (a) 연결 안 됨 / 잘못된 경로   ← 결함
    (b) 해당 운전점에서 물리적으로 무관 (예: 건코일에서 RH)
    (c) 특정 모드 전용 (예: EEV measure mode)
  → 자동 판정은 하지 않고 '불감(insensitive)' 목록만 뽑아 사람이 판정한다.

사용
  python3 tools/audit_input_sensitivity.py            # 전 컴포넌트
  python3 tools/audit_input_sensitivity.py compressor # 카테고리 필터
"""
import io
import math
import sys
from contextlib import redirect_stdout

sys.path.insert(0, 'backend')

# (모듈명, 기준 input, 기준 params) — 검증 BC 기준 운전점
BASE = {
    'compressor': (
        ['compressor_theoretical', 'compressor_winandy', 'compressor_chamber'],
        {'P_suc': 5.0889, 'P_dis': 9.8762, 'T_suc': 9.5, 'N': 1800.0, 'h_suc': 590.0,
         'T_amb': 25.0},
        {},
    ),
    'condenser': (
        ['condenser_off_design', 'condenser_moving_boundary', 'condenser_on_design'],
        {'P_cond': 9.8762, 'h_in': 651.260, 'm_dot_ref': 0.00206593,
         'T_air_in': 14.474, 'RH_air_in': 99.0, 'V_air_CMM': 2.42},
        {},
    ),
    'evaporator': (
        ['evaporator_off_design', 'evaporator_moving_boundary', 'evaporator_on_design'],
        {'P_evap': 5.0889, 'h_in': 364.157, 'm_dot_ref': 0.00206593,
         'T_air_in': 20.0, 'RH_air_in': 80.0, 'V_air_CMM': 2.42},
        {},
    ),
    'eev': (
        ['eev_off_design', 'eev_moving_boundary', 'eev_on_design'],
        {'P_in': 9.8762, 'h_in': 353.8, 'P_out': 5.0889, 'opening': 23.586},
        {},
    ),
    'air': (
        ['drum_on', 'filter_on', 'fan_on'],
        {'T_air_in': 30.0, 'RH_air_in': 40.0, 'W_air_in': 0.0107,
         'V_air_CMM': 2.42, 'm_dot_air': 0.048, 'T_amb': 25.0,
         'X_dry': 0.5, 'RPM': 3000.0, 'N': 3000.0, 'dp': 100.0},
        {},
    ),
}

REL = 0.05        # 섭동 크기 (상대)
ABS_MIN = 0.5     # 최소 절대 섭동 (온도 등)
TOL = 1e-9        # 이보다 작으면 '불감'


def _outvec(res):
    o = res.get('outputs', res) if isinstance(res, dict) else {}
    return {k: v for k, v in o.items() if isinstance(v, (int, float))
            and not isinstance(v, bool) and math.isfinite(v)}


def _run(mod, inp, par):
    with redirect_stdout(io.StringIO()):
        return _outvec(mod.step(dict(inp), dict(par), {}, 0.0))


def probe(modname, base_in, base_par):
    mod = __import__(f'components.{modname}', fromlist=['step'])
    md = mod.modelDescription() if callable(getattr(mod, 'modelDescription', None)) \
        else getattr(mod, 'modelDescription', {})
    declared = [v['name'] for v in md.get('variables', [])
                if v.get('causality') == 'input']
    try:
        ref = _run(mod, base_in, base_par)
    except Exception as e:
        return declared, None, f'기준 실행 실패: {type(e).__name__}: {str(e)[:60]}'
    if not ref:
        return declared, None, '수치 출력 없음'

    insensitive, skipped = [], []
    for name in declared:
        if name not in base_in:
            skipped.append((name, '기준 input에 없음'))
            continue
        v0 = base_in[name]
        if not isinstance(v0, (int, float)):
            skipped.append((name, '비수치'))
            continue
        d = max(abs(v0) * REL, ABS_MIN)
        moved = False
        for sgn in (+1, -1):
            trial = dict(base_in)
            trial[name] = v0 + sgn * d
            try:
                out = _run(mod, trial, base_par)
            except Exception:
                moved = True      # 예외 = 값을 쓰긴 함
                break
            for k, vr in ref.items():
                vt = out.get(k)
                if vt is None:
                    continue
                scale = max(abs(vr), 1e-12)
                if abs(vt - vr) / scale > TOL:
                    moved = True
                    break
            if moved:
                break
        if not moved:
            insensitive.append(name)
    return declared, insensitive, skipped


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"입력 감도 프로브 (섭동 {REL:.0%} 또는 최소 {ABS_MIN}, 판정 임계 {TOL:g})\n")
    total_bad = 0
    for cat, (mods, base_in, base_par) in BASE.items():
        if filt and filt not in cat:
            continue
        print(f"── {cat} " + "─" * (60 - len(cat)))
        for m in mods:
            declared, ins, extra = probe(m, base_in, base_par)
            if ins is None:
                print(f"  {m:<32} !! {extra}")
                continue
            mark = "OK" if not ins else "불감 " + str(len(ins))
            print(f"  {m:<32} 선언 {len(declared):>2}  {mark}")
            if ins:
                total_bad += len(ins)
                print(f"      ⚠ 불감: {', '.join(ins)}")
            miss = [n for n, why in extra if why == '기준 input에 없음']
            if miss:
                print(f"      · 미측정(기준 input 없음): {', '.join(miss)}")
        print()
    print(f"불감 입력 총 {total_bad}건 — 연결 결함 / 물리적 무관 / 모드 전용 구분 필요")


if __name__ == '__main__':
    main()
