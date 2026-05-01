"""
Heat Exchanger Solver — Level 2 Tube-Segment Model
Nr × Nt × N_seg segment-by-segment with T_wall iteration convergence.
"""
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal
from .properties import RefrigerantProperties, MoistAirProperties
from .geometry import FinTubeSpec, FinTubeGeo, MCHXSpec, MCHXGeo, generate_circuits
from .correlations import (
    compute_j_factor, select_correlations, recommend_correlation,
    compute_f_factor, recommend_f_correlation, get_available_f_correlations,
    FSIDE_CORRELATIONS,
    REFSIDE_EVAP_CORRELATIONS, REFSIDE_COND_CORRELATIONS,
    REFSIDE_DP_CORRELATIONS,
    h_with_transition,
    h_single_gnielinski,
    compute_dp_ref_seg, recommend_dp_ref_correlation,
    validate_re_range_wang2000,
)


# ============================================================
# Input Data Classes
# ============================================================

@dataclass
class SimulationInput:
    """Complete simulation input."""
    # Heat exchanger type
    hx_type: Literal["FT", "MCHX"] = "FT"
    mode: Literal["evap", "cond"] = "evap"

    # Air inlet
    T_air_in: float = 308.15    # [K] (35°C)
    RH_in: float = 0.50        # [-]
    V_air: float = 2.0          # face velocity [m/s]
    P_atm: float = 101325.0    # [Pa]

    # Refrigerant
    fluid: str = "R410A"
    T_sat: float = 280.15      # [K] (7°C for evaporator)
    m_ref: float = 0.02        # total mass flow rate [kg/s]
    x_in: float = 0.2          # inlet quality (evap) or 1.0 (cond)
    T_ref_in: Optional[float] = None  # [K] actual inlet temp (for single-phase entry)
    superheat: float = 5.0     # [K] target superheat (evap)
    subcool: float = 5.0       # [K] target subcool (cond)

    # Geometry (FT)
    ft_spec: Optional[FinTubeSpec] = None
    # Geometry (MCHX)
    mchx_spec: Optional[MCHXSpec] = None

    # Flow arrangement
    flow_arrangement: Literal["counter", "parallel"] = "counter"

    # Solver — inner (T_wall per segment)
    alpha: float = 0.7         # under-relaxation
    max_iter: int = 12         # T_wall iteration limit
    tol_T: float = 0.05        # [K]
    tol_Q: float = 0.5         # [W]

    # Solver — outer (air-refrigerant coupling)
    max_outer: int = 30        # outer iteration limit
    outer_tol_pct: float = 0.1 # [%] relative Q convergence
    outer_tol_T: float = 0.1   # [K] T_air_out convergence

    # Correction factors (multipliers, default 1.0)
    cf_j: float = 1.0         # air-side j-factor
    cf_f: float = 1.0         # air-side f-factor (friction)
    cf_hi: float = 1.0        # refrigerant-side HTC
    cf_dp_ref: float = 1.0    # refrigerant-side pressure drop
    
    # 한계 #8 — Wet coil dP correction 계수 (사용자 노출)
    # Korte & Jacobi (2001): dry 대비 wet 코일 dP 1.10~1.30배 (학계 범위).
    # default 1.20 (평균). 실 코일 데이터로 fitting 가능.
    # wet_dp_max = 1.0 → wet 보정 비활성 (dry 모델만)
    wet_dp_max: float = 1.20  # max factor when 100% wet
    # K-bend coefficient (180° U-bend smooth). Idelchik 0.5~1.0, default 0.75.
    K_bend: float = 0.75


