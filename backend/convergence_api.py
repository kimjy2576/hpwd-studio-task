"""convergence_api — 수렴 테스트 조합 실행·기록 API (2026-07-30).

UI (public/convergence/) 가 쓰는 두 엔드포인트를 제공한다.

    POST /api/convergence/run
      body { id, engine, props, jac, solver, kind, opts }
      resp { id, status, t, steps, metric, note, series? }

    GET  /api/convergence/history
      resp [ { id, status, t, steps, metric, note, at } ]

설계 방침
    실행은 오래 걸린다(Modelica 빌드 3~5분, Python 완전연성 35초).
    그래서 run 은 백그라운드 잡을 띄우고 즉시 'running' 을 돌려주는 대신,
    UI 가 단순하도록 동기 실행을 택했다. 다만 timeout 을 두어
    막히면 'bad' 로 정직하게 보고한다.
    (긴 해석은 워크스테이션에서 CLI 로 돌리는 편이 낫다 —
     cycle_runner/run_dynamic.py 참고)

기록은 JSON 파일에 누적한다. DB 를 붙이기 전 단계.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

convergence_router = APIRouter(prefix="/api/convergence", tags=["convergence"])

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
HISTORY = BACKEND / "_convergence_history.json"

# 조합 id -> 실행 방법. UI ROWS 의 id 와 일치해야 한다.
#   kind='py'  : 파이썬 함수 직접 호출
#   kind='omc' : OpenModelica 빌드+실행 (시간이 오래 걸린다)
RECIPES: Dict[str, Dict[str, Any]] = {
    # ── Python 정상해 ──
    "py-ss-part": {
        "kind": "py", "fn": "steady_partial",
        "desc": "부분 커플드 정상해 (공기 BC 고정, SH 구속)",
    },
    "py-ss-full": {
        "kind": "py", "fn": "steady_full",
        "desc": "완전 커플드 정상해 (드럼 루프 + SH 구속)",
    },
    "py-ss-full-broy": {
        "kind": "py", "fn": "steady_full", "extra": {"use_broyden": True},
        "desc": "완전 커플드 + broyden1 (참고용 — 실패 후 hybr 재시도)",
    },
    "py-ss-tab": {
        "kind": "py", "fn": "steady_partial", "extra": {"table_props": True},
        "desc": "부분 커플드 + 테이블 물성 (개선 전 기준)",
    },
    # ── Python 동적 ──
    "py-dyn-60":    {"kind": "py", "fn": "dynamic", "extra": {"dt": 60.0}},
    "py-dyn-20":    {"kind": "py", "fn": "dynamic", "extra": {"dt": 20.0}},
    "py-dyn-pulse": {"kind": "py", "fn": "dynamic",
                     "extra": {"dt": 20.0, "use_pulse": True}},
    # ── Modelica ──
    "omc-cond-tab-num": {"kind": "omc", "model": "CmpParts.Cond_L3",
                         "solver": "ida", "jac": "numeric"},
    "omc-cond-tab-sym": {"kind": "omc", "model": "CmpParts.Cond_L3",
                         "solver": "ida", "jac": "symbolic"},
    "omc-cond-ana-num": {"kind": "omc", "model": "CmpParts.Cond_L3",
                         "solver": "ida", "jac": "numeric"},
    "omc-cond-ana-sym": {"kind": "omc", "model": "CmpParts.Cond_L3",
                         "solver": "ida", "jac": "symbolic"},
    "omc-ss-tab-num":   {"kind": "omc", "model": "HPWDcycle.Cycle_L3_ssinit",
                         "solver": "gbode", "jac": "numeric"},
    "omc-ss-ana-num":   {"kind": "omc", "model": "HPWDcycle.Cycle_L3_ssinit",
                         "solver": "gbode", "jac": "numeric"},
    "omc-ss-ana-sym":   {"kind": "omc", "model": "HPWDcycle.Cycle_L3_ssinit",
                         "solver": "gbode", "jac": "symbolic"},
    "omc-cs-tab-num-ida": {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "ida", "jac": "numeric"},
    "omc-cs-ana-num-ida": {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "ida", "jac": "numeric"},
    "omc-cs-ana-num-das": {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "dassl", "jac": "numeric"},
    "omc-cs-ana-sym-das": {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "dassl", "jac": "symbolic"},
    "omc-cs-ana-num-gbo": {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "gbode", "jac": "numeric"},
    "omc-cs-pulse":       {"kind": "omc", "model": "HPWDcycle.Cycle_L3_coldstart_charge",
                           "solver": "dassl", "jac": "symbolic"},
}

def find_omc() -> Optional[str]:
    """omc 실행 파일을 찾는다.

    2026-07-30: shutil.which('omc') 만으로는 못 찾는 환경이 있다.
      - 서버가 PATH 를 물려받지 못한 경우(systemd, IDE 터미널 등)
      - Windows/WSL2 에서 omc.exe 로 설치된 경우
      - OpenModelica 기본 설치 경로에만 있는 경우
    환경변수 OMC_BIN (server.py 와 동일) 또는 OMC_PATH 로 지정 가능.
    """
    # 2026-07-30: 기존 server.py 는 $OMC_BIN 을 쓴다. 같은 이름을 우선한다.
    #   (OMC_PATH 로 잘못 찾아 '설치 필요' 로 오진했던 원인)
    for var in ("OMC_BIN", "OMC_PATH"):
        env = os.environ.get(var)
        if env and Path(env).is_file():
            return env
    for name in ("omc", "omc.exe"):
        w = shutil.which(name)
        if w:
            return w
    cands = [
        "/usr/bin/omc", "/usr/local/bin/omc", "/opt/openmodelica/bin/omc",
        "/C:/Program Files/OpenModelica/bin/omc.exe",
        "/mnt/c/Program Files/OpenModelica/bin/omc.exe",
    ]
    for c in cands:
        if Path(c).exists():
            return c
    # OPENMODELICAHOME 이 있으면 그 아래 bin
    home = os.environ.get("OPENMODELICAHOME")
    if home:
        for name in ("omc", "omc.exe"):
            c = Path(home) / "bin" / name
            if c.exists():
                return str(c)
    return None


GEOM = {
    "V_n1": 1.832e-5, "V_n2": 9.99e-6, "V_n3": 3.66e-6,
    "V_acc": 2.226e-4, "V_oil_cc": 160.0, "V_shell": 4.0e-4,
}
REF_FID = {"compressor": 3, "condenser": 3, "eev": 3, "evaporator": 3}
AIR_FID = {"drum": 1, "filter": 1, "fan": 1, "evaporator": 3, "condenser": 3}


class RunReq(BaseModel):
    id: str
    engine: str = "Python"
    props: str = "해석형"
    jac: str = "수치"
    solver: str = "hybr"
    kind: str = ""
    opts: Dict[str, Any] = Field(default_factory=dict)


class RunResp(BaseModel):
    id: str
    status: str               # ok | warn | bad | none
    t: Optional[float] = None
    steps: Optional[int] = None
    metric: str = "—"
    note: str = ""
    series: Optional[Dict[str, List[float]]] = None


def _f(d: Dict[str, Any], k: str, dv: float) -> float:
    try:
        return float(d.get(k, dv))
    except (TypeError, ValueError):
        return dv


def _save(rec: Dict[str, Any]) -> None:
    hist: List[Dict[str, Any]] = []
    if HISTORY.exists():
        try:
            hist = json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("id") != rec["id"]] + [rec]
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                       encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# Python 실행기
# ══════════════════════════════════════════════════════════════
def _air_bc(T: float = 12.70, RH: float = 99.0, Te: float = 20.0,
            RHe: float = 80.0, V: float = 2.42) -> Dict[str, Any]:
    return {"condenser": {"T_air_in": T, "RH_air_in": RH, "V_air_CMM": V},
            "evaporator": {"T_air_in": Te, "RH_air_in": RHe, "V_air_CMM": V}}


def run_py(rid: str, rec: Dict[str, Any], opts: Dict[str, Any]) -> RunResp:
    sys.path.insert(0, str(BACKEND))
    extra = dict(rec.get("extra") or {})
    charge = _f(opts, "charge", 100.0) / 1000.0
    sh = _f(opts, "sh", 6.0)
    sh_t = sh if sh > 0 else None
    op = {"P_evap": 6.09, "P_cond": 10.46, "N": 1800.0,
          "opening": 23.586, "h_suc": 595.4, "T_amb": 35.0}
    fn = rec["fn"]
    t0 = time.time()

    if fn == "steady_partial":
        from cycle_runner.charge_closure import solve_forward
        r = solve_forward(REF_FID, op, _air_bc(), charge, GEOM, SH_target=sh_t)
        w = time.time() - t0
        ok = bool(r["success"])
        return RunResp(id=rid, status="ok" if ok else "bad", t=round(w, 2),
                       steps=r.get("nfev"),
                       metric=f"Pc {r['P_cond']:.4f} / SH {r['SH_evap']:.3f}",
                       note=f"개도 {r.get('opening', op['opening']):.2f} %"
                            f"{'' if ok else ' · 미수렴'}")

    if fn == "steady_full":
        from cycle_runner.coupled_charge import solve as coupled
        r = coupled(REF_FID, AIR_FID, op,
                    {"T": 30.0, "RH": 40.0, "V_air_CMM": 2.42},
                    charge, GEOM, fan_position=4, SH_target=sh_t,
                    max_outer=int(_f(opts, "max_outer", 12)),
                    **{k: v for k, v in extra.items() if k != "table_props"})
        w = time.time() - t0
        rr = r["refrigerant"]
        conv = bool(r["converged"])
        return RunResp(id=rid, status="ok" if conv else "warn", t=round(w, 1),
                       steps=r["outer_iter"],
                       metric=f"Pc {rr['P_cond']:.4f} / SH {rr['SH_evap']:.3f}",
                       note=f"개도 {rr.get('opening', 0):.2f} %"
                            f"{'' if conv else ' · outer 미수렴'}")

    if fn == "dynamic":
        from cycle_runner import dynamic_charge as dc
        r = dc.run(REF_FID, AIR_FID, op,
                   {"T": 30.0, "RH": 40.0, "V_air_CMM": 2.42},
                   charge, GEOM, fan_position=4, SH_target=sh_t,
                   t_end=_f(opts, "stop", 120.0),
                   dt=_f(opts, "dt", extra.get("dt", 20.0)),
                   use_pulse=bool(extra.get("use_pulse",
                                            str(opts.get("pulse")) == "켬")),
                   max_outer=int(_f(opts, "max_outer", 8)))
        w = time.time() - t0
        n_ok, n = r["converged_steps"], r["total_steps"]
        tr = [x for x in r["trajectory"] if x.get("m_w") is not None]
        dried = (tr[0]["m_w"] - tr[-1]["m_w"]) * 1000 if len(tr) >= 2 else 0.0
        st = "ok" if n_ok == n else ("warn" if n_ok >= n * 0.5 else "bad")
        return RunResp(id=rid, status=st, t=round(w, 1), steps=n_ok,
                       metric=f"수렴 {n_ok}/{n} · 건조 {dried:.1f} g",
                       note=f"전환 t={r['phase_switch_t']}",
                       series={"t": [x["t"] for x in r["trajectory"]],
                               "SH": [x.get("SH") or 0.0 for x in r["trajectory"]]})

    return RunResp(id=rid, status="bad", metric="—",
                   note=f"실행 방법이 정의되지 않았습니다: {fn}")


# ══════════════════════════════════════════════════════════════
# Modelica 실행기
# ══════════════════════════════════════════════════════════════
def run_omc(rid: str, rec: Dict[str, Any], opts: Dict[str, Any]) -> RunResp:
    """omc 로 빌드 후 실행. 오래 걸리므로 timeout 을 넉넉히 준다."""
    omc = find_omc()
    if not omc:
        return RunResp(id=rid, status="bad", metric="—",
                       note="omc 를 찾지 못했습니다. 환경변수 OMC_PATH 로 "
                            "실행 파일 경로를 지정하십시오 (OMC_BIN). "
                            "(GET /api/convergence/recipes 에서 탐색 결과 확인)")

    model = rec["model"]
    solver = str(opts.get("solver") or rec.get("solver", "dassl"))
    jac = rec.get("jac", "numeric")
    tol = str(opts.get("tol", "1e-3"))
    stop = _f(opts, "stop", 120.0)
    threads = int(_f(opts, "threads", 1))
    work = BACKEND / "_omc_work" / rid
    work.mkdir(parents=True, exist_ok=True)

    flags = []
    if jac == "symbolic":
        flags.append('setCommandLineOptions("--generateDynamicJacobian=symbolic");')
    mos = "\n".join(flags + [
        f'runScript("{REPO}/verify/load_all.mos");',
        f'simulate({model}, stopTime={stop}, tolerance={tol}, '
        f'method="{solver}", outputFormat="csv", '
        'variableFilter="(M_total|Pc_bar|Pe_bar|SH|comp.N|evap.x_out|ctrl.n_act)");',
        "getErrorString();",
    ])
    (work / "run.mos").write_text(mos, encoding="utf-8")

    t0 = time.time()
    try:
        p = subprocess.run([omc, "run.mos"], cwd=work, timeout=900,
                           capture_output=True, text=True)
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return RunResp(id=rid, status="bad", t=900.0, metric="—",
                       note="15분 안에 끝나지 않았습니다. 워크스테이션 CLI 를 쓰십시오.")
    w = time.time() - t0

    exe = work / model
    csv = work / f"{model}_res.csv"
    if "Failed to build" in out or not exe.exists():
        err = ""
        for line in out.splitlines():
            if "Error" in line or "error:" in line:
                err = line.strip()[:90]
                break
        return RunResp(id=rid, status="bad", t=round(w, 1), metric="빌드 실패",
                       note=err or "빌드 로그를 확인하십시오.")

    # 결과 판독
    if not csv.exists():
        return RunResp(id=rid, status="bad", t=round(w, 1), metric="결과 없음",
                       note="빌드는 됐으나 실행 결과가 없습니다.")
    rows = [l.split(",") for l in csv.read_text().strip().split("\n")]
    head = [c.strip('"') for c in rows[0]]
    data = [[float(x) for x in r] for r in rows[1:] if len(r) == len(head)]
    if not data:
        return RunResp(id=rid, status="bad", t=round(w, 1), metric="출력 0점",
                       note="초기화만 끝났습니다.")

    def col(n: str) -> Optional[int]:
        for i, h in enumerate(head):
            if h == n or h.endswith("." + n):
                return i
        return None

    t_end = data[-1][0]
    im = col("M_total")
    drift = (max(abs(r[im] / 0.1 - 1) for r in data) * 100) if im else 0.0
    done = t_end >= stop * 0.98
    failed = "Integrator failed" in out
    st = "ok" if (done and drift < 0.5) else ("warn" if t_end > stop * 0.1 else "bad")
    metric = f"드리프트 {drift:.3f} %" if im else f"t={t_end:.2f}"
    note = f"t={t_end:.2f} / {stop:.0f} s"
    if failed:
        note += " · 적분 실패"
    if threads > 1:
        note += f" · {threads} 스레드"
    return RunResp(id=rid, status=st, t=round(w, 1), steps=len(data),
                   metric=metric, note=note)


# ══════════════════════════════════════════════════════════════
# 엔드포인트
# ══════════════════════════════════════════════════════════════
@convergence_router.post("/run", response_model=RunResp)
def run(req: RunReq) -> RunResp:
    rec = RECIPES.get(req.id)
    if rec is None:
        return RunResp(id=req.id, status="bad", metric="—",
                       note=f"알 수 없는 조합입니다: {req.id}")
    try:
        if rec["kind"] == "py":
            res = run_py(req.id, rec, req.opts)
        else:
            res = run_omc(req.id, rec, req.opts)
    except Exception as e:  # 실행 실패를 정직하게 돌려준다
        res = RunResp(id=req.id, status="bad", metric="예외",
                      note=f"{type(e).__name__}: {e}"[:120])
    _save({**res.model_dump(exclude={"series"}),
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return res


@convergence_router.get("/history")
def history() -> List[Dict[str, Any]]:
    if not HISTORY.exists():
        return []
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


@convergence_router.get("/recipes")
def recipes() -> Dict[str, Any]:
    """어떤 조합을 실행할 수 있는지. UI 가 표를 검증할 때 쓴다."""
    omc = find_omc()
    ver = None
    if omc:
        try:
            ver = subprocess.run([omc, "--version"], capture_output=True,
                                 text=True, timeout=20).stdout.strip()
        except Exception as e:
            ver = f"실행하지 못했습니다: {type(e).__name__}"
    return {
        "ids": sorted(RECIPES),
        "omc_available": omc is not None,
        "omc_path": omc,
        "omc_version": ver,
        "cpu_count": os.cpu_count(),
        "which_omc": shutil.which("omc"),
        "env_OMC_BIN": os.environ.get("OMC_BIN"),
        "env_OMC_PATH": os.environ.get("OMC_PATH"),
        "env_OPENMODELICAHOME": os.environ.get("OPENMODELICAHOME"),
        "path_head": (os.environ.get("PATH") or "").split(os.pathsep)[:6],
    }
