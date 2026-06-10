"""
캔버스 → Modelica 브릿지 (codegen + 컴파일 캐시 + omc 실행)
═══════════════════════════════════════════════════════════════
canvas 블록 스펙(/compute 요청과 동일 shape: {component, params, inputs})을 받아
  ① 컴포넌트별 매핑(파라미터 이름·단위)으로 SI 변환
  ② standalone Modelica .mo 생성 (경계조건 Source/Sink + 신호 입력)
  ③ OpenModelica(omc)로 실행
  ④ Python step()과 동일한 출력 키로 결과 회수
한다.

[속도] 호출마다 재컴파일(~10~28s)하지 않는다. 컴포넌트 타입별로 모델을
*1회만 buildModel*해서 실행파일을 캐시하고, 이후 호출은 `-override`로
파라미터만 바꿔 재실행한다(~0.02s). 모델 구조(토폴로지)는 타입당 고정이라
파라미터는 전부 런타임 override 가능. (FMU 선컴파일의 경량 버전)

설계 의도(docs/modelica-decision.md): 사이클 솔버는 Modelica(acausal),
캔버스는 이 생성기를 통해 .mo를 emit → omc 실행. 본 모듈이 그 생성기의 시작점.

현재 구현: EEV(type 130, Off) end-to-end. 검증 <0.001% vs eev_off_design.step().
확장 방법: COMPONENT_REGISTRY에 항목 추가 (template + override_map + build_bc).

환경:
  - omc (OpenModelica 1.26+) PATH에 존재
  - HelmholtzMedia: 환경변수 HELMHOLTZ_PATH (default 아래) — R290 물성
  - HPWD .mo: repo의 modelica/ (HPWD.mo 등)
"""
import os, subprocess, csv as _csv, tempfile

# ── 경로 (환경변수로 override 가능) ──────────────────────────────
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELICA_DIR = os.environ.get("HPWD_MODELICA_DIR", os.path.join(_REPO, "modelica"))
HELMHOLTZ_PATH = os.environ.get(
    "HELMHOLTZ_PATH", "/home/claude/HelmholtzMedia/HelmholtzMedia/package.mo")
_WORK = os.environ.get("HPWD_MODELICA_WORK",
                       os.path.join(tempfile.gettempdir(), "hpwd_modelica_work"))

_fs = lambda p: p.replace("\\", "/")   # omc .mos 문자열은 '/'만 안전 (Windows)


def _omc_bin():
    """omc 실행 파일 경로 결정. $OMC_BIN(omc.exe 전체 경로)이 있으면 우선 사용,
    없으면 'omc'를 그대로 반환(=PATH에서 찾음). Windows의 PATH 분쟁을 우회하는 통로."""
    return os.environ.get("OMC_BIN") or "omc"


# ── 단위 변환기 ──────────────────────────────────────────────────
def _ident(v): return float(v)
def _mm2_to_m2(v): return float(v) * 1e-6      # 면적 mm² → m²  ★ 단위변경 반영
def _cc_to_m3(v): return float(v) * 1e-6       # 부피 cm³ → m³ (행정체적)
def _bar_to_pa(v): return float(v) * 1e5       # 압력 bar → Pa
def _kjkg_to_jkg(v): return float(v) * 1e3     # 비엔탈피 kJ/kg → J/kg
def _c_to_k(v): return float(v) + 273.15       # 온도 °C → K
def _pct_to_frac(v): return float(v) / 100.0   # % → 0~1 (RH)


# ── EEV(Off, type 130) 템플릿 ───────────────────────────────────
# 파라미터는 leaf 컴포넌트(eev/src/snk/opn)의 parameter로 두고, 빌드 시점엔
# 기본값을 baked. 런타임엔 `-override eev.A_orifice=..,src.p=..` 로 변경.
def _eev_template(mp, bc):
    modstr = ",".join(f"{k}={v:.10g}" for k, v in mp.items())
    return f"""package CanvasGen
  model GenCase "canvas EEV(Off, t130) → HPWD.EEV_L1 (자동생성)"
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.EEV_L1 eev({modstr});
    HPWD.Source src(p={bc['P_in']:.10g}, h={bc['h_in']:.10g});
    HPWD.Sink snk(p={bc['P_out']:.10g});
    Modelica.Blocks.Sources.Constant opn(k={bc['opening']:.10g});
    Real m_dot_ref, phi_op, rho_in, h_out, T_out, x_out, hl, hv;
  equation
    connect(src.port, eev.port_a);
    connect(eev.port_b, snk.port);
    connect(opn.y, eev.opening);
    m_dot_ref = eev.port_a.m_flow;
    phi_op = eev.phi;
    rho_in = eev.rho_in;
    h_out  = eev.port_b.h_outflow;
    hl = M.bubbleEnthalpy(M.setSat_p(snk.p));
    hv = M.dewEnthalpy(M.setSat_p(snk.p));
    T_out = M.temperature(M.setState_ph(snk.p, h_out)) - 273.15;
    x_out = max(0.0, min(1.0, (h_out - hl)/(hv - hl)));
  end GenCase;
end CanvasGen;
"""


# ── Compressor(이론, L1) 템플릿 — HPWD.Comp_Theoretical ──────────
def _comp_theoretical_template(mp, bc):
    modstr = ",".join(f"{k}={v:.10g}" for k, v in mp.items())
    return f"""package CanvasGen
  model GenCase "canvas Compressor(이론) → HPWD.Comp_Theoretical (자동생성)"
    package M = HelmholtzMedia.HelmholtzFluids.Propane;
    HPWD.Comp_Theoretical comp({modstr});
    HPWD.Source src(p={bc['P_suc']:.10g}, h={bc['h_suc']:.10g});
    HPWD.Sink snk(p={bc['P_dis']:.10g});
    Real m_dot, W, h_dis, T_dis, rho_suc, h_dis_s, pi_ratio;
  equation
    connect(src.port, comp.port_a);
    connect(comp.port_b, snk.port);
    m_dot = comp.m_dot;
    W = comp.W;
    h_dis   = comp.h_dis/1000.0;     // J/kg → kJ/kg (Python 출력과 동일 단위)
    h_dis_s = comp.h_dis_s/1000.0;
    rho_suc = comp.rho_suc;
    pi_ratio = snk.p/src.p;
    T_dis = M.temperature(M.setState_ph(snk.p, comp.h_dis)) - 273.15;
  end GenCase;
end CanvasGen;
"""


def _comp_th_derive(src):
    """흡입 (P_suc, T_suc) → h_suc[J/kg] (Python과 동일 CoolProp 호출 → 동일 상태)."""
    import CoolProp.CoolProp as CP
    P = float(src['P_suc']) * 1e5
    T = float(src['T_suc']) + 273.15
    fluid = src.get('fluid', 'R290')
    return {'src.h': CP.PropsSI('H', 'P', P, 'T', T, fluid)}


# ── Evaporator(Off, L1) 템플릿 — HPWDhx.Evap_UA (2-zone ε-NTU, wet coil) ──
def _evap_template(mp, bc):
    modstr = ",".join(f"{k}={v:.10g}" for k, v in mp.items())
    return f"""package CanvasGen
  model GenCase "canvas Evaporator(Off) → HPWDhx.Evap_UA (자동생성)"
    HPWDhx.Evap_UA evap({modstr});
    HPWDhx.FlowSource src(p={bc['P_evap']:.10g}, h={bc['h_in']:.10g}, m_flow_set={bc['m_dot']:.10g});
    HPWDhx.SinkOpen snk;
    Real T_ref_out, h_ref_out, P_ref_out, SH_out, T_evap, T_air_out;
    Real Q_total, Q_sensible, Q_latent, condensate_rate, is_wet;
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
    T_ref_out = evap.T_ref_out;
    h_ref_out = evap.h_out/1000.0;          // J/kg → kJ/kg
    P_ref_out = evap.P_ref_out/1e5;         // Pa → bar
    SH_out = evap.SH_calc;
    T_evap = evap.T_evap;
    T_air_out = evap.T_air_out_K - 273.15;
    Q_total = evap.Q_2ph_total + evap.Q_SH;
    Q_sensible = evap.Q_sensible_2ph + evap.Q_SH;
    Q_latent = evap.Q_latent;
    condensate_rate = evap.condensate_rate;
    is_wet = evap.is_wet;
  end GenCase;
end CanvasGen;
"""