def recommend_N_seg(spec: FinTubeSpec, m_ref: float, fluid: str = "R290",
                    T_sat: float = 280.15) -> int:
    """
    한계 #2 — N_seg 자동 추천.
    
    G_ref가 큰 경우 (단일 회로, 고질량유속) dp_ref가 커지면서 P_local 변화가
    중요. 이런 경우 N_seg를 더 키워야 함.
    
    추천 규칙 (학계 가이드 + 실험적):
      G_ref < 100 kg/m²s   → N_seg = 8
      G_ref 100~300        → N_seg = 10 (default)
      G_ref 300~600        → N_seg = 15
      G_ref > 600          → N_seg = 20 (확실한 정확도)
    
    Args:
        spec: FinTubeSpec
        m_ref: 총 질량유량 [kg/s]
        fluid: refrigerant
        T_sat: saturation 온도 [K]
    Returns:
        권장 N_seg (8~20)
    """
    import math as _math
    # circuit 수 결정 — circuit_mode를 보고 판정
    if spec.circuits and spec.circuit_mode == "custom":
        n_circ = len(spec.circuits)
    elif spec.circuit_mode == "single":
        n_circ = 1
    elif spec.circuit_mode.startswith("serpentine"):
        try:
            grp = int(spec.circuit_mode.split("_")[1])
        except (IndexError, ValueError):
            grp = 2
        n_circ = max(1, spec.Nt // grp)
    else:  # row_parallel (default)
        n_circ = spec.Nt
    
    m_ref_circ = m_ref / max(n_circ, 1)
    A_cs = _math.pi * (spec.Di ** 2) / 4
    G_ref = m_ref_circ / A_cs if A_cs > 0 else 100.0
    
    if G_ref < 100:
        return 8
    elif G_ref < 300:
        return 10
    elif G_ref < 600:
        return 12
    else:
        # 600+ 이상도 15에서 캡 — N_seg=20은 outer iteration 수렴이 너무 느림
        # 매우 high G 운전점에선 사용자가 명시적으로 N_seg 더 키울 수 있음
        return 15


@dataclass
class SegmentResult:
    """Result for a single segment."""
    row: int = 0
    tube: int = 0
    seg: int = 0
    Q: float = 0.0             # heat transfer [W]
    Q_sensible: float = 0.0
    Q_latent: float = 0.0
    T_wall: float = 0.0        # [K]
    T_air_local: float = 0.0   # [K]
    T_ref: float = 0.0         # [K]
    x_ref: float = 0.0         # quality
    h_i: float = 0.0           # refrigerant-side HTC
    h_o: float = 0.0           # air-side HTC
    eta_o: float = 0.0         # overall fin efficiency
    dp_ref: float = 0.0        # refrigerant-side dp for this segment [Pa]
    P_local: float = 0.0       # segment 입구 P [Pa] (한계 #1 진단용)
    is_wet: bool = False
    converged: bool = False
    n_iter: int = 0


@dataclass
class SimulationResult:
    """Complete simulation result."""
    Q_total: float = 0.0
    Q_sensible: float = 0.0
    Q_latent: float = 0.0
    SHR: float = 0.0
    T_air_out: float = 0.0
    W_air_out: float = 0.0
    RH_out: float = 0.0
    x_ref_out: float = 0.0
    T_ref_out: float = 0.0
    dp_air: float = 0.0
    dp_ref: float = 0.0        # refrigerant-side total dp [Pa] (max across circuits)
    dp_bend_total: float = 0.0 # 한계 #6 — U-bend dP 누적 (진단용) [Pa]
    segments: List[SegmentResult] = field(default_factory=list)
    row_Q: List[float] = field(default_factory=list)
    correlations_used: Dict = field(default_factory=dict)
    convergence: Dict = field(default_factory=dict)
    circuit_paths: List = field(default_factory=list)  # [[tube,row,seg], ...] per circuit
    warnings: List = field(default_factory=list)  # 한계 #9 — 검증 범위 벗어남 등
    error: str = ""


# ============================================================
# Main Solver
# ============================================================

class HXSolver:
    """Level 2 Tube-Segment heat exchanger solver."""

    def __init__(self, inp: SimulationInput):
        self.inp = inp
        self.ref = RefrigerantProperties(inp.fluid)
        self.air = MoistAirProperties()

        # Build geometry
        if inp.hx_type == "FT":
            if inp.ft_spec is None:
                inp.ft_spec = FinTubeSpec()
            self.geo = FinTubeGeo.from_spec(inp.ft_spec)
            self.spec = inp.ft_spec
            self.Di = inp.ft_spec.Di
            self.Nr = inp.ft_spec.Nr
            self.Nt = inp.ft_spec.Nt
            self.N_seg = inp.ft_spec.N_seg
        else:
            if inp.mchx_spec is None:
                inp.mchx_spec = MCHXSpec()
            self.geo = MCHXGeo.from_spec(inp.mchx_spec)
            self.spec = inp.mchx_spec
            self.Di = self.geo.Dh_ref
            self.Nr = inp.mchx_spec.Nr
            self.Nt = inp.mchx_spec.Nt
            self.N_seg = inp.mchx_spec.N_seg

        # Auto-select correlations
        fin_type = inp.ft_spec.fin_type if inp.hx_type == "FT" else "louver"
        Pt = inp.ft_spec.Pt if inp.hx_type == "FT" else 0.01
        Pl = inp.ft_spec.Pl if inp.hx_type == "FT" else 0.01
        self.corr = select_correlations(inp.hx_type, self.Di, fin_type, Pt, Pl)

    def solve(self) -> SimulationResult:
        """Run the full simulation."""
        inp = self.inp
        result = SimulationResult()
        result.correlations_used = self.corr

        try:
            return self._solve_internal()
        except Exception as e:
            result.error = str(e)
            return result

    def _solve_internal(self) -> SimulationResult:
        inp = self.inp
        ref = self.ref
        P_sat = ref.P_sat(inp.T_sat)

        # Air inlet state
        W_in = self.air.W_from_TRH(inp.T_air_in, inp.RH_in, inp.P_atm)
        h_air_in = self.air.h_simple(inp.T_air_in, W_in)
        T_dp = self.air.Tdp_from_TW(inp.T_air_in, W_in, inp.P_atm)

        # Air mass flow rate
        rho_air = self.air.rho_air(inp.T_air_in, W_in, inp.P_atm)
        A_fr = self.geo.A_fr
        m_air = rho_air * inp.V_air * A_fr

        # ── Build circuit paths ──
        if inp.hx_type == "FT":
            spec = inp.ft_spec
            if spec.circuits and spec.circuit_mode == "custom":
                circuits = spec.circuits
            else:
                circuits = generate_circuits(
                    self.Nr, self.Nt, spec.circuit_mode, inp.flow_arrangement)
        else:
            # MCHX: check for multi-pass (baffle) design
            mspec = inp.mchx_spec
            if mspec.passes and len(mspec.passes) > 1:
                self._mchx_multipass = True
                self._pass_info = []
                A_cs_port = mspec.ch_width * mspec.ch_height
                circuit = []
                pass_slabs = mspec.pass_slabs if mspec.pass_slabs else [0] * len(mspec.passes)
                for pi, pass_tubes in enumerate(mspec.passes):
                    tpp = len(pass_tubes)
                    m_per_tube = inp.m_ref / tpp
                    m_per_port = m_per_tube / mspec.n_ports
                    G_pass = m_per_port / A_cs_port if A_cs_port > 0 else 100
                    rep_tube = pass_tubes[0]
                    slab = pass_slabs[pi] if pi < len(pass_slabs) else 0
                    self._pass_info.append({"tpp": tpp, "G": G_pass, "m_tube": m_per_tube, "rep": rep_tube, "tubes": pass_tubes, "slab": slab})
                    # Each pass goes through its own slab only
                    circuit.append([slab, rep_tube])
                circuits = [circuit]
                # Build tube→pass lookup
                self._tube_pass_map = {}
                for pi, pass_tubes in enumerate(mspec.passes):
                    for t in pass_tubes:
                        self._tube_pass_map[t] = pi
            else:
                self._mchx_multipass = False
                self._pass_info = None
                self._tube_pass_map = None
                circuits = generate_circuits(
                    self.Nr, self.Nt, "row_parallel", inp.flow_arrangement)

        n_circ = len(circuits)

        # Refrigerant per circuit
        m_ref_circ = inp.m_ref / n_circ
        if inp.hx_type == "FT":
            A_cs_ref = math.pi * self.Di ** 2 / 4
            G_ref = m_ref_circ / A_cs_ref if A_cs_ref > 0 else 100
        else:
            A_cs_port = inp.mchx_spec.ch_width * inp.mchx_spec.ch_height
            if getattr(self, '_mchx_multipass', False):
                G_ref = self._pass_info[0]["G"]  # initial, overridden per-tube
            else:
                m_per_port = m_ref_circ / inp.mchx_spec.n_ports
                G_ref = m_per_port / A_cs_port if A_cs_port > 0 else 100

        # Air mass flux & h_o
        G_air = m_air / self.geo.A_c if self.geo.A_c > 0 else 5.0
        h_o = self._compute_h_o(G_air, inp.T_air_in) * inp.cf_j
        h_fg = ref.h_fg(P_sat)
        L_seg = self.geo.L_seg if hasattr(self.geo, 'L_seg') and self.geo.L_seg > 0 else 0.05

        # Refrigerant dp correlation
        dp_corr_id = self.corr.get("dp_ref", recommend_dp_ref_correlation(inp.hx_type))
        self.corr["dp_ref"] = dp_corr_id

        # ── Outer iteration for air temperature convergence ──
        # Air state per column per row: T_air_2d[col][row]
        # Each column has INDEPENDENT air stream flowing through rows 0→Nr-1
        Ns = self.N_seg
        T_air_3d = [[[inp.T_air_in] * (self.Nr + 1) for _ in range(Ns)]
                     for _ in range(self.Nt)]
        W_air_3d = [[[W_in] * (self.Nr + 1) for _ in range(Ns)]
                     for _ in range(self.Nt)]
        m_air_cell = m_air / max(self.Nt * Ns, 1)

        seg_dict = {}
        max_outer = inp.max_outer
        outer_tol_pct = inp.outer_tol_pct
        outer_tol_T = inp.outer_tol_T
        Q_prev_outer = 0.0
        T_air_out_prev = 0.0
        outer_converged = False
        outer_history = []
        omega = 1.0  # under-relaxation: adaptive

        for outer_iter in range(max_outer):
            seg_dict.clear()
            circ_outlets = []
            circ_paths = []  # track actual segment order per circuit

            # ── Process each circuit ──
            for circ_idx, path in enumerate(circuits):
                x_ref = inp.x_in
                T_ref = inp.T_sat
                if inp.T_ref_in is not None and (inp.x_in >= 1.0 or inp.x_in <= 0.0):
                    T_ref = inp.T_ref_in
                # P_sat_local — circuit 입구에서 시작, segment마다 dp_seg만큼 감소.
                # 한계 #1 해결: 2-phase에서 T_sat가 P_local에 따라 변함 →
                #   h_fg, ρ_l, μ_l 등 모든 물성도 P_local 기반으로 사용.
                P_sat_local = P_sat
                dp_circ = 0.0  # accumulate dp for this circuit
                dp_bend_circ = 0.0  # 한계 #6 — U-bend dP per circuit
                circ_seg_keys = []

                for pass_idx, (row_idx, col_idx) in enumerate(path):
                    # MCHX multi-pass: override G_ref per pass
                    G_ref_local = G_ref
                    m_ref_local = m_ref_circ
                    mchx_tpp = 1  # tubes per pass (for Q scaling)
                    if getattr(self, '_mchx_multipass', False) and self._pass_info:
                        pi = self._tube_pass_map.get(col_idx, 0)  # col_idx = physical tube
                        pinfo = self._pass_info[pi]
                        G_ref_local = pinfo["G"]
                        m_ref_local = pinfo["m_tube"]
                        mchx_tpp = pinfo["tpp"]

                    # 한계 #6 — U-bend dP loss (FT only, pass 전환 시)
                    # K-factor based: ΔP_bend = K × G² / (2ρ_avg)
                    # 180° smooth bend: K ≈ 0.5~1.0. 평균 0.75 사용.
                    # First pass엔 entrance 무시, second pass부터 bend 누적.
                    if inp.hx_type == "FT" and pass_idx > 0:
                        # 평균 밀도 (homogeneous flow)
                        try:
                            rho_l_loc = ref.rho_l(P_sat_local)
                            rho_v_loc = ref.rho_v(P_sat_local)
                            x_for_rho = max(0.0, min(1.0, x_ref))
                            rho_avg = 1.0 / (x_for_rho / rho_v_loc + (1 - x_for_rho) / rho_l_loc)
                        except:
                            rho_avg = 500.0  # fallback
                        K_bend = getattr(inp, 'K_bend', 0.75)  # default 0.75 (180° smooth)
                        dp_bend = K_bend * (G_ref_local ** 2) / (2 * max(rho_avg, 1.0))
                        dp_bend *= inp.cf_dp_ref
                        P_sat_local = max(P_sat_local - dp_bend, 1e3)
                        dp_circ += dp_bend
                        dp_bend_circ += dp_bend

                    # Alternate segment direction per tube pass (U-bend)
                    if pass_idx % 2 == 0:
                        seg_order = range(Ns)
                    else:
                        seg_order = range(Ns - 1, -1, -1)

                    for seg_idx in seg_order:
                        T_air_local = T_air_3d[col_idx][seg_idx][row_idx]
                        W_air_local = W_air_3d[col_idx][seg_idx][row_idx]

                        # 한계 #4 해결: segment 진입 시 x_in, T_in 저장 → 이후 평균값으로 사용
                        x_in_seg = x_ref
                        T_in_seg = T_ref

                        # 한계 #1 해결: segment 진입 시점의 P_local로 dp 미리 계산
                        # (segment 내부 평균 P 사용 위해)
                        try:
                            dp_seg_pre = compute_dp_ref_seg(
                                dp_corr_id, x_ref, G_ref_local, self.Di, L_seg,
                                ref, P_sat_local, Dh=self.Di) * inp.cf_dp_ref
                        except:
                            dp_seg_pre = 0.0
                        # Segment 내부 평균 P (P_in - dp/2)
                        P_seg_mean = max(P_sat_local - dp_seg_pre / 2.0, 1e3)

                        seg_result = self._solve_segment(
                            row=row_idx, tube=col_idx, seg=seg_idx,
                            T_air=T_air_local, W_air=W_air_local, T_dp=T_dp,
                            x_ref=x_ref, T_ref=T_ref,
                            P_sat=P_seg_mean, G_ref=G_ref_local, G_air=G_air,
                            h_o=h_o, m_ref_tube=m_ref_local,
                        )

                        # Scale Q by tubes_per_pass (1 tube computed, tpp tubes in parallel)
                        if mchx_tpp > 1:
                            seg_result.Q *= mchx_tpp
                            seg_result.Q_latent *= mchx_tpp

                        # 실제 dp_seg는 segment 진입 시 계산한 값 사용
                        dp_seg = dp_seg_pre
                        seg_result.dp_ref = dp_seg
                        seg_result.P_local = P_sat_local  # segment 입구 P (진단용)
                        dp_circ += dp_seg

                        seg_dict[(col_idx, row_idx, seg_idx)] = seg_result
                        circ_seg_keys.append([col_idx, row_idx, seg_idx])

                        # Update refrigerant state (per-tube Q, not total pass Q)
                        Q_ref_seg = seg_result.Q / mchx_tpp if mchx_tpp > 1 else seg_result.Q

                        # 한계 #1 해결: T_sat, h_fg, cp 등 모든 물성을 P_seg_mean 기반으로
                        T_sat_K = ref.T_sat(P_seg_mean)
                        h_fg_local = ref.h_fg(P_seg_mean)

                        # Phase 판정 (segment 진입 상태 기반)
                        is_superheated = (x_in_seg >= 1.0 and T_in_seg > T_sat_K + 0.05)
                        is_subcooled = (x_in_seg <= 0.0 and T_in_seg < T_sat_K - 0.05)
                        is_two_phase = not is_superheated and not is_subcooled

                        if is_two_phase:
                            # Force T_ref = Tsat during two-phase (segment 평균 T_sat)
                            T_ref = T_sat_K
                            if h_fg_local > 0 and m_ref_local > 0:
                                dx = Q_ref_seg / (m_ref_local * h_fg_local)
                                if inp.mode == "evap":
                                    x_ref += dx
                                else:
                                    x_ref -= dx
                                # Handle boundary crossing: compute partial Q for single-phase
                                if x_ref > 1.0:
                                    Q_excess = (x_ref - 1.0) * m_ref_local * h_fg_local
                                    x_ref = 1.0
                                    try:
                                        cp_v = ref.cp_v(P_seg_mean)
                                        if m_ref_local > 0 and cp_v > 0:
                                            T_ref = T_sat_K + Q_excess / (m_ref_local * cp_v)
                                    except: pass
                                elif x_ref < 0.0:
                                    Q_excess = (-x_ref) * m_ref_local * h_fg_local
                                    x_ref = 0.0
                                    try:
                                        cp_l = ref.cp_l(P_seg_mean)
                                        if m_ref_local > 0 and cp_l > 0:
                                            T_ref = T_sat_K - Q_excess / (m_ref_local * cp_l)
                                    except: pass
                        elif is_superheated:
                            try:
                                cp_v = ref.cp_v(P_seg_mean)
                                if m_ref_local > 0 and cp_v > 0:
                                    dT = Q_ref_seg / (m_ref_local * cp_v)
                                    if inp.mode == "evap":
                                        T_ref += dT
                                    else:
                                        T_ref -= dT
                                    # Check if desuperheated to Tsat → enter two-phase
                                    if inp.mode == "cond" and T_ref <= T_sat_K:
                                        Q_excess = (T_sat_K - T_ref) * m_ref_local * cp_v
                                        T_ref = T_sat_K
                                        x_ref = 1.0
                                        if h_fg_local > 0:
                                            x_ref -= Q_excess / (m_ref_local * h_fg_local)
                            except: pass
                        elif is_subcooled:
                            try:
                                cp_l = ref.cp_l(P_seg_mean)
                                if m_ref_local > 0 and cp_l > 0:
                                    dT = Q_ref_seg / (m_ref_local * cp_l)
                                    if inp.mode == "cond":
                                        T_ref -= dT
                                    else:
                                        T_ref += dT
                                    # Check if heated to Tsat → enter two-phase
                                    if inp.mode == "evap" and T_ref >= T_sat_K:
                                        Q_excess = (T_ref - T_sat_K) * m_ref_local * cp_l
                                        T_ref = T_sat_K
                                        x_ref = 0.0
                                        if h_fg_local > 0:
                                            x_ref += Q_excess / (m_ref_local * h_fg_local)
                            except: pass

                        # 한계 #1 해결: P_sat_local 업데이트 — segment 끝나면 dp_seg만큼 감소
                        P_sat_local = max(P_sat_local - dp_seg, 1e3)

                circ_outlets.append((x_ref, T_ref, dp_circ, dp_bend_circ))
                circ_paths.append(circ_seg_keys)

            # ── Check outer convergence ──
            Q_this = sum(s.Q for s in seg_dict.values())
            T_air_out_this = sum(T_air_3d[c][s][self.Nr]
                                 for c in range(self.Nt) for s in range(Ns)) / max(self.Nt * Ns, 1)
            dQ_outer = abs(Q_this - Q_prev_outer)
            dT_outer = abs(T_air_out_this - T_air_out_prev)
            rel_dQ = dQ_outer / max(abs(Q_this), 1.0) * 100

            outer_history.append({
                "iter": outer_iter + 1,
                "Q": round(Q_this, 2),
                "dQ": round(dQ_outer, 2),
                "dQ_pct": round(rel_dQ, 3),
                "T_air_out": round(T_air_out_this - 273.15, 2),
                "dT": round(dT_outer, 3),
                "omega": round(omega, 3),
            })

            if outer_iter > 0 and rel_dQ < outer_tol_pct and dT_outer < outer_tol_T:
                outer_converged = True
                Q_prev_outer = Q_this
                T_air_out_prev = T_air_out_this
                break

            # ── Adaptive under-relaxation ──
            # Detect oscillation: if Q flipped sign between last 2 iterations
            if outer_iter >= 2:
                h1 = outer_history[-2]
                h2 = outer_history[-3]
                dQ_prev = h1["Q"] - h2["Q"]
                dQ_curr = Q_this - h1["Q"]
                if dQ_prev * dQ_curr < 0:
                    # Oscillation detected → reduce omega
                    omega = max(omega * 0.7, 0.3)
                else:
                    # Monotone → increase omega toward 1.0
                    omega = min(omega * 1.1, 0.9)
            elif outer_iter == 1:
                omega = 0.6  # conservative start after first full update

            Q_prev_outer = Q_this
            T_air_out_prev = T_air_out_this

            # ── Update per-(col, seg) air pencil with adaptive omega ──
            h_fg_water = 2501000.0
            # For MCHX multipass: map non-representative tubes to rep tube's Q
            _mp = getattr(self, '_mchx_multipass', False)
            for col_idx in range(self.Nt):
                for seg_idx in range(Ns):
                    T_air_3d[col_idx][seg_idx][0] = inp.T_air_in
                    W_air_3d[col_idx][seg_idx][0] = W_in
                    for row_idx in range(self.Nr):
                        sr = seg_dict.get((col_idx, row_idx, seg_idx))
                        if not sr and _mp and self._tube_pass_map:
                            # Look up rep tube for this tube's pass
                            pi = self._tube_pass_map.get(col_idx)
                            if pi is not None:
                                rep = self._pass_info[pi]["rep"]
                                sr = seg_dict.get((rep, row_idx, seg_idx))
                        Q_seg = sr.Q if sr else 0.0
                        Q_lat = sr.Q_latent if sr else 0.0
                        # For multipass: Q in seg_dict is scaled by tpp, divide for per-tube
                        if _mp and sr and self._tube_pass_map:
                            pi = self._tube_pass_map.get(col_idx)
                            if pi is not None:
                                tpp = self._pass_info[pi]["tpp"]
                                Q_seg = Q_seg / tpp
                                Q_lat = Q_lat / tpp
                        if m_air_cell > 0:
                            h_cur = self.air.h_simple(
                                T_air_3d[col_idx][seg_idx][row_idx],
                                W_air_3d[col_idx][seg_idx][row_idx])
                            if inp.mode == "evap":
                                h_next = h_cur - Q_seg / m_air_cell
                            else:
                                h_next = h_cur + Q_seg / m_air_cell
                            W_rem = Q_lat / (m_air_cell * h_fg_water)
                            W_next = max(W_air_3d[col_idx][seg_idx][row_idx] - W_rem, 0)
                            T_calc = self.air.T_from_h_simple(h_next, W_next)
                            # Under-relax: blend new with old
                            T_old = T_air_3d[col_idx][seg_idx][row_idx + 1]
                            T_air_3d[col_idx][seg_idx][row_idx + 1] = omega * T_calc + (1 - omega) * T_old
                            W_air_3d[col_idx][seg_idx][row_idx + 1] = omega * W_next + (1 - omega) * W_air_3d[col_idx][seg_idx][row_idx + 1]
                        else:
                            T_air_3d[col_idx][seg_idx][row_idx + 1] = T_air_3d[col_idx][seg_idx][row_idx]
                            W_air_3d[col_idx][seg_idx][row_idx + 1] = W_air_3d[col_idx][seg_idx][row_idx]

        # ── Compile results ──
        all_segments = []
        for col_idx in range(self.Nt):
            for row_idx in range(self.Nr):
                for seg_idx in range(Ns):
                    key = (col_idx, row_idx, seg_idx)
                    if key in seg_dict:
                        all_segments.append(seg_dict[key])

        Q_total = sum(s.Q for s in all_segments)
        Q_lat_total = sum(s.Q_latent for s in all_segments)
        Q_sen = Q_total - Q_lat_total

        x_ref_out_avg = sum(o[0] for o in circ_outlets) / n_circ if circ_outlets else inp.x_in
        T_ref_out_avg = sum(o[1] for o in circ_outlets) / n_circ if circ_outlets else inp.T_sat
        dp_ref_max = max(o[2] for o in circ_outlets) if circ_outlets else 0.0
        # 한계 #6 — dp_bend_total: 전체 circuit 최대 (병렬 회로 중 max)
        dp_bend_max = max(o[3] for o in circ_outlets) if circ_outlets else 0.0

        T_air_out = sum(T_air_3d[c][s][self.Nr]
                        for c in range(self.Nt) for s in range(Ns)) / max(self.Nt * Ns, 1)
        W_air_out = sum(W_air_3d[c][s][self.Nr]
                        for c in range(self.Nt) for s in range(Ns)) / max(self.Nt * Ns, 1)

        row_Q = [sum(seg_dict.get((t, r, s), SegmentResult()).Q
                     for t in range(self.Nt) for s in range(Ns))
                 for r in range(self.Nr)]

        result = SimulationResult()
        result.Q_total = Q_total
        result.Q_sensible = Q_sen
        result.Q_latent = Q_lat_total
        result.SHR = Q_sen / Q_total if Q_total > 0 else 1.0
        result.T_air_out = T_air_out
        result.W_air_out = W_air_out
        result.x_ref_out = x_ref_out_avg
        result.T_ref_out = T_ref_out_avg
        result.segments = all_segments
        result.row_Q = row_Q
        result.circuit_paths = circ_paths
        result.correlations_used = self.corr
        result.convergence = {
            "outer_converged": outer_converged,
            "outer_iterations": outer_iter + 1,
            "outer_max": max_outer,
            "outer_tol_pct": outer_tol_pct,
            "outer_tol_T": outer_tol_T,
            "final_dQ": outer_history[-1]["dQ"] if outer_history else 0,
            "final_dQ_pct": outer_history[-1]["dQ_pct"] if outer_history else 0,
            "final_dT": outer_history[-1]["dT"] if outer_history else 0,
            "history": outer_history,
            "seg_converged_pct": round(
                sum(1 for s in all_segments if s.converged) / max(len(all_segments), 1) * 100, 1),
        }

        # Store circuit info
        self.corr["n_circuits"] = n_circ
        self.corr["circuit_mode"] = inp.ft_spec.circuit_mode if inp.hx_type == "FT" else "row_parallel"

        # 한계 #8 — Wet fraction 계산 (segment 단위 is_wet 비율)
        if seg_dict:
            wet_count = sum(1 for s in seg_dict.values() if s.is_wet)
            self._wet_fraction = wet_count / len(seg_dict)
        else:
            self._wet_fraction = 0.0
        self.corr["wet_fraction"] = round(self._wet_fraction, 3)

        # Air-side pressure drop
        # 한계 #7 — 실제 W (humidity ratio) 전달 (기존: hardcoded 0.01)
        result.dp_air = self._compute_dp_air(G_air, inp.T_air_in, T_air_out,
                                              W_in=W_in, W_out=W_air_out,
                                              T_dp=T_dp)
        result.dp_ref = dp_ref_max
        result.dp_bend_total = dp_bend_max

        # 한계 #9 — Re 범위 검증 + warning 누적
        if inp.hx_type == "FT":
            mu_avg = self.air.mu_air((inp.T_air_in + T_air_out) / 2)
            Re_Dc_check = G_air * self.geo.Dc / mu_avg if mu_avg > 0 else 0
            re_check = validate_re_range_wang2000(Re_Dc_check)
            if re_check['level'] != 'ok':
                result.warnings.append({
                    'category': 'air_side_correlation',
                    'level': re_check['level'],
                    'msg': re_check['msg'],
                    'accuracy': re_check['accuracy'],
                    'recommend': re_check['recommend'],
                })

        # Outlet RH — handle supersaturation (condensate on coil)
        try:
            import CoolProp.CoolProp as CP
            # Saturation humidity ratio at outlet temperature
            W_sat_out = CP.HAPropsSI("W", "T", T_air_out, "R", 1.0, "P", inp.P_atm)
            if W_air_out > W_sat_out:
                # Supersaturated: condensate formed, air exits at 100% RH
                result.W_air_out = W_sat_out
                result.RH_out = 1.0
            else:
                result.RH_out = CP.HAPropsSI("R", "T", T_air_out, "W", W_air_out, "P", inp.P_atm)
        except:
            # Fallback: estimate RH from W ratio
            try:
                W_sat_out = CP.HAPropsSI("W", "T", T_air_out, "R", 1.0, "P", inp.P_atm)
                result.RH_out = min(W_air_out / W_sat_out, 1.0) if W_sat_out > 0 else 0.0
            except:
                result.RH_out = 0.0

        return result

    def _solve_segment(self, row, tube, seg, T_air, W_air, T_dp,
                       x_ref, T_ref, P_sat, G_ref, G_air, h_o,
                       m_ref_tube) -> SegmentResult:
        """Solve single segment with T_wall iteration."""
        inp = self.inp
        ref = self.ref
        sr = SegmentResult(row=row, tube=tube, seg=seg)

        # Segment areas
        if inp.hx_type == "FT":
            A_i_seg = self.geo.A_i_seg
            A_o_seg = self.geo.A_total / (self.Nr * self.Nt * self.N_seg)
        else:
            A_i_seg = self.geo.A_i_seg
            A_o_seg = self.geo.A_total / (self.Nr * self.Nt * self.N_seg)

        # Initial T_wall guess
        T_sat_K0 = inp.T_sat
        T_ref_g = T_ref if (x_ref >= 1.0 and T_ref > T_sat_K0 + 0.05) or (x_ref <= 0.0 and T_ref < T_sat_K0 - 0.05) else T_sat_K0
        T_w = (T_air + T_ref_g) / 2

        # Check wet/dry
        is_wet = (T_w < T_dp) and (inp.mode == "evap")

        alpha = inp.alpha
        Q_prev = 0

        for iteration in range(inp.max_iter):
            # --- Refrigerant side h_i ---
            # q_flux estimate for Kim&Mudawar
            q_flux_est = abs(T_air - T_w) * h_o if h_o > 0 else 5000

            h_i = h_with_transition(
                x=x_ref, G=G_ref, Di=self.Di, q_flux=q_flux_est,
                ref=ref, P=P_sat, mode=inp.mode,
                hx_type=inp.hx_type,
                evap_corr=self.corr.get("evap"),
                cond_corr=self.corr.get("cond"),
            ) * inp.cf_hi

            # --- Fin efficiency ---
            if is_wet:
                b = self._compute_b_factor(T_w, T_air, W_air, h_o)
                if inp.hx_type == "FT":
                    _, eta_o = self.geo.fin_efficiency_wet(h_o, b)
                else:
                    _, eta_o = self.geo.fin_efficiency_wet_straight(h_o, b)
            else:
                if inp.hx_type == "FT":
                    _, eta_o = self.geo.fin_efficiency_schmidt(h_o)
                else:
                    _, eta_o = self.geo.fin_efficiency_straight(h_o)

            # --- Thermal resistances ---
            R_o = 1.0 / (eta_o * h_o * A_o_seg) if (eta_o * h_o * A_o_seg) > 0 else 1e6
            R_i = 1.0 / (h_i * A_i_seg) if (h_i * A_i_seg) > 0 else 1e6
            UA = 1.0 / (R_o + R_i)

            # T_ref_eff: actual refrigerant temp for heat transfer
            # 한계 #4 해결: 단상 영역에서 T_in (inlet only) 가정은 segment 끝 부분에서
            #   ΔT 과대평가를 야기. 대신 forward Euler로 outlet 추정 후 평균값 사용.
            T_sat_K = ref.T_sat(P_sat)  # segment mean P 기반 (한계 #1)
            is_sh = (x_ref > 1) or (x_ref >= 1.0 and T_ref > T_sat_K + 0.05)
            is_sc = (x_ref < 0) or (x_ref <= 0.0 and T_ref < T_sat_K - 0.05)
            if is_sh or is_sc:
                # 단상: 1차 forward Euler 추정 후 평균
                # Q_est = UA × (T_air - T_ref_in) for evap (or 반대)
                if inp.mode == "evap":
                    dT_in = T_air - T_ref
                else:
                    dT_in = T_ref - T_air
                Q_est = UA * dT_in if dT_in > 0 else 0
                cp_phase = ref.cp_v(P_sat) if is_sh else ref.cp_l(P_sat)
                if m_ref_tube > 0 and cp_phase > 0:
                    dT_seg = Q_est / (m_ref_tube * cp_phase)
                    if inp.mode == "evap":
                        T_out_est = T_ref + dT_seg
                    else:
                        T_out_est = T_ref - dT_seg
                    T_ref_eff = (T_ref + T_out_est) / 2.0
                else:
                    T_ref_eff = T_ref
            else:
                T_ref_eff = T_sat_K  # two-phase: T_sat constant

            if inp.mode == "evap":
                dT = T_air - T_ref_eff
            else:
                dT = T_ref_eff - T_air

            Q_air = UA * dT if dT > 0 else 0

            # --- Wet surface: additional latent heat ---
            Q_lat = 0
            if is_wet and inp.mode == "evap":
                Ws_wall = self.air.Ws_from_T(T_w, inp.P_atm)
                if W_air > Ws_wall:
                    h_fg_w = 2501000.0
                    Q_lat = eta_o * h_o * A_o_seg * h_fg_w * (W_air - Ws_wall) / 1006.0
                    Q_lat = max(Q_lat, 0)

            Q_total_seg = Q_air + Q_lat

            # --- Update T_wall ---
            T_w_new = T_ref_eff + Q_total_seg * R_i if inp.mode == "evap" else T_ref_eff - Q_total_seg * R_i
            T_w_calc = alpha * T_w_new + (1 - alpha) * T_w

            # Convergence check
            dT_w = abs(T_w_calc - T_w)
            dQ = abs(Q_total_seg - Q_prev)

            T_w = T_w_calc
            Q_prev = Q_total_seg

            # Re-check wet condition
            is_wet = (T_w < T_dp) and (inp.mode == "evap")

            if dT_w < inp.tol_T and dQ < inp.tol_Q:
                sr.converged = True
                sr.n_iter = iteration + 1
                break

        sr.Q = Q_total_seg
        sr.Q_sensible = Q_air
        sr.Q_latent = Q_lat
        sr.T_wall = T_w
        sr.T_air_local = T_air
        sr.T_ref = T_ref_eff
        sr.x_ref = x_ref
        sr.h_i = h_i
        sr.h_o = h_o
        sr.eta_o = eta_o
        sr.is_wet = is_wet

        return sr

    def _compute_h_o(self, G_air: float, T_air: float) -> float:
        """Compute air-side HTC using selected j-factor correlation."""
        inp = self.inp
        mu = self.air.mu_air(T_air)
        Pr = self.air.Pr_air(T_air)
        cp = 1006.0

        corr_id = self.corr["air_j"]

        if inp.hx_type == "FT":
            spec = inp.ft_spec
            Dc = self.geo.Dc
            Re_Dc = G_air * Dc / mu

            j = compute_j_factor(
                corr_id,
                Re_Dc=Re_Dc, Nr=spec.Nr, Dc=Dc,
                Pt=spec.Pt, Pl=spec.Pl, FPI=spec.FPI,
                fin_thickness=spec.fin_thickness,
                # Wavy params
                Xa=spec.wavy_amplitude, wave_length=spec.wavy_wavelength,
                # Louver params
                Lp=spec.louver_pitch, theta=spec.louver_angle,
                # Slit params
                slit_height=spec.slit_height, slit_width=spec.slit_width,
                n_slits=spec.n_slits,
            )
        else:  # MCHX
            spec = inp.mchx_spec
            Re_Lp = G_air * spec.louver_pitch / mu
            j = compute_j_factor(
                corr_id,
                Re_Lp=Re_Lp, Lp=spec.louver_pitch,
                theta=spec.louver_angle, Fp=spec.fin_pitch,
                fin_thickness=spec.fin_thickness,
                Fl=spec.fin_height, Td=spec.D,
            )

        h_o = j * G_air * cp / Pr ** (2 / 3)
        return max(h_o, 10.0)

    def _compute_b_factor(self, T_wall: float, T_air: float, W_air: float,
                          h_o: float) -> float:
        """
        Compute b-factor for wet surface at T_fin_avg.
        b = cp_s/cp_a = 1 + h_fg × (dWs/dT) / cp_air
        Iterative: T_fin_avg → b → η_wet → T_fin_avg (3 iterations)
        """
        cp_air = 1006.0
        h_fg = 2501000.0

        # Initial dry fin efficiency for T_fin estimate
        if self.inp.hx_type == "FT":
            _, eta_dry = self.geo.fin_efficiency_schmidt(h_o)
        else:
            _, eta_dry = self.geo.fin_efficiency_straight(h_o)

        T_fin = T_air - eta_dry * (T_air - T_wall)

        for _ in range(3):
            T_fin = max(T_fin, 250.0)
            T_fin = min(T_fin, 370.0)
            dWs_dT = self.air.dWs_dT(T_fin)
            b = 1.0 + h_fg * dWs_dT / cp_air
            b = max(b, 1.0)

            # Recompute fin temp with wet efficiency
            if self.inp.hx_type == "FT":
                _, eta_wet = self.geo.fin_efficiency_wet(h_o, b)
            else:
                _, eta_wet = self.geo.fin_efficiency_wet_straight(h_o, b)

            T_fin = T_air - eta_wet * (T_air - T_wall)

        return b

    def _compute_dp_air(self, G_air: float, T_in: float, T_out: float,
                        W_in: float = 0.01, W_out: float = 0.01,
                        T_dp: float = 273.15) -> float:
        """
        Air-side pressure drop — Kays & London (1984) formulation.
        Uses f-factor from registry (auto or manual selection).
        
        한계 #7 해결: W (humidity ratio) 전달받아 실제 운전 조건 ρ 계산
        한계 #8 해결: Wet coil 보정 — 핀 표면 응축 시 dP 10~30% 증가
                     (Korte & Jacobi 2001, McLaughlin 2005)
        """
        inp = self.inp
        T_avg = (T_in + T_out) / 2
        W_avg = (W_in + W_out) / 2
        mu = self.air.mu_air(T_avg)
        # 한계 #7 — 실제 W 사용 (기존: hardcoded 0.01)
        rho_in = self.air.rho_air(T_in, W_in)
        rho_out = self.air.rho_air(T_out, W_out)
        rho_m = (rho_in + rho_out) / 2

        if inp.hx_type == "FT":
            spec = inp.ft_spec
            Dc = self.geo.Dc
            Re_Dc = G_air * Dc / mu
            sigma = self.geo.sigma

            # Determine f-factor correlation
            f_corr_id = getattr(self, '_f_corr_id', None)
            if not f_corr_id:
                # Auto-select default based on fin type
                fin_type_map = {
                    "plain": "f_wang2000_plain",
                    "wavy": "f_wang1999_wavy",
                    "slit": "f_wang2001_slit",
                    "louver": "f_louver_enhanced",
                }
                f_corr_id = fin_type_map.get(spec.fin_type, "f_wang2000_plain")

            # Build kwargs for the correlation
            f_kwargs = dict(
                Re_Dc=Re_Dc, Nr=spec.Nr, Dc=Dc,
                Pt=spec.Pt, Pl=spec.Pl, FPI=spec.FPI,
                fin_thickness=spec.fin_thickness,
                Xa=spec.wavy_amplitude, wave_length=spec.wavy_wavelength,
                slit_height=spec.slit_height, slit_width=spec.slit_width,
                n_slits=spec.n_slits,
                Lp=spec.louver_pitch, theta=spec.louver_angle,
                Ao_Ac=self.geo.A_total / self.geo.A_c if self.geo.A_c > 0 else 200,
            )

            try:
                f = compute_f_factor(f_corr_id, **f_kwargs)
            except Exception:
                # Fallback to plain
                f = compute_f_factor("f_wang2000_plain", **f_kwargs)

            # Store used f-correlation info
            self.corr["air_f"] = f_corr_id
            self.corr["f_value"] = round(f, 6)
            self.corr["Re_Dc_f"] = round(Re_Dc, 1)

            A_ratio = self.geo.A_total / self.geo.A_c if self.geo.A_c > 0 else 10
            # 한계 #10 — Kc, Ke edge type별 (Kays-London Fig. 5-2)
            edge_type = getattr(spec, 'edge_type', 'sharp')
            if edge_type == 'rounded':
                Kc_factor = 0.10  # rounded edge (Kc 약 25% of sharp)
                Ke_factor = 0.10  # 동일 방식 보정
            elif edge_type == 'chamfered':
                Kc_factor = 0.05  # chamfered edge (가장 작음)
                Ke_factor = 0.05
            else:  # sharp
                Kc_factor = 0.42
                Ke_factor = 1.0  # 원식 그대로
            
            Kc = Kc_factor * (1 - sigma ** 2)
            if edge_type == 'sharp':
                Ke = max((1 - sigma ** 2 - 0.4 * (1 - sigma ** 2) ** 1.25), 0.0)
            else:
                # Rounded/chamfered: Ke도 낮음 (entry 회복 효과)
                Ke = max(Ke_factor * (1 - sigma ** 2), 0.0)
            self.corr["edge_type"] = edge_type

        else:
            spec = inp.mchx_spec
            Re_Lp = G_air * spec.louver_pitch / mu

            f_corr_id = getattr(self, '_f_corr_id', None)
            if not f_corr_id:
                f_corr_id = "f_chang_wang1997_mchx"

            f_kwargs = dict(
                Re_Lp=Re_Lp, Lp=spec.louver_pitch,
                theta=spec.louver_angle, Fp=spec.fin_pitch,
            )

            try:
                f = compute_f_factor(f_corr_id, **f_kwargs)
            except Exception:
                f = compute_f_factor("f_chang_wang1997_mchx", **f_kwargs)

            self.corr["air_f"] = f_corr_id
            self.corr["f_value"] = round(f, 6)

            sigma = self.geo.sigma
            A_ratio = self.geo.A_total / self.geo.A_c if self.geo.A_c > 0 else 10
            # MCHX는 louver fin — sharp edge가 학계 표준 (Chang-Wang 1997)
            Kc = 0.42 * (1 - sigma ** 2)
            Ke = max((1 - sigma ** 2 - 0.4 * (1 - sigma ** 2) ** 1.25), 0.0)
            self.corr["edge_type"] = "sharp (MCHX louver)"

        # Apply correction factor to f
        f *= inp.cf_f

        # 한계 #8 — Wet coil correction
        # Korte & Jacobi (2001) Int. J. Refrigeration: wet coil은 dry 대비 dP 1.1~1.3배.
        # 정확한 판정: segment 단위 is_wet의 비율로 wet fraction 계산.
        # Wet fraction을 사용하여 보간된 보정 factor 적용.
        # max factor는 inp.wet_dp_max로 사용자 보정 가능 (default 1.20)
        wet_correction = 1.0
        wet_dp_max = getattr(inp, 'wet_dp_max', 1.20)
        if inp.mode == "evap" and hasattr(self, '_wet_fraction'):
            wet_frac = max(0.0, min(1.0, self._wet_fraction))
            # Linear interpolation between dry (1.0) and wet (wet_dp_max)
            wet_correction = 1.0 + (wet_dp_max - 1.0) * wet_frac
        elif inp.mode == "evap" and T_avg < T_dp:
            # Fallback: T_avg < T_dp이면 wet 가정 (보수적)
            wet_correction = wet_dp_max
        f *= wet_correction
        if wet_correction > 1.001:
            self.corr["wet_dp_factor"] = round(wet_correction, 3)

        # Kays & London full pressure drop
        dp = G_air ** 2 / (2 * rho_in) * (
            Kc +
            (1 + sigma ** 2) * (rho_in / rho_out - 1) +
            f * A_ratio * (rho_in / rho_m) -
            Ke * (rho_in / rho_out)
        )
        return max(dp, 0.0)
