"""
Design Studio Router — FastAPI endpoints
═══════════════════════════════════════════════════════════════════════
/design/* 경로로 접근. server.py에서 app.include_router(design_router).

Endpoints:
  GET  /design/components            — fitting 가능한 컴포넌트 list
  GET  /design/components/{name}     — 특정 컴포넌트의 parameter 분류
  POST /design/csv/parse             — CSV 텍스트 → 표준화 데이터 + 매핑 정보
  POST /design/calibrate             — fitting params 최적화 (sync, ~수초~분)
  POST /design/validate              — 주어진 params로 평가 + metrics
  POST /design/sessions              — session 저장
  GET  /design/sessions              — session list
  GET  /design/sessions/{id}         — session 로드
  DELETE /design/sessions/{id}       — session 삭제
"""

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from components import REGISTRY
from design import csv_loader, optimizer, validator, session_manager

router = APIRouter(prefix='/design')


def _get_component_module(name: str):
    """Component 이름 → 모듈 객체."""
    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown component: {name}")
    return REGISTRY[name]


def _get_md(name: str):
    """Component 이름 → modelDescription."""
    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown component: {name}")
    return REGISTRY[name].modelDescription


def _get_param_groups(md: dict) -> dict[str, list[dict]]:
    """Parameter들을 group별로 분류."""
    groups = {}
    for v in md['variables']:
        if v['causality'] != 'parameter':
            continue
        g = v.get('group', 'Other')
        if g not in groups:
            groups[g] = []
        groups[g].append({
            'name': v['name'],
            'unit': v.get('unit', ''),
            'start': v.get('start'),
            'description': v.get('description', ''),
            'options': v.get('options'),
            'type': v.get('type', 'Real'),
        })
    return groups


def _get_fitting_bounds(component_module, fitting_keys: list[str]) -> dict[str, tuple]:
    """validate 함수에서 fitting param의 bounds 추출.
    
    validate가 errors list 반환하는 형식이라 직접 bounds 빼낼 수 없음.
    대신 각 component의 validate 코드를 inspect — 단순화: hard-coded 사용.
    추후 modelDescription에 bounds 필드 추가 권장.
    """
    # 임시: 합리적 default bounds
    defaults = {
        # Winandy
        'AU_loss': (0.1, 100), 'AU_su': (0.1, 100), 'dP_su': (0.0, 0.5),
        'V_swept_eff': (0.5, 1.0), 'clearance_factor': (0.0, 1.0),
        'over_comp_factor': (0.0, 2.0), 'W_loss_const': (0.0, 500),
        'alpha_loss': (0.0, 1.0),
        # AHRI
        'alpha_W_rpm': (0.5, 1.5),
        # ROM
        'zeta_valve': (0.5, 5.0), 'A_leak_mm2': (0.001, 1.0),
        'Cd_leak': (0.1, 1.0), 'n_leak_rpm': (0.0, 2.0),
        'n_poly_base': (1.0, 1.5), 'W_f_const': (0.0, 200),
        'alpha_f_rpm': (0.0, 1e-4), 'eta_motor': (0.5, 1.0),
        'eta_inv': (0.5, 1.0),
    }
    out = {}
    for k in fitting_keys:
        out[k] = defaults.get(k, (0.0, 1e6))
    return out


# ════════ 1. 컴포넌트 정보 ════════

@router.get('/components')
def list_components_for_design():
    """fitting 가능한 컴포넌트 list. 'Fitting' group이 있는 것만."""
    items = []
    for name, mod in REGISTRY.items():
        md = mod.modelDescription
        groups = _get_param_groups(md)
        n_fitting = len(groups.get('Fitting', []))
        if n_fitting == 0:
            continue  # fitting params 없는 컴포넌트는 calibration 대상 아님
        items.append({
            'name': name,
            'displayName': md.get('name', name),
            'category': md.get('category', '-'),
            'modelType': md.get('modelType', '-'),
            'description': md.get('description', ''),
            'n_fitting': n_fitting,
            'n_inputs': len([v for v in md['variables'] if v['causality'] == 'input']),
            'n_outputs': len([v for v in md['variables'] if v['causality'] == 'output']),
        })
    return {'components': items}


@router.get('/components/{name}')
def get_component_for_design(name: str):
    """특정 컴포넌트의 parameter 분류 + I/O 정보."""
    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown: {name}")
    md = REGISTRY[name].modelDescription
    return {
        'name': name,
        'displayName': md.get('name'),
        'description': md.get('description'),
        'parameter_groups': _get_param_groups(md),
        'inputs': [
            {'name': v['name'], 'unit': v.get('unit', ''), 'description': v.get('description', '')}
            for v in md['variables'] if v['causality'] == 'input'
        ],
        'outputs': [
            {'name': v['name'], 'unit': v.get('unit', ''), 'description': v.get('description', '')}
            for v in md['variables'] if v['causality'] == 'output'
        ],
    }


