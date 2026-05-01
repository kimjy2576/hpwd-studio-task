"""
Heat Exchanger Geometry Models
FT-HX (Plate Fin-and-Tube) and MCHX (Micro-Channel)
"""
import math
from dataclasses import dataclass, field
from typing import Literal


# ============================================================
# FT-HX Geometry
# ============================================================

@dataclass
class FinTubeSpec:
    """Plate fin-and-tube heat exchanger specification."""
    # Overall dimensions [m]
    W: float = 0.5          # width (tube length direction)
    H: float = 0.3          # height (air flow face height)
    D: float = 0.08         # depth (air flow direction)

    # Tube specs
    Do: float = 0.00952     # outer diameter [m] (3/8 inch)
    Di: float = 0.00822     # inner diameter [m]
    Pt: float = 0.0254      # transverse pitch [m] (1 inch)
    Pl: float = 0.022       # longitudinal pitch [m]
    Nr: int = 4             # number of rows (air direction)
    Nt: int = 12            # number of tubes per row
    layout: Literal["staggered", "inline"] = "staggered"

    # Fin specs
    FPI: float = 14.0       # fins per inch
    fin_thickness: float = 0.00012  # [m]
    fin_type: Literal["plain", "wavy", "louver", "slit"] = "plain"
    k_fin: float = 200.0    # fin thermal conductivity [W/(m·K)] (aluminum)

    # Wavy fin extra
    wavy_amplitude: float = 0.001  # Xa [m] — wave amplitude (half peak-to-peak)
    wavy_wavelength: float = 0.01  # λ [m] — wave wavelength

    # Louver fin extra
    louver_pitch: float = 0.0017   # Lp [m]
    louver_angle: float = 27.0     # θ [degrees]

    # Slit fin extra
    slit_height: float = 0.001     # Ss [m] — slit height
    slit_width: float = 0.002      # Sh [m] — slit width
    n_slits: int = 6               # number of slits per fin row

    # Number of segments per tube
    # Default 10 — N_seg=5는 정확도 borderline (T_ref가 segment 내 inlet 가정).
    # 진영님 검토 결과 default 상향 (감소된 segment 길이 → in/out average 가정 유효).
    N_seg: int = 10

    # 한계 #10 — Kc, Ke edge type (Kays-London Fig. 5-2):
    #   "sharp"     — abrupt sharp edge (Kc=0.42), 보수적
    #   "rounded"   — rounded edge (Kc=0.10), 일반 fin-tube
    #   "chamfered" — chamfered edge (Kc=0.05), 최소
    # 기본값 sharp (학계 default, 보수적).
    # 실 코일은 보통 rounded — 사용자가 명시 권장.
    edge_type: Literal["sharp", "rounded", "chamfered"] = "sharp"

    # Circuiting
    circuit_mode: str = "row_parallel"  # row_parallel, serpentine_2, serpentine_4, single, custom
    circuits: list = field(default_factory=list)  # custom: list of circuits, each = list of [row, col]


