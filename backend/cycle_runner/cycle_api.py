"""cycle_api — Python cycle_runner를 FastAPI로 노출 (비동기 job 방식).

L3 커플드는 수십초~수분 걸리므로 동기 요청은 UI를 멈춤. 그래서 job 기반:
  POST /cycle/run       → 즉시 job_id 반환 (계산은 백그라운드 스레드)
  GET  /cycle/status/{job_id} → 진행상태/결과 폴링
  GET  /cycle/params    → 컴포넌트 fidelity별 설계변수 메타 (param-meta.js 대체)

Modelica 기반 /run_cycle (server.py)과 별개 — 이건 순수 Python 엔진.
"""
import io
import time
import uuid
import threading
import contextlib
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

cycle_router = APIRouter(prefix="/cycle", tags=["cycle_runner"])

# ─── job 저장소 (메모리) ──────────────────────────────────────────
# {job_id: {status, progress, message, result, error, started, finished}}
# status ∈ {'queued','running','done','error'}
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_MAX_JOBS = 50  # 오래된 job 정리 상한


def _cleanup_jobs():
    """완료된 오래된 job 제거 (메모리 관리)."""
    with _JOBS_LOCK:
        if len(_JOBS) <= _MAX_JOBS:
            return
        # finished 시각 오래된 것부터 제거
        done = [(jid, j) for jid, j in _JOBS.items()
                if j['status'] in ('done', 'error') and j.get('finished')]
        done.sort(key=lambda x: x[1]['finished'])
        for jid, _ in done[:len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(jid, None)


# ─── 요청/응답 모델 ───────────────────────────────────────────────
class CycleRunRequest(BaseModel):
    # fidelity: 냉매 comp/cond/eev/evap, 공기 drum/filter/fan (evap/cond 공유)
    ref_fidelity: dict[str, int]        # {'compressor':1/2/3, 'condenser':.., 'eev':.., 'evaporator':..}
    air_fidelity: dict[str, int]        # {'drum':.., 'filter':.., 'fan':.., 'evaporator':.., 'condenser':..}
    fan_position: Optional[int] = None  # 공기경로 팬 위치 (None=미배치)
    operating: dict[str, Any]           # comp_rpm/fan_rpm/drum_rpm/SH_target/M_dry/X0/fabric
    dynamic: bool = False               # True면 dynamic_runner (콜드스타트→기동)
    dynamic_opts: Optional[dict] = None # {P_equalize, ramp_time, t_end, dt}
    params_override: Optional[dict] = None  # 컴포넌트별 설계변수 오버라이드


class CycleRunResponse(BaseModel):
    job_id: str
    status: str


class CycleStatusResponse(BaseModel):
    job_id: str
    status: str                    # queued|running|done|error
    progress: float = 0.0          # 0~1
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    elapsed: Optional[float] = None


# ─── operating 변환 (UI 페이로드 → 엔진 규약) ─────────────────────
def _to_engine_operating(op: dict) -> dict:
    """UI operating → coupled_solver operating (초기 추정값 + 운전조건).

    엔진 규약: P_evap/P_cond [bar], N [rpm], opening [%|mm], h_suc [kJ/kg], T_amb [°C].
    UI는 comp_rpm/fan_rpm/drum_rpm/SH_target/M_dry/X0/fabric를 줌.
    초기 P_evap/P_cond/h_suc/opening은 12칸 검증 기본값에서 시작 (warm start가 수렴).
    """
    return {
        'P_evap': op.get('P_evap', 5.0889),
        'P_cond': op.get('P_cond', 9.8762),
        'N': op.get('comp_rpm', op.get('N', 1800)),
        'opening': op.get('opening', 23.586),
        'h_suc': op.get('h_suc', 587.309),
        'T_amb': op.get('T_amb', 35.0),
    }


def _to_air_inlet(op: dict) -> dict:
    """UI operating → coupled_solver air_inlet (드럼 입구 공기 초기 추정).

    실제 드럼 입구 공기는 응축기 출구에서 연성으로 결정되나, 초기값 필요.
    """
    return {
        'T': op.get('air_T', 30.0),
        'RH': op.get('air_RH', 40.0),
        'W': op.get('air_W', 0.0107),
        'V_air_CMM': op.get('V_air_CMM', 2.42),
        'm_dot_air': op.get('m_dot_air', 0.048),
    }


# ─── 백그라운드 계산 실행 ─────────────────────────────────────────
def _run_job(job_id: str, req: CycleRunRequest):
    """스레드에서 실행 — coupled_solver.solve 또는 dynamic_runner.run."""
    def _update(**kw):
        with _JOBS_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id].update(kw)

    _update(status='running', progress=0.05, message='엔진 초기화')
    t0 = time.time()
    try:
        # import는 여기서 (registration 로그 억제)
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            from cycle_runner import coupled_solver, dynamic_runner

        engine_op = _to_engine_operating(req.operating)
        air_inlet = _to_air_inlet(req.operating)
        override = dict(req.params_override or {})

        # 드럼 운전조건(fabric/M_dry/X0)을 params_override['drum']에 주입
        #   coupled_solver.solve는 이들을 operating이 아닌 드럼 params로 받음
        op = req.operating
        drum_params = dict(override.get('drum', {}))
        if 'M_dry' in op:
            drum_params.setdefault('M_dry', op['M_dry'])
        if 'X0' in op:
            drum_params.setdefault('X0', op['X0'])
            drum_params.setdefault('X_init', op['X0'])  # 키 변형 대비
        if 'fabric' in op:
            # UI fabric 명칭 → 백엔드 프리셋 (cotton/poly/mixed) 매핑
            _fabric_map = {
                'cotton': 'cotton', 'poly': 'poly', 'polyester': 'poly',
                'mixed': 'mixed', 'wool': 'mixed', 'synthetic': 'poly',
            }
            fab = _fabric_map.get(str(op['fabric']).lower(), 'cotton')  # 미지원→cotton 폴백
            drum_params.setdefault('fabric', fab)
        if drum_params:
            override['drum'] = drum_params

        # SH_target (EEV PI 제어 목표) — operating에서
        SH_target = req.operating.get('SH_target', None)

        _update(progress=0.15, message='커플드 사이클 수렴 중 (fidelity에 따라 수초~수분)')

        if req.dynamic:
            # 동적: 콜드스타트 → 기동 → 정상
            opts = req.dynamic_opts or {}
            with contextlib.redirect_stdout(io.StringIO()):
                res = dynamic_runner.run(
                    req.ref_fidelity, req.air_fidelity, engine_op, air_inlet,
                    fan_position=req.fan_position,
                    params_override=override,
                    t_end=opts.get('t_end', 1800.0),
                    dt=opts.get('dt', 60.0),
                    N_target=req.operating.get('comp_rpm', 1800.0),
                    ramp_time=opts.get('ramp_time', 120.0),
                    P_equalize=opts.get('P_equalize', 7.0),
                )
            result = _serialize_dynamic(res)
        else:
            # 정상상태 커플드
            with contextlib.redirect_stdout(io.StringIO()):
                res = coupled_solver.solve(
                    req.ref_fidelity, req.air_fidelity, engine_op, air_inlet,
                    fan_position=req.fan_position,
                    params_override=override,
                    SH_target=SH_target,
                )
            result = _serialize_steady(res)

        elapsed = time.time() - t0
        _update(status='done', progress=1.0,
                message=f'완료 ({elapsed:.1f}s)',
                result=result, finished=time.time())
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _update(status='error', progress=1.0,
                message='계산 실패',
                error=f"{type(e).__name__}: {e}\n{tb[-500:]}",
                finished=time.time())


