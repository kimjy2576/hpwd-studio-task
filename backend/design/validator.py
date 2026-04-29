"""
Validator — 시뮬 vs 측정 metrics, train/test split
═══════════════════════════════════════════════════════════════════════
Calibration 후 별도 시험점으로 모델 정확도 검증.

기능:
  - train/test split (random or sequential)
  - per-output metrics: RMSE, MAPE, R², max error
  - parity plot 데이터 (시뮬 vs 측정 점들)
  - residual plot 데이터 (운전 조건 vs error)
"""

import math
import random
from typing import Any


def split_train_test(
    inputs: dict[str, list],
    outputs_meas: dict[str, list],
    test_ratio: float = 0.2,
    random_seed: int = 42,
    mode: str = 'random',  # 'random' or 'sequential'
) -> dict[str, Any]:
    """데이터를 train/test로 분할.
    
    Returns:
        {
            'train': {'inputs': {...}, 'outputs_meas': {...}, 'n': int, 'indices': [...]},
            'test':  {'inputs': {...}, 'outputs_meas': {...}, 'n': int, 'indices': [...]},
        }
    """
    n_total = len(next(iter(inputs.values())))
    n_test = max(1, int(n_total * test_ratio))
    n_train = n_total - n_test

    indices = list(range(n_total))
    if mode == 'random':
        rng = random.Random(random_seed)
        rng.shuffle(indices)

    train_idx = sorted(indices[:n_train])
    test_idx = sorted(indices[n_train:])

    def take(d, idx):
        return {k: [v[i] for i in idx] for k, v in d.items()}

    return {
        'train': {
            'inputs': take(inputs, train_idx),
            'outputs_meas': take(outputs_meas, train_idx),
            'n': len(train_idx),
            'indices': train_idx,
        },
        'test': {
            'inputs': take(inputs, test_idx),
            'outputs_meas': take(outputs_meas, test_idx),
            'n': len(test_idx),
            'indices': test_idx,
        },
    }


def evaluate(
    component_module,
    params: dict,
    inputs: dict[str, list],
    outputs_meas: dict[str, list],
) -> dict[str, Any]:
    """주어진 params로 component를 모든 시험점에서 평가.
    
    Returns:
        {
            'sim': {port: [...]},     # 시뮬 결과
            'meas': {port: [...]},    # 측정값 (입력 그대로)
            'metrics': {port: {rmse, mape, r2, max_err, mean_err}, ...},
            'parity': {port: [(meas, sim), ...]},
        }
    """
    step_fn = component_module.step
    init_state_fn = getattr(component_module, 'init_state', None)

    n_rows = len(next(iter(inputs.values())))
    sim = {port: [] for port in outputs_meas.keys()}
    failed_rows = []

    for r_idx in range(n_rows):
        inputs_row = {p: vals[r_idx] for p, vals in inputs.items()}
        try:
            state = init_state_fn(params) if init_state_fn else {}
            r = step_fn(inputs_row, params, state, 1.0)
            outs = r['outputs']
            for port in sim:
                sim[port].append(outs.get(port, float('nan')))
        except Exception:
            failed_rows.append(r_idx)
            for port in sim:
                sim[port].append(float('nan'))

    # Metrics 계산 (per output)
    metrics = {}
    parity = {}
    for port, meas_vals in outputs_meas.items():
        sim_vals = sim[port]
        valid_pairs = [(m, s) for m, s in zip(meas_vals, sim_vals)
                       if not (math.isnan(m) or math.isnan(s))]
        parity[port] = valid_pairs

        if not valid_pairs:
            metrics[port] = {'rmse': None, 'mape': None, 'r2': None,
                             'max_err': None, 'mean_err': None, 'n': 0}
            continue

        n = len(valid_pairs)
        errs = [s - m for m, s in valid_pairs]
        sq_errs = [e**2 for e in errs]
        rmse = math.sqrt(sum(sq_errs) / n)

        # MAPE (avoiding /0)
        mape_terms = [abs(e / m) for e, (m, _) in zip(errs, valid_pairs) if abs(m) > 1e-9]
        mape = sum(mape_terms) / len(mape_terms) * 100 if mape_terms else None

        # R²
        meas_mean = sum(m for m, _ in valid_pairs) / n
        ss_tot = sum((m - meas_mean)**2 for m, _ in valid_pairs)
        ss_res = sum(sq_errs)
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else None

        max_err = max(abs(e) for e in errs)
        mean_err = sum(errs) / n  # bias

        metrics[port] = {
            'rmse': rmse,
            'mape': mape,
            'r2': r2,
            'max_err': max_err,
            'mean_err': mean_err,  # bias indicator
            'n': n,
        }

    return {
        'sim': sim,
        'meas': outputs_meas,
        'metrics': metrics,
        'parity': parity,
        'failed_rows': failed_rows,
    }
