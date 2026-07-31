"""parallel_jac — 뉴턴 야코비안을 프로세스로 병렬 계산한다 (2026-07-31).

배경
    solve_forward 실측 (미지수 4개)
        전체 6.15 s · nfev 14 · 잔차 1회 0.439 s
        야코비안 3회 x 4평가 = 12/14 (86%) 가 야코비안 계산
    야코비안 열은 서로 완전히 독립이라 병렬로 계산할 수 있다.
    4코어 병렬 시 2.20 s 예상 (2.8배).

왜 스레드가 아니라 프로세스인가
    프로파일 결과 시간의 100% 가 파이썬 루프에 있다
    (_solve_segment 3040회, _poly2 31004회, math.log 181199회).
    numpy·linalg 는 0.0% 다. GIL 때문에 스레드로는 전혀 빨라지지 않는다.

한계 — 정직하게
    미지수가 4개이므로 4코어까지만 쓴다. 16코어를 채우려면
    바깥쪽(파라미터 스윕, 동적 스텝)에서 병렬화해야 하는데,
    동적 스텝은 시간 방향으로 의존이 있어 나눌 수 없다.
    남은 축은 '여러 운전조건을 동시에' 뿐이다.

    프로세스 시작 비용(임포트 포함)이 있어 잔차 1회가 짧으면 손해다.
    잔차가 0.2 s 미만이면 순차가 낫다 — auto 모드가 그렇게 판단한다.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

# 워커 프로세스가 잡고 있는 잔차 함수 (초기화 시 1회 구성)
_WORKER: Dict[str, Any] = {}


def _init_worker(build: Callable[[], Callable], payload: Dict[str, Any]) -> None:
    """워커 프로세스 초기화 — 잔차 함수를 한 번만 만든다.

    컴포넌트 임포트가 무거우므로 매 평가마다 하지 않는다.
    """
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        _WORKER['fn'] = build(**payload)


def _eval_worker(x: Sequence[float]) -> List[float]:
    """워커에서 잔차 1회 평가."""
    fn = _WORKER.get('fn')
    if fn is None:
        raise RuntimeError('워커가 초기화되지 않았습니다.')
    try:
        r = fn(list(x))
    except Exception:
        # 범위 밖 등으로 실패하면 큰 값을 돌려 뉴턴이 그 방향을 피하게 한다.
        return [1e6] * len(x)
    return [float(v) for v in r]


class ParallelJacobian:
    """유한차분 야코비안을 프로세스 풀로 계산한다.

    사용
        pj = ParallelJacobian(build_residual, payload, n_x=4)
        with pj:
            J = pj.jacobian(x0, f0)
    """

    def __init__(self, build: Callable, payload: Dict[str, Any],
                 n_x: int, workers: Optional[int] = None,
                 rel_step: float = 1e-7):
        self.build = build
        self.payload = payload
        self.n_x = n_x
        # 미지수 수를 넘겨봐야 놀 뿐이다
        self.workers = min(workers or (os.cpu_count() or 1), n_x)
        self.rel_step = rel_step
        self._pool: Optional[ProcessPoolExecutor] = None

    def __enter__(self):
        self._pool = ProcessPoolExecutor(
            max_workers=self.workers,
            initializer=_init_worker, initargs=(self.build, self.payload))
        return self

    def __exit__(self, *exc):
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool = None
        return False

    def jacobian(self, x: Sequence[float], f0: Sequence[float]) -> np.ndarray:
        """전진차분 야코비안. 열마다 한 프로세스."""
        if self._pool is None:
            raise RuntimeError('with 블록 안에서 쓰십시오.')
        x = np.asarray(x, dtype=float)
        f0 = np.asarray(f0, dtype=float)
        # scipy 와 같은 규약: 값의 크기에 비례한 스텝, 0 근처는 절대 스텝
        h = self.rel_step * np.maximum(np.abs(x), 1.0)
        pts = [list(x + h[j] * np.eye(len(x))[j]) for j in range(len(x))]
        fs = list(self._pool.map(_eval_worker, pts))
        J = np.empty((len(f0), len(x)))
        for j, fj in enumerate(fs):
            J[:, j] = (np.asarray(fj, dtype=float) - f0) / h[j]
        return J


def should_parallelize(t_residual: float, n_x: int,
                       min_t: float = 0.2) -> bool:
    """병렬이 이득인지 판단.

    프로세스 시작·통신 비용이 있어 잔차가 짧으면 순차가 낫다.
    실측 기준 0.2 s 를 경계로 둔다 (우리 잔차는 0.44 s 라 이득).
    """
    return t_residual >= min_t and n_x >= 2 and (os.cpu_count() or 1) >= 2