# ─── 결과 직렬화 (엔진 dict → JSON 안전) ──────────────────────────
def _serialize_steady(res: dict) -> dict:
    """coupled_solver.solve 결과 → UI용 요약."""
    rf = res.get('refrigerant', {})
    st = rf.get('state', {})
    air = res.get('air', {})
    air_bc = res.get('air_bc', {})

    # 핵심 성능 지표
    Q_cond = st.get('Q_cond', 0.0)
    Q_evap = st.get('Q_evap', 0.0)
    m_dot = st.get('m_dot', 0.0)
    # 압축기 일: fidelity별 키 다름
    #   L1: state['compressor']['W']  (기계 일)
    #   L2: state['compressor']['W_elec'] (전기) / 'W_shaft' (축)
    #   COP는 실소비전력(전기) 우선, 없으면 축/기계 일
    W_comp = st.get('W_comp', st.get('P_comp', 0.0))
    if not W_comp:
        comp_st = st.get('compressor', {})
        if isinstance(comp_st, dict):
            W_comp = (comp_st.get('W_elec')
                      or comp_st.get('W')
                      or comp_st.get('W_shaft')
                      or comp_st.get('W_comp')
                      or 0.0)
    COP = (Q_evap / W_comp) if W_comp else 0.0
    COP_heating = (Q_cond / W_comp) if W_comp else 0.0

    return {
        'kind': 'steady',
        'converged': res.get('converged', False),
        'outer_iter': res.get('outer_iter', 0),
        'performance': {
            'P_evap': rf.get('P_evap'),
            'P_cond': rf.get('P_cond'),
            'm_dot': m_dot,
            'Q_cond': Q_cond,
            'Q_evap': Q_evap,
            'W_comp': W_comp,
            'COP': COP,                  # 냉방 COP (Q_evap/W)
            'COP_heating': COP_heating,  # 난방 COP (Q_cond/W)
            'SH_evap': st.get('SH_evap'),
            'SC_cond': st.get('SC_cond'),
        },
        'air_bc': {
            hx: {
                'T_air_in': v.get('T_air_in'),
                'RH_air_in': v.get('RH_air_in'),
                'V_air_CMM': v.get('V_air_CMM'),
            } for hx, v in air_bc.items()
        },
        'state': {k: (float(v) if isinstance(v, (int, float)) else v)
                  for k, v in st.items() if not isinstance(v, (list, dict))},
    }