# ── Condenser(Off, L1) 템플릿 — HPWDhx.Cond_UA (3-zone cascade ε-NTU) ──
def _cond_template(mp, bc):
    modstr = ",".join(f"{k}={v:.10g}" for k, v in mp.items())
    return f"""package CanvasGen
  model GenCase "canvas Condenser(Off) → HPWDhx.Cond_UA (자동생성)"
    HPWDhx.Cond_UA cond({modstr});
    HPWDhx.FlowSource src(p={bc['P_cond']:.10g}, h={bc['h_in']:.10g}, m_flow_set={bc['m_dot']:.10g});
    HPWDhx.SinkOpen snk;
    Real T_ref_out, h_ref_out, P_ref_out, SC_out, T_cond, T_air_out, RH_air_out;
    Real Q_total, Q_deSH, Q_2ph, Q_SC, quality_out;
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
    T_ref_out = cond.T_ref_out;
    h_ref_out = cond.h_out/1000.0;
    P_ref_out = src.p*(1.0 - cond.dP_ref)/1e5;   // Pa → bar (dP 후)
    SC_out = cond.SC_calc;
    T_cond = cond.T_cond_C;
    T_air_out = cond.T_air_out;
    RH_air_out = cond.RH_air_out;
    Q_total = cond.Q_total;
    Q_deSH = cond.Q_deSH;
    Q_2ph = cond.Q_2ph;
    Q_SC = cond.Q_SC;
    quality_out = cond.quality_out;
  end GenCase;
end CanvasGen;
"""


# ── 컴포넌트 레지스트리 (확장 지점) ──────────────────────────────
#   type → { template, param_defaults, build_bc, override_map, outputs }
#   override_map: canvas_key → (flatten된 leaf parameter 이름, 단위변환기)
COMPONENT_REGISTRY = {
    'eev_off_design': {
        'modelica_model': 'HPWD.EEV_L1',
        'param_defaults': {'A_orifice': 3.14e-6, 'Cv_rated': 0.7,
                           'c0': 0.0, 'c1': 0.5, 'c2': 0.3, 'c3': 0.2, 'opening_min': 0.0},
        'build_bc': {'P_in': 1700000.0, 'h_in': 280000.0, 'P_out': 584000.0, 'opening': 50.0},
        'override_map': {
            'A_orifice':   ('eev.A_orifice', _mm2_to_m2),   # ★ mm² → m²
            'Cv_rated':    ('eev.Cv_rated', _ident),
            'c0': ('eev.c0', _ident), 'c1': ('eev.c1', _ident),
            'c2': ('eev.c2', _ident), 'c3': ('eev.c3', _ident),
            'opening_min': ('eev.opening_min', _ident),
            'P_in':  ('src.p', _bar_to_pa),   # bar → Pa
            'h_in':  ('src.h', _kjkg_to_jkg), # kJ/kg → J/kg
            'P_out': ('snk.p', _bar_to_pa),
            'opening': ('opn.k', _ident),
        },
        'outputs': ['m_dot_ref', 'phi_op', 'rho_in', 'h_out', 'T_out', 'x_out'],
        'template': _eev_template,
    },
    'compressor_theoretical': {
        'modelica_model': 'HPWD.Comp_Theoretical',
        'param_defaults': {'V_disp': 10e-6, 'N': 3000.0, 'eta_vol': 0.85, 'eta_isen': 0.65},
        'build_bc': {'P_suc': 551000.0, 'h_suc': 590000.0, 'P_dis': 1907000.0},
        'override_map': {
            'V_disp':   ('comp.V_disp', _cc_to_m3),   # cm³ → m³
            'eta_vol':  ('comp.eta_vol', _ident),
            'eta_isen': ('comp.eta_isen', _ident),
            'N':        ('comp.N', _ident),
            'P_suc':    ('src.p', _bar_to_pa),
            'P_dis':    ('snk.p', _bar_to_pa),
        },
        'derive': _comp_th_derive,   # (P_suc,T_suc) → src.h
        'outputs': ['m_dot', 'W', 'h_dis', 'T_dis', 'rho_suc', 'h_dis_s', 'pi_ratio'],
        'template': _comp_theoretical_template,
    },
    'evaporator_off_design': {
        'modelica_model': 'HPWDhx.Evap_UA',
        'extra_mo': ['EvapUA.mo'],
        'param_defaults': {'T_air_in': 323.15, 'RH_in': 0.9, 'V_air_CMM': 2.54,
                           'UA_2ph': 25.0, 'UA_SH': 4.0, 'dP_ref': 0.02},
        'build_bc': {'P_evap': 551000.0, 'h_in': 336563.0, 'm_dot': 0.00458812},
        'override_map': {
            'T_air_in':  ('evap.T_air_in', _c_to_k),     # °C → K
            'RH_air_in': ('evap.RH_in', _pct_to_frac),   # % → 0~1
            'V_air_CMM': ('evap.V_air_CMM', _ident),
            'UA_2ph':    ('evap.UA_2ph', _ident),
            'UA_SH':     ('evap.UA_SH', _ident),
            'dP_ref':    ('evap.dP_ref', _ident),
            'P_evap':    ('src.p', _bar_to_pa),
            'h_in':      ('src.h', _kjkg_to_jkg),
            'm_dot_ref': ('src.m_flow_set', _ident),
        },
        'outputs': ['T_ref_out', 'h_ref_out', 'P_ref_out', 'SH_out', 'T_evap',
                    'T_air_out', 'Q_total', 'Q_sensible', 'Q_latent',
                    'condensate_rate', 'is_wet'],
        'template': _evap_template,
    },
    'condenser_off_design': {
        'modelica_model': 'HPWDhx.Cond_UA',
        'extra_mo': ['EvapUA.mo'],
        'param_defaults': {'T_air_in_C': 35.0, 'RH_in': 0.5, 'V_air_CMM': 25.42,
                           'UA_deSH': 8.0, 'UA_2ph': 50.0, 'UA_SC': 5.0, 'dP_ref': 0.03},
        'build_bc': {'P_cond': 1907000.0, 'h_in': 702725.0, 'm_dot': 0.00458812},
        'override_map': {
            'T_air_in':  ('cond.T_air_in_C', _ident),    # °C (변환 없음)
            'RH_air_in': ('cond.RH_in', _pct_to_frac),
            'V_air_CMM': ('cond.V_air_CMM', _ident),
            'UA_deSH':   ('cond.UA_deSH', _ident),
            'UA_2ph':    ('cond.UA_2ph', _ident),
            'UA_SC':     ('cond.UA_SC', _ident),
            'dP_ref':    ('cond.dP_ref', _ident),
            'P_cond':    ('src.p', _bar_to_pa),
            'h_in':      ('src.h', _kjkg_to_jkg),
            'm_dot_ref': ('src.m_flow_set', _ident),
        },
        'outputs': ['T_ref_out', 'h_ref_out', 'P_ref_out', 'SC_out', 'T_cond',
                    'T_air_out', 'RH_air_out', 'Q_total', 'Q_deSH', 'Q_2ph',
                    'Q_SC', 'quality_out'],
        'template': _cond_template,
    },
    # L1 컴포넌트 전부 등록됨 (EEV·압축기·증발기·응축기). 다음: 사이클 그래프 조립.
}


# ── 컴파일 캐시 (컴포넌트 타입당 1회 buildModel → 실행파일 재사용) ──
_BUILD_CACHE = {}   # comp_type → {'dir': str, 'exe': str}


