"""
Optimizer — scipy least_squares wrapper for fitting parameter calibration
═══════════════════════════════════════════════════════════════════════
사용자가 fitting params를 시험 데이터에 fit. Levenberg-Marquardt /
Trust Region Reflective 알고리즘 (gradient 기반, 빠름).

목적함수: residuals = (시뮬 - 측정) / scale  per output per row
   → 다목적 (m_dot, W_elec, T_dis 등) → 가중 합산
   → least_squares가 minimize Σ residuals²

기존 component 함수들(step)을 그대로 호출. component 코드 수정 X.
"""

import math
import time
from typing import Any, Callable

try:
    from scipy.optimize import least_squares
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def _eval_component(step_fn, inputs_row: dict, fitting_params: dict, fixed_params: dict, init_state_fn=None):
    """Component step 1회 호출 + outputs 반환. 에러 시 None.
    
    iteration이 있는 컴포넌트라도 init_state warm start와 fixed-point 자체 수렴을
    이미 step() 안에서 함. 외부 warm-up은 불필요 — 1회만 호출.
    """
    try:
        params = {**fixed_params, **fitting_params}
        state = init_state_fn(params) if init_state_fn else {}
        r = step_fn(inputs_row, params, state, 1.0)
        return r['outputs']
    except Exception:
        return None


def _build_residuals_fn(
    step_fn,
    init_state_fn,
    fixed_params: dict,
    fitting_keys: list[str],
    inputs: dict[str, list],   # {port: [val, val, ...]}
    outputs_meas: dict[str, list],  # {port: [val, val, ...]}
    output_weights: dict[str, float],  # {port: weight} — None이면 1/std로 자동
    n_rows: int,
):
    """least_squares가 호출할 residuals 함수 생성."""
    # output별 자동 정규화 scale (0이 되지 않게 보호)
    auto_scale = {}
    for port, vals in outputs_meas.items():
        if not vals: continue
        mean_abs = sum(abs(v) for v in vals) / len(vals)
        auto_scale[port] = max(mean_abs, 1e-9)

    def residuals(x):
        # x = fitting_keys 순서대로 값 array
        fitting_params = {k: float(x[i]) for i, k in enumerate(fitting_keys)}
        all_res = []
        for r_idx in range(n_rows):
            inputs_row = {p: vals[r_idx] for p, vals in inputs.items()}
            outs = _eval_component(step_fn, inputs_row, fitting_params, fixed_params, init_state_fn)
            for port, meas_vals in outputs_meas.items():
                meas = meas_vals[r_idx]
                if outs is None:
                    sim = meas  # 평가 실패 — residual 0 (penalty는 별도)
                    all_res.append(1e3)  # 큰 페널티
                    continue
                sim = outs.get(port, meas)
                w = output_weights.get(port, 1.0)
                scale = auto_scale.get(port, 1.0)
                all_res.append(w * (sim - meas) / scale)
        return all_res
    return residuals


def calibrate(
    component_module,
    fixed_params: dict,
    fitting_init: dict[str, float],
    fitting_bounds: dict[str, tuple[float, float]],
    inputs: dict[str, list],
    outputs_meas: dict[str, list],
    output_weights: dict[str, float] | None = None,
    method: str = 'trf',  # 'trf' (Trust Region Reflective) or 'lm' (Levenberg-Marquardt, no bounds)
    max_iter: int = 200,
    callback=None,  # callback(iter, x, residuals) — 진행률 표시용
) -> dict[str, Any]:
    """Fitting parameter LSQ 최적화.
    
    Args:
        component_module: components.compressor_winandy 같은 모듈
        fixed_params: 변경 안 할 parameters (Material/Operating/Geometry 등)
        fitting_init: 최적화 대상 시작값 {key: value}
        fitting_bounds: {key: (lo, hi)} 범위 (validate 함수에서)
        inputs: {port: [list]} — 시험 데이터 입력
        outputs_meas: {port: [list]} — 측정 출력
        output_weights: 출력별 가중치 (None=균등)
        method: 'trf' (bounded) 또는 'lm' (unbounded, 더 빠름)
        max_iter: 최대 함수 호출
        callback: 진행 표시
    
    Returns:
        {
            'success': bool,
            'message': str,
            'fitting_optimized': {key: value},
            'cost_initial': float,
            'cost_final': float,
            'n_iter': int,
            'duration_s': float,
            'residuals_final': [float, ...],
        }
    """
    if not HAS_SCIPY:
        return {
            'success': False,
            'message': 'scipy 미설치. pip install scipy 필요',
            'fitting_optimized': fitting_init,
        }

    step_fn = component_module.step
    init_state_fn = getattr(component_module, 'init_state', None)
    fitting_keys = list(fitting_init.keys())
    output_weights = output_weights or {}

    # 데이터 일관성
    if not inputs or not outputs_meas:
        return {'success': False, 'message': 'inputs 또는 outputs_meas가 비어있음'}
    n_rows = len(next(iter(inputs.values())))
    if any(len(v) != n_rows for v in inputs.values()):
        return {'success': False, 'message': 'input rows 길이 불일치'}
    if any(len(v) != n_rows for v in outputs_meas.values()):
        return {'success': False, 'message': 'output rows 길이 불일치 (input과 다름)'}

    # 초기값 array
    x0 = [fitting_init[k] for k in fitting_keys]
    lo = [fitting_bounds[k][0] for k in fitting_keys]
    hi = [fitting_bounds[k][1] for k in fitting_keys]

    # x0이 bounds 안에 있는지 확인
    for i, (k, v) in enumerate(zip(fitting_keys, x0)):
        if not (lo[i] <= v <= hi[i]):
            x0[i] = max(lo[i], min(hi[i], v))  # clip

    residuals_fn = _build_residuals_fn(
        step_fn, init_state_fn, fixed_params, fitting_keys,
        inputs, outputs_meas, output_weights, n_rows,
    )

    # 초기 cost
    res0 = residuals_fn(x0)
    cost0 = 0.5 * sum(r**2 for r in res0)

    t_start = time.time()
    iter_count = [0]

    def wrap_residuals(x):
        iter_count[0] += 1
        r = residuals_fn(x)
        if callback:
            try:
                callback(iter_count[0], list(x), r)
            except Exception:
                pass
        return r

    try:
        if method == 'lm':
            # Levenberg-Marquardt — bounds 미지원
            sol = least_squares(wrap_residuals, x0, method='lm', max_nfev=max_iter, ftol=1e-6)
        else:
            sol = least_squares(wrap_residuals, x0, method='trf', bounds=(lo, hi),
                                max_nfev=max_iter, ftol=1e-6, xtol=1e-6)
    except Exception as e:
        return {'success': False, 'message': f'최적화 실패: {e}',
                'fitting_optimized': fitting_init}

    duration = time.time() - t_start
    cost_final = float(sol.cost)
    fitting_opt = {k: float(sol.x[i]) for i, k in enumerate(fitting_keys)}

    return {
        'success': bool(sol.success),
        'message': sol.message if hasattr(sol, 'message') else 'OK',
        'fitting_optimized': fitting_opt,
        'cost_initial': float(cost0),
        'cost_final': cost_final,
        'cost_reduction_pct': (1 - cost_final / cost0) * 100 if cost0 > 0 else 0,
        'n_iter': iter_count[0],
        'duration_s': duration,
        'residuals_final': [float(r) for r in sol.fun] if hasattr(sol, 'fun') else [],
    }
