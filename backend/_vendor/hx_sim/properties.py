"""
Refrigerant & Air Property Module
CoolProp wrapper with caching for performance
"""
import CoolProp.CoolProp as CP
from functools import lru_cache
import math

# ============================================================
# Refrigerant Properties
# ============================================================

class RefrigerantProperties:
    """CoolProp-based refrigerant property calculator."""

    SUPPORTED = [
        "R410A", "R134a", "R32", "R290", "R1234yf",
        "R22", "R407C", "R404A", "R507A", "R513A",
        "R454C", "R454A", "R455A", "R452B", "R1234ze(E)",
    ]

    def __init__(self, fluid: str):
        if fluid not in self.SUPPORTED:
            raise ValueError(f"Unsupported refrigerant: {fluid}. Supported: {self.SUPPORTED}")
        self.fluid = fluid
        self.P_crit = CP.PropsSI("Pcrit", self.fluid)
        self.T_crit = CP.PropsSI("Tcrit", self.fluid)
        self.M = CP.PropsSI("M", self.fluid)  # molar mass [kg/mol]
        self._cache = {}  # property cache keyed by (method_name, P_rounded)

    def _cached(self, key, P, fn):
        """Cache wrapper — rounds P to 1 Pa to avoid float issues."""
        P_r = round(P, 0)
        ck = (key, P_r)
        if ck not in self._cache:
            self._cache[ck] = fn()
        return self._cache[ck]

    # ------ saturation ------
    def T_sat(self, P: float) -> float:
        return self._cached("T_sat", P, lambda: CP.PropsSI("T", "P", P, "Q", 0, self.fluid))

    def P_sat(self, T: float) -> float:
        return CP.PropsSI("P", "T", T, "Q", 0, self.fluid)

    # ------ two-phase ------
    def h_fg(self, P: float) -> float:
        return self._cached("h_fg", P, lambda: (
            CP.PropsSI("H", "P", P, "Q", 1, self.fluid) -
            CP.PropsSI("H", "P", P, "Q", 0, self.fluid)))

    def rho_l(self, P: float) -> float:
        return self._cached("rho_l", P, lambda: CP.PropsSI("D", "P", P, "Q", 0, self.fluid))

    def rho_v(self, P: float) -> float:
        return self._cached("rho_v", P, lambda: CP.PropsSI("D", "P", P, "Q", 1, self.fluid))

    def mu_l(self, P: float) -> float:
        return self._cached("mu_l", P, lambda: CP.PropsSI("V", "P", P, "Q", 0, self.fluid))

    def mu_v(self, P: float) -> float:
        return self._cached("mu_v", P, lambda: CP.PropsSI("V", "P", P, "Q", 1, self.fluid))

    def k_l(self, P: float) -> float:
        return self._cached("k_l", P, lambda: CP.PropsSI("L", "P", P, "Q", 0, self.fluid))

    def k_v(self, P: float) -> float:
        return self._cached("k_v", P, lambda: CP.PropsSI("L", "P", P, "Q", 1, self.fluid))

    def cp_l(self, P: float) -> float:
        return self._cached("cp_l", P, lambda: CP.PropsSI("C", "P", P, "Q", 0, self.fluid))

    def cp_v(self, P: float) -> float:
        return self._cached("cp_v", P, lambda: CP.PropsSI("C", "P", P, "Q", 1, self.fluid))

    def Pr_l(self, P: float) -> float:
        return self._cached("Pr_l", P, lambda: CP.PropsSI("Prandtl", "P", P, "Q", 0, self.fluid))

    def Pr_v(self, P: float) -> float:
        return self._cached("Pr_v", P, lambda: CP.PropsSI("Prandtl", "P", P, "Q", 1, self.fluid))

    def sigma(self, P: float) -> float:
        return self._cached("sigma", P, lambda: CP.PropsSI("I", "P", P, "Q", 0, self.fluid))

    def P_r(self, P: float) -> float:
        """Reduced pressure P/P_crit."""
        return P / self.P_crit

    # ------ single-phase ------
    def props_single(self, T: float, P: float) -> dict:
        """Single-phase properties at T [K], P [Pa]."""
        ck = ("props_single", round(T, 1), round(P, 0))
        if ck not in self._cache:
            self._cache[ck] = {
                "rho": CP.PropsSI("D", "T", T, "P", P, self.fluid),
                "mu": CP.PropsSI("V", "T", T, "P", P, self.fluid),
                "k": CP.PropsSI("L", "T", T, "P", P, self.fluid),
                "cp": CP.PropsSI("C", "T", T, "P", P, self.fluid),
                "Pr": CP.PropsSI("Prandtl", "T", T, "P", P, self.fluid),
                "h": CP.PropsSI("H", "T", T, "P", P, self.fluid),
            }
        return self._cache[ck]

    # ------ Lockhart-Martinelli parameter ------
    def Xtt(self, x: float, P: float) -> float:
        """Lockhart-Martinelli parameter."""
        if x <= 0.001:
            return 1e6
        if x >= 0.999:
            return 1e-6
        rho_l = self.rho_l(P)
        rho_v = self.rho_v(P)
        mu_l = self.mu_l(P)
        mu_v = self.mu_v(P)
        return ((1 - x) / x) ** 0.9 * (rho_v / rho_l) ** 0.5 * (mu_l / mu_v) ** 0.1


