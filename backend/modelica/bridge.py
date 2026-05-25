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


# ── 단위 변환기 ──────────────────────────────────────────────────
def _ident(v): return float(v)
def _mm2_to_m2(v): return float(v) * 1e-6      # 면적 mm² → m²  ★ 단위변경 반영
def _bar_to_pa(v): return float(v) * 1e5       # 압력 bar → Pa
def _kjkg_to_jkg(v): return float(v) * 1e3     # 비엔탈피 kJ/kg → J/kg


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
    # TODO: 'compressor_ahri', 'evaporator_off_design', 'condenser_off_design' ...
    #       각 항목에 template + override_map(leaf 이름) + build_bc 추가
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
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{_fs(HELMHOLTZ_PATH)}"); getErrorString();\n'
           f'loadFile("{_fs(os.path.join(MODELICA_DIR, "HPWD.mo"))}"); getErrorString();\n'
           f'loadFile("{_fs(os.path.join(bdir, "CanvasGen.mo"))}"); getErrorString();\n'
           f'buildModel(CanvasGen.GenCase, outputFormat="csv", stopTime=1,'
           f' numberOfIntervals=1); getErrorString();\n')
    open(os.path.join(bdir, "build.mos"), "w").write(mos)
    r = subprocess.run(["omc", "build.mos"], cwd=bdir, capture_output=True,
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


# ── 캐시 무효화 (모델/템플릿 수정 후 강제 재빌드용) ──────────────
def clear_cache():
    _BUILD_CACHE.clear()
