"""
컴포넌트 자동 등록
═══════════════════════════════════════════════════════════════════════
이 폴더의 모든 .py 파일을 자동으로 import해서 REGISTRY에 등록.
파일 이름이 컴포넌트 이름. 예: adder.py → REGISTRY['adder']

새 컴포넌트 추가 방법:
  1. 이 폴더에 새 .py 파일 생성 (예: my_component.py)
  2. 다음을 정의:
     - modelDescription (dict)
     - step(input, params, state, dt) -> {'outputs': ..., 'newState': ...}
     - validate(params) -> [{'key': ..., 'msg': ...}]  # 선택
  3. 서버 재시작
"""

import importlib
import os
import pkgutil
import sys
from pathlib import Path

REGISTRY = {}


def _load_components():
    """components/ 폴더의 모든 .py 파일을 import해서 REGISTRY에 등록"""
    components_dir = Path(__file__).parent

    for finder, name, ispkg in pkgutil.iter_modules([str(components_dir)]):
        if name.startswith("_"):
            continue
        if ispkg:
            # Sub-package (예: correlations/) — 컴포넌트 아님, skip
            continue
        try:
            mod = importlib.import_module(f"components.{name}")
            if not hasattr(mod, "step"):
                print(f"[WARN] components/{name}.py: missing step() — skipped")
                continue
            REGISTRY[name] = mod
            print(f"[OK]   components/{name}.py registered")
        except Exception as e:
            print(f"[FAIL] components/{name}.py: {type(e).__name__}: {e}")


def list_components():
    """등록된 컴포넌트 이름 리스트"""
    return sorted(REGISTRY.keys())


# 모듈 import 시 자동 실행
_load_components()
