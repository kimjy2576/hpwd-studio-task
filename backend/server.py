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
                                  run_canvas_cycle as _run_canvas_cycle,
                                  run_air_cycle as _run_air_cycle,
                                  run_coupled_cycle as _run_coupled_cycle, COUPLED_MODELS,
                                  run_canvas_coupled_cycle as _run_canvas_coupled_cycle,
                                  run_cycle_l2 as _run_cycle_l2, ALL_L2_MODELS,
                                  CYCLE_MODELS_L2, COUPLED_MODELS_L2,
                                  COMPONENT_REGISTRY, CYCLE_MODELS, HELMHOLTZ_PATH)
    _modelica['imported'] = True
    print(f"[OK]   Modelica bridge imported (components: {list(COMPONENT_REGISTRY)})")
except Exception as e:
    _modelica['error'] = f"{type(e).__name__}: {e}"
    print(f"[WARN] Modelica bridge import 실패: {_modelica['error']}")


def _modelica_status():
    """Modelica 엔진 사용 가능 여부 (omc + HelmholtzMedia 존재).
    omc 탐지 순서: ① $OMC_BIN (직접 지정한 omc.exe 경로) → ② PATH 상의 'omc'."""
    if not _modelica['imported']:
        return False, f"bridge import 실패: {_modelica['error']}"
    omc_bin = os.environ.get("OMC_BIN")
    if omc_bin:
        if not os.path.isfile(omc_bin):
            return False, f"OMC_BIN 경로에 파일 없음: {omc_bin}"
    elif shutil.which("omc") is None:
        return False, "omc 없음 (OpenModelica 미설치 or PATH 미설정 — $OMC_BIN env로 omc.exe 경로 직접 지정 가능)"
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


class CanvasCycleRequest(BaseModel):
    # 캔버스에서 추출한 링 토폴로지 + 기동/초기화 설정
    topology: dict[str, Any]            # {components:[{id,kind,params}], ring:[id...], volumes:[V...]}
    settings: dict[str, Any] = {}       # {charge_g, p_rest_bar, t_ramp, stop_time, tolerance, intervals}


class CanvasCycleResponse(BaseModel):
    settled: dict[str, Any] = {}
    trajectory: dict[str, Any] = {}
    meta: dict[str, Any] = {}           # {h_rest, charge_g, pc_vol, pe_vol, ...}
    generated_mo: str | None = None     # 생성된 .mo 텍스트 (디버그/표시용)
    stop_time: float = 0.0
    error: str | None = None


class CoupledCanvasRequest(BaseModel):
    # 캔버스에서 추출한 냉매 링 + 공기 링 (evap/cond 공유 = merged HX)
    ref_topology: dict[str, Any]        # {components:[{id,kind,params}], ring:[id...]} comp→cond→eev→evap
    air_topology: dict[str, Any]        # {components:[{id,kind,params}], ring:[id...]} drum→[filter]→fan→evap→cond
    settings: dict[str, Any] = {}       # {stop_time, tolerance, intervals}


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
            "cycles_l2": list(ALL_L2_MODELS) if _modelica['imported'] else [],
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


@app.post("/run_canvas_cycle", response_model=CanvasCycleResponse)
def run_canvas_cycle(req: CanvasCycleRequest):
    """캔버스 토폴로지 → 사이클 .mo 자동생성 → transient 시뮬 → 정착값+궤적.

    /run_cycle 은 손으로 짠 고정 모델, 이건 사용자가 캔버스에서 구성한 링을
    받아 .mo 를 생성해서 푼다. omc 필요."""
    ok, why = _modelica_status()
    if not ok:
        return CanvasCycleResponse(error=f"Modelica 엔진 사용 불가: {why}.")
    try:
        topo = req.topology or {}
        ring = topo.get('ring') or []
        kinds = {c.get('kind') for c in (topo.get('components') or [])}
        need = {'compressor', 'condenser', 'eev', 'evaporator'}
        if not need.issubset(kinds):
            return CanvasCycleResponse(
                error=f"링에 필요한 컴포넌트 부족: {sorted(need - kinds)} 누락 "
                      f"(현재 {sorted(kinds)}). Comp·Cond·EEV·Evap 4개가 닫힌 링이어야 함.")
        r = _run_canvas_cycle(topo, req.settings or {})
        return CanvasCycleResponse(settled=r['settled'], trajectory=r['trajectory'],
                                   meta=r['meta'], generated_mo=r['generated_mo'],
                                   stop_time=r['stop_time'])
    except Exception as e:
        return CanvasCycleResponse(error=f"{type(e).__name__}: {e}")


