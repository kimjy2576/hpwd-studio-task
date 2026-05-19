"""
Evaporator (L3 On-Design / Tube-Segment)
═══════════════════════════════════════════════════════════════════════
HX-Sim Tube-Segment Model wrapping (Phase 4-A).

벤더드 HX-Sim (backend/_vendor/hx_sim/) 의 Nr × Nt × N_seg 세그먼트 모델을
HPWD Studio component 인터페이스에 맞게 wrapping.

핵심 차별점 (vs L1/L2):
  L1 (off_design): UA 직접 입력 (설계 변수 0)
  L2 (moving_boundary): 2-zone ε-NTU + Schmidt fin (설계 변수 일부)
  L3 (on_design): 모든 설계 정보 (cabinet 치수, fin geometry, circuit 등)

Wrapping 후 가능 (HX-Sim의 학계 정통 검증된 식들):
  • 30+ correlation 선택 (Wang/Chen/Shah/Kim-Mudawar/Friedel 등)
  • Circuit mode (row_parallel/serpentine_2/serpentine_4/single/custom)
  • 4 fin type (plain/wavy/louver/slit)
  • 3 edge type (sharp/rounded/chamfered) — Kc/Ke 보정
  • Wet coil correction (사용자 노출 wet_dp_max)
  • U-bend dP loss (사용자 노출 K_bend)
  • Re/x/P_r 검증 자동 warning

진영님 audit 검증 완료 (한계 #1~#10 + 하드코딩 + correlation 검증범위):
  ✓ P_local segment-by-segment 추적
  ✓ N_seg 사용자 직접 설정 (default 10, auto-recommend 가능)
  ✓ T_ref segment 평균 (forward Euler)
  ✓ N_fins round, U-bend dP, edge type
  ✓ Wet coil correction (학계 1.10~1.30 변동 노출)
  ✓ 모든 물리 상수 CoolProp (cp_air, h_fg_water, M_mol)
  ✓ Cooper pool boiling M_mol audit (R290 이외 fluid OK)
  ✓ Correlation 검증 범위 자동 warning
"""

import sys
import os

# vendored HX-Sim 경로 추가 (backend/ 기준 import)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import math
import CoolProp.CoolProp as CP

from _vendor.hx_sim import (
    SimulationInput, HXSolver, FinTubeSpec,
    recommend_N_seg,
)

# ════════ Available options (UI dropdown) ════════
FLUIDS = ['R290', 'R134a', 'R410A', 'R32', 'R1234yf', 'R22', 'R407C']

FIN_TYPES = ['plain', 'wavy', 'louver', 'slit']
EDGE_TYPES = ['sharp', 'rounded', 'chamfered']
CIRCUIT_MODES = ['row_parallel', 'serpentine_2', 'serpentine_4', 'single', 'custom']
LAYOUTS = ['staggered', 'inline']

# Air-side j-factor correlations (HX-Sim 30+ 노출, 4가지로 단순화)
# user-friendly subset
AIR_J_PLAIN = ['wang2000_plain', 'gray_webb1986', 'kim1999_plain', 'kayansayan1993']
AIR_J_WAVY = ['wang1999_wavy', 'wang2002_wavy', 'beecher_fagan1987', 'kim1997_wavy', 'jang1996_wavy']
AIR_J_LOUVER = ['wang2000_louver', 'chang2000_louver', 'achaichia_cowell1988', 'davenport1983']
AIR_J_SLIT = ['wang2001_slit', 'manglik_bergles1995', 'nakayama_xu1983', 'du_wang2000']
AIR_J_ALL = AIR_J_PLAIN + AIR_J_WAVY + AIR_J_LOUVER + AIR_J_SLIT

# Refrigerant correlations (sensible default + alternatives)
REF_EVAP = ['chen1966', 'gungor_winterton1986', 'kandlikar1990']
REF_COND = ['shah1979', 'cavallini2006', 'dobson_chato1998']
REF_DP = ['friedel1979', 'lockhart_martinelli1949', 'muller_steinhagen1986']


