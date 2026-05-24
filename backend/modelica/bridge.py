"""
캔버스 → Modelica 브릿지 (codegen + OMC 실행)
═══════════════════════════════════════════════════════════════
canvas 블록 스펙(/compute 요청과 동일 shape: {component, params, inputs})을 받아
  ① 컴포넌트별 매핑(파라미터 이름·단위)으로 SI 변환
  ② standalone Modelica .mo 생성 (경계조건 Source/Sink + 신호 입력)
  ③ OpenModelica(omc)로 실행
  ④ Python step()과 동일한 출력 키로 결과 회수
한다.

설계 의도(docs/modelica-decision.md): 사이클 솔버는 Modelica(acausal),
캔버스는 이 생성기를 통해 .mo를 emit → omc 실행. 본 모듈이 그 생성기의 시작점.

현재 구현: EEV(type 130, Off) end-to-end. 검증 <0.001% vs eev_off_design.step().
확장 방법: COMPONENT_REGISTRY에 항목 추가 (modelica_model, param_map, template_fn).

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


# ── 단위 변환기 ──────────────────────────────────────────────────
def _ident(v): return float(v)
def _mm2_to_m2(v): return float(v) * 1e-6      # 면적 mm² → m²  ★ 단위변경 반영
def _bar_to_pa(v): return float(v) * 1e5       # 압력 bar → Pa
def _kjkg_to_jkg(v): return float(v) * 1e3     # 비엔탈피 kJ/kg → J/kg


# ── EEV(Off, type 130) 템플릿 ───────────────────────────────────
def _eev_template(mp, bc):
    """mp: SI로 변환된 Modelica 파라미터, bc: SI 경계조건."""
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
    hl = M.bubbleEnthalpy(M.setSat_p({bc['P_out']:.10g}));
    hv = M.dewEnthalpy(M.setSat_p({bc['P_out']:.10g}));
    T_out = M.temperature(M.setState_ph({bc['P_out']:.10g}, h_out)) - 273.15;
    x_out = max(0.0, min(1.0, (h_out - hl)/(hv - hl)));
  end GenCase;
end CanvasGen;
"""


# ── 컴포넌트 레지스트리 (확장 지점) ──────────────────────────────
#   type → { modelica_model, param_map(canvas→(modelica,conv)), input_map, outputs, template }
COMPONENT_REGISTRY = {
    'eev_off_design': {
        'modelica_model': 'HPWD.EEV_L1',
        'param_map': {
            'A_orifice':   ('A_orifice', _mm2_to_m2),   # ★ mm² → m²
            'Cv_rated':    ('Cv_rated', _ident),
            'c0': ('c0', _ident), 'c1': ('c1', _ident),
            'c2': ('c2', _ident), 'c3': ('c3', _ident),
            'opening_min': ('opening_min', _ident),
        },
        'param_defaults': {'A_orifice': 3.14e-6, 'Cv_rated': 0.7,
                           'c0': 0.0, 'c1': 0.5, 'c2': 0.3, 'c3': 0.2, 'opening_min': 0.0},
        'input_map': {  # canvas input → (bc_key, conv)
            'P_in': ('P_in', _bar_to_pa), 'h_in': ('h_in', _kjkg_to_jkg),
            'P_out': ('P_out', _bar_to_pa), 'opening': ('opening', _ident),
        },
        'outputs': ['m_dot_ref', 'phi_op', 'rho_in', 'h_out', 'T_out', 'x_out'],
        'template': _eev_template,
    },
    # TODO: 'compressor_ahri', 'evaporator_off_design', 'condenser_off_design' ...
    #       각 항목에 동일 구조로 modelica_model + param/input map + template 추가
}


def gen_component_mo(block):
    """block={'component','params','inputs'} → (mo_str, outputs_list)."""
    comp = block['component']
    if comp not in COMPONENT_REGISTRY:
        raise ValueError(f"Modelica 브릿지 미지원 컴포넌트: {comp} "
                         f"(지원: {list(COMPONENT_REGISTRY)})")
    spec = COMPONENT_REGISTRY[comp]
    p, inp = block.get('params', {}), block['inputs']
    mp = dict(spec['param_defaults'])
    for ck, (mk, conv) in spec['param_map'].items():
        if ck in p:
            mp[mk] = conv(p[ck])
    bc = {}
    for ck, (bk, conv) in spec['input_map'].items():
        if ck in inp:
            bc[bk] = conv(inp[ck])
    return spec['template'](mp, bc), spec['outputs']


def run_omc(mo, vars_, timeout=120):
    """.mo(str) 실행 → {var: 최종값} (실패 시 (None, log))."""
    os.makedirs(_WORK, exist_ok=True)
    open(os.path.join(_WORK, "CanvasGen.mo"), "w").write(mo)
    vf = "|".join(["time"] + vars_)
    # omc .mos의 문자열 리터럴에선 '\'가 escape로 해석됨 → Windows 경로(C:\..)가 깨짐.
    # omc는 forward slash를 허용하므로 모든 경로를 '/'로 정규화해서 넘긴다.
    fs = lambda p: p.replace("\\", "/")
    helm = fs(HELMHOLTZ_PATH)
    hpwd = fs(os.path.join(MODELICA_DIR, "HPWD.mo"))
    canvas = fs(os.path.join(_WORK, "CanvasGen.mo"))
    mos = (f'loadModel(Modelica); getErrorString();\n'
           f'loadFile("{helm}"); getErrorString();\n'
           f'loadFile("{hpwd}"); getErrorString();\n'
           f'loadFile("{canvas}"); getErrorString();\n'
           f'simulate(CanvasGen.GenCase, startTime=0, stopTime=1, numberOfIntervals=1,'
           f' outputFormat="csv", variableFilter="{vf}"); getErrorString();\n')
    open(os.path.join(_WORK, "run.mos"), "w").write(mos)
    r = subprocess.run(["omc", "run.mos"], cwd=_WORK, capture_output=True,
                       text=True, timeout=timeout)
    csv_path = os.path.join(_WORK, "CanvasGen.GenCase_res.csv")
    if not os.path.exists(csv_path):
        return None, r.stdout + r.stderr
    rows = list(_csv.reader(open(csv_path)))
    hdr = [h.strip('"') for h in rows[0]]
    last = rows[-1]
    return {hdr[i]: float(last[i]) for i in range(len(hdr))}, None


def compute_modelica(block):
    """canvas /compute 와 동일 인터페이스 — Modelica 엔진 버전.
    반환: {'outputs': {...}}  (Python step()과 동일 키)."""
    mo, outs = gen_component_mo(block)
    res, err = run_omc(mo, outs)
    if res is None:
        raise RuntimeError(f"OMC 실행 실패:\n{err[-1200:]}")
    return {'outputs': {k: res[k] for k in outs if k in res}}