@app.post("/run_air_cycle", response_model=CanvasCycleResponse)
def run_air_cycle(req: CanvasCycleRequest):
    """캔버스 공기 토폴로지 → 공기 사이클 .mo 자동생성 → 시뮬 → 정착값+궤적.

    냉매 /run_canvas_cycle 의 공기 대칭판. 공기 링(drum→fan→evap→cond→drum)을
    받아 .mo 생성·실행. 코일온도(T_evap/T_cond)는 고정 경계조건. omc 필요."""
    ok, why = _modelica_status()
    if not ok:
        return CanvasCycleResponse(error=f"Modelica 엔진 사용 불가: {why}.")
    try:
        topo = req.topology or {}
        kinds = {c.get('kind') for c in (topo.get('components') or [])}
        need = {'drum', 'fan', 'evaporator', 'condenser'}
        if not need.issubset(kinds):
            return CanvasCycleResponse(
                error=f"공기 링에 필요한 컴포넌트 부족: {sorted(need - kinds)} 누락 "
                      f"(현재 {sorted(kinds)}). Drum·Fan·Evap·Cond 4개가 공기 연결로 닫힌 링이어야 함.")
        r = _run_air_cycle(topo, req.settings or {})
        return CanvasCycleResponse(settled=r['settled'], trajectory=r['trajectory'],
                                   meta=r['meta'], generated_mo=r['generated_mo'],
                                   stop_time=r['stop_time'])
    except Exception as e:
        return CanvasCycleResponse(error=f"{type(e).__name__}: {e}")


@app.post("/run_coupled_cycle", response_model=CycleResponse)
def run_coupled_cycle(req: CycleRequest):
    """냉매-공기 커플드 사이클 (HPWDcpl.Cycle_coupled_*) transient 시뮬.

    merged HX(Evap/Cond_coupled)로 냉매 링 + 공기 폐루프를 동시에 결합 — 코일온도가
    prescribed가 아니라 상호결정됨. 냉매(Pc/Pe/W/SH)+공기(X/m_evap/열풍)+SMER 반환. omc 필요."""
    ok, why = _modelica_status()
    if not ok:
        return CycleResponse(model=req.model, error=f"Modelica 엔진 사용 불가: {why}.")
    model = req.model if req.model in COUPLED_MODELS else 'Cycle_coupled_closed'
    try:
        r = _run_coupled_cycle(model=model, stop_time=req.stop_time,
                               tolerance=req.tolerance, intervals=req.intervals)
        return CycleResponse(model=r['model'], stop_time=r['stop_time'],
                             settled=r['settled'], trajectory=r['trajectory'])
    except Exception as e:
        return CycleResponse(model=model, error=f"{type(e).__name__}: {e}")


class CycleL2Request(BaseModel):
    model: str = "CycleDynL2"    # CycleDynL2 | Cycle_SEMI_full | Cycle_coupled_closed_L2air
    stop_time: float = 120.0
    tolerance: float = 1e-6
    intervals: int | None = None   # None → stopTime(1s 스텝): 풀SEMI init 안정화


