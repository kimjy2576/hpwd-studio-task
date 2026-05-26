"""
HPWD-Studio Backend Server
═══════════════════════════════════════════════════════════════════════
컴포넌트 시뮬 계산을 처리하는 FastAPI 서버.

Endpoints:
  GET  /health                      — 서버 살아있는지 + 컴포넌트 목록
  POST /compute                     — 컴포넌트 1 step 계산
  GET  /components                  — 모든 컴포넌트 목록
  GET  /components/{name}           — 특정 컴포넌트 modelDescription

CORS: 모든 origin 허용 (localhost 환경 가정)
Port: 8000 (환경변수 PORT로 변경 가능)
"""

import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── components 모듈 import (자동 등록) ─────────────────────────────
from components import REGISTRY, list_components

# ─── App 초기화 ─────────────────────────────────────────────────────
app = FastAPI(
    title="HPWD-Studio Backend",
    description="Python 컴포넌트 시뮬 계산 서버",
    version="0.1.0",
)

# CORS — Studio가 다른 origin (file://, localhost:8080 등)에서 호출
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Calibration Studio router 등록 (legacy URL: /design/*) ──────────
# /design/* 경로의 endpoint를 추가. fitting / calibration / validation /
# session 관리. 앱 이름은 'Calibration Studio'로 변경됐지만 외부 API는
# /design/* 유지 (호환성).
_design_status = {'mounted': False, 'error': None}
try:
    from design import design_router
    app.include_router(design_router)
    _design_status['mounted'] = True
    print("[OK]   Calibration Studio router mounted at /design/*")
except Exception as e:
    _design_status['error'] = f"{type(e).__name__}: {e}"
    print(f"[WARN] Calibration router 마운트 실패: {_design_status['error']}")
    import traceback
    traceback.print_exc()

# ─── Modelica 브릿지 (canvas→.mo→omc) — 로컬 dev 전용 ────────────────
# import는 omc 불필요(안전). 실제 실행 시에만 omc 필요 → 배포본(omc 없음)은
# /compute_modelica 호출 시 친절한 에러만 반환하고 /compute(Python)는 정상 동작.
import shutil
_modelica = {'imported': False, 'error': None}
try:
    from modelica.bridge import (compute_modelica as _mod_compute,
                                  run_cycle as _run_cycle,
                                  COMPONENT_REGISTRY, CYCLE_MODELS, HELMHOLTZ_PATH)
    _modelica['imported'] = True
    print(f"[OK]   Modelica bridge imported (components: {list(COMPONENT_REGISTRY)})")
except Exception as e:
    _modelica['error'] = f"{type(e).__name__}: {e}"
    print(f"[WARN] Modelica bridge import 실패: {_modelica['error']}")


def _modelica_status():
    """Modelica 엔진 사용 가능 여부 (omc + HelmholtzMedia 존재)."""
    if not _modelica['imported']:
        return False, f"bridge import 실패: {_modelica['error']}"
    if shutil.which("omc") is None:
        return False, "omc 없음 (OpenModelica 미설치 — 로컬 dev에서만 사용 가능)"
    if not os.path.exists(HELMHOLTZ_PATH):
        return False, f"HelmholtzMedia 없음: {HELMHOLTZ_PATH} (env HELMHOLTZ_PATH 설정)"
    return True, None


# ─── Request/Response 스키마 ───────────────────────────────────────
class ComputeRequest(BaseModel):
    component: str
    input: dict[str, Any] = {}
    params: dict[str, Any] = {}
    state: dict[str, Any] = {}
    dt: float = 1.0


class ComputeResponse(BaseModel):
    outputs: dict[str, Any]
    newState: dict[str, Any]
    error: str | None = None


class CycleRequest(BaseModel):
    model: str = "Cycle_L1_ramp_PI"   # Cycle_L1_ramp | Cycle_L1_ramp_PI | Cycle_L1_dyn
    stop_time: float = 120.0
    tolerance: float = 1e-6
    intervals: int = 240


class CycleResponse(BaseModel):
    model: str
    stop_time: float = 0.0
    settled: dict[str, Any] = {}        # 정착값 (Pc_bar, Pe_bar, SH_evap, ... , W)
    trajectory: dict[str, Any] = {}     # {time:[...], var:[...]} 다운샘플 궤적
    error: str | None = None


# ─── Routes ─────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """서버가 살아있는지 + 등록된 컴포넌트 목록 + design router 상태"""
    m_ok, m_why = _modelica_status()
    return {
        "status": "ok",
        "version": "0.1.0",
        "components": list_components(),
        "design_studio": {
            "mounted": _design_status['mounted'],
            "error": _design_status['error'],
        },
        "modelica_engine": {
            "available": m_ok,
            "reason": m_why,
            "components": list(COMPONENT_REGISTRY) if _modelica['imported'] else [],
            "cycles": list(CYCLE_MODELS) if _modelica['imported'] else [],
        },
    }


@app.get("/components")
def list_all_components():
    """모든 컴포넌트의 modelDescription 요약"""
    out = {}
    for name, mod in REGISTRY.items():
        md = getattr(mod, "modelDescription", {})
        out[name] = {
            "typeNo": md.get("typeNo"),
            "name": md.get("name", name),
            "category": md.get("category"),
            "modelType": md.get("modelType"),
            "description": md.get("description"),
        }
    return out


@app.get("/components/{name}")
def get_component(name: str):
    """특정 컴포넌트의 전체 modelDescription"""
    if name not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Component '{name}' not found")
    mod = REGISTRY[name]
    return getattr(mod, "modelDescription", {})


@app.post("/compute", response_model=ComputeResponse)
def compute(req: ComputeRequest):
    """컴포넌트 1 step 계산"""
    if req.component not in REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Component '{req.component}' not registered. Available: {list_components()}",
        )

    mod = REGISTRY[req.component]
    try:
        result = mod.step(req.input, req.params, req.state, req.dt)
        return ComputeResponse(
            outputs=result.get("outputs", {}),
            newState=result.get("newState", req.state),
        )
    except Exception as e:
        # 에러를 throw하지 말고 응답에 담아 반환 — Studio가 친절히 표시
        return ComputeResponse(
            outputs={},
            newState=req.state,
            error=f"{type(e).__name__}: {e}",
        )


@app.post("/compute_modelica", response_model=ComputeResponse)
def compute_modelica(req: ComputeRequest):
    """컴포넌트 1 step 계산 — Modelica 엔진 버전 (canvas→.mo→omc).

    /compute 와 동일 입출력 shape. 프론트는 엔진 토글로 둘 중 하나를 호출.
    omc 미설치(배포본)면 error 필드에 사유를 담아 반환(크래시 안 함).
    주의: 호출마다 omc 컴파일(~10s) — 인터랙티브엔 느림. 배포·고속화는 FMU 선컴파일(PILOT.md).
    """
    ok, why = _modelica_status()
    if not ok:
        return ComputeResponse(
            outputs={}, newState=req.state,
            error=f"Modelica 엔진 사용 불가: {why}. (배포본은 /compute[Python] 사용)",
        )
    if req.component not in COMPONENT_REGISTRY:
        return ComputeResponse(
            outputs={}, newState=req.state,
            error=f"Modelica 브릿지 미지원 컴포넌트: '{req.component}'. "
                  f"지원: {list(COMPONENT_REGISTRY)}",
        )
    try:
        block = {'component': req.component, 'params': req.params, 'inputs': req.input}
        result = _mod_compute(block)
        return ComputeResponse(
            outputs=result.get("outputs", {}),
            newState=req.state,
        )
    except Exception as e:
        return ComputeResponse(
            outputs={}, newState=req.state,
            error=f"{type(e).__name__}: {e}",
        )


@app.post("/run_cycle", response_model=CycleResponse)
def run_cycle(req: CycleRequest):
    """전체 L1 폐루프 사이클을 Modelica로 transient 시뮬 → 정착값 + 궤적.

    단일 컴포넌트(/compute_modelica)와 달리 닫힌 루프 + Volume + N-ramp라
    transient 시뮬(dassl)로 정착시킴 (~수십초, 컴파일 포함). omc 필요.
    """
    ok, why = _modelica_status()
    if not ok:
        return CycleResponse(model=req.model,
                             error=f"Modelica 엔진 사용 불가: {why}.")
    if req.model not in CYCLE_MODELS:
        return CycleResponse(model=req.model,
                             error=f"미지원 사이클 모델: '{req.model}'. 지원: {list(CYCLE_MODELS)}")
    try:
        r = _run_cycle(model=req.model, stop_time=req.stop_time,
                       tolerance=req.tolerance, intervals=req.intervals)
        return CycleResponse(model=r['model'], stop_time=r['stop_time'],
                             settled=r['settled'], trajectory=r['trajectory'])
    except Exception as e:
        return CycleResponse(model=req.model, error=f"{type(e).__name__}: {e}")


# ─── Server 실행 ────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"\nLoaded components: {list_components()}\n")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
