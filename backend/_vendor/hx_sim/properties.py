"""
Refrigerant & Air Property Module
CoolProp wrapper with caching for performance
"""
import CoolProp.CoolProp as CP
from functools import lru_cache
import math

# ============================================================
# 전역 물성 캐시 (프로세스 수명 유지 — step/outer 간 재사용)
# ============================================================
# 인스턴스별 self._cache는 HXSolver가 step마다 재생성되어 리셋됨.
# 물성은 (fluid, 물성종류, 양자화P/T)의 순수 함수이므로 전역 캐시 안전:
# 같은 입력 → 항상 같은 CoolProp 출력. 양자화 덕에 키 종류가 제한적
# (P 1kPa 단위, T 0.2K 단위)이라 무한 증가하지 않음. 만일을 대비해
# 크기 상한(_GCACHE_MAX)에서 가장 오래된 항목부터 정리.
_GCACHE: dict = {}          # {(fluid, key, P_q[, T_q]): value|dict}
_GCACHE_MAX = 200_000       # 항목 상한 (양자화로 실제론 훨씬 적음)


def _gcache_get(ck):
    return _GCACHE.get(ck)


def _gcache_put(ck, val):
    if len(_GCACHE) >= _GCACHE_MAX:
        # 초과 시 앞쪽(오래된) 10% 제거 — dict는 삽입순 유지(3.7+)
        for k in list(_GCACHE.keys())[:_GCACHE_MAX // 10]:
            _GCACHE.pop(k, None)
    _GCACHE[ck] = val
    return val


def clear_property_cache():
    """전역 물성 캐시 비우기 (테스트/벤치마크용)."""
    _GCACHE.clear()


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
        # ── 캐시 양자화 해상도 (성능) ──────────────────────────────
        # HX 셀별로 압력강하(셀당 ~1.6kPa)로 P가 미세하게 달라 캐시 미스가
        # 잦음. 포화물성은 압력에, 단상물성은 온도에 매우 둔감하므로
        # 캐시 키를 양자화하면 인접 셀이 같은 키를 공유해 CoolProp 호출↓.
        # 검증(R290): P 1kPa 양자화 → T_sat 20mK/rho_l 0.006%/h_fg 0.011%,
        #             T 0.2K 양자화 → rho 0.046%/cp 0.007%/mu 0.029%.
        # 모두 <0.05% (N_seg 축소 0.1~0.5%보다 작음). ground-truth 물성값
        # 자체는 불변 — 양자화된 P/T 지점에서 CoolProp을 정확히 호출.
        # 되돌리려면 P_cache_res=1.0, T_cache_res=0.1로 설정 (기존 동작).
        self.P_cache_res = 1000.0   # 포화물성 P 양자화 [Pa] (1kPa)
        self.T_cache_res = 0.2      # 단상물성 T 양자화 [K]

    def _cached(self, key, P, fn):
        """Cache wrapper — P를 P_cache_res로 양자화, 전역 캐시 사용.

        키에 fluid 포함 → 여러 냉매 혼용 안전. 양자화된 대표 P_q에서
        fn(P_q) 호출 → 같은 구간 셀은 동일 지점 값 재사용 (일관성).
        전역 캐시라 step/outer 간에도 유지 (인스턴스 재생성 무관).
        P_cache_res=1이면 기존 동작(1Pa)과 사실상 동일.
        """
        res = getattr(self, 'P_cache_res', 1.0)
        P_q = round(P / res) * res
        ck = (self.fluid, key, P_q)
        v = _gcache_get(ck)
        if v is None:
            v = _gcache_put(ck, fn(P_q))
        return v

    # ------ saturation ------
    def T_sat(self, P: float) -> float:
        return self._cached("T_sat", P, lambda Pq: CP.PropsSI("T", "P", Pq, "Q", 0, self.fluid))

    def P_sat(self, T: float) -> float:
        return CP.PropsSI("P", "T", T, "Q", 0, self.fluid)

    # ------ two-phase ------
    def h_fg(self, P: float) -> float:
        return self._cached("h_fg", P, lambda Pq: (
            CP.PropsSI("H", "P", Pq, "Q", 1, self.fluid) -
            CP.PropsSI("H", "P", Pq, "Q", 0, self.fluid)))

    def rho_l(self, P: float) -> float:
        return self._cached("rho_l", P, lambda Pq: CP.PropsSI("D", "P", Pq, "Q", 0, self.fluid))

    def rho_v(self, P: float) -> float:
        return self._cached("rho_v", P, lambda Pq: CP.PropsSI("D", "P", Pq, "Q", 1, self.fluid))

    def mu_l(self, P: float) -> float:
        return self._cached("mu_l", P, lambda Pq: CP.PropsSI("V", "P", Pq, "Q", 0, self.fluid))

    def mu_v(self, P: float) -> float:
        return self._cached("mu_v", P, lambda Pq: CP.PropsSI("V", "P", Pq, "Q", 1, self.fluid))

    def k_l(self, P: float) -> float:
        return self._cached("k_l", P, lambda Pq: CP.PropsSI("L", "P", Pq, "Q", 0, self.fluid))

    def k_v(self, P: float) -> float:
        return self._cached("k_v", P, lambda Pq: CP.PropsSI("L", "P", Pq, "Q", 1, self.fluid))

    def cp_l(self, P: float) -> float:
        return self._cached("cp_l", P, lambda Pq: CP.PropsSI("C", "P", Pq, "Q", 0, self.fluid))

    def cp_v(self, P: float) -> float:
        return self._cached("cp_v", P, lambda Pq: CP.PropsSI("C", "P", Pq, "Q", 1, self.fluid))

    def Pr_l(self, P: float) -> float:
        return self._cached("Pr_l", P, lambda Pq: CP.PropsSI("Prandtl", "P", Pq, "Q", 0, self.fluid))

    def Pr_v(self, P: float) -> float:
        return self._cached("Pr_v", P, lambda Pq: CP.PropsSI("Prandtl", "P", Pq, "Q", 1, self.fluid))

    def sigma(self, P: float) -> float:
        return self._cached("sigma", P, lambda Pq: CP.PropsSI("I", "P", Pq, "Q", 0, self.fluid))

    def P_r(self, P: float) -> float:
        """Reduced pressure P/P_crit."""
        return P / self.P_crit

    # ------ single-phase ------
    def props_single(self, T: float, P: float) -> dict:
        """Single-phase properties at T [K], P [Pa].

        T/P 양자화 + 전역 캐시 (fluid 포함 키). 단상물성은 T에 둔감
        (T 0.2K 양자화 → rho 0.046%/cp 0.007%/mu 0.029%). step/outer 간
        재사용. 양자화된 T_q/P_q에서 CoolProp 호출.
        """
        T_res = getattr(self, 'T_cache_res', 0.1)
        P_res = getattr(self, 'P_cache_res', 1.0)
        T_q = round(T / T_res) * T_res
        P_q = round(P / P_res) * P_res
        ck = (self.fluid, "props_single", T_q, P_q)
        v = _gcache_get(ck)
        if v is None:
            v = _gcache_put(ck, {
                "rho": CP.PropsSI("D", "T", T_q, "P", P_q, self.fluid),
                "mu": CP.PropsSI("V", "T", T_q, "P", P_q, self.fluid),
                "k": CP.PropsSI("L", "T", T_q, "P", P_q, self.fluid),
                "cp": CP.PropsSI("C", "T", T_q, "P", P_q, self.fluid),
                "Pr": CP.PropsSI("Prandtl", "T", T_q, "P", P_q, self.fluid),
                "h": CP.PropsSI("H", "T", T_q, "P", P_q, self.fluid),
            })
        return v

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

# 물 증발잠열 h_fg(T) 모듈 전역 캐시 (T 0.2K 양자화).
# wet-coil 증발기가 셀별 wall T로 h_fg_water를 수천 회 호출 → 양자화 캐시로
# CoolProp Water 상태방정식 호출 급감. 양자화 T_q에서 정확히 계산 (값 불변).
_H_FG_WATER_CACHE: dict = {}


class MoistAirProperties:
    """Moist air property calculations using CoolProp HAPropsSI.
    
    진영님 audit 결과 (R290 등 다른 fluid 호환성):
      - 모든 물성을 CoolProp HAPropsSI로 통일
      - 하드코딩 (1006, 1860, 2501000, Sutherland) 제거
      - cp_air(T,W), h_simple(T,W), rho_air(T,W,P) 모두 CoolProp 사용
      - mu_air(T), k_air(T): dry air properties from CoolProp 'Air'
    """

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
    def cp_air(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Specific heat of moist air [J/(kg_da·K)] from CoolProp.
        
        진영님 audit: 기존 '1006 + 1860×W' 단순식 → CoolProp HAPropsSI('Cha').
        Cha = specific heat per kg of dry air (moist air basis).
        """
        return CP.HAPropsSI("Cha", "T", T_db, "W", W, "P", P_atm)

    @staticmethod
    def h_simple(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Enthalpy [J/kg_da] — direct CoolProp call.
        
        진영님 audit: 기존 단순식 (1006×Tc + W×2501000 + ...) → CoolProp.
        함수 이름은 'simple' 유지 (호환성), but 실제로는 정확한 CoolProp.
        """
        return CP.HAPropsSI("H", "T", T_db, "W", W, "P", P_atm)

    @staticmethod
    def T_from_h_simple(h: float, W: float, P_atm: float = 101325.0) -> float:
        """Inverse of h_simple → T_db [K], CoolProp."""
        return CP.HAPropsSI("T", "H", h, "W", W, "P", P_atm)

    @staticmethod
    def dWs_dT(T: float, P_atm: float = 101325.0) -> float:
        """dWs/dT at temperature T [K], central difference."""
        dT = 0.5  # K
        Ws_plus = CP.HAPropsSI("W", "T", T + dT, "R", 1.0, "P", P_atm)
        Ws_minus = CP.HAPropsSI("W", "T", T - dT, "R", 1.0, "P", P_atm)
        return (Ws_plus - Ws_minus) / (2 * dT)

    @staticmethod
    def rho_air(T_db: float, W: float, P_atm: float = 101325.0) -> float:
        """Moist air density [kg/m³] from CoolProp.
        
        진영님 audit: 기존 P/(R×T×(1+1.6078W)) 단순식 → CoolProp HAPropsSI.
        Vha = volume per kg of dry air → ρ_ha = (1+W)/Vha (per kg moist air)
        """
        Vha = CP.HAPropsSI("Vha", "T", T_db, "W", W, "P", P_atm)  # m³/kg moist
        return 1.0 / Vha if Vha > 0 else 1.2  # safety floor

    @staticmethod
    def mu_air(T: float, P_atm: float = 101325.0) -> float:
        """Dynamic viscosity of dry air [Pa·s] from CoolProp.
        
        진영님 audit: Sutherland 식 → CoolProp 'Air'.
        Note: dry air 가정 (W 영향 < 1%, 무시).
        """
        try:
            return CP.PropsSI("V", "T", T, "P", P_atm, "Air")
        except Exception as e:
            # 진영님 audit: silent fallback 대신 명시 raise
            raise RuntimeError(
                f"CoolProp 'Air' viscosity 호출 실패 (T={T:.1f}K, P={P_atm:.0f}Pa): {e}"
            )

    @staticmethod
    def k_air(T: float, P_atm: float = 101325.0) -> float:
        """Thermal conductivity of dry air [W/(m·K)] from CoolProp."""
        try:
            return CP.PropsSI("L", "T", T, "P", P_atm, "Air")
        except Exception as e:
            raise RuntimeError(
                f"CoolProp 'Air' conductivity 호출 실패 (T={T:.1f}K, P={P_atm:.0f}Pa): {e}"
            )

    @staticmethod
    def Pr_air(T: float, P_atm: float = 101325.0) -> float:
        """Prandtl number of dry air from CoolProp."""
        try:
            return CP.PropsSI("Prandtl", "T", T, "P", P_atm, "Air")
        except Exception as e:
            raise RuntimeError(
                f"CoolProp 'Air' Prandtl 호출 실패 (T={T:.1f}K, P={P_atm:.0f}Pa): {e}"
            )

    @staticmethod
    def h_fg_water(T: float = 273.15, P_atm: float = 101325.0) -> float:
        """Water vaporization enthalpy [J/kg] at given T from CoolProp.
        
        진영님 audit: solver.py에서 hardcoded '2501000' (water h_fg @ 0°C) 사용.
        실제로는 T에 따라 변함 (10°C 2477 kJ/kg, 50°C 2382 kJ/kg).
        wet coil에서 평균 wall T로 호출.

        성능: wet-coil 증발기는 셀별 wall T로 이 함수를 수천 회 호출
        (H|T,Q Water 2118회 = 증발기 L3 CoolProp의 75%). h_fg_water는
        온도에 완만 (0.2K 차 → 0.0194% 변화)하므로 T를 0.2K 양자화해
        모듈 전역 캐시. 양자화된 T_q에서 정확히 CoolProp 호출 (물성값 불변).
        """
        T_q = round(T / 0.2) * 0.2   # 0.2K 양자화 (오차 <0.02%)
        cached = _H_FG_WATER_CACHE.get(T_q)
        if cached is not None:
            return cached
        try:
            h_v = CP.PropsSI("H", "T", T_q, "Q", 1, "Water")
            h_l = CP.PropsSI("H", "T", T_q, "Q", 0, "Water")
            val = h_v - h_l
            _H_FG_WATER_CACHE[T_q] = val
            return val
        except Exception as e:
            raise RuntimeError(
                f"CoolProp 'Water' h_fg 호출 실패 (T={T:.1f}K): {e}"
            )