modelDescription = {
    'typeNo': 122,
    'name': 'Evaporator (On-Design / Tube-Segment)',
    'category': 'refrigerant',
    'modelType': 'on-design',
    'fidelity': 0.95,
    'description': 'HX-Sim Nr×Nt×N_seg tube-segment model with T_wall iteration — 학계 정통 30+ correlation',
    'backend': 'python',
    'variables': [
        # ═══════ Material ═══════
        {'name': 'fluid', 'causality': 'parameter', 'type': 'String',
         'group': 'Material', 'start': 'R290', 'unit': '-', 'options': FLUIDS,
         'description': '냉매 종류'},
        
        # ═══════ Geometry — 외관 ═══════
        {'name': 'W', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.40, 'unit': 'm',
         'description': '튜브 길이 방향 (코일 width)'},
        {'name': 'H', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.30, 'unit': 'm',
         'description': '공기 흐름 face 높이 (코일 height)'},
        {'name': 'D', 'causality': 'parameter', 'type': 'Real',
         'group': 'Geometry', 'start': 0.044, 'unit': 'm',
         'description': '공기 흐름 방향 두께 (코일 depth)'},
        
        # ═══════ Geometry — 튜브 ═══════
        {'name': 'D_o', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 7.0e-3, 'unit': 'm',
         'description': '튜브 외경'},
        {'name': 'D_i', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 6.5e-3, 'unit': 'm',
         'description': '튜브 내경'},
        {'name': 'P_t', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 25.0e-3, 'unit': 'm',
         'description': 'Transverse pitch (공기 방향 수직)'},
        {'name': 'P_l', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 22.0e-3, 'unit': 'm',
         'description': 'Longitudinal pitch (공기 방향)'},
        {'name': 'N_rows', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 2.0, 'unit': '-',
         'description': '공기 흐름 row 수'},
        {'name': 'N_tubes_per_row', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tube', 'start': 12.0, 'unit': '-',
         'description': 'Row당 튜브 수 (총 튜브: Nr × Nt)'},
        {'name': 'layout', 'causality': 'parameter', 'type': 'String',
         'group': 'Tube', 'start': 'staggered', 'unit': '-', 'options': LAYOUTS,
         'description': '튜브 배열: staggered (일반) / inline'},
        
        # ═══════ Geometry — Fin ═══════
        {'name': 'FPI', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 12.0, 'unit': 'fins/inch',
         'description': '핀 밀도 (FPI=12 → P_fin ≈ 2.12mm)'},
        {'name': 't_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 0.12e-3, 'unit': 'm',
         'description': '핀 두께'},
        {'name': 'fin_type', 'causality': 'parameter', 'type': 'String',
         'group': 'Fin', 'start': 'plain', 'unit': '-', 'options': FIN_TYPES,
         'description': 'Fin 타입 — plain/wavy/louver/slit'},
        {'name': 'k_fin', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 200.0, 'unit': 'W/(m·K)',
         'description': '핀 열전도율 (Al~200, Cu~390)'},
        {'name': 'edge_type', 'causality': 'parameter', 'type': 'String',
         'group': 'Fin', 'start': 'rounded', 'unit': '-', 'options': EDGE_TYPES,
         'description': 'Kc/Ke edge type — sharp(보수적)/rounded(실코일)/chamfered(최소)'},
        # 추가 fin 파라미터 (wavy/louver/slit 일 때만 사용)
        {'name': 'wavy_amplitude', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 1.0e-3, 'unit': 'm',
         'description': '(wavy) 진폭 (peak-to-peak/2)'},
        {'name': 'wavy_wavelength', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 10.0e-3, 'unit': 'm',
         'description': '(wavy) 파장'},
        {'name': 'louver_pitch', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 1.7e-3, 'unit': 'm',
         'description': '(louver) Lp'},
        {'name': 'louver_angle', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fin', 'start': 27.0, 'unit': 'deg',
         'description': '(louver) θ'},

        # ═══════ Circuit ═══════
        {'name': 'circuit_mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Circuit', 'start': 'row_parallel', 'unit': '-',
         'options': CIRCUIT_MODES,
         'description': 'Circuit 모드: row_parallel/serpentine_2/serpentine_4/single/custom'},
        # custom 모드용 — JSON string 형태로 [[ [r,c], ... ], ...] 전달
        {'name': 'custom_circuits', 'causality': 'parameter', 'type': 'String',
         'group': 'Circuit', 'start': '', 'unit': '-',
         'description': '(custom 모드만) JSON: [[[r,c], ...], ...]  비워두면 row_parallel'},

        # ═══════ Numerical / Solver ═══════
        {'name': 'N_seg', 'causality': 'parameter', 'type': 'Real',
         'group': 'Numerical', 'start': 10.0, 'unit': '-',
         'description': '튜브당 segment 수 (8~15 권장, default 10)'},
        {'name': 'N_seg_auto', 'causality': 'parameter', 'type': 'String',
         'group': 'Numerical', 'start': 'off', 'unit': '-', 'options': ['off', 'on'],
         'description': 'N_seg 자동 추천 (G_ref 기반, 8~15)'},
        
        # ═══════ Correlations ═══════
        {'name': 'evap_corr', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlations', 'start': 'chen1966', 'unit': '-', 'options': REF_EVAP,
         'description': 'Evaporation HTC correlation'},
        {'name': 'cond_corr', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlations', 'start': 'shah1979', 'unit': '-', 'options': REF_COND,
         'description': '(condenser 모드) Condensation HTC correlation'},
        {'name': 'dp_corr', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlations', 'start': 'friedel1979', 'unit': '-', 'options': REF_DP,
         'description': 'Refrigerant dP correlation'},
        # Air j-factor — fin_type에 따라 자동 선택, 사용자가 override 가능
        {'name': 'air_j_corr', 'causality': 'parameter', 'type': 'String',
         'group': 'Correlations', 'start': 'auto', 'unit': '-',
         'options': ['auto'] + AIR_J_ALL,
         'description': 'Air-side j-factor (auto = fin_type 기반 자동 선택)'},

        # ═══════ Operating mode ═══════
        {'name': 'mode', 'causality': 'parameter', 'type': 'String',
         'group': 'Operating', 'start': 'evap', 'unit': '-', 'options': ['evap', 'cond'],
         'description': '운전 모드: evap (증발기) / cond (응축기)'},
        
        # ═══════ Model parameters (학계 평균, 사용자 보정 가능) ═══════
        {'name': 'wet_dp_max', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tuning', 'start': 1.20, 'unit': '-',
         'description': 'Wet coil dP factor max (학계 1.10~1.30, 1.0 = 비활성)'},
        {'name': 'K_bend', 'causality': 'parameter', 'type': 'Real',
         'group': 'Tuning', 'start': 0.75, 'unit': '-',
         'description': 'U-bend loss coefficient (Idelchik 0.5~1.0)'},
        
        # ═══════ Fitting (calibration multipliers) ═══════
        {'name': 'cf_j', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'Air j-factor 보정 multiplier'},
        {'name': 'cf_f', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': 'Air f-factor (friction) 보정'},
        {'name': 'cf_hi', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '냉매측 HTC 보정'},
        {'name': 'cf_dp_ref', 'causality': 'parameter', 'type': 'Real',
         'group': 'Fitting', 'start': 1.0, 'unit': '-',
         'description': '냉매측 dP 보정'},
        
        # ═══════ Inputs (운전 조건) ═══════
        {'name': 'P_evap', 'causality': 'input', 'type': 'Real',
         'unit': 'bar', 'description': '증발 압력 (abs)'},
        {'name': 'h_in', 'causality': 'input', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 입구 비엔탈피'},
        {'name': 'm_dot_ref', 'causality': 'input', 'type': 'Real',
         'unit': 'kg/s', 'description': '냉매 질량 유량'},
        {'name': 'T_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '°C', 'description': '공기 입구 온도'},
        {'name': 'RH_air_in', 'causality': 'input', 'type': 'Real',
         'unit': '%', 'description': '공기 입구 상대습도'},
        {'name': 'V_air_CMM', 'causality': 'input', 'type': 'Real',
         'unit': 'CMM', 'description': '공기 풍량 (m³/min, CMM) — 한국 HVAC 표준 단위'},
        
        # ═══════ Outputs ═══════
        # Refrigerant
        {'name': 'T_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '냉매 출구 온도'},
        {'name': 'h_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kJ/kg', 'description': '냉매 출구 엔탈피'},
        {'name': 'P_ref_out', 'causality': 'output', 'type': 'Real',
         'unit': 'bar', 'description': '냉매 출구 압력'},
        {'name': 'quality_out', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '출구 quality (>1 = SH)'},
        {'name': 'SH_out', 'causality': 'output', 'type': 'Real',
         'unit': 'K', 'description': '출구 과열도 (evap mode)'},
        {'name': 'T_evap', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '증발 포화 온도'},
        # Air
        {'name': 'T_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '°C', 'description': '공기 출구 온도'},
        {'name': 'RH_air_out', 'causality': 'output', 'type': 'Real',
         'unit': '%', 'description': '공기 출구 RH'},
        {'name': 'W_air_out', 'causality': 'output', 'type': 'Real',
         'unit': 'kg/kg', 'description': '공기 출구 humidity ratio'},
        # 열량
        {'name': 'Q_total', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '총 열교환량'},
        {'name': 'Q_sensible', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '현열'},
        {'name': 'Q_latent', 'causality': 'output', 'type': 'Real',
         'unit': 'W', 'description': '잠열 (응축)'},
        {'name': 'SHR', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Sensible Heat Ratio = Q_sensible / Q_total'},
        # 압력강하
        {'name': 'dP_ref', 'causality': 'output', 'type': 'Real',
         'unit': 'Pa', 'description': '냉매측 총 dP (마찰 + 가속 + bend)'},
        {'name': 'dP_bend', 'causality': 'output', 'type': 'Real',
         'unit': 'Pa', 'description': 'U-bend dP만 분리 (진단)'},
        {'name': 'dP_air', 'causality': 'output', 'type': 'Real',
         'unit': 'Pa', 'description': '공기측 총 dP'},
        # Tube-segment 진단
        {'name': 'N_seg_used', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '실제 사용된 N_seg'},
        {'name': 'wet_fraction', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Wet segment 비율'},
        {'name': 'is_wet', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Wet coil 여부 (1 if wet_fraction > 0.05)'},
        {'name': 'wet_dp_factor', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Wet coil dP boost factor'},
        # Convergence + warning 진단
        {'name': 'outer_iter', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Outer iteration count'},
        {'name': 'converged', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': '1 if converged'},
        {'name': 'warnings_count', 'causality': 'output', 'type': 'Real',
         'unit': '-', 'description': 'Correlation 검증 범위 외 warning 수'},
        # Warning 텍스트 (UI 표시용)
        {'name': 'warnings_text', 'causality': 'output', 'type': 'String',
         'unit': '-', 'description': '검증 범위 warning 메시지 (다중 -> | 구분)'},
        # Correlation 사용 (진단)
        {'name': 'evap_corr_used', 'causality': 'output', 'type': 'String',
         'unit': '-', 'description': '실제 사용된 evap correlation'},
        {'name': 'air_j_corr_used', 'causality': 'output', 'type': 'String',
         'unit': '-', 'description': '실제 사용된 air j-factor correlation'},
        {'name': 'dp_corr_used', 'causality': 'output', 'type': 'String',
         'unit': '-', 'description': '실제 사용된 refrigerant dP correlation'},
    ],
    'capabilities': {
        'canDoStep': True,
        'canGetDerivatives': False,
    },
}


def init_state(params):
    """Steady-state model — no internal state."""
    return {}


def _parse_custom_circuits(json_str):
    """Custom circuit JSON 파싱.
    
    형식: [[[r1,c1], [r2,c2], ...], [...], ...]
    각 회로는 ordered list of [row, col] tube passes.
    """
    if not json_str or not json_str.strip():
        return []
    try:
        import json
        data = json.loads(json_str)
        if not isinstance(data, list):
            return []
        # validate
        result = []
        for circuit in data:
            if not isinstance(circuit, list):
                continue
            valid_circ = []
            for tube in circuit:
                if isinstance(tube, list) and len(tube) == 2:
                    try:
                        valid_circ.append([int(tube[0]), int(tube[1])])
                    except (ValueError, TypeError):
                        continue
            if valid_circ:
                result.append(valid_circ)
        return result
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


def step(input, params, state, dt):
    # ═══════ Parameters ═══════
    fluid = params.get('fluid', 'R290')
    
    # Geometry — outer dimensions
    W = float(params.get('W', 0.40))
    H = float(params.get('H', 0.30))
    D = float(params.get('D', 0.044))
    
    # Tube
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    P_t = float(params.get('P_t', 25.0e-3))
    P_l = float(params.get('P_l', 22.0e-3))
    N_rows = int(float(params.get('N_rows', 2.0)))
    N_tubes_per_row = int(float(params.get('N_tubes_per_row', 12.0)))
    layout = params.get('layout', 'staggered')
    
    # Fin
    FPI = float(params.get('FPI', 12.0))
    t_fin = float(params.get('t_fin', 0.12e-3))
    fin_type = params.get('fin_type', 'plain')
    k_fin = float(params.get('k_fin', 200.0))
    edge_type = params.get('edge_type', 'rounded')
    wavy_amp = float(params.get('wavy_amplitude', 1.0e-3))
    wavy_wl = float(params.get('wavy_wavelength', 10.0e-3))
    louver_pitch = float(params.get('louver_pitch', 1.7e-3))
    louver_angle = float(params.get('louver_angle', 27.0))
    
    # Circuit
    circuit_mode = params.get('circuit_mode', 'row_parallel')
    custom_circuits_json = params.get('custom_circuits', '')
    custom_circuits = _parse_custom_circuits(custom_circuits_json)
    
    # Numerical
    N_seg = int(float(params.get('N_seg', 10.0)))
    N_seg = max(3, min(N_seg, 30))  # safety clamp
    N_seg_auto = params.get('N_seg_auto', 'off')
    
    # Correlations
    mode = params.get('mode', 'evap')
    evap_corr = params.get('evap_corr', 'chen1966')
    cond_corr = params.get('cond_corr', 'shah1979')
    dp_corr = params.get('dp_corr', 'friedel1979')
    air_j_corr = params.get('air_j_corr', 'auto')
    
    # Tuning
    wet_dp_max = float(params.get('wet_dp_max', 1.20))
    K_bend = float(params.get('K_bend', 0.75))
    
    # Fitting
    cf_j = float(params.get('cf_j', 1.0))
    cf_f = float(params.get('cf_f', 1.0))
    cf_hi = float(params.get('cf_hi', 1.0))
    cf_dp_ref = float(params.get('cf_dp_ref', 1.0))
    
    # ═══════ Inputs ═══════
    P_evap_bar = float(input.get('P_evap', 5.84))
    h_in_kjkg = float(input.get('h_in', 270.0))
    m_dot_ref = float(input.get('m_dot_ref', 0.005))
    T_air_in_C = float(input.get('T_air_in', 35.0))
    RH_air_in_pct = float(input.get('RH_air_in', 50.0))
    V_air_CMM = float(input.get('V_air_CMM', 9.0))  # CMM (m³/min) — 한국 HVAC 표준 단위
    # CMM → face velocity (m/s) 변환: V = (CMM / 60) / A_fr,  A_fr = W × H
    A_fr = W * H if (W > 0 and H > 0) else 0.12
    V_air = (V_air_CMM / 60.0) / A_fr if A_fr > 0 else 0.0
    
    if P_evap_bar <= 0 or m_dot_ref <= 0:
        raise ValueError(f"입력 0 이하: P_evap={P_evap_bar}, m_dot_ref={m_dot_ref}")
    
    # ═══════ 입구 상태 → quality / T_ref_in 계산 ═══════
    P_evap_Pa = P_evap_bar * 1e5
    h_in_J = h_in_kjkg * 1000.0
    
    T_sat = CP.PropsSI('T', 'P', P_evap_Pa, 'Q', 0, fluid)
    h_l = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 0, fluid)
    h_v = CP.PropsSI('H', 'P', P_evap_Pa, 'Q', 1, fluid)
    
    T_ref_in_K = None  # 단상 입구일 때만 사용
    if h_in_J <= h_l:
        # Subcooled liquid
        x_in = 0.0
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_evap_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_sat - 5.0
    elif h_in_J >= h_v:
        # Superheated vapor
        x_in = 1.0
        try:
            T_ref_in_K = CP.PropsSI('T', 'P', P_evap_Pa, 'H', h_in_J, fluid)
        except Exception:
            T_ref_in_K = T_sat + 5.0
    else:
        # Two-phase
        x_in = (h_in_J - h_l) / (h_v - h_l)
        T_ref_in_K = T_sat
    
    # ═══════ FinTubeSpec 구성 ═══════
    spec_kwargs = dict(
        W=W, H=H, D=D,
        Do=D_o, Di=D_i, Pt=P_t, Pl=P_l,
        Nr=N_rows, Nt=N_tubes_per_row,
        layout=layout,
        FPI=FPI, fin_thickness=t_fin,
        fin_type=fin_type, k_fin=k_fin,
        edge_type=edge_type,
        N_seg=N_seg,
        circuit_mode=circuit_mode,
        circuits=custom_circuits if circuit_mode == 'custom' else [],
    )
    # fin type별 추가 파라미터
    if fin_type == 'wavy':
        spec_kwargs['wavy_amplitude'] = wavy_amp
        spec_kwargs['wavy_wavelength'] = wavy_wl
    if fin_type == 'louver':
        spec_kwargs['louver_pitch'] = louver_pitch
        spec_kwargs['louver_angle'] = louver_angle
    
    spec = FinTubeSpec(**spec_kwargs)
    
    # N_seg auto-recommend (사용자가 선택 시)
    if N_seg_auto == 'on':
        spec.N_seg = recommend_N_seg(spec, m_dot_ref, fluid, T_sat)
    
    # ═══════ SimulationInput 구성 ═══════
    T_air_in_K = T_air_in_C + 273.15
    RH_in = RH_air_in_pct / 100.0
    
    sim_inp = SimulationInput(
        hx_type='FT',
        mode=mode,
        T_air_in=T_air_in_K,
        RH_in=RH_in,
        V_air=V_air,
        fluid=fluid,
        T_sat=T_sat,
        m_ref=m_dot_ref,
        x_in=x_in,
        T_ref_in=T_ref_in_K,
        ft_spec=spec,
        flow_arrangement='counter',
        # Fitting multipliers
        cf_j=cf_j, cf_f=cf_f, cf_hi=cf_hi, cf_dp_ref=cf_dp_ref,
        # Tuning
        wet_dp_max=wet_dp_max,
        K_bend=K_bend,
    )
    
    # Air j-factor — auto가 아니면 명시
    solver = HXSolver(sim_inp)
    if air_j_corr != 'auto':
        solver.corr['air_j'] = air_j_corr
    # ref correlation 명시
    solver.corr['evap'] = evap_corr
    solver.corr['cond'] = cond_corr
    solver.corr['dp_ref'] = dp_corr
    
    # ═══════ Solve ═══════
    result = solver.solve()
    
    if result.error:
        raise RuntimeError(f"HX-Sim solve 실패: {result.error}")
    
    # ═══════ 결과 → outputs 매핑 ═══════
    T_ref_out_K = result.T_ref_out
    T_air_out_K = result.T_air_out
    
    # h_ref_out 계산 (P, x 또는 T_ref_out 기반)
    P_ref_out_Pa = max(P_evap_Pa - result.dp_ref, 1e3)
    x_out = result.x_ref_out
    
    try:
        if x_out >= 1.0:
            # Superheated
            h_ref_out_J = CP.PropsSI('H', 'P', P_ref_out_Pa, 'T', T_ref_out_K, fluid)
        elif x_out <= 0.0:
            # Subcooled
            h_ref_out_J = CP.PropsSI('H', 'P', P_ref_out_Pa, 'T', T_ref_out_K, fluid)
        else:
            # Two-phase
            h_l_out = CP.PropsSI('H', 'P', P_ref_out_Pa, 'Q', 0, fluid)
            h_v_out = CP.PropsSI('H', 'P', P_ref_out_Pa, 'Q', 1, fluid)
            h_ref_out_J = h_l_out + x_out * (h_v_out - h_l_out)
    except Exception:
        # Fallback — 입구 + Q
        h_ref_out_J = h_in_J + result.Q_total / m_dot_ref if mode == 'evap' \
                      else h_in_J - result.Q_total / m_dot_ref
    
    # SH/SC 계산
    if mode == 'evap':
        SH_out = max(0.0, T_ref_out_K - T_sat)
    else:
        SH_out = max(0.0, T_sat - T_ref_out_K)  # subcool for cond
    
    # Wet diagnostics
    wet_frac = result.correlations_used.get('wet_fraction', 0.0)
    wet_factor = result.correlations_used.get('wet_dp_factor', 1.0)
    if isinstance(wet_factor, str):
        wet_factor = 1.0
    is_wet = 1.0 if wet_frac > 0.05 else 0.0
    
    # Convergence + warnings
    conv = result.convergence or {}
    outer_iter = conv.get('outer_iterations', 0)
    converged = 1.0 if conv.get('outer_converged', False) else 0.0
    
    warnings_count = len(result.warnings)
    if warnings_count > 0:
        warnings_text = ' | '.join(
            f"[{w.get('level','?')}] {w.get('msg','?')}"
            for w in result.warnings[:3]  # 최대 3개
        )
    else:
        warnings_text = ''
    
    # SHR
    Q_total = result.Q_total
    SHR = result.Q_sensible / Q_total if Q_total > 0 else 0.0
    
    return {
        'outputs': {
            # Refrigerant
            'T_ref_out': T_ref_out_K - 273.15,
            'h_ref_out': h_ref_out_J / 1000.0,
            'P_ref_out': P_ref_out_Pa / 1e5,
            'quality_out': x_out,
            'SH_out': SH_out,
            'T_evap': T_sat - 273.15,
            # Air
            'T_air_out': T_air_out_K - 273.15,
            'RH_air_out': result.RH_out * 100.0,
            'W_air_out': result.W_air_out,
            # 열량
            'Q_total': Q_total,
            'Q_sensible': result.Q_sensible,
            'Q_latent': result.Q_latent,
            'SHR': SHR,
            # 압력강하
            'dP_ref': result.dp_ref,
            'dP_bend': result.dp_bend_total,
            'dP_air': result.dp_air,
            # 진단
            'N_seg_used': float(spec.N_seg),
            'wet_fraction': wet_frac,
            'is_wet': is_wet,
            'wet_dp_factor': wet_factor,
            'outer_iter': float(outer_iter),
            'converged': converged,
            'warnings_count': float(warnings_count),
            'warnings_text': warnings_text,
            'evap_corr_used': result.correlations_used.get('evap', evap_corr),
            'air_j_corr_used': result.correlations_used.get('air_j', 'auto'),
            'dp_corr_used': result.correlations_used.get('dp_ref', dp_corr),
        },
        'newState': {},
    }


def validate(params):
    """Parameter validation — 사용자에게 미리 알릴 만한 issues."""
    issues = []
    
    D_o = float(params.get('D_o', 7.0e-3))
    D_i = float(params.get('D_i', 6.5e-3))
    if D_i >= D_o:
        issues.append({'key': 'D_i', 'msg': f'D_i ({D_i*1000:.2f}mm) ≥ D_o ({D_o*1000:.2f}mm) — D_i < D_o 이어야'})
    
    P_t = float(params.get('P_t', 25.0e-3))
    if P_t <= D_o:
        issues.append({'key': 'P_t', 'msg': f'P_t ({P_t*1000:.1f}mm) ≤ D_o ({D_o*1000:.1f}mm) — 튜브가 겹칩'})
    
    FPI = float(params.get('FPI', 12.0))
    t_fin = float(params.get('t_fin', 0.12e-3))
    fin_pitch = 0.0254 / FPI
    if t_fin >= fin_pitch:
        issues.append({'key': 't_fin', 'msg': f'핀 두께({t_fin*1000:.2f}mm) ≥ 핀 간격({fin_pitch*1000:.2f}mm)'})
    
    N_rows = int(float(params.get('N_rows', 2.0)))
    if N_rows < 1 or N_rows > 12:
        issues.append({'key': 'N_rows', 'msg': f'N_rows={N_rows} — 1~12 범위 권장'})
    
    fin_type = params.get('fin_type', 'plain')
    if fin_type not in FIN_TYPES:
        issues.append({'key': 'fin_type', 'msg': f"unknown fin_type='{fin_type}'"})
    
    edge_type = params.get('edge_type', 'rounded')
    if edge_type not in EDGE_TYPES:
        issues.append({'key': 'edge_type', 'msg': f"unknown edge_type='{edge_type}'"})
    
    return issues