# ============================================================
# Moist Air Properties (psychrometrics)
# ============================================================

class MoistAirProperties:
    """Moist air property calculations using CoolProp HAPropsSI."""

    @staticmethod
    def W_from_TRH(T_db: float, RH: float, P_atm: float = 101325.0) -> float:
        """Humidity ratio [kg_w/kg_da] from T_db [K] and RH [0-1]."""
        return CP.HAPropsSI("W", "T", T_db, "R", RH, "P", P_atm)

    @staticmethod
    def h_from_TW(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Enthalpy [J/kg_da] from T_db [K] and W [kg/kg]."""
        return CP.HAPropsSI("H", "T", T_db, "W", W, "P", P_atm)

    @staticmethod
    def T_from_hW(h: float, W: float, P_atm: float = 101325.0) -> float:
        """T_db [K] from enthalpy and humidity ratio."""
        return CP.HAPropsSI("T", "H", h, "W", W, "P", P_atm)

    @staticmethod
    def Tdp_from_TW(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Dew point temperature [K]."""
        return CP.HAPropsSI("D", "T", T_db, "W", W, "P", P_atm)

    @staticmethod
    def Ws_from_T(T: float, P_atm: float = 101325.0) -> float:
        """Saturated humidity ratio at temperature T [K]."""
        return CP.HAPropsSI("W", "T", T, "R", 1.0, "P", P_atm)

    @staticmethod
    def cp_air(T_db: float, W: float) -> float:
        """Specific heat of moist air [J/(kg_da·K)]."""
        return 1006.0 + 1860.0 * W

    @staticmethod
    def h_simple(T_db: float, W: float) -> float:
        """Simplified enthalpy [J/kg_da]: h = cp_a*(T-273.15) + W*(2501000 + 1860*(T-273.15))."""
        T_c = T_db - 273.15
        return 1006.0 * T_c + W * (2501000.0 + 1860.0 * T_c)

    @staticmethod
    def T_from_h_simple(h: float, W: float) -> float:
        """Inverse of h_simple → T_db [K]."""
        T_c = (h - W * 2501000.0) / (1006.0 + W * 1860.0)
        return T_c + 273.15

    @staticmethod
    def dWs_dT(T: float, P_atm: float = 101325.0) -> float:
        """dWs/dT at temperature T [K], central difference."""
        dT = 0.5  # K
        Ws_plus = CP.HAPropsSI("W", "T", T + dT, "R", 1.0, "P", P_atm)
        Ws_minus = CP.HAPropsSI("W", "T", T - dT, "R", 1.0, "P", P_atm)
        return (Ws_plus - Ws_minus) / (2 * dT)

    @staticmethod
    def rho_air(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Moist air density [kg/m³]."""
        R_da = 287.058
        T = T_db
        rho_da = P_atm / (R_da * T * (1 + 1.6078 * W))
        return rho_da * (1 + W)

    @staticmethod
    def mu_air(T: float) -> float:
        """Dynamic viscosity of air [Pa·s], Sutherland's law."""
        return 1.716e-5 * (T / 273.15) ** 1.5 * (273.15 + 110.4) / (T + 110.4)

    @staticmethod
    def k_air(T: float) -> float:
        """Thermal conductivity of air [W/(m·K)]."""
        return 0.0241 * (T / 273.15) ** 0.81

    @staticmethod
    def Pr_air(T: float) -> float:
        """Prandtl number of air."""
        return 0.71  # approximately constant