def _ensure_built(comp, timeout=240):
    """컴포넌트 타입의 Modelica 모델을 1회 buildModel하고 실행파일 경로를 캐시."""
    if comp in _BUILD_CACHE:
        return _BUILD_CACHE[comp]
    spec = COMPONENT_REGISTRY[comp]
    bdir = os.path.join(_WORK, f"build_{comp}")
    os.makedirs(bdir, exist_ok=True)
    # 기본값으로 .mo 생성 (런타임에 -override로 바꿀 것)
    mo = spec['template'](dict(spec['param_defaults']), dict(spec['build_bc']))
    open(os.path.join(bdir, "CanvasGen.mo"), "w").write(mo)
    # 추가 .mo 의존 (예: HX는 EvapUA.mo) — HPWD.mo 뒤, CanvasGen.mo 앞에 로드
    extra_loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in spec.get('extra_mo', []))
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'loadFile("{_fs(os.path.join(MODELICA_DIR, "HPWD.mo"))}"); getErrorString();\n'
           f'{extra_loads}'
           f'loadFile("{_fs(os.path.join(bdir, "CanvasGen.mo"))}"); getErrorString();\n'
           f'buildModel(CanvasGen.GenCase, outputFormat="csv", stopTime=1,'
           f' numberOfIntervals=1); getErrorString();\n')
    open(os.path.join(bdir, "build.mos"), "w").write(mos)
    r = subprocess.run([_omc_bin(), "build.mos"], cwd=bdir, capture_output=True,
                       text=True, timeout=timeout)
    # 실행파일 탐색 (Windows .exe / Linux 확장자 없음)
    exe = None
    for cand in ("CanvasGen.GenCase.exe", "CanvasGen.GenCase"):
        p = os.path.join(bdir, cand)
        if os.path.exists(p):
            exe = p
            break
    if exe is None:
        raise RuntimeError(f"buildModel 실패 ({comp}):\n{(r.stdout + r.stderr)[-1500:]}")
    _BUILD_CACHE[comp] = {'dir': bdir, 'exe': exe}
    return _BUILD_CACHE[comp]


def _read_last_row(csv_path):
    rows = list(_csv.reader(open(csv_path)))
    hdr = [h.strip('"') for h in rows[0]]
    last = rows[-1]
    return {hdr[i]: float(last[i]) for i in range(len(hdr))}


def gen_component_mo(block):
    """디버그용: block → 빌드에 쓰는 .mo(str) + outputs. (실행은 캐시 경로 사용)"""
    comp = block['component']
    if comp not in COMPONENT_REGISTRY:
        raise ValueError(f"미지원 컴포넌트: {comp}")
    spec = COMPONENT_REGISTRY[comp]
    return spec['template'](dict(spec['param_defaults']), dict(spec['build_bc'])), spec['outputs']


