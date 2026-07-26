#!/usr/bin/env python3
"""check_overrides.py — 실행 전 -override 가 실제로 먹는지 검사.

배경 (2026-07-25):
  OMC 는 start 속성에만 쓰이는 파라미터를 컴파일 시점에 상수폴딩해
  init.xml 에서 제거한다. 그러면 -override 가 '조용히' 무시되고
  경고는 stdout 로만 흘러가 놓치기 쉽다. 실제로 오일 용해 정상해 검증
  실행이 전부 use_oil=false / 정지조건 초기값으로 돌아갔는데도
  결과가 그럴듯해 보여 한동안 눈치채지 못했다.

  이 스크립트는 실행 전에 init.xml 을 뒤져 각 override 이름이 존재하는지
  확인하고, 하나라도 없으면 0이 아닌 코드로 종료한다.

사용:
  python3 verify/check_overrides.py <init.xml> name1=val1,name2=val2,...
  python3 verify/check_overrides.py <init.xml> --list-missing name1,name2

해결책 (없다고 나올 때):
  해당 파라미터 선언에 annotation(Evaluate=false) 를 붙여 재컴파일.
  그래도 안 되면 .mo 기본값을 직접 바꿔 케이스마다 재컴파일할 것.
"""
import re
import sys


def param_names(init_xml_path):
    """override 가능한 이름 집합.

    ※ 단순히 init.xml 에 이름이 있는지로는 부족하다. start 속성에만 쓰이는
      파라미터는 XML 에 남아 있어도 isValueChangeable="false" 라서 런타임이
      거부한다 (2026-07-25 실측: p1_0/cond.h_ref_start 는 false,
      Kp_c/use_oil 은 true). 반드시 이 속성으로 판별할 것.
    """
    with open(init_xml_path, encoding='utf-8', errors='replace') as f:
        txt = f.read()
    ok = set()
    for m in re.finditer(r'<ScalarVariable(.*?)</ScalarVariable>', txt, re.S):
        blk = m.group(1)
        nm = re.search(r'name\s*=\s*"([^"]+)"', blk)
        ch = re.search(r'isValueChangeable\s*=\s*"(\w+)"', blk)
        if nm and ch and ch.group(1) == 'true':
            ok.add(nm.group(1))
    return ok


def parse_override(spec):
    names = []
    for tok in spec.split(','):
        tok = tok.strip()
        if not tok:
            continue
        names.append(tok.split('=')[0].strip())
    return names


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    init_xml = argv[1]
    if argv[2] == '--list-missing':
        wanted = [x.strip() for x in argv[3].split(',') if x.strip()]
    else:
        wanted = parse_override(argv[2])

    have = param_names(init_xml)
    ok, missing = [], []
    for n in wanted:
        (ok if n in have else missing).append(n)

    for n in ok:
        print(f"  [OK]      {n}")
    for n in missing:
        print(f"  [MISSING] {n}   <- isValueChangeable=false. .mo 기본값 수정 + 재컴파일 필요")

    if missing:
        print(f"\n실패: {len(missing)}/{len(wanted)} 개가 init.xml 에 없음. "
              f"이대로 실행하면 조용히 무시됨.")
        return 1
    print(f"\n통과: {len(ok)}개 전부 override 가능.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