def _serialize_dynamic(res: dict) -> dict:
    """dynamic_runner.run 결과 → UI용 (궤적 포함).

    trajectory 스텝 키: t, N, P_evap, P_cond, m_dot, Q_cond, Q_evap, X_dry, phase.
    시계열 배열(그래프용) + 최종 스텝 요약.
    """
    traj = res.get('trajectory', res.get('history', []))
    series = {}
    if traj and isinstance(traj, list):
        # 그래프용 시계열 (실제 존재 키만)
        num_keys = ['t', 'N', 'P_evap', 'P_cond', 'm_dot', 'Q_cond', 'Q_evap', 'X_dry']
        for k in num_keys:
            vals = [pt.get(k) for pt in traj if isinstance(pt, dict)]
            # None 아닌 값이 하나라도 있으면 포함
            if any(v is not None for v in vals):
                series[k] = vals
        # phase는 문자열 시계열 (상태 전환 표시)
        phases = [pt.get('phase') for pt in traj if isinstance(pt, dict)]
        if any(p is not None for p in phases):
            series['phase'] = phases

    final = traj[-1] if traj else {}
    return {
        'kind': 'dynamic',
        'converged': res.get('converged_steps', 0) == res.get('total_steps', 1),
        'converged_steps': res.get('converged_steps', 0),
        'total_steps': res.get('total_steps', len(traj) if isinstance(traj, list) else 0),
        'n_steps': len(traj) if isinstance(traj, list) else 0,
        'series': series,
        'final': {k: (float(v) if isinstance(v, (int, float)) else v)
                  for k, v in final.items() if not isinstance(v, (list, dict))} if isinstance(final, dict) else {},
    }