def compute_modelica(block, timeout=60):
    """canvas /compute 와 동일 인터페이스 — Modelica 엔진(캐시+override) 버전.
    반환: {'outputs': {...}}  (Python step()과 동일 키)."""
    comp = block['component']
    if comp not in COMPONENT_REGISTRY:
        raise ValueError(f"Modelica 브릿지 미지원 컴포넌트: {comp} "
                         f"(지원: {list(COMPONENT_REGISTRY)})")
    spec = COMPONENT_REGISTRY[comp]
    built = _ensure_built(comp)   # 최초 1회만 컴파일(~수십초), 이후 즉시

    # 캔버스 params + inputs → leaf parameter override 문자열
    src = {**block.get('params', {}), **block['inputs']}
    overrides = []
    for ck, (leaf, conv) in spec['override_map'].items():
        if ck in src and src[ck] is not None and src[ck] != '':
            overrides.append(f"{leaf}={conv(src[ck]):.10g}")
    # 파생 override (예: (P_suc,T_suc) → src.h) — 여러 입력 조합이 필요한 경우
    if 'derive' in spec:
        for leaf, val in spec['derive'](src).items():
            overrides.append(f"{leaf}={float(val):.10g}")

    args = [built['exe']]
    if overrides:
        args.append("-override=" + ",".join(overrides))
    args.append("-r=result.csv")
    r = subprocess.run(args, cwd=built['dir'], capture_output=True, text=True, timeout=timeout)
    csv_path = os.path.join(built['dir'], "result.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"실행 실패 ({comp}):\n{(r.stdout + r.stderr)[-1200:]}")
    res = _read_last_row(csv_path)
    return {'outputs': {k: res[k] for k in spec['outputs'] if k in res}}


# ── 폐루프 사이클 실행 (전체 L1 cycle, transient) ────────────────
#   단일 컴포넌트(FlowSource→블록→SinkOpen, 대수)와 달리 사이클은
#   닫힌 루프 + Volume 상태 + N-ramp → transient 시뮬(dassl)로 정착시킴.
CYCLE_MODELS = {
    'Cycle_L1_ramp':    {'has_opening': False},   # 고정 phi EEV (깔끔한 레퍼런스)
    'Cycle_L1_ramp_PI': {'has_opening': True},    # PI(SH 제어) — 현재 메인
    'Cycle_L1_dyn':     {'has_opening': False},   # 구버전
}
_CYCLE_MO = ['HPWD.mo', 'EvapUA.mo', 'Control.mo', 'Cycle.mo']
_CYCLE_MONITORS = ['Pc_bar', 'Pe_bar', 'mdot_comp', 'SH_evap', 'SC_cond',
                   'charge', 'opening', 'comp.W']


def run_cycle(model='Cycle_L1_ramp_PI', stop_time=120.0, tolerance=1e-6,
              intervals=240, n_traj=80, timeout=900):
    """HPWDcycle.<model>을 transient 시뮬 → 정착값 + 다운샘플 궤적 반환.

    반환: {model, stop_time, settled{...}, trajectory{time, var:[...]}}
    settled = 마지막 행(정착), trajectory = ~n_traj 포인트로 다운샘플.
    """
    if model not in CYCLE_MODELS:
        raise ValueError(f"미지원 사이클 모델: {model} (지원: {list(CYCLE_MODELS)})")
    wdir = os.path.join(_WORK, 'cycle_' + model)
    os.makedirs(wdir, exist_ok=True)
    loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in _CYCLE_MO)
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'{loads}'
           f'simulate(HPWDcycle.{model}, stopTime={float(stop_time):.6g}, '
           f'numberOfIntervals={int(intervals)}, method="dassl", '
           f'tolerance={float(tolerance):.3g}, outputFormat="csv"); getErrorString();\n')
    open(os.path.join(wdir, 'run.mos'), 'w').write(mos)
    r = subprocess.run([_omc_bin(), "run.mos"], cwd=wdir,
                       capture_output=True, text=True, timeout=timeout)
    csv_path = os.path.join(wdir, f"HPWDcycle.{model}_res.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"사이클 실행 실패 ({model}):\n{(r.stdout + r.stderr)[-1500:]}")

    rows = list(_csv.reader(open(csv_path)))
    hdr, data = rows[0], rows[1:]
    col = {h: i for i, h in enumerate(hdr)}
    present = [m for m in _CYCLE_MONITORS if m in col]
    last = data[-1]
    settled = {('W' if m == 'comp.W' else m): float(last[col[m]]) for m in present}
    # 다운샘플 궤적
    step = max(1, len(data) // n_traj)
    idx = list(range(0, len(data), step))
    if idx[-1] != len(data) - 1:
        idx.append(len(data) - 1)
    traj = {'time': [float(data[i][col['time']]) for i in idx]}
    for m in present:
        traj['W' if m == 'comp.W' else m] = [float(data[i][col[m]]) for i in idx]
    return {'model': model, 'stop_time': float(stop_time),
            'settled': settled, 'trajectory': traj}


# ── 캔버스 토폴로지 → 사이클 .mo 자동생성 (Phase A: 고정 EEV 링) ──────
#   사용자가 캔버스에서 구성한 링(comp→cond→eev→evap)을 받아서,
#   각 연결에 Volume(압력노드)를 자동삽입하고 acausal connect를 emit →
#   검증된 컴포넌트 모델(HPWD/HPWDhx/HPWDcycle)을 재사용하는 .mo 생성.
_GEN_MONITORS = ['Pc_bar', 'Pe_bar', 'mdot_comp', 'SH_evap', 'SC_cond', 'charge', 'W']

# 캔버스 kind → (Modelica 모델, 파라미터 emit)
def _emit_compressor(inst, p):
    return (f'    HPWD.Comp_Theoretical {inst}(V_disp={p.get("V_disp",10e-6):.6g}, '
            f'N={p.get("N",3000.0):.6g}, eta_vol={p.get("eta_vol",0.85):.6g}, '
            f'eta_isen={p.get("eta_isen",0.65):.6g}, t_ramp=t_ramp);\n')
def _emit_condenser(inst, p):
    return (f'    HPWDhx.Cond_UA_eq {inst}(T_air_in_C={p.get("T_air_in_C",35.0):.6g}, '
            f'RH_in={p.get("RH_in",0.5):.6g}, V_air_CMM={p.get("V_air_CMM",25.42):.6g}, '
            f'UA_deSH={p.get("UA_deSH",8.0):.6g}, UA_2ph={p.get("UA_2ph",50.0):.6g}, '
            f'UA_SC={p.get("UA_SC",5.0):.6g}, R_fric={p.get("R_fric",1e7):.6g}, m_dot(start=1e-5));\n')
def _emit_eev(inst, p):
    return (f'    HPWDcycle.EEV_Orifice {inst}(A_orifice={p.get("A_orifice",5.5e-7):.6g}, '
            f'Cv={p.get("Cv",0.7):.6g}, phi_fixed={p.get("phi_fixed",0.35):.6g}, m_dot(start=1e-5));\n')
def _emit_evaporator(inst, p):
    return (f'    HPWDhx.Evap_UA_eq {inst}(T_air_in={p.get("T_air_in_K",323.15):.6g}, '
            f'RH_in={p.get("RH_in",0.9):.6g}, V_air_CMM={p.get("V_air_CMM",2.54):.6g}, '
            f'UA_2ph={p.get("UA_2ph",25.0):.6g}, UA_SH={p.get("UA_SH",4.0):.6g}, '
            f'R_fric={p.get("R_fric",2e6):.6g}, m_dot(start=1e-5));\n')
_KIND_EMIT = {'compressor': _emit_compressor, 'condenser': _emit_condenser,
              'eev': _emit_eev, 'evaporator': _emit_evaporator}


def _canvas_to_cycle_params(kind, raw):
    """캔버스 raw 파라미터(+inputValues, 캔버스 단위) → SI 사이클 파라미터.

    물리 매핑을 한 곳(백엔드)에 집중:
      - 단위변환: V_disp cm³→m³, A_orifice mm²→m², RH %→frac, T_air °C→K(evap)
      - R_fric 역산: dP_ref · p_nom / ṁ_nom   (캔버스 dP_ref 재사용; (b) 결정)
      - EEV phi_fixed = ARI곡선 Φ(opening) = c0+c1·u+c2·u²+c3·u³, u=opening/100
    """
    def g(k, d):
        v = raw.get(k, None)
        try:
            return float(v) if v not in (None, '') else float(d)
        except (TypeError, ValueError):
            return float(d)

    if kind == 'compressor':
        return {'V_disp': g('V_disp', 10.0) * 1e-6, 'N': g('N', 3000.0),
                'eta_vol': g('eta_vol', 0.85), 'eta_isen': g('eta_isen', 0.65)}
    if kind == 'condenser':
        dP, P, mdot = g('dP_ref', 0.03), g('P_cond', 19.07) * 1e5, g('m_dot_ref', 0.00458)
        return {'T_air_in_C': g('T_air_in', 35.0), 'RH_in': g('RH_air_in', 50.0) / 100.0,
                'V_air_CMM': g('V_air_CMM', 25.42), 'UA_deSH': g('UA_deSH', 8.0),
                'UA_2ph': g('UA_2ph', 50.0), 'UA_SC': g('UA_SC', 5.0),
                'R_fric': dP * P / max(mdot, 1e-6)}
    if kind == 'evaporator':
        dP, P, mdot = g('dP_ref', 0.02), g('P_evap', 5.51) * 1e5, g('m_dot_ref', 0.00458)
        return {'T_air_in_K': g('T_air_in', 50.0) + 273.15, 'RH_in': g('RH_air_in', 90.0) / 100.0,
                'V_air_CMM': g('V_air_CMM', 2.54), 'UA_2ph': g('UA_2ph', 25.0),
                'UA_SH': g('UA_SH', 4.0), 'R_fric': dP * P / max(mdot, 1e-6)}
    if kind == 'eev':
        u = g('opening', 50.0) / 100.0
        phi = g('c0', 0.0) + g('c1', 0.5) * u + g('c2', 0.3) * u**2 + g('c3', 0.2) * u**3
        return {'A_orifice': g('A_orifice', 3.14) * 1e-6, 'Cv': g('Cv_rated', 0.7),
                'phi_fixed': max(phi, 1e-4)}
    raise ValueError(f"미지원 kind: {kind}")


def _h_rest_from_charge(charge_kg, p_rest_pa, sumV_m3, fluid='R290'):
    """목표 충전량 → 균압 p_rest에서의 균일 엔탈피 h_rest 역산.
    charge = rho(p_rest, h_rest) * ΣV  →  rho_target = charge/ΣV  →  h(p,rho)."""
    import CoolProp.CoolProp as CP
    rho_target = charge_kg / sumV_m3
    return CP.PropsSI('H', 'P', p_rest_pa, 'D', rho_target, fluid)   # J/kg


def generate_cycle_mo(topology, settings):
    """캔버스 토폴로지 → GenCycle.Cycle_gen .mo 텍스트 생성.

    topology = {components:[{id,kind,params}], ring:[id...], volumes:[V...]}
    settings = {charge_g, p_rest_bar, t_ramp, ...}
    반환: (mo_text, meta)
    """
    comps = {c['id']: c for c in topology['components']}
    ring = topology['ring']
    n = len(ring)
    vols = topology.get('volumes') or [5e-4] * n
    p_rest = float(settings.get('p_rest_bar', 9.0)) * 1e5
    sumV = sum(vols)
    charge_kg = float(settings.get('charge_g', 89.0)) / 1000.0
    h_rest = _h_rest_from_charge(charge_kg, p_rest, sumV,
                                 fluid=settings.get('fluid', 'R290'))
    t_ramp = float(settings.get('t_ramp', 20.0))

    # 컴포넌트 + Volume 선언 (링 순서: cᵢ 다음에 volᵢ₊₁)
    decl = []
    for i, cid in enumerate(ring):
        c = comps[cid]
        emit = _KIND_EMIT.get(c['kind'])
        if emit is None:
            raise ValueError(f"미지원 컴포넌트 kind: {c['kind']}")
        decl.append(emit(cid, c.get('params', {})))
        decl.append(f'    HPWDcycle.Volume vol{i+1}(V={vols[i]:.6g}, '
                    f'p_start=p_rest, h_start=h_rest, fixedState=true);\n')

    # acausal 연결: cᵢ.port_b → volᵢ₊₁.port_a → c(다음).port_a (마지막은 ring[0]로 닫힘)
    conn = []
    for i, cid in enumerate(ring):
        nxt = ring[(i + 1) % n]
        conn.append(f'    connect({cid}.port_b, vol{i+1}.port_a);\n')
        conn.append(f'    connect(vol{i+1}.port_b, {nxt}.port_a);\n')

    # 모니터 매핑: 압축기 직후 vol = HP(Pc), EEV 직후 vol = LP(Pe)
    def _id_of(kind):
        return next(c['id'] for c in topology['components'] if c['kind'] == kind)
    comp_id, eev_id = _id_of('compressor'), _id_of('eev')
    cond_id, evap_id = _id_of('condenser'), _id_of('evaporator')
    pc_vol = f'vol{ring.index(comp_id)+1}'
    pe_vol = f'vol{ring.index(eev_id)+1}'
    charge_expr = ' + '.join(f'vol{i+1}.rho*vol{i+1}.V' for i in range(n))

    mo = (f'within ;\n'
          f'package GenCycle "캔버스 토폴로지에서 자동생성된 L1 사이클"\n'
          f'  model Cycle_gen\n'
          f'    parameter Modelica.Units.SI.Pressure p_rest = {p_rest:.6g};\n'
          f'    parameter Modelica.Units.SI.SpecificEnthalpy h_rest = {h_rest:.6g};\n'
          f'    parameter Real t_ramp = {t_ramp:.6g};\n'
          f'{"".join(decl)}'
          f'    Real charge, Pc_bar, Pe_bar, mdot_comp, SH_evap, SC_cond, W;\n'
          f'  equation\n'
          f'{"".join(conn)}'
          f'    charge = {charge_expr};\n'
          f'    Pc_bar = {pc_vol}.p/1e5;\n'
          f'    Pe_bar = {pe_vol}.p/1e5;\n'
          f'    mdot_comp = {comp_id}.m_dot;\n'
          f'    SH_evap = {evap_id}.SH;\n'
          f'    SC_cond = {cond_id}.SC;\n'
          f'    W = {comp_id}.W;\n'
          f'  end Cycle_gen;\n'
          f'end GenCycle;\n')
    meta = {'h_rest': h_rest, 'charge_g': charge_kg * 1000, 'sumV': sumV,
            'pc_vol': pc_vol, 'pe_vol': pe_vol, 'n_volumes': n}
    return mo, meta


def _parse_cycle_csv(csv_path, monitors, n_traj=80):
    rows = list(_csv.reader(open(csv_path)))
    hdr, data = rows[0], rows[1:]
    col = {h: i for i, h in enumerate(hdr)}
    present = [m for m in monitors if m in col]
    last = data[-1]
    settled = {m: float(last[col[m]]) for m in present}
    step = max(1, len(data) // n_traj)
    idx = list(range(0, len(data), step))
    if idx[-1] != len(data) - 1:
        idx.append(len(data) - 1)
    traj = {'time': [float(data[i][col['time']]) for i in idx]}
    for m in present:
        traj[m] = [float(data[i][col[m]]) for i in idx]
    return settled, traj


def run_canvas_cycle(topology, settings, raw_params=True):
    """캔버스 토폴로지로 사이클 .mo 생성 → transient 시뮬 → 정착값+궤적.

    raw_params=True (기본): components[].params 가 캔버스 raw 값 → SI로 변환.
    False: 이미 SI 파라미터로 간주 (내부 검증용)."""
    if raw_params:
        comps = [{'id': c['id'], 'kind': c['kind'],
                  'params': _canvas_to_cycle_params(c['kind'], c.get('params', {}))}
                 for c in topology['components']]
        topology = {**topology, 'components': comps}
    mo, meta = generate_cycle_mo(topology, settings)
    wdir = os.path.join(_WORK, 'cycle_gen')
    os.makedirs(wdir, exist_ok=True)
    open(os.path.join(wdir, 'GenCycle.mo'), 'w').write(mo)
    loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in _CYCLE_MO)
    stop = float(settings.get('stop_time', 120.0))
    tol = float(settings.get('tolerance', 1e-6))
    intervals = int(settings.get('intervals', 240))
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'{loads}'
           f'loadFile("{_fs(os.path.join(wdir, "GenCycle.mo"))}"); getErrorString();\n'
           f'simulate(GenCycle.Cycle_gen, stopTime={stop:.6g}, '
           f'numberOfIntervals={intervals}, method="dassl", '
           f'tolerance={tol:.3g}, outputFormat="csv"); getErrorString();\n')
    open(os.path.join(wdir, 'run.mos'), 'w').write(mos)
    r = subprocess.run([_omc_bin(), "run.mos"], cwd=wdir,
                       capture_output=True, text=True, timeout=900)
    csv_path = os.path.join(wdir, "GenCycle.Cycle_gen_res.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"생성 사이클 실행 실패:\n{(r.stdout + r.stderr)[-1800:]}")
    settled, traj = _parse_cycle_csv(csv_path, _GEN_MONITORS)
    return {'settled': settled, 'trajectory': traj, 'meta': meta, 'generated_mo': mo,
            'stop_time': stop}

# ══════════════════════════════════════════════════════════════════
# 캔버스 토폴로지 → 공기 사이클 .mo 자동생성 (냉매 Run Cycle의 공기 대칭판)
#   공기 링(drum→fan→evap→cond→drum)을 받아 AirVolume 노드 자동삽입.
#   냉매 Run Cycle이 *공기입구 고정*인 것과 대칭으로, 공기 Run Cycle은
#   *코일온도(T_evap/T_cond) 고정* — EvapAir_L1/CondAir_L1 사용.
#   첫 vol(드럼 직후)만 AirVolumeC = 폐루프 압력앵커 (비압축이라 절대레벨 자유 DOF).
# ══════════════════════════════════════════════════════════════════
_AIR_CYCLE_MO = ['HPWDair.mo']   # 외부 의존성 없음 (MoistAir 내장, HelmholtzMedia 불필요)
_AIR_MONITORS = ['X', 'm_evap', 'm_cond', 'mdot_da', 'T_cond_out_C', 'T_evap_out_C',
                 'T_drum_out_C', 'T_cl_C', 'fan_dp', 'Q_latent', 'Q_cond', 'W_drum_out',
                 'filter_dp']
# 컴포넌트 직후 AirVolume 초기값 (해당 컴포넌트 kind 기준; fixedState라 init 추정값)
_AIR_VOL_START = {'drum': (308.15, 0.018), 'filter': (308.15, 0.018), 'fan': (308.15, 0.018),
                  'evaporator': (288.15, 0.010), 'condenser': (328.15, 0.011)}

def _emit_drum_air(inst, p):
    return (f'    HPWDair.Drum_L1 {inst}(m_cl_dry={p.get("m_cl_dry",3.0):.6g}, '
            f'c_p_cl={p.get("c_p_cl",1500.0):.6g}, A_eff={p.get("A_eff",10.0):.6g}, '
            f'h_a={p.get("h_a",50.0):.6g}, A_drum={p.get("A_drum",0.15):.6g}, '
            f'K_drum={p.get("K_drum",30.0):.6g}, X0={p.get("X0",0.6):.6g}, '
            f'Tcl0={p.get("Tcl0",298.15):.6g}, UA_amb={p.get("UA_amb",0.0):.6g}, '
            f'T_amb={p.get("T_amb",298.15):.6g});\n')
def _emit_fan_air(inst, p):
    return (f'    HPWDair.Fan_L1 {inst}(D2={p.get("D2",0.15):.6g}, b2={p.get("b2",0.04):.6g}, '
            f'Z={int(p.get("Z",40))}, beta2={p.get("beta2",150.0):.6g}, '
            f'eta_h={p.get("eta_h",0.78):.6g}, eta_mech={p.get("eta_mech",0.95):.6g}, '
            f'N={p.get("N",3000.0):.6g});\n')
def _emit_evap_air(inst, p):
    return (f'    HPWDair.EvapAir_L1 {inst}(T_evap={p.get("T_evap",283.15):.6g}, '
            f'BF={p.get("BF",0.2):.6g}, A_face={p.get("A_face",0.05):.6g}, '
            f'K_air={p.get("K_air",50.0):.6g});\n')
def _emit_cond_air(inst, p):
    return (f'    HPWDair.CondAir_L1 {inst}(T_cond={p.get("T_cond",333.15):.6g}, '
            f'BF={p.get("BF",0.2):.6g}, A_face={p.get("A_face",0.05):.6g}, '
            f'K_air={p.get("K_air",50.0):.6g});\n')
def _emit_filter_air(inst, p):
    return (f'    HPWDair.Filter_L1 {inst}(A_face={p.get("A_face",0.05):.6g}, '
            f'r_pleat={p.get("r_pleat",1.0):.6g}, theta_face={p.get("theta_face",0.0):.6g}, '
            f'K={p.get("K",20.0):.6g});\n')
_AIR_KIND_EMIT = {'drum': _emit_drum_air, 'fan': _emit_fan_air,
                  'evaporator': _emit_evap_air, 'condenser': _emit_cond_air,
                  'filter': _emit_filter_air}


def _canvas_to_air_params(kind, raw):
    """캔버스 raw 파라미터 → SI 공기모델 파라미터.

    drum/fan은 native 키(m_cl_dry,X0,h_a,N..) 우선, 없으면 캔버스 placeholder
    키(m_fabric,MC_init,hA,RPM)로 폴백. evap/cond의 코일온도는 native T_evap_C/
    T_cond_C 가 있으면 그걸, 없으면 P_evap/P_cond → R290 포화온도(CoolProp)로 역산.
    """
    def pick(keys, d):
        for k in keys:
            v = raw.get(k)
            if v not in (None, ''):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return float(d)

    if kind == 'drum':
        return {'m_cl_dry': pick(['m_cl_dry', 'm_fabric'], 3.0),
                'c_p_cl': pick(['c_p_cl'], 1500.0), 'A_eff': pick(['A_eff'], 10.0),
                'h_a': pick(['h_a', 'hA'], 50.0), 'A_drum': pick(['A_drum'], 0.15),
                'K_drum': pick(['K_drum'], 30.0), 'X0': pick(['X0', 'MC_init'], 0.6),
                'Tcl0': pick(['Tcl0'], 298.15), 'UA_amb': pick(['UA_amb'], 0.0),
                'T_amb': pick(['T_amb'], 298.15)}
    if kind == 'fan':
        return {'D2': pick(['D2'], 0.15), 'b2': pick(['b2'], 0.04),
                'Z': pick(['Z'], 40.0), 'beta2': pick(['beta2'], 150.0),
                'eta_h': pick(['eta_h', 'eta'], 0.78), 'eta_mech': pick(['eta_mech'], 0.95),
                'N': pick(['N', 'RPM'], 3000.0)}
    if kind in ('evaporator', 'condenser'):
        import CoolProp.CoolProp as CP
        if kind == 'evaporator':
            if raw.get('T_evap_C') not in (None, ''):
                T_coil = pick(['T_evap_C'], 10.0) + 273.15
            else:
                T_coil = CP.PropsSI('T', 'P', pick(['P_evap'], 5.51) * 1e5, 'Q', 0.0, 'R290')
            return {'T_evap': T_coil, 'BF': pick(['BF'], 0.2),
                    'A_face': pick(['A_face'], 0.05), 'K_air': pick(['K_air'], 50.0)}
        else:
            if raw.get('T_cond_C') not in (None, ''):
                T_coil = pick(['T_cond_C'], 60.0) + 273.15
            else:
                T_coil = CP.PropsSI('T', 'P', pick(['P_cond'], 19.07) * 1e5, 'Q', 1.0, 'R290')
            return {'T_cond': T_coil, 'BF': pick(['BF'], 0.2),
                    'A_face': pick(['A_face'], 0.05), 'K_air': pick(['K_air'], 50.0)}
    if kind == 'filter':
        return {'A_face': pick(['A_face'], 0.05), 'r_pleat': pick(['r_pleat'], 1.0),
                'theta_face': pick(['theta_face'], 0.0), 'K': pick(['K'], 20.0)}
    raise ValueError(f"미지원 공기 kind: {kind}")


def generate_air_cycle_mo(topology, settings):
    """캔버스 공기 토폴로지 → GenAirCycle.AirCycle_gen .mo 텍스트.

    topology = {components:[{id,kind,params}], ring:[id...], volumes:[V...]}
    ring 순서는 드럼에서 시작 (drum→fan→evap→cond). 반환: (mo_text, meta)
    """
    comps = {c['id']: c for c in topology['components']}
    ring = topology['ring']
    n = len(ring)
    vols = topology.get('volumes') or [0.05] * n
    decl = []
    for i, cid in enumerate(ring):
        c = comps[cid]
        emit = _AIR_KIND_EMIT.get(c['kind'])
        if emit is None:
            raise ValueError(f"미지원 공기 컴포넌트 kind: {c['kind']}")
        decl.append(emit(cid, c.get('params', {})))
        # 직후 vol 초기값 = 이 컴포넌트 kind 기준 (필터 삽입 등 링 변화에 강건)
        T0, W0 = _AIR_VOL_START.get(c['kind'], (308.15, 0.018))
        if i == 0:   # 드럼 직후 vol = 압력앵커 (AirVolumeC)
            decl.append(f'    HPWDair.AirVolumeC vol{i+1}(V={vols[i]:.6g}, '
                        f'p_start=HPWDair.MoistAir.p_ref, T_start={T0:.6g}, '
                        f'W_start={W0:.6g}, fixedState=true);\n')
        else:
            decl.append(f'    HPWDair.AirVolume vol{i+1}(V={vols[i]:.6g}, '
                        f'T_start={T0:.6g}, W_start={W0:.6g}, fixedState=true);\n')

    conn = []
    for i, cid in enumerate(ring):
        nxt = ring[(i + 1) % n]
        conn.append(f'    connect({cid}.port_b, vol{i+1}.port_a);\n')
        conn.append(f'    connect(vol{i+1}.port_b, {nxt}.port_a);\n')

    def _id_of(kind):
        return next(c['id'] for c in topology['components'] if c['kind'] == kind)
    drum_id, fan_id = _id_of('drum'), _id_of('fan')
    evap_id, cond_id = _id_of('evaporator'), _id_of('condenser')

    # 모니터: 항상 12종 + 필터가 링에 있으면 filter_dp 추가
    mons = [('X', f'{drum_id}.X'), ('m_evap', f'{drum_id}.m_evap'),
            ('m_cond', f'{evap_id}.m_cond'), ('mdot_da', f'{drum_id}.m_flow_da'),
            ('T_cond_out_C', f'{cond_id}.T_out - 273.15'),
            ('T_evap_out_C', f'{evap_id}.T_out - 273.15'),
            ('T_drum_out_C', f'{drum_id}.T_out - 273.15'),
            ('T_cl_C', f'{drum_id}.T_cl - 273.15'), ('fan_dp', f'{fan_id}.dp'),
            ('Q_latent', f'{evap_id}.Q_latent'), ('Q_cond', f'{cond_id}.Q_total'),
            ('W_drum_out', f'{drum_id}.W_out')]
    filter_ids = [cid for cid in ring if comps[cid]['kind'] == 'filter']
    if filter_ids:
        mons.append(('filter_dp', f'{filter_ids[0]}.dp'))
    real_decl = '    Real ' + ', '.join(nm for nm, _ in mons) + ';\n'
    eqs = ''.join(f'    {nm} = {expr};\n' for nm, expr in mons)

    mo = (f'within ;\n'
          f'package GenAirCycle "캔버스 토폴로지에서 자동생성된 L1 공기 사이클"\n'
          f'  model AirCycle_gen\n'
          f'{"".join(decl)}'
          f'{real_decl}'
          f'  equation\n'
          f'{"".join(conn)}'
          f'{eqs}'
          f'  end AirCycle_gen;\n'
          f'end GenAirCycle;\n')
    meta = {'n_volumes': n, 'anchor_vol': 'vol1',
            'has_filter': bool(filter_ids),
            'ring': [comps[cid]['kind'] for cid in ring]}
    return mo, meta


def run_air_cycle(topology, settings, raw_params=True):
    """캔버스 공기 토폴로지로 .mo 생성 → transient 시뮬 → 정착값+궤적.

    raw_params=True (기본): components[].params 가 캔버스 raw → SI 변환.
    공기측은 HelmholtzMedia 불필요 (MoistAir 내장) → 로드 빠름.
    """
    if raw_params:
        comps = [{'id': c['id'], 'kind': c['kind'],
                  'params': _canvas_to_air_params(c['kind'], c.get('params', {}))}
                 for c in topology['components']]
        topology = {**topology, 'components': comps}
    mo, meta = generate_air_cycle_mo(topology, settings)
    wdir = os.path.join(_WORK, 'air_cycle_gen')
    os.makedirs(wdir, exist_ok=True)
    open(os.path.join(wdir, 'GenAirCycle.mo'), 'w').write(mo)
    loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in _AIR_CYCLE_MO)
    stop = float(settings.get('stop_time', 300.0))
    tol = float(settings.get('tolerance', 1e-6))
    intervals = int(settings.get('intervals', 300))
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'{loads}'
           f'loadFile("{_fs(os.path.join(wdir, "GenAirCycle.mo"))}"); getErrorString();\n'
           f'simulate(GenAirCycle.AirCycle_gen, stopTime={stop:.6g}, '
           f'numberOfIntervals={intervals}, method="dassl", '
           f'tolerance={tol:.3g}, outputFormat="csv"); getErrorString();\n')
    open(os.path.join(wdir, 'run.mos'), 'w').write(mos)
    r = subprocess.run([_omc_bin(), "run.mos"], cwd=wdir,
                       capture_output=True, text=True, timeout=900)
    csv_path = os.path.join(wdir, "GenAirCycle.AirCycle_gen_res.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"공기 사이클 실행 실패:\n{(r.stdout + r.stderr)[-1800:]}")
    settled, traj = _parse_cycle_csv(csv_path, _AIR_MONITORS)
    return {'settled': settled, 'trajectory': traj, 'meta': meta,
            'generated_mo': mo, 'stop_time': stop}


# ══════════════════════════════════════════════════════════════════
# 냉매-공기 커플드 사이클 Run Cycle (고정 모델)
#   HPWDcpl.Cycle_coupled_* 를 실행. evap/cond가 merged HX(Evap/Cond_coupled)로
#   냉매 링과 공기 링을 동시에 결합 — 코일온도가 prescribed가 아니라 상호결정됨.
#   (냉매 Run=공기입구 고정, 공기 Run=코일온도 고정, 커플드=둘 다 안 고정)
# ══════════════════════════════════════════════════════════════════
_COUPLED_MO = ['HPWD.mo', 'EvapUA.mo', 'Control.mo', 'Cycle.mo', 'HPWDair.mo', 'Coupled.mo']
COUPLED_MODELS = ('Cycle_coupled_closed', 'Cycle_coupled_open')

# 커플드 KPI 매핑: flat 이름 → (CSV 컬럼, 변환). 모델 변수는 component-qualified.
_COUPLED_MAP = {
    'Pc_bar':       ('cond.P_cond',   lambda v: v / 1e5),
    'Pe_bar':       ('evap.P_evap',   lambda v: v / 1e5),
    'W':            ('comp.W',        lambda v: v),
    'mdot':         ('comp.m_dot',    lambda v: v),
    'SH_evap':      ('evap.SH',       lambda v: v),
    'SC_cond':      ('cond.SC',       lambda v: v),
    'opening':      ('eev.opening',   lambda v: v),
    'X':            ('drum.X',        lambda v: v),
    'm_evap':       ('drum.m_evap',   lambda v: v),
    'm_cond':       ('evap.m_cond',   lambda v: v),
    'mdot_da':      ('drum.m_flow_da', lambda v: v),
    'T_cond_air_C': ('cond.T_air_out', lambda v: v - 273.15),
    'T_evap_air_C': ('evap.T_air_out', lambda v: v - 273.15),
    'T_drum_out_C': ('drum.T_out',    lambda v: v - 273.15),
    'fan_dp':       ('fan.dp',        lambda v: v),
}


def _parse_coupled_csv(csv_path, n_traj=80):
    """커플드 CSV → flat KPI(settled, traj) + 파생 SMER.
    SMER [kg/kWh] = m_evap[kg/s] / W[W] × 3.6e6 (단위 제습량/소비전력)."""
    rows = list(_csv.reader(open(csv_path)))
    hdr, data = rows[0], rows[1:]
    col = {h: i for i, h in enumerate(hdr)}
    present = {flat: (c, fn) for flat, (c, fn) in _COUPLED_MAP.items() if c in col}

    def kpis(row):
        out = {flat: fn(float(row[col[c]])) for flat, (c, fn) in present.items()}
        if 'm_evap' in out and out.get('W', 0) > 1e-9:
            out['SMER'] = out['m_evap'] / out['W'] * 3.6e6
        return out

    settled = kpis(data[-1])
    step = max(1, len(data) // n_traj)
    idx = list(range(0, len(data), step))
    if idx[-1] != len(data) - 1:
        idx.append(len(data) - 1)
    keys = list(present.keys()) + (['SMER'] if 'SMER' in settled else [])
    traj = {'time': [float(data[i][col['time']]) for i in idx]}
    for k in keys:
        traj[k] = []
    for i in idx:
        kk = kpis(data[i])
        for k in keys:
            traj[k].append(kk.get(k))
    return settled, traj


def run_coupled_cycle(model='Cycle_coupled_closed', stop_time=180.0, tolerance=1e-6,
                      intervals=300, n_traj=80, timeout=900):
    """HPWDcpl.<model> 커플드 사이클 transient 시뮬 → 정착값 + 궤적.

    냉매(Pc/Pe/W/SH/opening) + 공기(X/m_evap/열풍/풍량) + 파생 SMER 동시 반환.
    """
    if model not in COUPLED_MODELS:
        raise ValueError(f"미지원 커플드 모델: {model} (지원: {list(COUPLED_MODELS)})")
    wdir = os.path.join(_WORK, 'coupled_' + model)
    os.makedirs(wdir, exist_ok=True)
    loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in _COUPLED_MO)
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'{loads}'
           f'simulate(HPWDcpl.{model}, stopTime={float(stop_time):.6g}, '
           f'numberOfIntervals={int(intervals)}, method="dassl", '
           f'tolerance={float(tolerance):.3g}, outputFormat="csv"); getErrorString();\n')
    open(os.path.join(wdir, 'run.mos'), 'w').write(mos)
    r = subprocess.run([_omc_bin(), "run.mos"], cwd=wdir,
                       capture_output=True, text=True, timeout=timeout)
    csv_path = os.path.join(wdir, f"HPWDcpl.{model}_res.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"커플드 사이클 실행 실패 ({model}):\n{(r.stdout + r.stderr)[-1500:]}")
    settled, traj = _parse_coupled_csv(csv_path, n_traj)
    return {'model': model, 'stop_time': float(stop_time),
            'settled': settled, 'trajectory': traj}


# ══════════════════════════════════════════════════════════════════
# 캔버스 토폴로지 → 커플드 .mo 자동생성 (냉매 closed + 공기 closed 결합)
#   냉매 링(comp→cond→eev→evap)과 공기 링(drum→[filter]→fan→evap→cond)을
#   각각 추출. evap/cond는 양쪽이 공유하는 merged HX(한 번만 선언, 냉매 chain은
#   port_a/b · 공기 chain은 air_a/b 참조). 표준 토폴로지면 Cycle_coupled_closed
#   구조·init·파라미터와 동일 → SMER~2.44 재현. (_parse_coupled_csv가 고정
#   인스턴스명 comp/cond/evap/drum/fan/eev를 읽으므로 role명으로 emit)
# ══════════════════════════════════════════════════════════════════
_COUPLED_ROLE = {'compressor': 'comp', 'condenser': 'cond', 'eev': 'eev',
                 'evaporator': 'evap', 'drum': 'drum', 'fan': 'fan', 'filter': 'filt'}
# 냉매 Volume init (선행 컴포넌트 kind 기준 — Cycle_coupled_closed 값)
_REF_VOL_INIT = {'compressor': (16e5, 665e3), 'condenser': (15.5e5, 345e3),
                 'eev': (6.5e5, 345e3), 'evaporator': (6.4e5, 595e3)}
# 공기 Volume init (선행 노드 kind 기준; drum 직후 = AirVolumeC 앵커)
_AIR_VOL_INIT_C = {'drum': (304.0, 0.018), 'fan': (305.0, 0.018),
                   'evaporator': (291.0, 0.012), 'condenser': (333.0, 0.012),
                   'filter': (305.0, 0.018)}
_COUPLED_K_AIR = 300.0   # merged HX 공기측 핀저항 (검증값; 캔버스 미노출)


def _emit_eev_ctrl(inst, raw):
    """PI 제어 EEV (EEV_Orifice_ctrl) — opening 입력. 캔버스 eev 파라미터 오버레이."""
    def g(k, d):
        v = raw.get(k)
        try:
            return float(v) if v not in (None, '') else float(d)
        except (TypeError, ValueError):
            return float(d)
    return (f'    HPWDcycle.EEV_Orifice_ctrl {inst}(m_dot(start=0.006), '
            f'A_orifice={g("A_orifice", 0.55) * 1e-6:.6g}, Cv={g("Cv_rated", 0.7):.6g}, '
            f'c0={g("c0", 0.0):.6g}, c1={g("c1", 0.5):.6g}, '
            f'c2={g("c2", 0.3):.6g}, c3={g("c3", 0.2):.6g});\n')


def generate_coupled_mo(ref_topology, air_topology, settings=None):
    """냉매 + 공기 토폴로지 → GenCoupled.Coupled_gen .mo 텍스트.

    ref_topology = {components:[{id,kind,params}], ring:[id...]} (comp→cond→eev→evap)
    air_topology = {components:[{id,kind,params}], ring:[id...]} (drum→[filter]→fan→evap→cond)
    evap/cond는 두 링이 공유(merged Evap/Cond_coupled). 반환: (mo_text, meta).
    """
    settings = settings or {}
    rC = {c['id']: c for c in ref_topology['components']}
    aC = {c['id']: c for c in air_topology['components']}
    rR, aR = ref_topology['ring'], air_topology['ring']
    kR = lambda i: rC[i]['kind']
    kA = lambda i: aC[i]['kind']
    R = _COUPLED_ROLE

    # 공유 HX 검증: evap/cond가 냉매·공기 링 양쪽에 존재해야 함
    for k in ('evaporator', 'condenser'):
        if k not in {kR(c) for c in rR} or k not in {kA(c) for c in aR}:
            raise ValueError(f"커플드: '{k}'가 냉매·공기 링 양쪽에 있어야 함 (merged HX 공유점)")

    decl = []
    # ── 냉매 컴포넌트 + 냉매 Volume (cond/evap = merged) ──
    for i, cid in enumerate(rR):
        k = kR(cid); inst = R[k]; raw = rC[cid].get('params', {})
        if k == 'compressor':
            p = _canvas_to_cycle_params('compressor', raw)
            decl.append(f'    HPWD.Comp_Theoretical {inst}(V_disp={p["V_disp"]:.6g}, '
                        f'N={p["N"]:.6g}, eta_vol={p["eta_vol"]:.6g}, eta_isen={p["eta_isen"]:.6g});\n')
        elif k == 'condenser':
            decl.append(f'    HPWDcpl.Cond_coupled {inst}(m_dot(start=0.006), K_air={_COUPLED_K_AIR:.6g});\n')
        elif k == 'evaporator':
            decl.append(f'    HPWDcpl.Evap_coupled {inst}(m_dot(start=0.006), K_air={_COUPLED_K_AIR:.6g});\n')
        elif k == 'eev':
            decl.append(_emit_eev_ctrl(inst, raw))
        else:
            raise ValueError(f"커플드 냉매 링 미지원 kind: {k}")
        p0, h0 = _REF_VOL_INIT.get(k, (9e5, 360e3))
        decl.append(f'    HPWDcycle.Volume vol{i+1}(p_start={p0:.6g}, h_start={h0:.6g}, fixedState=true);\n')
    decl.append('    HPWDctrl.PI_Controller ctrl(I(fixed=true));\n')

    # ── 공기 컴포넌트 (evap/cond는 냉매측에서 이미 선언) + 공기 Volume ──
    for i, cid in enumerate(aR):
        k = kA(cid); inst = R[k]; raw = aC[cid].get('params', {})
        if k == 'drum':
            ap = _canvas_to_air_params('drum', raw)
            # 커플드 검증 기본값 (캔버스 미설정 시): 대기 열손실 100 W/K, 초기 의류온도 305 K
            ap['UA_amb'] = float(raw.get('UA_amb', 100.0))
            if raw.get('Tcl0') in (None, ''):
                ap['Tcl0'] = 305.0
            decl.append(_emit_drum_air(inst, ap))
        elif k == 'fan':
            decl.append(_emit_fan_air(inst, _canvas_to_air_params('fan', raw)))
        elif k == 'filter':
            decl.append(_emit_filter_air(inst, _canvas_to_air_params('filter', raw)))
        elif k in ('evaporator', 'condenser'):
            pass   # merged HX — 냉매측에서 이미 선언됨
        else:
            raise ValueError(f"커플드 공기 링 미지원 kind: {k}")
        T0, W0 = _AIR_VOL_INIT_C.get(k, (305.0, 0.018))
        if i == 0:   # drum 직후 = 압력 앵커
            decl.append(f'    HPWDair.AirVolumeC volA{i+1}(V=0.05, p_start=HPWDair.MoistAir.p_ref, '
                        f'T_start={T0:.6g}, W_start={W0:.6g}, fixedState=true);\n')
        else:
            decl.append(f'    HPWDair.AirVolume volA{i+1}(V=0.05, T_start={T0:.6g}, '
                        f'W_start={W0:.6g}, fixedState=true);\n')

    # ── 연결 ──
    conn = []
    nR = len(rR)
    for i, cid in enumerate(rR):
        conn.append(f'    connect({R[kR(cid)]}.port_b, vol{i+1}.port_a);\n')
        conn.append(f'    connect(vol{i+1}.port_b, {R[kR(rR[(i+1) % nR])]}.port_a);\n')
    conn.append('    connect(evap.SH, ctrl.SH_meas);\n')
    conn.append('    connect(ctrl.opening, eev.opening);\n')
    # 공기 chain: merged HX는 air_a/air_b, 나머지는 port_a/port_b
    a_in = lambda c: f'{R[kA(c)]}.air_a' if kA(c) in ('evaporator', 'condenser') else f'{R[kA(c)]}.port_a'
    a_out = lambda c: f'{R[kA(c)]}.air_b' if kA(c) in ('evaporator', 'condenser') else f'{R[kA(c)]}.port_b'
    nA = len(aR)
    for i, cid in enumerate(aR):
        conn.append(f'    connect({a_out(cid)}, volA{i+1}.port_a);\n')
        conn.append(f'    connect(volA{i+1}.port_b, {a_in(aR[(i+1) % nA])});\n')

    mo = (f'within ;\n'
          f'package GenCoupled "캔버스 토폴로지에서 자동생성된 L1 커플드 사이클"\n'
          f'  model Coupled_gen\n'
          f'{"".join(decl)}'
          f'  equation\n'
          f'{"".join(conn)}'
          f'  end Coupled_gen;\n'
          f'end GenCoupled;\n')
    meta = {'n_ref_vol': nR, 'n_air_vol': nA,
            'ref_ring': [kR(c) for c in rR], 'air_ring': [kA(c) for c in aR],
            'has_filter': any(kA(c) == 'filter' for c in aR), 'K_air': _COUPLED_K_AIR}
    return mo, meta


def run_canvas_coupled_cycle(ref_topology, air_topology, settings=None,
                             stop_time=180.0, tolerance=1e-6, intervals=300,
                             n_traj=80, timeout=900):
    """캔버스 냉매+공기 토폴로지 → 커플드 .mo 생성 → 시뮬 → 냉매·공기 KPI + SMER.

    표준 토폴로지면 고정 모델 Cycle_coupled_closed와 동일 결과(SMER~2.44).
    """
    mo, meta = generate_coupled_mo(ref_topology, air_topology, settings or {})
    wdir = os.path.join(_WORK, 'coupled_canvas')
    os.makedirs(wdir, exist_ok=True)
    open(os.path.join(wdir, 'GenCoupled.mo'), 'w').write(mo)
    loads = "".join(
        f'loadFile("{_fs(os.path.join(MODELICA_DIR, f))}"); getErrorString();\n'
        for f in _COUPLED_MO)
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'{loads}'
           f'loadFile("{_fs(os.path.join(wdir, "GenCoupled.mo"))}"); getErrorString();\n'
           f'simulate(GenCoupled.Coupled_gen, stopTime={float(stop_time):.6g}, '
           f'numberOfIntervals={int(intervals)}, method="dassl", '
           f'tolerance={float(tolerance):.3g}, outputFormat="csv"); getErrorString();\n')
    open(os.path.join(wdir, 'run.mos'), 'w').write(mos)
    r = subprocess.run([_omc_bin(), "run.mos"], cwd=wdir,
                       capture_output=True, text=True, timeout=timeout)
    csv_path = os.path.join(wdir, "GenCoupled.Coupled_gen_res.csv")
    if not os.path.exists(csv_path):
        raise RuntimeError(f"커플드 캔버스 실행 실패:\n{(r.stdout + r.stderr)[-1500:]}")
    settled, traj = _parse_coupled_csv(csv_path, n_traj)
    return {'settled': settled, 'trajectory': traj, 'meta': meta,
            'generated_mo': mo, 'stop_time': float(stop_time)}



# ── 캐시 무효화 (모델/템플릿 수정 후 강제 재빌드용) ──────────────
def clear_cache():
    _BUILD_CACHE.clear()