# ════════ 2. CSV 파싱 ════════

class CSVParseRequest(BaseModel):
    csv_text: str
    component: str | None = None  # 있으면 input/output 분리까지


@router.post('/csv/parse')
def csv_parse(req: CSVParseRequest):
    """CSV 텍스트 → 표준화 데이터 + 매핑 정보."""
    parsed = csv_loader.parse_csv(req.csv_text)
    response = dict(parsed)
    if req.component and req.component in REGISTRY:
        md = REGISTRY[req.component].modelDescription
        split = csv_loader.split_inputs_outputs(parsed, md)
        response['split'] = split
    return response


# ════════ 3. Calibration ════════

class CalibrateRequest(BaseModel):
    component: str
    fixed_params: dict[str, Any]              # Material/Geometry/Operating 등 (변경 안 함)
    fitting_init: dict[str, float]             # 최적화 시작값
    fitting_keys: list[str] | None = None      # 일부만 최적화 (None=전체)
    fitting_bounds: dict[str, list[float]] | None = None  # 사용자 지정 bounds (있으면 default 덮어씀)
    inputs: dict[str, list[float]]
    outputs_meas: dict[str, list[float]]
    output_weights: dict[str, float] | None = None
    method: str = 'trf'
    max_iter: int = 200


@router.post('/calibrate')
def calibrate(req: CalibrateRequest):
    """Fitting params 최적화 — scipy LSQ."""
    component_module = _get_component_module(req.component)

    # 일부만 fitting하는 경우
    if req.fitting_keys:
        fitting_init = {k: req.fitting_init[k] for k in req.fitting_keys if k in req.fitting_init}
    else:
        fitting_init = dict(req.fitting_init)

    if not fitting_init:
        raise HTTPException(status_code=400, detail='fitting_init 비어있음')

    # bounds 결정
    keys = list(fitting_init.keys())
    bounds = _get_fitting_bounds(component_module, keys)
    if req.fitting_bounds:
        for k, v in req.fitting_bounds.items():
            if k in bounds and len(v) == 2:
                bounds[k] = (v[0], v[1])

    result = optimizer.calibrate(
        component_module=component_module,
        fixed_params=req.fixed_params,
        fitting_init=fitting_init,
        fitting_bounds=bounds,
        inputs=req.inputs,
        outputs_meas=req.outputs_meas,
        output_weights=req.output_weights or {},
        method=req.method,
        max_iter=req.max_iter,
    )
    return result


# ════════ 4. Validation ════════

class ValidateRequest(BaseModel):
    component: str
    params: dict[str, Any]                     # 모든 parameters (fixed + optimized fitting)
    inputs: dict[str, list[float]]
    outputs_meas: dict[str, list[float]]
    test_ratio: float = 0.0   # 0이면 전체 데이터 평가, 0.2면 80/20 split
    random_seed: int = 42


@router.post('/validate')
def validate(req: ValidateRequest):
    """주어진 params로 component 평가 + metrics."""
    component_module = _get_component_module(req.component)

    if req.test_ratio > 0:
        split = validator.split_train_test(
            req.inputs, req.outputs_meas, req.test_ratio, req.random_seed)
        train_eval = validator.evaluate(component_module, req.params,
                                         split['train']['inputs'], split['train']['outputs_meas'])
        test_eval = validator.evaluate(component_module, req.params,
                                        split['test']['inputs'], split['test']['outputs_meas'])
        return {
            'mode': 'split',
            'split': {
                'train_n': split['train']['n'],
                'test_n': split['test']['n'],
                'train_indices': split['train']['indices'],
                'test_indices': split['test']['indices'],
            },
            'train': train_eval,
            'test': test_eval,
        }
    else:
        evaluated = validator.evaluate(component_module, req.params,
                                        req.inputs, req.outputs_meas)
        return {'mode': 'all', 'evaluation': evaluated}


# ════════ 5. Session 관리 ════════

@router.get('/sessions')
def sessions_list():
    return {'sessions': session_manager.list_sessions()}


@router.get('/sessions/{session_id}')
def sessions_get(session_id: str):
    s = session_manager.load_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail='Session not found')
    return s


@router.post('/sessions')
def sessions_save(payload: dict):
    """payload는 자유 dict — id 있으면 update, 없으면 새로 생성."""
    sid = payload.get('id')
    new_id = session_manager.save_session(payload, sid)
    return {'id': new_id}


@router.delete('/sessions/{session_id}')
def sessions_delete(session_id: str):
    ok = session_manager.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Not found or delete failed')
    return {'deleted': session_id}