# ─── 엔드포인트 ───────────────────────────────────────────────────
@cycle_router.post("/run", response_model=CycleRunResponse)
def cycle_run(req: CycleRunRequest):
    """커플드 사이클 계산 시작 → job_id 반환 (백그라운드 실행)."""
    _cleanup_jobs()
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            'status': 'queued', 'progress': 0.0, 'message': '대기 중',
            'result': None, 'error': None,
            'started': time.time(), 'finished': None,
        }
    # 백그라운드 스레드 (daemon — 서버 종료 시 함께)
    th = threading.Thread(target=_run_job, args=(job_id, req), daemon=True)
    th.start()
    return CycleRunResponse(job_id=job_id, status='queued')


@cycle_router.get("/status/{job_id}", response_model=CycleStatusResponse)
def cycle_status(job_id: str):
    """job 진행 상태/결과 조회."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return CycleStatusResponse(job_id=job_id, status='error',
                                       error='job_id 없음 (만료되었거나 잘못된 ID)')
        j = dict(job)  # 복사
    elapsed = None
    if j.get('started'):
        end = j.get('finished') or time.time()
        elapsed = end - j['started']
    return CycleStatusResponse(
        job_id=job_id, status=j['status'], progress=j.get('progress', 0.0),
        message=j.get('message', ''), result=j.get('result'),
        error=j.get('error'), elapsed=elapsed,
    )


@cycle_router.get("/params")
def cycle_params():
    """컴포넌트 fidelity별 설계변수 메타 (param-meta.js 대체).

    UI ParamPanel이 이걸 fetch해서 동적 표시. 우선순위:
      1) 모듈에 modelDescription 있으면 그 variables 중 causality='parameter' 사용
         (냉매 comp/cond/eev/evap — group/unit/options 풍부).
      2) 없으면(공기 함수형) default_params + 알려진 형상 파라미터 폴백.
    """
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf):
        try:
            from cycle_runner.refrigerant_loop import get_component
        except Exception as e:
            return {'error': f'get_component import 실패: {e}'}

    def _from_model_desc(mod):
        """modelDescription.variables → parameter 리스트."""
        md = getattr(mod, 'modelDescription', None)
        if not md or 'variables' not in md:
            return None
        out = []
        for v in md['variables']:
            if v.get('causality') != 'parameter':
                continue
            item = {
                'name': v['name'],
                'start': v.get('start'),
                'type': v.get('type', 'Real'),
                'unit': v.get('unit', '-'),
                'group': v.get('group', 'General'),
                'desc': v.get('description', ''),
            }
            if 'options' in v:
                item['options'] = v['options']
            out.append(item)
        return out

    # 공기 컴포넌트 형상 파라미터 (modelDescription 없음 — 수동 정의)
    # 필터는 앞서 형상 작업으로 shape/mesh, 팬은 fan-sim, 드럼은 형상
    AIR_MANUAL = {
        'filter': {
            '1': [
                {'name': 'shape', 'start': 'rectangular', 'type': 'String', 'unit': '-', 'group': 'Geometry', 'desc': '필터 면 형상', 'options': ['rectangular', 'circular']},
                {'name': 'W', 'start': 200.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '가로 (직사각형)'},
                {'name': 'H', 'start': 100.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '세로 (직사각형)'},
                {'name': 'D_major', 'start': 250.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '장축 (원형/타원)'},
                {'name': 'D_minor', 'start': 250.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '단축 (원형/타원)'},
                {'name': 'K', 'start': 20.0, 'type': 'Real', 'unit': '1/m', 'group': 'Fitting', 'desc': '압력강하 계수'},
            ],
            '2': [
                {'name': 'shape', 'start': 'rectangular', 'type': 'String', 'unit': '-', 'group': 'Geometry', 'desc': '필터 면 형상', 'options': ['rectangular', 'circular']},
                {'name': 'W', 'start': 200.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '가로'},
                {'name': 'H', 'start': 100.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '세로'},
                {'name': 'a_visc', 'start': 50000.0, 'type': 'Real', 'unit': '-', 'group': 'Fitting', 'desc': '점성 계수'},
                {'name': 'b_inert', 'start': 17.0, 'type': 'Real', 'unit': '-', 'group': 'Fitting', 'desc': '관성 계수'},
            ],
            '3': [
                {'name': 'shape', 'start': 'rectangular', 'type': 'String', 'unit': '-', 'group': 'Geometry', 'desc': '필터 면 형상', 'options': ['rectangular', 'circular']},
                {'name': 'W', 'start': 200.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '가로 (직사각형)'},
                {'name': 'H', 'start': 100.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '세로 (직사각형)'},
                {'name': 'D_major', 'start': 250.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '장축 (원형/타원)'},
                {'name': 'D_minor', 'start': 250.0, 'type': 'Real', 'unit': 'mm', 'group': 'Geometry', 'desc': '단축 (원형/타원)'},
                {'name': 'MPI', 'start': 15.0, 'type': 'Real', 'unit': '1/inch', 'group': 'Mesh', 'desc': '인치당 메쉬 수'},
                {'name': 'd_w', 'start': 0.4, 'type': 'Real', 'unit': 'mm', 'group': 'Mesh', 'desc': '선경 (wire diameter)'},
                {'name': 'L_thick', 'start': 0.6, 'type': 'Real', 'unit': 'mm', 'group': 'Mesh', 'desc': '메쉬 두께'},
            ],
        },
        'fan': {
            '3': [
                {'name': 'D1', 'start': 120.0, 'type': 'Real', 'unit': 'mm', 'group': 'Impeller', 'desc': '입구경'},
                {'name': 'D2', 'start': 175.0, 'type': 'Real', 'unit': 'mm', 'group': 'Impeller', 'desc': '출구경'},
                {'name': 'b1', 'start': 60.0, 'type': 'Real', 'unit': 'mm', 'group': 'Impeller', 'desc': '입구폭'},
                {'name': 'b2', 'start': 50.0, 'type': 'Real', 'unit': 'mm', 'group': 'Impeller', 'desc': '출구폭'},
                {'name': 'beta2', 'start': 145.0, 'type': 'Real', 'unit': '°', 'group': 'Impeller', 'desc': '출구각'},
                {'name': 'Z', 'start': 36.0, 'type': 'Real', 'unit': '-', 'group': 'Impeller', 'desc': '블레이드 수'},
                {'name': 'cutoffGap', 'start': 8.0, 'type': 'Real', 'unit': 'mm', 'group': 'Scroll', 'desc': '컷오프 간극'},
                {'name': 'wrapAngle', 'start': 360.0, 'type': 'Real', 'unit': '°', 'group': 'Scroll', 'desc': '감김각'},
                {'name': 'diffAngle', 'start': 7.0, 'type': 'Real', 'unit': '°', 'group': 'Diffuser', 'desc': '확산각'},
            ],
        },
    }

    comps = ['compressor', 'condenser', 'eev', 'evaporator', 'drum', 'filter', 'fan']
    ref_comps = {'compressor', 'condenser', 'eev', 'evaporator'}
    meta: dict[str, dict] = {}
    for comp in comps:
        meta[comp] = {}
        for fid in (1, 2, 3):
            params = None
            # 냉매: modelDescription
            if comp in ref_comps:
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        mod = get_component('refrigerant', comp, fid)
                    params = _from_model_desc(mod)
                except Exception:
                    params = None
            # 공기 수동 정의
            if params is None and comp in AIR_MANUAL:
                params = AIR_MANUAL[comp].get(str(fid))
            meta[comp][str(fid)] = params or []
    return meta