def generate_circuits(Nr: int, Nt: int, mode: str, flow_arr: str = "counter") -> list:
    """
    Generate circuit definitions for FT-HX.
    Each circuit = ordered list of [row, col] tube-passes.
    Refrigerant flows through them sequentially.

    Modes:
      row_parallel — each column is independent circuit (Nt circuits)
      serpentine_2 — pair 2 adjacent columns per circuit (Nt/2 circuits)
      serpentine_4 — group 4 columns per circuit (Nt/4 circuits)
      single       — all tubes in one circuit
    """
    counter = (flow_arr == "counter")

    if mode == "single":
        # One big serpentine through all columns
        circuit = []
        for col in range(Nt):
            if (col % 2 == 0) == counter:
                rows = list(range(Nr - 1, -1, -1))
            else:
                rows = list(range(Nr))
            for r in rows:
                circuit.append([r, col])
        return [circuit]

    elif mode.startswith("serpentine"):
        # Extract group size from mode name
        try:
            grp = int(mode.split("_")[1])
        except (IndexError, ValueError):
            grp = 2
        grp = max(1, min(grp, Nt))
        n_circ = max(1, Nt // grp)
        circuits = []
        for c in range(n_circ):
            cols_start = c * grp
            cols = list(range(cols_start, min(cols_start + grp, Nt)))
            circuit = []
            for i, col in enumerate(cols):
                if (i % 2 == 0) == counter:
                    rows = list(range(Nr - 1, -1, -1))
                else:
                    rows = list(range(Nr))
                for r in rows:
                    circuit.append([r, col])
            circuits.append(circuit)
        # Handle remaining tubes
        remaining = list(range(n_circ * grp, Nt))
        if remaining:
            circuit = []
            for i, col in enumerate(remaining):
                if (i % 2 == 0) == counter:
                    rows = list(range(Nr - 1, -1, -1))
                else:
                    rows = list(range(Nr))
                for r in rows:
                    circuit.append([r, col])
            circuits.append(circuit)
        return circuits

    else:
        # row_parallel (default) — each column is one circuit
        circuits = []
        for col in range(Nt):
            if counter:
                circuit = [[r, col] for r in range(Nr - 1, -1, -1)]
            else:
                circuit = [[r, col] for r in range(Nr)]
            circuits.append(circuit)
        return circuits


@dataclass
class FinTubeGeo:
    """Computed FT-HX geometry quantities."""
    spec: FinTubeSpec = None

    # Computed
    A_total: float = 0.0     # total air-side area [m²]
    A_fin: float = 0.0       # fin area [m²]
    A_tube_ext: float = 0.0  # external tube area (between fins) [m²]
    A_i: float = 0.0         # internal (refrigerant-side) area [m²]
    A_fr: float = 0.0        # frontal area [m²]
    A_c: float = 0.0         # minimum free-flow area [m²]
    sigma: float = 0.0       # A_c / A_fr
    Dh: float = 0.0          # air-side hydraulic diameter [m]
    Dc: float = 0.0          # collar diameter [m]
    N_tubes: int = 0
    N_fins: int = 0
    L_tube: float = 0.0

    # Per-segment
    A_i_seg: float = 0.0     # internal area per segment
    L_seg: float = 0.0       # tube length per segment

    # Schmidt equivalent parameters
    Xm: float = 0.0
    XL: float = 0.0

    @classmethod
    def from_spec(cls, s: FinTubeSpec) -> "FinTubeGeo":
        g = cls(spec=s)

        g.Dc = s.Do + 2 * s.fin_thickness  # collar diameter
        g.N_tubes = s.Nr * s.Nt
        g.L_tube = s.W
        fin_pitch = 0.0254 / s.FPI  # [m]
        # 한계 #5 — int() 절삭 대신 round (실제 핀 수에 더 가까움, ±0.5% 정확도 ↑)
        g.N_fins = int(round(s.W / fin_pitch))
        gap = fin_pitch - s.fin_thickness

        # Frontal area: face perpendicular to air flow (H × W)
        g.A_fr = s.H * s.W

        # Schmidt equivalent radius parameters
        if s.layout == "staggered":
            g.Xm = s.Pt / 2.0
            diag = math.sqrt((s.Pt / 2) ** 2 + s.Pl ** 2)
            g.XL = diag / 2.0
        else:
            g.Xm = s.Pt / 2.0
            g.XL = s.Pl / 2.0

        # Total air-side area
        # Each fin plate spans H × D
        A_plate = s.H * s.D
        tube_hole_area = g.N_tubes * math.pi * g.Dc ** 2 / 4
        A_one_fin = 2 * (A_plate - tube_hole_area)
        g.A_fin = g.N_fins * A_one_fin

        # Tube external area between fins
        g.A_tube_ext = g.N_tubes * math.pi * g.Dc * g.N_fins * gap

        g.A_total = g.A_fin + g.A_tube_ext

        # Internal area (heat transfer area)
        # 한계 #6 — U-bend 길이는 의도적으로 제외함:
        #   U-bend 영역은 fin이 없어 air-side HTC ≈ 0 → heat transfer 기여 거의 없음.
        #   단순히 A_i 늘리면 Q 과대평가. 학계 표준 처리: 직선 튜브 영역만 A_i,
        #   U-bend 효과는 dP에 bend loss로 추가 (compute_dp_ref_seg 외부에서).
        g.A_i = math.pi * s.Di * s.W * g.N_tubes

        # Minimum free-flow area
        # σ = (Pt - Dc)(Fp - δ) / (Pt × Fp)
        g.sigma = (s.Pt - g.Dc) * gap / (s.Pt * fin_pitch)
        g.sigma = max(g.sigma, 0.1)
        g.A_c = g.sigma * g.A_fr

        # Hydraulic diameter
        if g.A_total > 0:
            g.Dh = 4 * g.A_c * s.D / g.A_total
        else:
            g.Dh = s.Di

        # Per-segment values
        g.L_seg = s.W / s.N_seg
        g.A_i_seg = math.pi * s.Di * g.L_seg

        return g

    def fin_efficiency_schmidt(self, h_o: float) -> tuple:
        """
        Schmidt equivalent circular fin efficiency.
        Returns (eta_fin, eta_o).
        """
        s = self.spec
        r_i = self.Dc / 2.0  # collar radius
        r_eq_ratio = 1.27 * (self.Xm / r_i) * math.sqrt(self.XL / self.Xm - 0.3)
        r_eq_ratio = max(r_eq_ratio, 1.0)
        r_eq = r_eq_ratio * r_i

        phi = (r_eq / r_i - 1) * (1 + 0.35 * math.log(max(r_eq / r_i, 1.001)))

        m = math.sqrt(2 * h_o / (s.k_fin * s.fin_thickness))
        mr_phi = m * r_i * phi

        if mr_phi > 0.01:
            eta_fin = math.tanh(mr_phi) / mr_phi
        else:
            eta_fin = 1.0

        A_fin_ratio = self.A_fin / self.A_total if self.A_total > 0 else 0.9
        eta_o = 1 - A_fin_ratio * (1 - eta_fin)

        return eta_fin, eta_o

    def fin_efficiency_wet(self, h_o: float, b: float) -> tuple:
        """
        Wet-surface fin efficiency.
        b = cp_s/cp_a (b-factor from wet surface model).
        Only affects η_fin calculation, NOT h_o or UA.
        """
        s = self.spec
        r_i = self.Dc / 2.0
        r_eq_ratio = 1.27 * (self.Xm / r_i) * math.sqrt(self.XL / self.Xm - 0.3)
        r_eq_ratio = max(r_eq_ratio, 1.0)
        r_eq = r_eq_ratio * r_i

        phi = (r_eq / r_i - 1) * (1 + 0.35 * math.log(max(r_eq / r_i, 1.001)))

        # Wet fin: m_wet uses b factor
        m_wet = math.sqrt(2 * h_o * b / (s.k_fin * s.fin_thickness))
        mr_phi = m_wet * r_i * phi

        if mr_phi > 0.01:
            eta_fin_wet = math.tanh(mr_phi) / mr_phi
        else:
            eta_fin_wet = 1.0

        A_fin_ratio = self.A_fin / self.A_total if self.A_total > 0 else 0.9
        eta_o_wet = 1 - A_fin_ratio * (1 - eta_fin_wet)

        return eta_fin_wet, eta_o_wet


# ============================================================
# MCHX Geometry
# ============================================================

@dataclass
class MCHXSpec:
    """Micro-channel heat exchanger specification."""
    # Overall dimensions [m]
    W: float = 0.6          # width (header-to-header)
    H: float = 0.4          # height (air face height)
    D: float = 0.020        # depth (air flow direction, single slab)

    # Slab
    Nr: int = 1              # rows (air flow direction, slabs)

    # Channel
    ch_width: float = 0.001    # [m]
    ch_height: float = 0.0015  # [m]
    ch_wall: float = 0.0003    # wall between channels [m]
    n_ports: int = 12          # number of parallel ports per tube

    # Tube
    tube_height: float = 0.002  # flat tube height [m]
    tube_pitch: float = 0.010   # tube-to-tube pitch [m]

    # Louver fin
    louver_pitch: float = 0.0013   # Lp [m]
    louver_angle: float = 27.0     # θ [degrees]
    fin_pitch: float = 0.0014      # Fp [m]
    fin_thickness: float = 0.0001  # δ_fin [m]
    fin_height: float = 0.008      # fin height [m]
    k_fin: float = 200.0           # [W/(m·K)]

    N_seg: int = 10
    Nt: int = 40             # columns (height direction, tubes)

    # Multi-pass (from baffle design)
    passes: list = field(default_factory=list)  # [[tube_indices], ...] per pass, empty = all parallel
    pass_slabs: list = field(default_factory=list)  # [slab_idx, ...] per pass


@dataclass
class MCHXGeo:
    """Computed MCHX geometry."""
    spec: MCHXSpec = None

    Dh_ref: float = 0.0     # refrigerant hydraulic diameter [m]
    Dh_air: float = 0.0     # air-side hydraulic diameter [m]
    A_i: float = 0.0        # total internal area [m²]
    A_total: float = 0.0    # total air-side area [m²]
    A_fin: float = 0.0
    A_fr: float = 0.0       # frontal area
    A_c: float = 0.0        # minimum free-flow area
    sigma: float = 0.0
    N_ch: int = 0            # total channels
    A_i_seg: float = 0.0
    L_seg: float = 0.0
    n_ports_total: int = 0

    @classmethod
    def from_spec(cls, s: MCHXSpec) -> "MCHXGeo":
        g = cls(spec=s)

        # Refrigerant hydraulic diameter
        g.Dh_ref = 2 * s.ch_width * s.ch_height / (s.ch_width + s.ch_height)

        # Number of channels total
        g.N_ch = s.Nt * s.n_ports
        g.n_ports_total = g.N_ch

        # Internal area per channel
        perimeter_ch = 2 * (s.ch_width + s.ch_height)
        A_i_per_ch = perimeter_ch * s.W  # per channel
        g.A_i = A_i_per_ch * g.N_ch * s.Nr

        # Air-side geometry — frontal area is face perpendicular to air flow
        g.A_fr = s.H * s.W

        # Fin area (louver fin between tubes)
        n_fins_per_tube_gap = int((s.W) / s.fin_pitch)
        fin_area_one = 2 * s.fin_height * s.D  # two sides
        g.A_fin = n_fins_per_tube_gap * fin_area_one * (s.Nt - 1) * s.Nr

        # Tube external area
        tube_ext = 2 * s.W * s.tube_height * s.Nt * s.Nr
        g.A_total = g.A_fin + tube_ext

        # Minimum free-flow area
        fin_blockage = n_fins_per_tube_gap * s.fin_thickness * s.fin_height
        g.A_c = s.H * s.D * s.Nr - s.Nt * s.tube_height * s.D * s.Nr - fin_blockage * s.Nr
        g.A_c = max(g.A_c, g.A_fr * 0.3)
        g.sigma = g.A_c / g.A_fr if g.A_fr > 0 else 0.5

        # Air-side hydraulic diameter
        if g.A_total > 0:
            g.Dh_air = 4 * g.A_c * s.D * s.Nr / g.A_total
        else:
            g.Dh_air = 0.003

        # Per-segment
        g.L_seg = s.W / s.N_seg
        g.A_i_seg = perimeter_ch * g.L_seg * s.n_ports  # per tube, all ports

        return g

    def fin_efficiency_straight(self, h_o: float) -> tuple:
        """Straight fin efficiency η = tanh(mL)/(mL)."""
        s = self.spec
        m = math.sqrt(2 * h_o / (s.k_fin * s.fin_thickness))
        mL = m * s.fin_height / 2

        if mL > 0.01:
            eta_fin = math.tanh(mL) / mL
        else:
            eta_fin = 1.0

        A_fin_ratio = self.A_fin / self.A_total if self.A_total > 0 else 0.8
        eta_o = 1 - A_fin_ratio * (1 - eta_fin)

        return eta_fin, eta_o

    def fin_efficiency_wet_straight(self, h_o: float, b: float) -> tuple:
        """Wet straight fin efficiency."""
        s = self.spec
        m_wet = math.sqrt(2 * h_o * b / (s.k_fin * s.fin_thickness))
        mL = m_wet * s.fin_height / 2

        if mL > 0.01:
            eta_fin = math.tanh(mL) / mL
        else:
            eta_fin = 1.0

        A_fin_ratio = self.A_fin / self.A_total if self.A_total > 0 else 0.8
        eta_o_wet = 1 - A_fin_ratio * (1 - eta_fin)

        return eta_fin, eta_o_wet
