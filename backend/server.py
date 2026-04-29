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

# ─── Design Studio router 등록 ──────────────────────────────────────
# /design/* 경로의 endpoint를 추가. fitting / calibration / validation /
# session 관리.
try:
    from design import design_router
    app.include_router(design_router)
    print("[OK]   Design Studio router mounted at /design/*")
except Exception as e:
    print(f"[WARN] Design Studio router 마운트 실패: {e}")


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


# ─── Routes ─────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """서버가 살아있는지 + 등록된 컴포넌트 목록"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "components": list_components(),
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