@app.post("/run_cycle_l2", response_model=CycleResponse)
def run_cycle_l2_endpoint(req: CycleL2Request):
    """L2 SEMI 사이클(냉매 CycleDynL2 / 커플드 Cycle_SEMI_full·_L2air) transient 시뮬.

    L1 /run_cycle·/run_coupled_cycle의 L2판 — 전 컴포넌트 SEMI MB HX. 냉매(Pc/Pe/
    SH/W)+커플드(X/응축수/SMER) 통합 반환. 모델별 패키지·로드파일은 bridge
    레지스트리(ALL_L2_MODELS)가 조회. omc 필요(컴파일 포함 수십초~수분).
    """
    ok, why = _modelica_status()
    if not ok:
        return CycleResponse(model=req.model, error=f"Modelica 엔진 사용 불가: {why}.")
    if req.model not in ALL_L2_MODELS:
        return CycleResponse(model=req.model,
                             error=f"미지원 L2 사이클 모델: '{req.model}'. 지원: {list(ALL_L2_MODELS)}")
    try:
        r = _run_cycle_l2(model=req.model, stop_time=req.stop_time,
                          tolerance=req.tolerance, intervals=req.intervals)
        return CycleResponse(model=r['model'], stop_time=r['stop_time'],
                             settled=r['settled'], trajectory=r['trajectory'])
    except Exception as e:
        return CycleResponse(model=req.model, error=f"{type(e).__name__}: {e}")


@app.post("/run_canvas_coupled_cycle", response_model=CanvasCycleResponse)
def run_canvas_coupled_cycle(req: CoupledCanvasRequest):
    """캔버스에서 추출한 냉매 링 + 공기 링 → 커플드 .mo 자동생성 → transient 시뮬.

    evap/cond를 양쪽 링이 공유(merged HX). 표준 토폴로지면 고정 모델 Cycle_coupled_closed와
    동일 결과(SMER~2.44). 냉매+공기 KPI + SMER + 생성된 .mo 반환. omc 필요."""
    ok, why = _modelica_status()
    if not ok:
        return CanvasCycleResponse(error=f"Modelica 엔진 사용 불가: {why}.")
    st = req.settings or {}
    try:
        r = _run_canvas_coupled_cycle(
            req.ref_topology, req.air_topology, st,
            stop_time=float(st.get('stop_time', 180.0)),
            tolerance=float(st.get('tolerance', 1e-6)),
            intervals=int(st.get('intervals', 300)))
        return CanvasCycleResponse(settled=r['settled'], trajectory=r['trajectory'],
                                   meta=r['meta'], generated_mo=r['generated_mo'],
                                   stop_time=r['stop_time'])
    except Exception as e:
        return CanvasCycleResponse(error=f"{type(e).__name__}: {e}")


# ─── 프론트엔드(public/) 정적 서빙 — 단일 서버로 UI+API 통합 ──────────
# 반드시 모든 API 라우트/라우터 등록 이후(여기)에 마운트 → "/" catch-all.
# 로컬/사내서버 공유 시 프론트·API가 same-origin → URL 분기·CORS 불필요.
from fastapi.staticfiles import StaticFiles
_PUBLIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "public"))
if os.path.isdir(_PUBLIC_DIR):
    app.mount("/", StaticFiles(directory=_PUBLIC_DIR, html=True), name="frontend")
    print(f"[OK]   Frontend(public/) mounted at / — {_PUBLIC_DIR}")
else:
    print(f"[WARN] public/ 없음: {_PUBLIC_DIR} (API 전용 모드)")


# ─── Server 실행 ────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\nLoaded components: {list_components()}\n")
    # 사내 공유용 LAN IP 안내
    try:
        import socket
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80)); _lan_ip = _s.getsockname()[0]; _s.close()
    except Exception:
        _lan_ip = None
    print("═══════════════════════════════════════════════════════════")
    print("  HPWD-Studio — UI + API 단일 서버")
    print(f"  로컬:      http://localhost:{port}")
    if _lan_ip:
        print(f"  사내 공유: http://{_lan_ip}:{port}   (같은 망에서 접속)")
    print(f"  Health:    http://localhost:{port}/health")
    m_ok, m_why = _modelica_status()
    if m_ok:
        print("  Modelica:  활성 (OM 엔진 사용 가능)")
    else:
        print(f"  Modelica:  비활성 — {m_why}")
        print(f"             ↳ 서버가 보는 OMC_BIN = {os.environ.get('OMC_BIN') or '(미설정)'}")
        print(f"             ↳ 서버가 보는 HELMHOLTZ_PATH = {os.environ.get('HELMHOLTZ_PATH') or '(미설정 → 기본값)'}")
    print("  종료: Ctrl+C")
    print("═══════════════════════════════════════════════════════════\n")
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
