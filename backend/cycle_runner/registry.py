"""
registry.py — Cycle Runner 컴포넌트 fidelity dispatch

각 냉매/공기 컴포넌트를 fidelity(1/2/3)로 조회. 전 컴포넌트가 동일한
step(input, params, state, dt) 시그니처를 가지므로 dispatch는 단순 lookup.

fidelity 매핑:
  1 = off_design (L1, 상수/UA)
  2 = moving_boundary (L2, 물리 상관식)
  3 = on_design (L3, 셀별/상세)

기존 bridge.py COMPONENT_REGISTRY(OMC 모델 매핑)와 달리, 여기는 Python
step() 모듈을 직접 참조 (OMC 무관, 재컴파일 없이 조합).
"""

from components import (
    compressor_theoretical, compressor_winandy, compressor_chamber,
    eev_off_design, eev_moving_boundary, eev_on_design,
    condenser_off_design, condenser_moving_boundary, condenser_on_design,
    evaporator_off_design, evaporator_moving_boundary, evaporator_on_design,
    drum_on, filter_on, fan_on,
)

# 냉매측 4 컴포넌트 × 3 fidelity
REFRIGERANT_REGISTRY = {
    'compressor': {1: compressor_theoretical, 2: compressor_winandy, 3: compressor_chamber},
    'eev':        {1: eev_off_design,         2: eev_moving_boundary,  3: eev_on_design},
    'condenser':  {1: condenser_off_design,   2: condenser_moving_boundary, 3: condenser_on_design},
    'evaporator': {1: evaporator_off_design,  2: evaporator_moving_boundary, 3: evaporator_on_design},
}

# 공기측 컴포넌트 (drum/filter/fan은 현재 단일 fidelity 모듈 내부에서 L1/L2/L3 분기)
AIR_REGISTRY = {
    'drum':   {1: drum_on, 2: drum_on, 3: drum_on},
    'filter': {1: filter_on, 2: filter_on, 3: filter_on},
    'fan':    {1: fan_on, 2: fan_on, 3: fan_on},
}


def get_component(domain, comp, fidelity):
    """도메인('refrigerant'|'air'), 컴포넌트명, fidelity(1/2/3)로 모듈 조회."""
    reg = REFRIGERANT_REGISTRY if domain == 'refrigerant' else AIR_REGISTRY
    if comp not in reg:
        raise ValueError(f"미등록 컴포넌트: {comp} (지원: {list(reg)})")
    if fidelity not in reg[comp]:
        raise ValueError(f"{comp} fidelity {fidelity} 없음 (지원: {list(reg[comp])})")
    return reg[comp][fidelity]


# 컴포넌트별 기본 params (fidelity별 필수 설정). L3 HX는 microfin/circuit 필요.
DEFAULT_PARAMS = {
    ('condenser', 3):  {'tube_type': 'microfin', 'fluid': 'R290', 'circuit_mode': 'single'},
    ('evaporator', 3): {'tube_type': 'microfin', 'fluid': 'R290', 'circuit_mode': 'row_parallel'},
    ('condenser', 2):  {'fluid': 'R290'},
    ('evaporator', 2): {'fluid': 'R290'},
}


def default_params(comp, fidelity):
    """컴포넌트/fidelity 기본 params (없으면 빈 dict)."""
    return dict(DEFAULT_PARAMS.get((comp, fidelity), {}))
