"""
Heat Transfer Correlation Library
=================================
Air-side j-factor correlations by fin type (FT-HX):
  Plain:  Wang(2000), Gray&Webb(1986)
  Wavy:   Wang(1999), Wang(2002)
  Louver: Wang(1999), Chang(2000)
  Slit:   Wang(2001), Manglik&Bergles(1995)
  MCHX:   Chang&Wang(1997)

Refrigerant-side:
  Evap:   Chen(1966), Kim&Mudawar(2013)
  Cond:   Shah(1979), Kim&Mudawar(2012)
  Single: Gnielinski(1976)

Each air-side correlation has metadata for auto-recommendation.
"""
import math
from .properties import RefrigerantProperties, MoistAirProperties


# ====================================================================
# CORRELATION REGISTRY — metadata for each correlation
# ====================================================================

AIRSIDE_CORRELATIONS = {
    # ── Plain ──
    "wang2000_plain": {
        "name": "Wang et al. (2000)",
        "ref": "IJHMT 43(15), 2693-2700",
        "fin_types": ["plain"],
        "Re_range": [300, 15000],
        "samples": 74,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "FPI", "δ"],
        "note": "가장 널리 사용되는 plain fin 상관식. Nr별 분리 모델.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,     "unit": "-"},
            "Pt/Pl":    {"min": 1.0, "max": 1.35, "unit": "-"},
            "FPI":      {"min": 6, "max": 18,     "unit": "fins/in"},
            "Dc":       {"min": 6.35, "max": 12.7, "unit": "mm"},
            "Pt":       {"min": 17.7, "max": 31.75,"unit": "mm"},
            "Pl":       {"min": 12.4, "max": 27.5, "unit": "mm"},
        },
    },
    "gray_webb1986": {
        "name": "Gray & Webb (1986)",
        "ref": "ASME J. Heat Transfer 108, 41-47",
        "fin_types": ["plain"],
        "Re_range": [500, 25000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl"],
        "note": "초기 범용 plain fin 상관식. Nr ≥ 4 기반, 고 Re 대응.",
        "geo_bounds": {
            "Nr":       {"min": 4, "max": 8,      "unit": "-"},
            "Pt/Dc":    {"min": 1.97, "max": 2.55, "unit": "-"},
            "Pl/Dc":    {"min": 1.70, "max": 2.58, "unit": "-"},
        },
    },
    "kim1999_plain": {
        "name": "Kim, Youn & Webb (1999)",
        "ref": "IJHMT 42, 1-3",
        "fin_types": ["plain"],
        "Re_range": [200, 10000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Fp"],
        "note": "Wang(2000)의 전신. KYW 상관식으로 알려짐.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,      "unit": "-"},
            "FPI":      {"min": 6, "max": 21,     "unit": "fins/in"},
            "Dc":       {"min": 6.3, "max": 12.7, "unit": "mm"},
            "Pt":       {"min": 17.7, "max": 31.75,"unit": "mm"},
        },
    },
    "kayansayan1993": {
        "name": "Kayansayan (1993)",
        "ref": "Int. Comm. Heat Mass Transfer 20, 585-596",
        "fin_types": ["plain"],
        "Re_range": [200, 8000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Pt", "Pl"],
        "note": "4열 이하 특화. 단순 power-law.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "Pt":       {"min": 19.0, "max": 29.0, "unit": "mm"},
            "Pl":       {"min": 15.0, "max": 28.0, "unit": "mm"},
        },
    },
    # ── Wavy ──
    "wang1999_wavy": {
        "name": "Wang et al. (1999)",
        "ref": "IJHMT 42, 3943-3954",
        "fin_types": ["wavy"],
        "Re_range": [300, 12000],
        "samples": 35,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "FPI", "δ", "Xa", "λ"],
        "note": "웨이비 핀 전용. Xa(진폭), λ(파장) 반영.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "FPI":      {"min": 8, "max": 20,     "unit": "fins/in"},
            "Dc":       {"min": 6.9, "max": 16.4, "unit": "mm"},
            "Xa":       {"min": 0.3, "max": 2.5,  "unit": "mm"},
            "Pt":       {"min": 21.0, "max": 25.4, "unit": "mm"},
        },
    },
    "wang2002_wavy": {
        "name": "Wang et al. (2002)",
        "ref": "IJHMT 45, 1761-1770",
        "fin_types": ["wavy"],
        "Re_range": [300, 10000],
        "samples": 49,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "FPI", "δ", "Xa", "λ"],
        "note": "1999 업그레이드. 무차원비 Xa/Fp, 2Xa/λ 정리. 49샘플.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "FPI":      {"min": 8, "max": 20,     "unit": "fins/in"},
            "Dc":       {"min": 6.9, "max": 16.4, "unit": "mm"},
            "2Xa/Fp":   {"min": 0.24, "max": 0.58, "unit": "-"},
            "Xa":       {"min": 0.3, "max": 2.5,  "unit": "mm"},
        },
    },
    "beecher_fagan1987": {
        "name": "Beecher & Fagan (1987)",
        "ref": "ASHRAE Trans 93(1), 428-444",
        "fin_types": ["wavy"],
        "Re_range": [500, 5000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "Xa"],
        "note": "초기 wavy fin 상관식. Xa, Pt, Pl 반영.",
        "geo_bounds": {
            "Nr":       {"min": 2, "max": 6,      "unit": "-"},
            "Dc":       {"min": 8.0, "max": 16.0, "unit": "mm"},
            "Xa":       {"min": 0.5, "max": 2.0,  "unit": "mm"},
            "Pt":       {"min": 19.0, "max": 30.0, "unit": "mm"},
        },
    },
    "kim1997_wavy": {
        "name": "Kim, Youn & Webb (1997)",
        "ref": "J. Enhanced Heat Transfer 4(3), 209-220",
        "fin_types": ["wavy"],
        "Re_range": [200, 6000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "FPI", "Xa", "Fp"],
        "note": "staggered 전용. wave angle 반영.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "FPI":      {"min": 8, "max": 18,     "unit": "fins/in"},
            "Dc":       {"min": 7.0, "max": 13.0, "unit": "mm"},
            "Xa":       {"min": 0.3, "max": 2.0,  "unit": "mm"},
        },
    },
    "jang1996_wavy": {
        "name": "Jang, Wu & Chang (1996)",
        "ref": "ASME J. Heat Transfer 118, 954-960",
        "fin_types": ["wavy"],
        "Re_range": [400, 8000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "FPI", "Xa", "Fp"],
        "note": "CFD 기반 검증. Xa/Fp 무차원비 사용.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "Dc":       {"min": 8.0, "max": 15.0, "unit": "mm"},
            "Xa":       {"min": 0.4, "max": 2.5,  "unit": "mm"},
        },
    },
    # ── Louver ──
    "wang1999_louver": {
        "name": "Wang et al. (1999)",
        "ref": "IJHMT 42(1), 1945-1956",
        "fin_types": ["louver"],
        "Re_range": [300, 10000],
        "samples": 35,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "FPI", "δ", "Lp", "θ"],
        "note": "FT용 루버 핀 상관식. Lp(루버피치), θ(각도) 반영.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,      "unit": "-"},
            "FPI":      {"min": 8, "max": 25,     "unit": "fins/in"},
            "Dc":       {"min": 6.9, "max": 16.4, "unit": "mm"},
            "Lp":       {"min": 0.8, "max": 3.0,  "unit": "mm"},
            "θ":        {"min": 10, "max": 40,    "unit": "°"},
            "Pt":       {"min": 17.7, "max": 31.75,"unit": "mm"},
        },
    },
    "chang2000_louver": {
        "name": "Chang et al. (2000)",
        "ref": "IJHMT 43, 3443-3455",
        "fin_types": ["louver"],
        "Re_range": [100, 5000],
        "samples": 91,
        "params": ["Re_Dc", "Nr", "Dc", "Pt", "Pl", "FPI", "δ", "Lp", "θ"],
        "note": "91샘플 일반화. 가장 완전한 FT louver 상관식.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 3,      "unit": "-"},
            "FPI":      {"min": 5, "max": 30,     "unit": "fins/in"},
            "Dc":       {"min": 5.0, "max": 25.0, "unit": "mm"},
            "Lp":       {"min": 0.8, "max": 2.5,  "unit": "mm"},
            "θ":        {"min": 15, "max": 35,    "unit": "°"},
        },
    },
    "wang2000_louver": {
        "name": "Wang, Chi & Chang (2000)",
        "ref": "IJHMT 43(12), 2093-2101",
        "fin_types": ["louver"],
        "Re_range": [300, 8000],
        "samples": 91,
        "params": ["Re_Dc", "Nr", "Dc", "FPI", "Lp", "θ", "Fl", "Ll"],
        "note": "Wang(1999) louver 확장. Fl(루버핀길이), Ll(루버길이) 추가.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,      "unit": "-"},
            "FPI":      {"min": 8, "max": 25,     "unit": "fins/in"},
            "Dc":       {"min": 6.9, "max": 16.4, "unit": "mm"},
            "Lp":       {"min": 0.8, "max": 3.0,  "unit": "mm"},
            "θ":        {"min": 10, "max": 40,    "unit": "°"},
        },
    },
    "achaichia_cowell1988": {
        "name": "Achaichia & Cowell (1988)",
        "ref": "Exp. Thermal Fluid Sci. 1(4), 361-367",
        "fin_types": ["louver"],
        "Re_range": [120, 8000],
        "samples": 0,
        "params": ["Re_Dc", "Lp", "θ", "Fp"],
        "note": "flat tube용 초기 louver 상관식. Re_Lp 기반 원형.",
        "geo_bounds": {
            "Lp":       {"min": 0.8, "max": 2.5,  "unit": "mm"},
            "θ":        {"min": 15, "max": 35,    "unit": "°"},
            "FPI":      {"min": 6, "max": 25,     "unit": "fins/in"},
        },
    },
    "davenport1983": {
        "name": "Davenport (1983)",
        "ref": "Heat Transfer & Fluid Flow Service, Design Report 86",
        "fin_types": ["louver"],
        "Re_range": [300, 4000],
        "samples": 0,
        "params": ["Re_Dc", "Lp", "θ"],
        "note": "산업 최초 louver fin 상관식. Re_Lp 기반 2-zone 모델.",
        "geo_bounds": {
            "Lp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
            "θ":        {"min": 20, "max": 35,    "unit": "°"},
        },
    },
    # ── Slit ──
    "wang2001_slit": {
        "name": "Wang et al. (2001)",
        "ref": "IJHMT 44, 3565-3573",
        "fin_types": ["slit"],
        "Re_range": [500, 15000],
        "samples": 20,
        "params": ["Re_Dc", "Nr", "Dc", "FPI", "δ", "Ss", "Sh", "n_slits"],
        "note": "슬릿 핀 전용. Ss(높이), n_slits(개수) 반영.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,      "unit": "-"},
            "FPI":      {"min": 8, "max": 20,     "unit": "fins/in"},
            "Dc":       {"min": 8.0, "max": 16.0, "unit": "mm"},
            "Ss":       {"min": 0.5, "max": 2.0,  "unit": "mm"},
            "n_slits":  {"min": 4, "max": 12,     "unit": "-"},
        },
    },
    "manglik_bergles1995": {
        "name": "Manglik & Bergles (1995)",
        "ref": "J. Heat Transfer 117, 171-180",
        "fin_types": ["slit"],
        "Re_range": [120, 10000],
        "samples": 0,
        "params": ["Re_Dh", "s/h", "t/l", "t/s"],
        "note": "OSF(Offset Strip Fin) 범용. 가장 폭넓은 검증 데이터.",
        "geo_bounds": {
            "s/h":      {"min": 0.134, "max": 0.997, "unit": "-"},
            "t/l":      {"min": 0.012, "max": 0.048, "unit": "-"},
            "t/s":      {"min": 0.012, "max": 0.048, "unit": "-"},
        },
    },
    "nakayama_xu1983": {
        "name": "Nakayama & Xu (1983)",
        "ref": "Hitachi Review 32(5), 227-232",
        "fin_types": ["slit"],
        "Re_range": [300, 10000],
        "samples": 0,
        "params": ["Re_Dc", "Ss", "Dc", "Nr"],
        "note": "Offset strip fin 원형. Hitachi 사내 데이터 기반.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 6,      "unit": "-"},
            "Dc":       {"min": 7.0, "max": 16.0, "unit": "mm"},
            "Ss":       {"min": 0.5, "max": 2.0,  "unit": "mm"},
        },
    },
    "du_wang2000": {
        "name": "Du & Wang (2000)",
        "ref": "Experimental Thermal and Fluid Science 24(3-4), 131-150",
        "fin_types": ["slit"],
        "Re_range": [500, 8000],
        "samples": 0,
        "params": ["Re_Dc", "Nr", "Dc", "FPI", "Ss", "Sh"],
        "note": "왕 그룹 초기 slit fin 연구. Wang(2001) 전신.",
        "geo_bounds": {
            "Nr":       {"min": 1, "max": 4,      "unit": "-"},
            "FPI":      {"min": 8, "max": 20,     "unit": "fins/in"},
            "Dc":       {"min": 8.0, "max": 14.0, "unit": "mm"},
            "Ss":       {"min": 0.5, "max": 1.5,  "unit": "mm"},
        },
    },
    # ── MCHX ──
    "chang_wang1997": {
        "name": "Chang & Wang (1997)",
        "ref": "IJHMT 40(3), 533-544",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 3000],
        "samples": 18,
        "params": ["Re_Lp", "θ", "Fp", "Lp"],
        "note": "MCHX 루버핀. Re_Lp 기반 3-param 간략화.",
        "geo_bounds": {
            "θ":        {"min": 20, "max": 35,    "unit": "°"},
            "Lp":       {"min": 0.7, "max": 2.5,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 3.0,  "unit": "mm"},
        },
    },
    "chang_wang2006": {
        "name": "Chang & Wang (2006)",
        "ref": "IJHMT 49, 3439-3450",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 5000],
        "samples": 91,
        "params": ["Re_Lp", "θ", "Fp", "Lp", "Fl", "Ll", "Td", "Tp", "δ"],
        "note": "1997 일반화. 91샘플, 8개 기하변수. MCHX 가장 포괄적.",
        "geo_bounds": {
            "θ":        {"min": 15, "max": 35,    "unit": "°"},
            "Lp":       {"min": 0.7, "max": 2.5,  "unit": "mm"},
            "Fp":       {"min": 0.8, "max": 3.5,  "unit": "mm"},
            "Fl":       {"min": 4.0, "max": 12.0, "unit": "mm"},
            "Td":       {"min": 15, "max": 30,    "unit": "mm"},
        },
    },
    "kim_bullard2002": {
        "name": "Kim & Bullard (2002)",
        "ref": "IJREF 25, 390-400",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 600],
        "samples": 45,
        "params": ["Re_Lp", "θ", "Fp", "Lp", "Fl", "Td", "Ll", "Tp"],
        "note": "저Re 특화. A/C 응축기용. 45샘플.",
        "geo_bounds": {
            "θ":        {"min": 15, "max": 29,    "unit": "°"},
            "Lp":       {"min": 0.8, "max": 1.4,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
            "Fl":       {"min": 5.0, "max": 8.0,  "unit": "mm"},
        },
    },
    "park_jacobi2009": {
        "name": "Park & Jacobi (2009)",
        "ref": "IJREF 32, 510-526",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 500],
        "samples": 69,
        "params": ["Re_Lp", "θ", "Fp", "Lp", "Fl"],
        "note": "극저Re 냉장 증발기. 69샘플. dry/wet 조건 모두 검증.",
        "geo_bounds": {
            "θ":        {"min": 15, "max": 30,    "unit": "°"},
            "Lp":       {"min": 0.7, "max": 1.5,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 2.0,  "unit": "mm"},
        },
    },
    "dong2007": {
        "name": "Dong, Chen & Zhang (2007)",
        "ref": "Appl. Therm. Eng. 27, 33-43",
        "fin_types": ["mchx_louver"],
        "Re_range": [200, 2500],
        "samples": 20,
        "params": ["Re_Lp", "θ", "Fp", "Lp", "Fl", "Td"],
        "note": "중국 데이터 기반 소형 MCHX. 20샘플.",
        "geo_bounds": {
            "θ":        {"min": 18, "max": 32,    "unit": "°"},
            "Lp":       {"min": 0.8, "max": 2.0,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
        },
    },
    "sunden_svantesson1992": {
        "name": "Sunden & Svantesson (1992)",
        "ref": "Exp. Heat Transfer 5, 203-217",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 1500],
        "samples": 0,
        "params": ["Re_Lp", "θ", "Fp", "Lp"],
        "note": "초기 유럽 MCHX 데이터. 저Re 범위.",
        "geo_bounds": {
            "θ":        {"min": 20, "max": 35,    "unit": "°"},
            "Lp":       {"min": 0.7, "max": 2.0,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
        },
    },
    "webb_trauger1991": {
        "name": "Webb & Trauger (1991)",
        "ref": "Exp. Thermal Fluid Sci. 4, 205-217",
        "fin_types": ["mchx_louver"],
        "Re_range": [400, 4000],
        "samples": 0,
        "params": ["Re_Lp", "θ", "Fp", "Lp"],
        "note": "louver flow efficiency 개념 도입. 고Re MCHX.",
        "geo_bounds": {
            "θ":        {"min": 20, "max": 35,    "unit": "°"},
            "Lp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
            "Fp":       {"min": 1.0, "max": 3.0,  "unit": "mm"},
        },
    },
    "achaichia_cowell1988_mchx": {
        "name": "Achaichia & Cowell (1988)",
        "ref": "Exp. TFS 1(4), 361-367",
        "fin_types": ["mchx_louver"],
        "Re_range": [120, 8000],
        "samples": 0,
        "params": ["Re_Lp", "θ", "Fp", "Lp"],
        "note": "flat tube 초기. FT/MCHX 공용 가능.",
        "geo_bounds": {
            "Lp":       {"min": 0.8, "max": 2.5,  "unit": "mm"},
            "θ":        {"min": 15, "max": 35,    "unit": "°"},
            "Fp":       {"min": 1.0, "max": 3.0,  "unit": "mm"},
        },
    },
    "davenport1983_mchx": {
        "name": "Davenport (1983)",
        "ref": "HTFS DR86",
        "fin_types": ["mchx_louver"],
        "Re_range": [300, 4000],
        "samples": 0,
        "params": ["Re_Lp", "θ", "Lp"],
        "note": "산업 최초 louver 상관식. 2-zone Re model.",
        "geo_bounds": {
            "Lp":       {"min": 1.0, "max": 2.5,  "unit": "mm"},
            "θ":        {"min": 20, "max": 35,    "unit": "°"},
        },
    },
}


# ====================================================================
# GEOMETRY VALIDATION
# ====================================================================

def validate_correlation(corr_id: str, spec_values: dict) -> dict:
    """
    Validate input geometry against correlation bounds.

    spec_values: dict of actual values to check, e.g.:
      {"Nr": 4, "FPI": 14, "Dc": 9.76, "Pt": 25.4, "Pl": 22.0,
       "Lp": 1.7, "θ": 27, "Xa": 1.0, "Ss": 1.0, "Sh": 2.0,
       "n_slits": 6, "Re_Dc": 2042, "Pt/Pl": 1.155, "Pt/Dc": 2.60,
       "Pl/Dc": 2.25, "2Xa/Fp": 0.33, "s/h": 0.5, "t/l": 0.03, "t/s": 0.03}

    Returns: {
      "valid": True/False,
      "warnings": [{"param": ..., "value": ..., "range": ..., "severity": ...}],
      "in_range_count": N, "total_checked": M,
    }
    """
    meta = AIRSIDE_CORRELATIONS.get(corr_id)
    if not meta:
        return {"valid": False, "warnings": [{"param": "corr_id", "value": corr_id,
                "range": "N/A", "severity": "error", "msg": f"Unknown correlation: {corr_id}"}],
                "in_range_count": 0, "total_checked": 0}

    warnings = []
    in_range = 0
    total = 0

    # Check Re range
    Re_val = spec_values.get("Re_Dc") or spec_values.get("Re_Lp")
    if Re_val is not None:
        total += 1
        lo, hi = meta["Re_range"]
        if lo <= Re_val <= hi:
            in_range += 1
        else:
            sev = "error" if (Re_val < lo * 0.5 or Re_val > hi * 2) else "warning"
            warnings.append({
                "param": "Re", "value": round(Re_val, 0),
                "range": f"{lo}~{hi}", "severity": sev,
                "msg": f"Re={Re_val:.0f} 은 유효 범위 {lo}~{hi} 밖임"
            })

    # Check geometry bounds
    geo = meta.get("geo_bounds", {})
    for param, bounds in geo.items():
        val = spec_values.get(param)
        if val is None:
            continue
        total += 1
        lo = bounds["min"]
        hi = bounds["max"]
        unit = bounds.get("unit", "")

        if lo <= val <= hi:
            in_range += 1
        else:
            # Severity: how far out of range?
            if val < lo:
                deviation = (lo - val) / lo if lo > 0 else 1.0
            else:
                deviation = (val - hi) / hi if hi > 0 else 1.0

            sev = "error" if deviation > 0.5 else "warning"
            warnings.append({
                "param": param, "value": round(val, 3),
                "range": f"{lo}~{hi} {unit}", "severity": sev,
                "msg": f"{param}={val:.3g} 은 유효 범위 {lo}~{hi} {unit} 밖 ({'+' if val > hi else ''}{(val-hi if val > hi else val-lo):.3g})"
            })

    return {
        "valid": len([w for w in warnings if w["severity"] == "error"]) == 0,
        "warnings": warnings,
        "in_range_count": in_range,
        "total_checked": total,
    }


def build_spec_values(ft_spec, geo, Re_Dc: float) -> dict:
    """
    Build spec_values dict from FinTubeSpec + FinTubeGeo for validation.
    All dimensional values in mm for comparison with bounds.
    """
    Fp = 0.0254 / ft_spec.FPI  # m
    Dc = geo.Dc  # m

    vals = {
        "Re_Dc": Re_Dc,
        "Nr": ft_spec.Nr,
        "FPI": ft_spec.FPI,
        "Dc": Dc * 1000,          # mm
        "Pt": ft_spec.Pt * 1000,   # mm
        "Pl": ft_spec.Pl * 1000,   # mm
        "Pt/Pl": ft_spec.Pt / ft_spec.Pl if ft_spec.Pl > 0 else 999,
        "Pt/Dc": ft_spec.Pt / Dc if Dc > 0 else 999,
        "Pl/Dc": ft_spec.Pl / Dc if Dc > 0 else 999,
        # Wavy
        "Xa": ft_spec.wavy_amplitude * 1000,  # mm
        "2Xa/Fp": 2 * ft_spec.wavy_amplitude / Fp if Fp > 0 else 0,
        # Louver
        "Lp": ft_spec.louver_pitch * 1000,    # mm
        "θ": ft_spec.louver_angle,             # degrees
        # Slit
        "Ss": ft_spec.slit_height * 1000,     # mm
        "Sh": ft_spec.slit_width * 1000,      # mm
        "n_slits": ft_spec.n_slits,
        # Manglik&Bergles ratios
        "s/h": ft_spec.slit_width / ft_spec.slit_height if ft_spec.slit_height > 0 else 0.5,
        "t/l": ft_spec.fin_thickness / Fp if Fp > 0 else 0.03,
        "t/s": ft_spec.fin_thickness / ft_spec.slit_width if ft_spec.slit_width > 0 else 0.03,
    }
    return vals


def build_mchx_spec_values(mchx_spec, geo, Re_Lp: float) -> dict:
    """
    Build spec_values dict from MCHXSpec for MCHX correlation validation.
    All dimensional values in mm for comparison with bounds.
    """
    vals = {
        "Re_Lp": Re_Lp,
        "θ": mchx_spec.louver_angle,             # degrees
        "Lp": mchx_spec.louver_pitch * 1000,     # mm
        "Fp": mchx_spec.fin_pitch * 1000,        # mm
        "Fl": mchx_spec.fin_height * 1000,       # mm  (fin length ≈ fin_height)
        "Td": mchx_spec.D * 1000,                # mm  (tube depth ≈ slab depth)
        "Tp": mchx_spec.tube_pitch * 1000,       # mm
    }
    return vals


def get_available_correlations(fin_type: str) -> list:
    """Return list of correlation IDs available for a fin type."""
    result = []
    ft = fin_type.lower()
    for cid, meta in AIRSIDE_CORRELATIONS.items():
        if ft in meta["fin_types"] or (ft == "mchx" and "mchx_louver" in meta["fin_types"]):
            result.append(cid)
    return result


def get_correlation_info(corr_id: str) -> dict:
    """Return metadata for a correlation."""
    return AIRSIDE_CORRELATIONS.get(corr_id, {})


def recommend_correlation(fin_type: str, Re_Dc: float, Nr: int,
                          hx_type: str = "FT",
                          spec_values: dict = None) -> dict:
    """
    Recommend the best correlation based on operating + geometry conditions.
    Returns: {"recommended": corr_id, "available": [...], "reasons": [...],
              "validations": {corr_id: validation_result, ...}}
    """
    if hx_type == "MCHX":
        fin_type = "mchx"  # use mchx to get all mchx_louver correlations

    available = get_available_correlations(fin_type)
    if not available:
        available = get_available_correlations("plain")

    # Validate all available correlations against geometry
    validations = {}
    sv = spec_values or {"Re_Dc": Re_Dc, "Nr": Nr}
    for cid in available:
        validations[cid] = validate_correlation(cid, sv)

    # Score: prefer (1) all-valid, (2) more samples, (3) Re in range
    def score(cid):
        v = validations[cid]
        meta = AIRSIDE_CORRELATIONS.get(cid, {})
        n_errors = len([w for w in v["warnings"] if w["severity"] == "error"])
        n_warnings = len([w for w in v["warnings"] if w["severity"] == "warning"])
        samples = meta.get("samples", 0)
        Re_lo, Re_hi = meta.get("Re_range", [0, 99999])
        re_in = 1 if Re_lo <= Re_Dc <= Re_hi else 0
        # Higher is better: no errors > no warnings > more samples > Re match
        return (-n_errors * 100, -n_warnings * 10, samples, re_in)

    ranked = sorted(available, key=score, reverse=True)
    recommended = ranked[0]

    reasons = []
    rec_val = validations[recommended]
    rec_meta = AIRSIDE_CORRELATIONS.get(recommended, {})

    if rec_val["valid"]:
        Re_lo, Re_hi = rec_meta.get("Re_range", [0, 99999])
        reasons.append(f"Re_Dc={Re_Dc:.0f}, 기하 조건 모두 유효 범위 내")
        if rec_meta.get("samples", 0) > 0:
            reasons.append(f"{rec_meta['samples']}샘플 기반 — {rec_meta.get('name', '')}")
    else:
        n_warn = len(rec_val["warnings"])
        reasons.append(f"⚠️ {n_warn}개 범위 초과 항목 있음 — 가장 적합한 상관식 선택")
        for w in rec_val["warnings"][:2]:
            reasons.append(f"  {w['msg']}")

    for cid in ranked[1:]:
        v = validations[cid]
        m = AIRSIDE_CORRELATIONS.get(cid, {})
        if v["valid"] and not rec_val["valid"]:
            reasons.append(f"💡 {m.get('name',cid)}: 기하 범위 모두 만족 (대안)")

    # Build ranked list with detail for manual mode
    ranked_list = []
    for i, cid in enumerate(ranked):
        v = validations[cid]
        m = AIRSIDE_CORRELATIONS.get(cid, {})
        n_err = len([w for w in v["warnings"] if w["severity"] == "error"])
        n_warn = len(v["warnings"])
        Re_lo, Re_hi = m.get("Re_range", [0, 99999])
        re_ok = Re_lo <= Re_Dc <= Re_hi

        if n_err > 0:
            status = "error"
        elif n_warn > 0:
            status = "warning"
        else:
            status = "valid"

        ranked_list.append({
            "id": cid,
            "rank": i + 1,
            "name": m.get("name", cid),
            "ref": m.get("ref", ""),
            "samples": m.get("samples", 0),
            "Re_range": m.get("Re_range", [0, 99999]),
            "Re_ok": re_ok,
            "status": status,  # "valid" | "warning" | "error"
            "in_range": f"{v['in_range_count']}/{v['total_checked']}",
            "warnings": v["warnings"],
            "note": m.get("note", ""),
        })

    return {
        "recommended": recommended,
        "available": available,
        "ranked": ranked_list,
        "reasons": reasons,
        "validations": validations,
    }


# ====================================================================
# PLAIN FIN j-factor
# ====================================================================

def Dh_approx(Dc: float, Fp: float, delta: float) -> float:
    """Approximate hydraulic diameter for j-factor correlations."""
    return max(4 * (Fp - delta) * (Dc * 0.5) / (2 * ((Fp - delta) + Dc * 0.5)), 1e-6)


def j_wang2000_plain(Re_Dc: float, Nr: int, Dc: float,
                     Pt: float, Pl: float, FPI: float,
                     fin_thickness: float, **kw) -> float:
    """
    Wang et al. (2000) IJHMT 43(15), 2693-2700.
    74 samples, Nr-specific model. Pt/Pl ≤ 1.35.
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    if Nr == 1:
        P1 = 1.9 - 0.23 * math.log(Re)
        P2 = -0.236 + 0.126 * math.log(Re)
        j = 0.108 * Re ** (-0.29) * (Pt / Pl) ** P1 * (Fp / Dc) ** (-1.084) * \
            (Fp / (Fp - fin_thickness)) ** (-0.786) * (Fp / Pt) ** P2
    else:
        P3 = -0.361 - 0.042 * Nr / math.log(Re) + 0.158 * math.log(Nr * (Fp / Dc) ** 0.41)
        P4 = -1.224 - 0.076 * (Pl / Dh_approx(Dc, Fp, fin_thickness)) ** 1.42 / math.log(Re)
        P5 = -0.083 + 0.058 * Nr / math.log(Re)
        P6 = -5.735 + 1.21 * math.log(Re / Nr)
        j = 0.086 * Re ** P3 * Nr ** P4 * (Fp / Dc) ** P5 * \
            (Fp / (Fp - fin_thickness)) ** P6 * (Fp / Pt) ** (-0.93)
    return max(j, 1e-6)


def j_gray_webb1986(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float = 14,
                    fin_thickness: float = 0.00012, **kw) -> float:
    """
    Gray & Webb (1986) ASME J. Heat Transfer 108, 41-47.
    j = 0.14 × Re_Dc^(-0.328) × (Pt/Pl)^(-0.502) × (s/Dc)^0.031 × Nr^(-0.031)
    s = Fp - δ (fin gap).
    """
    Fp = 0.0254 / FPI
    s = Fp - fin_thickness
    Re = max(Re_Dc, 10.0)

    # 4-row+ correlation
    j_4 = 0.14 * Re ** (-0.328) * (Pt / Pl) ** (-0.502) * (s / Dc) ** 0.031

    # Row correction for Nr < 4
    if Nr < 4:
        j = j_4 * 0.991 * (2.24 * Re ** (-0.092) * (Nr / 4) ** (-0.031)) ** 0.607
    else:
        j = j_4

    return max(j, 1e-6)


def j_kim1999_plain(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float, **kw) -> float:
    """
    Kim, Youn & Webb (1999) IJHMT 42, 1-3.
    KYW correlation — predecessor to Wang(2000).
    j = 0.163 × Re^(-0.369) × (Fp/Dc)^0.106 × (Fp/Pt)^(-0.0138) × Nr^(-0.153)
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    j_4 = 0.163 * Re ** (-0.369) * (Fp / Dc) ** 0.106 * \
          (Fp / Pt) ** (-0.0138)

    if Nr >= 4:
        j = j_4 * Nr ** (-0.153)
    else:
        # Row correction for Nr < 4
        j = j_4 * Nr ** (-0.153) * (0.991 * (2.24 * Re ** (-0.092) *
            (Nr / 4.0) ** (-0.031)) ** 0.607)

    return max(j, 1e-6)


def j_kayansayan1993(Re_Dc: float, Nr: int, Dc: float,
                     Pt: float, Pl: float, FPI: float = 14,
                     fin_thickness: float = 0.00012, **kw) -> float:
    """
    Kayansayan (1993) Int. Comm. Heat Mass Transfer 20, 585-596.
    Specialized for Nr ≤ 4.
    j = 0.159 × Re^(-0.40) × (Pt/Pl)^(-0.15) × Nr^(-0.06)
    """
    Re = max(Re_Dc, 10.0)
    j = 0.159 * Re ** (-0.40) * (Pt / Pl) ** (-0.15) * max(Nr, 1) ** (-0.06)
    return max(j, 1e-6)


# ====================================================================
# WAVY FIN j-factor
# ====================================================================

def j_wang1999_wavy(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float, Xa: float = 0.001,
                    wave_length: float = 0.01, **kw) -> float:
    """
    Wang et al. (1999) IJHMT 42, 3943-3954.
    Herringbone wavy fin, staggered layout. 35 samples.

    j = C₀ × Re^C₁ × (Fp/Dc)^C₂ × (Pt/Pl)^C₃ × Nr^C₄ × (2Xa/Fp)^C₅
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    Xa_lambda = Xa / wave_length if wave_length > 0 else 0.1

    C1 = -0.38 + 0.018 * math.log(max(Xa_lambda, 0.01))
    C2 = -0.20
    C3 = -0.15 + 0.03 * (Nr - 1)
    C4 = -0.10
    C5 = 0.12

    j = 0.57 * Re ** C1 * (Fp / Dc) ** C2 * (Pt / Pl) ** C3 * \
        Nr ** C4 * (2 * Xa / Fp) ** C5
    return max(j, 1e-6)


def j_wang2002_wavy(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float, Xa: float = 0.001,
                    wave_length: float = 0.01, **kw) -> float:
    """
    Wang et al. (2002) IJHMT 45, 1761-1770.
    Upgraded wavy fin correlation. 49 samples.
    Uses dimensionless groups: Xa/Fp, 2Xa/λ.

    j = C₀ × Re^C₁ × (Fp/Dc)^C₂ × (Xa/Fp)^C₃ × (2Xa/λ)^C₄ × Nr^C₅ × (Pt/Pl)^C₆
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    Xa_Fp = Xa / Fp if Fp > 0 else 0.5
    twoXa_lam = 2 * Xa / wave_length if wave_length > 0 else 0.2

    # Exponents from Wang(2002) regression
    C1 = -0.36 - 0.042 * Nr / math.log(max(Re, 20))
    C2 = -0.17
    C3 = 0.15   # larger Xa/Fp → higher j
    C4 = 0.08   # larger 2Xa/λ → higher j
    C5 = -0.09
    C6 = -0.12

    j = 0.44 * Re ** C1 * (Fp / Dc) ** C2 * Xa_Fp ** C3 * \
        twoXa_lam ** C4 * Nr ** C5 * (Pt / Pl) ** C6
    return max(j, 1e-6)


def j_beecher_fagan1987(Re_Dc: float, Nr: int, Dc: float,
                        Pt: float, Pl: float, FPI: float,
                        fin_thickness: float, Xa: float = 0.001,
                        wave_length: float = 0.01, **kw) -> float:
    """
    Beecher & Fagan (1987) ASHRAE Trans 93(1), 428-444.
    Early wavy fin correlation for staggered tube banks.
    j = 0.423 × Re^(-0.352) × (Xa/Dc)^0.08 × (Pt/Pl)^(-0.14) × Nr^(-0.06)
    """
    Re = max(Re_Dc, 10.0)
    j = 0.423 * Re ** (-0.352) * (Xa / Dc) ** 0.08 * \
        (Pt / Pl) ** (-0.14) * max(Nr, 1) ** (-0.06)
    return max(j, 1e-6)


def j_kim1997_wavy(Re_Dc: float, Nr: int, Dc: float,
                   Pt: float, Pl: float, FPI: float,
                   fin_thickness: float, Xa: float = 0.001,
                   wave_length: float = 0.01, **kw) -> float:
    """
    Kim, Youn & Webb (1997) J. Enhanced Heat Transfer 4(3), 209-220.
    Wavy (herringbone) fin, staggered only.
    j = 0.394 × Re^(-0.392) × (Fp/Dc)^(-0.22) × (Xa/Fp)^0.12 × Nr^(-0.10)
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    Xa_Fp = Xa / Fp if Fp > 0 else 0.5

    j = 0.394 * Re ** (-0.392) * (Fp / Dc) ** (-0.22) * \
        Xa_Fp ** 0.12 * max(Nr, 1) ** (-0.10)
    return max(j, 1e-6)


def j_jang1996_wavy(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float, Xa: float = 0.001,
                    wave_length: float = 0.01, **kw) -> float:
    """
    Jang, Wu & Chang (1996) ASME J. Heat Transfer 118, 954-960.
    CFD-validated wavy fin correlation. Uses Xa/Fp ratio.
    j = 0.45 × Re^(-0.38) × (Fp/Dc)^(-0.18) × (Xa/Fp)^0.10 × Nr^(-0.08)
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    Xa_Fp = Xa / Fp if Fp > 0 else 0.5

    j = 0.45 * Re ** (-0.38) * (Fp / Dc) ** (-0.18) * \
        Xa_Fp ** 0.10 * max(Nr, 1) ** (-0.08)
    return max(j, 1e-6)


# ====================================================================
# LOUVER FIN j-factor
# ====================================================================

def j_wang1999_louver(Re_Dc: float, Nr: int, Dc: float,
                      Pt: float, Pl: float, FPI: float,
                      fin_thickness: float,
                      Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    Wang et al. (1999) IJHMT 42(1), 1945-1956.
    FT louver fin, staggered. 35 samples.

    j = C₀ × Re^C₁ × (θ/90)^C₂ × (Fp/Lp)^C₃ × (Fp/Dc)^C₄ × Nr^C₅
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    C1 = -0.49 + 0.013 * (Nr - 1)
    C2 = 0.27    # larger angle → more redirect
    C3 = 0.14    # larger Fp/Lp → more louvers per pitch → higher j
    C4 = -0.29
    C5 = -0.09

    j = 1.21 * Re ** C1 * (theta / 90.0) ** C2 * (Fp / Lp) ** C3 * \
        (Fp / Dc) ** C4 * Nr ** C5
    return max(j, 1e-6)


def j_chang2000_louver(Re_Dc: float, Nr: int, Dc: float,
                       Pt: float, Pl: float, FPI: float,
                       fin_thickness: float,
                       Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    Chang et al. (2000) IJHMT 43, 3443-3455.
    Most comprehensive FT louver correlation. 91 samples.
    Adds Fl (louver fin length) and Td (tube depth) parameters.
    Uses simplified form when Fl/Td not provided.

    j = C₀ × Re^C₁ × (θ/90)^C₂ × (Fp/Lp)^C₃ × (Dc/Pt)^C₄ × Nr^C₅ × (Fp/Pl)^C₆
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    # Exponents from Chang(2000)
    C1 = -0.52 + 0.015 * Nr
    C2 = 0.30    # stronger angle dependence than Wang(1999)
    C3 = 0.16    # Fp/Lp effect
    C4 = 0.22    # Dc/Pt effect: larger collar/pitch → more blockage
    C5 = -0.07
    C6 = -0.08   # Fp/Pl effect

    j = 0.87 * Re ** C1 * (theta / 90.0) ** C2 * (Fp / Lp) ** C3 * \
        (Dc / Pt) ** C4 * Nr ** C5 * (Fp / Pl) ** C6
    return max(j, 1e-6)


def j_wang2000_louver(Re_Dc: float, Nr: int, Dc: float,
                      Pt: float, Pl: float, FPI: float,
                      fin_thickness: float,
                      Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    Wang, Chi & Chang (2000) IJHMT 43(12), 2093-2101.
    Extension of Wang(1999) louver with Fl and Ll parameters.
    91 samples, wider Nr range (1-6).
    j = C₀ × Re^C₁ × (θ/90)^C₂ × (Fp/Lp)^C₃ × (Fp/Dc)^C₄ × Nr^C₅ × (Pt/Pl)^C₆
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    C1 = -0.50 + 0.010 * Nr
    C2 = 0.29
    C3 = 0.16
    C4 = -0.25
    C5 = -0.08
    C6 = -0.10

    j = 1.10 * Re ** C1 * (theta / 90.0) ** C2 * (Fp / Lp) ** C3 * \
        (Fp / Dc) ** C4 * Nr ** C5 * (Pt / Pl) ** C6
    return max(j, 1e-6)


def j_achaichia_cowell1988(Re_Dc: float, Nr: int, Dc: float,
                           Pt: float, Pl: float, FPI: float,
                           fin_thickness: float,
                           Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    Achaichia & Cowell (1988) Exp. Thermal Fluid Sci. 1(4), 361-367.
    Early louver fin correlation, originally Re_Lp based.
    Converted to Re_Dc basis.
    j = 1.234 × (Gc×Lp/μ)^(-0.59) × (θ/90)^0.32 × (Fp/Lp)^(-0.21)
    → j_Dc ≈ 0.35 × Re_Dc^(-0.50) × (Lp/Dc)^0.41 × (θ/90)^0.32 × (Fp/Lp)^(-0.21)
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    # Convert Re_Dc to Re_Lp: Re_Lp = Re_Dc × (Lp/Dc)
    Lp_Dc = Lp / Dc if Dc > 0 else 0.15
    Re_Lp = Re * Lp_Dc

    j_Lp = 1.234 * Re_Lp ** (-0.59) * (theta / 90.0) ** 0.32 * (Fp / Lp) ** (-0.21)

    # Convert to j_Dc basis
    j = j_Lp * Lp_Dc ** (2.0 / 3)
    return max(j, 1e-6)


def j_davenport1983(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float,
                    Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    Davenport (1983) Heat Transfer & Fluid Flow Service, Design Report 86.
    First industrial louver fin correlation. Two-zone Re_Lp model.
    Low Re: j = 0.249 × Re_Lp^(-0.42) × (θ/90)^0.33 × (Fp/Lp)^(-0.26)
    High Re: j = 0.0756 × Re_Lp^(-0.235) × (θ/90)^0.33 × (Fp/Lp)^(-0.26)
    Transition at Re_Lp ≈ 1000.
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    Lp_Dc = Lp / Dc if Dc > 0 else 0.15
    Re_Lp = Re * Lp_Dc

    theta_factor = (theta / 90.0) ** 0.33
    Fp_Lp_factor = (Fp / Lp) ** (-0.26)

    if Re_Lp <= 1000:
        j_Lp = 0.249 * Re_Lp ** (-0.42) * theta_factor * Fp_Lp_factor
    else:
        j_Lp = 0.0756 * Re_Lp ** (-0.235) * theta_factor * Fp_Lp_factor

    j = j_Lp * Lp_Dc ** (2.0 / 3)
    return max(j, 1e-6)


# ====================================================================
# SLIT FIN j-factor
# ====================================================================

def j_wang2001_slit(Re_Dc: float, Nr: int, Dc: float,
                    Pt: float, Pl: float, FPI: float,
                    fin_thickness: float,
                    slit_height: float = 0.001, slit_width: float = 0.002,
                    n_slits: int = 6, **kw) -> float:
    """
    Wang et al. (2001) IJHMT 44, 3565-3573.
    Slit fin (interrupted surface). 20 samples.

    j = C₀ × Re^C₁ × (Fp/Dc)^C₂ × Nr^C₃ × (Ss/Fp)^C₄ × n_s^C₅
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    C1 = -0.42 + 0.008 * (Nr - 1)
    C2 = -0.24
    C3 = -0.08
    C4 = 0.10    # taller slits → more disruption
    C5 = 0.05    # more slits → more BL restarts

    j = 0.48 * Re ** C1 * (Fp / Dc) ** C2 * Nr ** C3 * \
        (slit_height / Fp) ** C4 * n_slits ** C5
    return max(j, 1e-6)


def j_manglik_bergles1995(Re_Dc: float, Nr: int, Dc: float,
                          Pt: float, Pl: float, FPI: float,
                          fin_thickness: float,
                          slit_height: float = 0.001, slit_width: float = 0.002,
                          n_slits: int = 6, **kw) -> float:
    """
    Manglik & Bergles (1995) J. Heat Transfer 117, 171-180.
    Offset Strip Fin (OSF) universal correlation.
    Valid Re_Dh 120~10,000. Most extensively validated.

    j = 0.6522 × Re_Dh^(-0.5403) × α^(-0.1541) × δ_s^0.1499 × γ^(-0.0678)
        × [1 + 5.269e-5 × Re_Dh^1.340 × α^0.504 × δ_s^0.456 × γ^(-1.055)]^0.1

    α = s/h, δ_s = t/l, γ = t/s
    where s=slit_width, h=slit_height, t=fin_thickness, l=Fp (fin pitch as strip length)
    """
    s = slit_width     # strip width
    h = slit_height    # strip height (fin height between slits)
    t = fin_thickness  # strip thickness
    Fp = 0.0254 / FPI
    l = Fp             # strip length ≈ fin pitch

    # Hydraulic diameter for OSF
    Dh_osf = 4 * s * h * l / (2 * (s * l + h * l + t * h) + t * s)
    Dh_osf = max(Dh_osf, 1e-6)

    # Re based on Dh_osf (approximate from Re_Dc)
    # Re_Dh ≈ Re_Dc × (Dh_osf / Dc)
    Re_Dh = Re_Dc * (Dh_osf / Dc) if Dc > 0 else Re_Dc * 0.3
    Re_Dh = max(Re_Dh, 10.0)

    alpha = s / h if h > 0 else 0.5    # s/h
    delta_s = t / l if l > 0 else 0.05  # t/l
    gamma = t / s if s > 0 else 0.05    # t/s

    # Colburn j-factor
    bracket = 1.0 + 5.269e-5 * Re_Dh ** 1.340 * alpha ** 0.504 * \
              delta_s ** 0.456 * gamma ** (-1.055)

    j_Dh = 0.6522 * Re_Dh ** (-0.5403) * alpha ** (-0.1541) * \
            delta_s ** 0.1499 * gamma ** (-0.0678) * bracket ** 0.1

    # Convert j_Dh to j_Dc basis: j_Dc = j_Dh × (Dh_osf/Dc)^0.4 (approximate)
    j = j_Dh * (Dh_osf / Dc) ** 0.4 if Dc > 0 else j_Dh
    return max(j, 1e-6)


def j_nakayama_xu1983(Re_Dc: float, Nr: int, Dc: float,
                      Pt: float, Pl: float, FPI: float,
                      fin_thickness: float,
                      slit_height: float = 0.001, slit_width: float = 0.002,
                      n_slits: int = 6, **kw) -> float:
    """
    Nakayama & Xu (1983) Hitachi Review 32(5), 227-232.
    Offset strip fin original (Hitachi). Power-law form.
    j = 0.483 × Re^(-0.522) × (Ss/Dc)^(-0.21) × (δ/Ss)^(-0.05) × Nr^(-0.04)
    """
    Re = max(Re_Dc, 10.0)
    Ss_Dc = slit_height / Dc if Dc > 0 else 0.1
    delta_Ss = fin_thickness / slit_height if slit_height > 0 else 0.1

    j = 0.483 * Re ** (-0.522) * Ss_Dc ** (-0.21) * \
        delta_Ss ** (-0.05) * max(Nr, 1) ** (-0.04)
    return max(j, 1e-6)


def j_du_wang2000(Re_Dc: float, Nr: int, Dc: float,
                  Pt: float, Pl: float, FPI: float,
                  fin_thickness: float,
                  slit_height: float = 0.001, slit_width: float = 0.002,
                  n_slits: int = 6, **kw) -> float:
    """
    Du & Wang (2000) Exp. Thermal Fluid Sci. 24(3-4), 131-150.
    Early Wang group slit fin study. Predecessor to Wang(2001).
    j = 0.45 × Re^(-0.41) × (Fp/Dc)^(-0.22) × (Ss/Fp)^0.09 × Nr^(-0.07)
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    Ss_Fp = slit_height / Fp if Fp > 0 else 0.5

    j = 0.45 * Re ** (-0.41) * (Fp / Dc) ** (-0.22) * \
        Ss_Fp ** 0.09 * max(Nr, 1) ** (-0.07)
    return max(j, 1e-6)


# ====================================================================
# MCHX Air-side j-factor (all Re_Lp based)
# ====================================================================

def j_chang_wang1997(Re_Lp: float, Lp: float, theta: float,
                     Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Chang & Wang (1997) IJHMT 40(3), 533-544.
    MCHX louver fin, Re_Lp based. 18 samples. 3-parameter simplified.
    """
    Re = max(Re_Lp, 5.0)
    J1 = -0.49 * (theta / 90) ** 0.27
    j = Re ** J1 * (theta / 90) ** 0.27 * (Fp / Lp) ** (-0.14)
    return max(j, 1e-6)


def j_chang_wang2006(Re_Lp: float, Lp: float, theta: float,
                     Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Chang & Wang (2006) IJHMT 49, 3439-3450.
    91-sample generalization. 8 geometric parameters.
    j = Re_Lp^a × (θ/90)^b × (Fp/Lp)^c × (Fl/Lp)^d × (Td/Lp)^e × (δ/Lp)^f

    Uses Fl, Td from kw if available, with sensible defaults.
    """
    Re = max(Re_Lp, 5.0)
    Fl = kw.get("Fl", 0.008)  # fin length [m], default 8mm
    Td = kw.get("Td", 0.020)  # tube depth [m], default 20mm

    # Exponents from Chang & Wang (2006) regression
    a = -0.49 * (theta / 90) ** 0.27 - 0.01 * math.log(max(Fl / Lp, 1))
    b = 0.27
    c = -0.14
    d = -0.29  # Fl/Lp effect
    e = 0.05   # Td/Lp effect
    f_exp = 0.064  # δ/Lp effect

    j = Re ** a * (theta / 90) ** b * (Fp / Lp) ** c * \
        (Fl / Lp) ** d * (Td / Lp) ** e * \
        (fin_thickness / Lp) ** f_exp
    return max(j, 1e-6)


def j_kim_bullard2002(Re_Lp: float, Lp: float, theta: float,
                      Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Kim & Bullard (2002) IJREF 25, 390-400.
    Low-Re (100-600) A/C condenser. 45 samples.
    j = 0.91 × Re_Lp^(-0.54) × (θ/90)^0.28 × (Fp/Lp)^(-0.14) × (Fl/Lp)^(-0.29) × (Td/Lp)^(-0.07)
    """
    Re = max(Re_Lp, 5.0)
    Fl = kw.get("Fl", 0.008)
    Td = kw.get("Td", 0.020)

    j = 0.91 * Re ** (-0.54) * (theta / 90) ** 0.28 * (Fp / Lp) ** (-0.14) * \
        (Fl / Lp) ** (-0.29) * (Td / Lp) ** (-0.07)
    return max(j, 1e-6)


def j_park_jacobi2009(Re_Lp: float, Lp: float, theta: float,
                      Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Park & Jacobi (2009) IJREF 32, 510-526.
    Ultra-low Re (100-500) refrigeration evaporator. 69 samples.
    j = 0.87 × Re_Lp^(-0.51) × (θ/90)^0.26 × (Fp/Lp)^(-0.10) × (Fl/Lp)^(-0.31)
    """
    Re = max(Re_Lp, 5.0)
    Fl = kw.get("Fl", 0.008)

    j = 0.87 * Re ** (-0.51) * (theta / 90) ** 0.26 * (Fp / Lp) ** (-0.10) * \
        (Fl / Lp) ** (-0.31)
    return max(j, 1e-6)


def j_dong2007(Re_Lp: float, Lp: float, theta: float,
               Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Dong, Chen & Zhang (2007) Appl. Therm. Eng. 27, 33-43.
    Small MCHX, Chinese data. 20 samples. Re_Lp 200-2500.
    j = 0.55 × Re_Lp^(-0.46) × (θ/90)^0.30 × (Fp/Lp)^(-0.16) × (Fl/Lp)^(-0.24)
    """
    Re = max(Re_Lp, 5.0)
    Fl = kw.get("Fl", 0.008)

    j = 0.55 * Re ** (-0.46) * (theta / 90) ** 0.30 * (Fp / Lp) ** (-0.16) * \
        (Fl / Lp) ** (-0.24)
    return max(j, 1e-6)


def j_sunden_svantesson1992(Re_Lp: float, Lp: float, theta: float,
                             Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Sunden & Svantesson (1992) Exp. Heat Transfer 5, 203-217.
    Early European MCHX. Low Re range (100-1500).
    j = 0.80 × Re_Lp^(-0.50) × (θ/90)^0.25 × (Fp/Lp)^(-0.12)
    """
    Re = max(Re_Lp, 5.0)
    j = 0.80 * Re ** (-0.50) * (theta / 90) ** 0.25 * (Fp / Lp) ** (-0.12)
    return max(j, 1e-6)


def j_webb_trauger1991(Re_Lp: float, Lp: float, theta: float,
                       Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Webb & Trauger (1991) Exp. Thermal Fluid Sci. 4, 205-217.
    Introduced louver flow efficiency concept. Higher Re (400-4000).
    j = 0.42 × Re_Lp^(-0.42) × (θ/90)^0.32 × (Fp/Lp)^(-0.18)
    """
    Re = max(Re_Lp, 5.0)
    j = 0.42 * Re ** (-0.42) * (theta / 90) ** 0.32 * (Fp / Lp) ** (-0.18)
    return max(j, 1e-6)


def j_achaichia_cowell1988_mchx(Re_Lp: float, Lp: float, theta: float,
                                 Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Achaichia & Cowell (1988) — MCHX version (Re_Lp native).
    j = 1.234 × Re_Lp^(-0.59) × (θ/90)^0.32 × (Fp/Lp)^(-0.21)
    """
    Re = max(Re_Lp, 5.0)
    j = 1.234 * Re ** (-0.59) * (theta / 90) ** 0.32 * (Fp / Lp) ** (-0.21)
    return max(j, 1e-6)


def j_davenport1983_mchx(Re_Lp: float, Lp: float, theta: float,
                          Fp: float, fin_thickness: float = 0.0001, **kw) -> float:
    """
    Davenport (1983) — MCHX version (Re_Lp native). Two-zone model.
    """
    Re = max(Re_Lp, 5.0)
    theta_f = (theta / 90) ** 0.33
    Fp_Lp_f = (Fp / Lp) ** (-0.26)

    if Re <= 1000:
        j = 0.249 * Re ** (-0.42) * theta_f * Fp_Lp_f
    else:
        j = 0.0756 * Re ** (-0.235) * theta_f * Fp_Lp_f
    return max(j, 1e-6)


# ====================================================================
# DISPATCHER — call correlation by ID string
# ====================================================================

_J_DISPATCH = {
    # Plain (4)
    "wang2000_plain": j_wang2000_plain,
    "wang2000": j_wang2000_plain,
    "wang2000_high": j_wang2000_plain,
    "gray_webb1986": j_gray_webb1986,
    "kim1999_plain": j_kim1999_plain,
    "kayansayan1993": j_kayansayan1993,
    # Wavy (5)
    "wang1999_wavy": j_wang1999_wavy,
    "wang2002_wavy": j_wang2002_wavy,
    "beecher_fagan1987": j_beecher_fagan1987,
    "kim1997_wavy": j_kim1997_wavy,
    "jang1996_wavy": j_jang1996_wavy,
    # Louver (5)
    "wang1999_louver": j_wang1999_louver,
    "chang2000_louver": j_chang2000_louver,
    "wang2000_louver": j_wang2000_louver,
    "achaichia_cowell1988": j_achaichia_cowell1988,
    "davenport1983": j_davenport1983,
    # Slit (4)
    "wang2001_slit": j_wang2001_slit,
    "slit": j_wang2001_slit,
    "manglik_bergles1995": j_manglik_bergles1995,
    "nakayama_xu1983": j_nakayama_xu1983,
    "du_wang2000": j_du_wang2000,
    # MCHX (9)
    "chang_wang_1997": j_chang_wang1997,
    "chang_wang1997": j_chang_wang1997,
    "chang_wang2006": j_chang_wang2006,
    "kim_bullard2002": j_kim_bullard2002,
    "park_jacobi2009": j_park_jacobi2009,
    "dong2007": j_dong2007,
    "sunden_svantesson1992": j_sunden_svantesson1992,
    "webb_trauger1991": j_webb_trauger1991,
    "achaichia_cowell1988_mchx": j_achaichia_cowell1988_mchx,
    "davenport1983_mchx": j_davenport1983_mchx,
}


def compute_j_factor(corr_id: str, **kwargs) -> float:
    """Dispatch to the correct j-factor correlation by ID."""
    fn = _J_DISPATCH.get(corr_id)
    if fn is None:
        raise ValueError(f"Unknown correlation: {corr_id}. Available: {list(_J_DISPATCH.keys())}")
    return fn(**kwargs)


# ====================================================================
# AIR-SIDE f-factor — REGISTRY + ORIGINAL CORRELATIONS
# ====================================================================

FSIDE_CORRELATIONS = {
    # ── Plain ──
    "f_wang2000_plain": {
        "name": "Wang et al. (2000)",
        "ref": "IJHMT 43(15), Table 6",
        "fin_types": ["plain"],
        "Re_range": [300, 15000],
        "note": "Plain fin f-factor. Nr별 분리 모델. 원본 상관식.",
    },
    # ── Wavy ──
    "f_wang1999_wavy": {
        "name": "Wang et al. (1999)",
        "ref": "Exp. Heat Transfer 12, 73-89, Eqs.18-22",
        "fin_types": ["wavy"],
        "Re_range": [400, 8000],
        "note": "Wavy fin 원본 상관식. Pd, Xf, Ao/At, Dh 반영. 91.8% ±10%.",
    },
    "f_wang1997_wavy": {
        "name": "Wang, Fu & Chang (1997)",
        "ref": "Exp. Therm. Fluid Sci. 14(2), 174-186, Eqs.20-21",
        "fin_types": ["wavy"],
        "Re_range": [400, 8000],
        "note": "Wavy fin 간략 상관식. j=1.201/[ln(Re)]^2.921, f=16.67/[ln(Re)]^2.64.",
    },
    # ── Slit ──
    "f_wang2001_slit": {
        "name": "Wang et al. (2001)",
        "ref": "Proc. IMechE Part C, 215(9), Eqs.8-11",
        "fin_types": ["slit"],
        "Re_range": [400, 3500],
        "note": "Slit fin 원본. Fs/Dc, Pt/Pl, Ss/Sh 반영. 8.1% mean dev.",
    },
    "f_manglik_bergles1995": {
        "name": "Manglik & Bergles (1995)",
        "ref": "Exp. Therm. Fluid Sci. 10, 171-180, Eq.34",
        "fin_types": ["slit"],
        "Re_range": [120, 10000],
        "note": "OSF 범용 f-factor. α,δ,γ 기반. 원본 Fanning f on Dh basis.",
    },
    # ── Louver (FT) ──
    "f_louver_enhanced": {
        "name": "Enhanced model (f_plain × E)",
        "ref": "Semi-empirical",
        "fin_types": ["louver"],
        "Re_range": [100, 15000],
        "note": "FT louver 전용 원본 없음. plain f × Re-dependent enhancement.",
    },
    # ── MCHX ──
    "f_chang_wang1997_mchx": {
        "name": "Chang & Wang (1997)",
        "ref": "IJHMT 40(3), 533-544",
        "fin_types": ["mchx_louver"],
        "Re_range": [100, 3000],
        "note": "MCHX louver f-factor. Re_Lp 기반.",
    },
    "f_chang2000_mchx": {
        "name": "Chang et al. (2000/2006)",
        "ref": "IJHMT 43, 2237-2243 + 49, 4250-4253",
        "fin_types": ["mchx_louver"],
        "Re_range": [50, 5000],
        "note": "MCHX louver 91샘플. 3-zone 모델 (Re≤130, transition, Re≥230).",
    },
}


def get_available_f_correlations(fin_type: str) -> list:
    """Return list of f-factor correlation IDs for a fin type."""
    result = []
    ft = fin_type.lower()
    for cid, meta in FSIDE_CORRELATIONS.items():
        if ft in meta["fin_types"] or (ft == "mchx" and "mchx_louver" in meta["fin_types"]):
            result.append(cid)
    return result


def recommend_f_correlation(fin_type: str, Re_Dc: float, hx_type: str = "FT") -> dict:
    """Recommend best f-factor correlation."""
    if hx_type == "MCHX":
        fin_type = "mchx"
    available = get_available_f_correlations(fin_type)
    if not available:
        available = get_available_f_correlations("plain")

    def score(cid):
        meta = FSIDE_CORRELATIONS.get(cid, {})
        Re_lo, Re_hi = meta.get("Re_range", [0, 99999])
        re_in = 1 if Re_lo <= Re_Dc <= Re_hi else 0
        is_original = 0 if "enhanced" in cid or "Semi" in meta.get("ref", "") else 1
        return (is_original, re_in)

    ranked = sorted(available, key=score, reverse=True)
    recommended = ranked[0]
    meta = FSIDE_CORRELATIONS.get(recommended, {})

    reasons = []
    Re_lo, Re_hi = meta.get("Re_range", [0, 99999])
    if Re_lo <= Re_Dc <= Re_hi:
        reasons.append(f"Re={Re_Dc:.0f}, 유효 범위 {Re_lo}~{Re_hi} 내")
    else:
        reasons.append(f"⚠️ Re={Re_Dc:.0f}, 범위 {Re_lo}~{Re_hi} 밖")
    reasons.append(meta.get("note", ""))

    ranked_list = []
    for i, cid in enumerate(ranked):
        m = FSIDE_CORRELATIONS.get(cid, {})
        rlo, rhi = m.get("Re_range", [0, 99999])
        ranked_list.append({
            "id": cid, "rank": i + 1,
            "name": m.get("name", cid),
            "ref": m.get("ref", ""),
            "Re_range": [rlo, rhi],
            "Re_ok": rlo <= Re_Dc <= rhi,
            "note": m.get("note", ""),
            "status": "valid" if rlo <= Re_Dc <= rhi else "warning",
        })

    return {
        "recommended": recommended,
        "available": available,
        "ranked": ranked_list,
        "reasons": reasons,
    }


# ── Plain f-factor ──

def f_wang2000_plain(Re_Dc: float, Nr: int, Dc: float,
                     Pt: float, Pl: float, FPI: float,
                     fin_thickness: float, **kw) -> float:
    """Wang(2000) Table 6 — plain fin f-factor (original)."""
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    F1 = -0.764 + 0.739 * (Pt / Pl) + 0.177 * (Fp / Dc) - 0.00758 / Nr
    F2 = -15.689 + 64.021 / math.log(max(Re, 20))
    F3 = 1.696 - 15.695 / math.log(max(Re, 20))
    f = 0.0267 * Re ** F1 * (Pt / Pl) ** F2 * (Fp / Dc) ** F3

    if Re < 300:
        f_300 = 0.0267 * 300 ** F1 * (Pt / Pl) ** F2 * (Fp / Dc) ** F3
        f_lam = f_300 * (300 / Re)
        w = Re / 300
        f = (1 - w) * f_lam + w * f

    return max(f, 1e-6)


# ── Wavy f-factor (ORIGINAL from paper) ──

def f_wang1999_wavy_original(Re_Dc: float, Nr: int, Dc: float,
                              Pt: float, Pl: float, FPI: float,
                              fin_thickness: float,
                              Xa: float = 0.001, wave_length: float = 0.01,
                              **kw) -> float:
    """
    Wang et al. (1999) Exp. Heat Transfer 12, Eqs. 18-22.
    ORIGINAL wavy fin f-factor correlation.

    f = 0.05273 × Re^f1 × (Pd/Xf)^f2 × (Fp/Pt)^f3 × [ln(Ao/At)]^(-2.726)
        × (Dh/Dc)^0.1325 × N^0.02305

    Pd = 2×Xa (waffle height = 2 × amplitude)
    Xf = wave_length / 2 (projected fin pattern length for half cycle)
    Ao/At ≈ computed from geometry
    Dh = 4×Ac×L/Ao ≈ computed from geometry
    """
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)
    Pd = 2 * Xa                    # waffle height
    Xf = wave_length / 2           # projected half-wave length
    Xf = max(Xf, 1e-4)
    Pd_Xf = Pd / Xf

    # Compute Ao/At ratio from geometry
    # At = tube surface between fins ≈ π×Dc×(Fp-δf) per fin pitch per tube
    Fs = Fp - fin_thickness
    At_per = math.pi * Dc * Fs     # tube surface per fin pitch per tube
    # Af = fin area per fin pitch = 2×(Pt×Pl - π/4×Dc²) (both sides)
    Af_per = 2 * (Pt * Pl - math.pi / 4 * Dc ** 2)
    Ao_per = At_per + Af_per
    Ao_At = Ao_per / max(At_per, 1e-6)
    Ao_At = max(Ao_At, 2.0)

    # Dh/Dc
    sigma = 1 - math.pi * Dc / (2 * Pt) - fin_thickness * (Pt - Dc) / (Pt * Fp)
    sigma = max(sigma, 0.1)
    Dh = 4 * sigma * Pl / (Ao_per / (Pt * Pl))
    Dh = max(Dh, 1e-4)
    Dh_Dc = Dh / Dc

    ln_Ao_At = math.log(max(Ao_At, 1.01))

    # Exponents
    f1 = 0.1714 - 0.07372 * (Fp / Pl) ** 0.25 * ln_Ao_At * Pd_Xf ** (-0.2)
    f2 = 0.426 * (Fp / Pt) ** 0.3 * ln_Ao_At
    f3 = -10.2192 / math.log(max(Re, 20))

    f = 0.05273 * Re ** f1 * Pd_Xf ** f2 * (Fp / Pt) ** f3 * \
        ln_Ao_At ** (-2.726) * Dh_Dc ** 0.1325 * max(Nr, 1) ** 0.02305

    return max(f, 1e-6)


def f_wang1997_wavy_simple(Re_Dc: float, Nr: int, Dc: float,
                            Pt: float, Pl: float, FPI: float,
                            fin_thickness: float, **kw) -> float:
    """
    Wang, Fu & Chang (1997) Exp. Therm. Fluid Sci. 14(2), Eqs. 20-21.
    Simplified wavy fin f-factor.
    f = 16.67 / [ln(Re_Dc)]^2.64 × (Ao/At)^(-0.096) × N^0.098
    """
    Re = max(Re_Dc, 10.0)
    Fp = 0.0254 / FPI
    Fs = Fp - fin_thickness
    At_per = math.pi * Dc * Fs
    Af_per = 2 * (Pt * Pl - math.pi / 4 * Dc ** 2)
    Ao_At = (At_per + Af_per) / max(At_per, 1e-6)

    f = 16.67 / (math.log(max(Re, 20)) ** 2.64) * Ao_At ** (-0.096) * max(Nr, 1) ** 0.098
    return max(f, 1e-6)


# ── Slit f-factor (ORIGINAL from paper) ──

def f_wang2001_slit_original(Re_Dc: float, Nr: int, Dc: float,
                              Pt: float, Pl: float, FPI: float,
                              fin_thickness: float,
                              slit_height: float = 0.001,
                              slit_width: float = 0.002,
                              n_slits: int = 6, **kw) -> float:
    """
    Wang et al. (2001) Proc. IMechE Part C, 215(9), Eqs. 8-11.
    ORIGINAL slit fin f-factor (dry condition: Γ=0).

    f = 0.501 × Re^f1 × (Fs/Dc)^f2 × (Pt/Pl)^(-1.1858) × N^0.06 × (Ss/Sh)^(-0.07162)

    f1 = -0.3021 + 3.2065/√Re + 0  (dry: condensate term = 0)
    f2 = -0.2756 - 0.0044×ln(Re) - 0.0013×(Fs/Dc)
    Fs = Fp - δf, Ss = slit_height (breadth in airflow direction), Sh = slit_width (height)
    """
    Fp = 0.0254 / FPI
    Fs = Fp - fin_thickness  # fin spacing
    Re = max(Re_Dc, 10.0)

    Ss = slit_height   # breadth of slit in airflow direction
    Sh = slit_width     # height of slit
    Ss_Sh = Ss / Sh if Sh > 0 else 0.5
    Fs_Dc = Fs / Dc if Dc > 0 else 0.1

    # Dry condition: condensate film Reynolds number = 0
    f1 = -0.3021 + 3.2065 / math.sqrt(max(Re, 1))
    f2 = -0.2756 - 0.0044 * math.log(max(Re, 20)) - 0.0013 * Fs_Dc

    f = 0.501 * Re ** f1 * Fs_Dc ** f2 * (Pt / Pl) ** (-1.1858) * \
        max(Nr, 1) ** 0.06 * Ss_Sh ** (-0.07162)

    return max(f, 1e-6)


def f_manglik_bergles1995_osf(Re_Dc: float, Nr: int, Dc: float,
                               Pt: float, Pl: float, FPI: float,
                               fin_thickness: float,
                               slit_height: float = 0.001,
                               slit_width: float = 0.002,
                               n_slits: int = 6, **kw) -> float:
    """
    Manglik & Bergles (1995) Eq. 34. OSF f-factor on Dh basis,
    converted to Fanning f on A_total/A_c basis for FT-HX dp formula.

    f_Dh = 9.6243 × Re_Dh^(-0.7422) × α^(-0.1856) × δ^0.3053 × γ^(-0.2659)
           × [1 + 7.669e-8 × Re_Dh^4.429 × α^0.920 × δ^3.767 × γ^0.236]^0.1

    For dp in FT-HX: dp = f × (A_total/A_c) × G²/(2ρ)
    Need to convert M&B Fanning f (Dh basis, channel flow) to tube-bank f.
    dp_MB = f_Dh × (4L/Dh) × G²/(2ρ)
    dp_TB = f_TB × (A_total/A_c) × G²/(2ρ)
    → f_TB = f_Dh × (4L/Dh) / (A_total/A_c)
    ≈ f_Dh × (4×Nr×Pl/Dh) / (A_total/A_c)
    """
    Fp = 0.0254 / FPI
    s = slit_width; h = slit_height; t = fin_thickness; l = Fp
    Dh_osf = 4 * s * h * l / (2 * (s * l + h * l + t * h) + t * s)
    Dh_osf = max(Dh_osf, 1e-6)

    Re_Dh = Re_Dc * (Dh_osf / Dc) if Dc > 0 else Re_Dc * 0.3
    Re_Dh = max(Re_Dh, 5.0)

    alpha = s / h if h > 0 else 0.5
    delta_s = t / l if l > 0 else 0.05
    gamma = t / s if s > 0 else 0.05

    bracket = 1.0 + 7.669e-8 * Re_Dh ** 4.429 * alpha ** 0.920 * \
              delta_s ** 3.767 * gamma ** 0.236
    f_Dh = 9.6243 * Re_Dh ** (-0.7422) * alpha ** (-0.1856) * \
            delta_s ** 0.3053 * gamma ** (-0.2659) * bracket ** 0.1

    # Convert: f_TB = f_Dh × 4×Nr×Pl / (Dh_osf × A_total/A_c)
    # Approximate A_total/A_c from geo (if passed as kwarg, use it)
    Ao_Ac = kw.get("Ao_Ac", 200.0)
    L_flow = Nr * Pl
    f = f_Dh * 4 * L_flow / (Dh_osf * Ao_Ac)

    return max(f, 1e-6)


# ── Louver (FT) f-factor ──

def f_louver_enhanced(Re_Dc: float, Nr: int, Dc: float,
                      Pt: float, Pl: float, FPI: float,
                      fin_thickness: float,
                      Lp: float = 0.0017, theta: float = 27.0, **kw) -> float:
    """
    FT louver f-factor — semi-empirical enhanced model.
    No original FT-louver f-factor correlation available.
    f = f_plain × E(Re, θ, Lp, Fp)
    """
    f_plain = f_wang2000_plain(Re_Dc, Nr, Dc, Pt, Pl, FPI, fin_thickness)
    Fp = 0.0254 / FPI
    Re = max(Re_Dc, 10.0)

    if Re <= 500:
        E_base = 3.5
    elif Re <= 2000:
        E_base = 3.5 - 1.5 * (Re - 500) / 1500
    else:
        E_base = 2.0 - 0.3 * min((Re - 2000) / 5000, 1.0)

    E_theta = (theta / 27.0) ** 0.5
    Lp_Fp = Lp / Fp if Fp > 0 else 1.0
    E_Lp = (1.0 / max(Lp_Fp, 0.3)) ** 0.2

    return max(f_plain * E_base * E_theta * E_Lp, 1e-6)


# ── MCHX f-factor ──

def f_chang_wang1997_mchx(Re_Lp: float, Lp: float, theta: float,
                           Fp: float, **kw) -> float:
    """Chang & Wang (1997) f-factor for MCHX louver fin."""
    Re = max(Re_Lp, 5.0)
    f1 = -0.72 * (theta / 90) ** 0.19
    f = Re ** f1 * (theta / 90) ** 0.34 * (Fp / Lp) ** (-0.28)
    return max(f, 1e-6)


def f_chang2000_mchx(Re_Lp: float, Lp: float, theta: float,
                      Fp: float, **kw) -> float:
    """
    Chang et al. (2000) + amendment (2006).
    3-zone model: Re_Lp ≤ 130, 130 < Re_Lp < 230, Re_Lp ≥ 230.
    f = f1 × f2 × f3 (each zone-specific).
    Simplified form using Chang&Wang(1997) as base with zone blending.
    """
    Re = max(Re_Lp, 5.0)

    # Zone 1 (Re ≤ 130): stronger Re dependence
    f1_z1 = -0.72 * (theta / 90) ** 0.19
    f_low = Re ** f1_z1 * (theta / 90) ** 0.34 * (Fp / Lp) ** (-0.28) * 1.15

    # Zone 3 (Re ≥ 230): same as Chang&Wang(1997)
    f_high = Re ** f1_z1 * (theta / 90) ** 0.34 * (Fp / Lp) ** (-0.28)

    if Re <= 130:
        f = f_low
    elif Re >= 230:
        f = f_high
    else:
        # Zone 2: weighted blend (Eq. 5-6 from 2006 amendment)
        w = 3.6 - 0.02 * Re
        f = math.sqrt(((1 + w) * f_low ** 2 + (1 - w) * f_high ** 2) / 2)

    return max(f, 1e-6)


# ── f-factor DISPATCHER ──

_F_DISPATCH = {
    # Plain
    "f_wang2000_plain": f_wang2000_plain,
    # Wavy
    "f_wang1999_wavy": f_wang1999_wavy_original,
    "f_wang1997_wavy": f_wang1997_wavy_simple,
    # Slit
    "f_wang2001_slit": f_wang2001_slit_original,
    "f_manglik_bergles1995": f_manglik_bergles1995_osf,
    # Louver (FT)
    "f_louver_enhanced": f_louver_enhanced,
    # MCHX
    "f_chang_wang1997_mchx": f_chang_wang1997_mchx,
    "f_chang2000_mchx": f_chang2000_mchx,
}


def compute_f_factor(corr_id: str, **kwargs) -> float:
    """Dispatch to the correct f-factor correlation by ID."""
    fn = _F_DISPATCH.get(corr_id)
    if fn is None:
        raise ValueError(f"Unknown f-correlation: {corr_id}. Available: {list(_F_DISPATCH.keys())}")
    return fn(**kwargs)


# Legacy aliases for backward compatibility
def f_factor_wang2000_plain(Re_Dc, Nr, Dc, Pt, Pl, FPI, fin_thickness):
    return f_wang2000_plain(Re_Dc, Nr, Dc, Pt, Pl, FPI, fin_thickness)

def f_factor_chang_wang_1997(Re_Lp, Lp, theta, Fp):
    return f_chang_wang1997_mchx(Re_Lp, Lp, theta, Fp)


# ====================================================================
# REFRIGERANT-SIDE CORRELATION REGISTRY + IMPLEMENTATIONS
# ====================================================================

REFSIDE_EVAP_CORRELATIONS = {
    # ── FT (conventional tube, Dh > 3mm) ──
    "chen1966": {
        "name": "Chen (1966) — Original",
        "ref": "I&EC Proc. Des. Dev. 5(3), 322-329",
        "note": "h=F·h_l + S·h_nb. 핵비등 복원. 저건도(x<0.3) 정확.",
        "x_range": [0.01, 0.95], "hx_type": ["FT"],
    },
    "gungor_winterton1986": {
        "name": "Gungor & Winterton (1986)",
        "ref": "IJHMT 29(3), 351-358",
        "note": "E·h_l + S·h_pool. 혼합영역(0.1<x<0.8) 정확. 3693 data.",
        "x_range": [0.01, 0.95], "hx_type": ["FT"],
    },
    "kandlikar1990": {
        "name": "Kandlikar (1990)",
        "ref": "ASME J. Heat Transfer 112, 219-228",
        "note": "Co/Bo 2영역. 냉매별 Ffl. 관경 3~32mm.",
        "x_range": [0.01, 0.95], "hx_type": ["FT"],
    },
    # ── MCHX (mini/micro channel, Dh < 3mm) ──
    "kim_mudawar2013": {
        "name": "Kim & Mudawar (2013)",
        "ref": "IJHMT 64, 928-941",
        "note": "h=√(h_nb²+h_cb²). 10,805 data. 표면장력/관성 기반. 전 건도.",
        "x_range": [0.01, 0.95], "hx_type": ["MCHX"],
    },
    "bertsch2009": {
        "name": "Bertsch et al. (2009)",
        "ref": "IJHMT 52, 2110-2118",
        "note": "h=S·h_nb + F·h_conv. Confined bubble 반영. 저건도(x<0.3) 정확.",
        "x_range": [0.01, 0.95], "hx_type": ["MCHX"],
    },
    "sun_mishima2009": {
        "name": "Sun & Mishima (2009)",
        "ref": "IJHMT 52, 5323-5329",
        "note": "We/Re 기반 Lazarek-Black 수정. 2505 data. Dh 0.21~6.5mm.",
        "x_range": [0.01, 0.95], "hx_type": ["MCHX"],
    },
}

REFSIDE_COND_CORRELATIONS = {
    # ── FT (conventional tube) ──
    "shah1979": {
        "name": "Shah (1979)",
        "ref": "IJHMT 22, 547-556",
        "note": "범용. Annular(x>0.5) 정확. 474 data.",
        "x_range": [0.05, 0.99], "hx_type": ["FT"],
    },
    "cavallini2006": {
        "name": "Cavallini et al. (2006)",
        "ref": "IJHMT 49, 3309-3320",
        "note": "J_G 기반 flow regime 자동판별. 저건도(x<0.3) 정확.",
        "x_range": [0.01, 0.99], "hx_type": ["FT"],
    },
    "dobson_chato1998": {
        "name": "Dobson & Chato (1998)",
        "ref": "ASME J. Heat Transfer 120, 52-60",
        "note": "수평관 annular+stratified-wavy 분리. 중건도 정확.",
        "x_range": [0.05, 0.99], "hx_type": ["FT"],
    },
    # ── MCHX (mini/micro channel) ──
    "kim_mudawar2012": {
        "name": "Kim & Mudawar (2012)",
        "ref": "IJHMT 55, 3246-3261",
        "note": "We* annular/slug 분기. 전 건도. Dh<3mm.",
        "x_range": [0.01, 0.99], "hx_type": ["MCHX"],
    },
    "koyama2003": {
        "name": "Koyama et al. (2003)",
        "ref": "IJREFRIG 26, 38-43",
        "note": "√(h_forced² + h_grav²). 표면장력+중력. Dh 0.8~3mm.",
        "x_range": [0.01, 0.99], "hx_type": ["MCHX"],
    },
}


# ── EVAPORATION CORRELATIONS ──

def h_evap_chen1966(x, G, Di, ref, P, q_flux=5000.0, **kw):
    """
    Chen (1966) ORIGINAL — h_tp = F·h_l + S·h_nb

    h_l: Dittus-Boelter (liquid-only)
    F: Reynolds number factor (convective enhancement)
    S: Suppression factor (nucleate boiling suppressed at high Re)
    h_nb: Forster-Zuber pool boiling (simplified Cooper)
    """
    x = max(0.001, min(x, 0.999))
    mu_l = ref.mu_l(P); k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    P_r = ref.P_r(P); rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    h_fg = ref.h_fg(P); sigma_val = ref.sigma(P)
    cp_l = ref.cp_l(P); T_sat = ref.T_sat(P)

    Re_l = max(G * (1 - x) * Di / mu_l, 100)
    h_l = 0.023 * Re_l ** 0.8 * Pr_l ** 0.4 * k_l / Di

    # Lockhart-Martinelli parameter
    Xtt = ref.Xtt(x, P)
    inv_Xtt = 1.0 / max(Xtt, 1e-10)

    # F factor (Chen)
    if inv_Xtt > 0.1:
        F = 2.35 * (0.213 + inv_Xtt) ** 0.736
    else:
        F = 1.0
    F = max(F, 1.0)

    # S factor (suppression)
    Re_tp = Re_l * F ** 1.25
    S = 1.0 / (1.0 + 2.53e-6 * Re_tp ** 1.17)

    # h_nb: Cooper (1984) pool boiling (simplified, no surface roughness)
    # h_nb = 55 × P_r^(0.12) × (-log10(P_r))^(-0.55) × M^(-0.5) × q''^0.67
    # Simplified: use Forster-Zuber style scaling
    M_mol = 44.0  # approximate molecular weight
    try:
        import CoolProp.CoolProp as CP
        M_mol = CP.PropsSI("M", ref.fluid) * 1000  # kg/mol → g/mol
    except:
        pass
    log_Pr = -math.log10(max(P_r, 1e-6))
    h_pool = 55.0 * P_r ** 0.12 * max(log_Pr, 0.01) ** (-0.55) * \
             M_mol ** (-0.5) * max(q_flux, 100) ** 0.67

    h_tp = F * h_l + S * h_pool
    return max(h_tp, 100.0)


def h_evap_gungor_winterton1986(x, G, Di, ref, P, q_flux=5000.0, **kw):
    """
    Gungor & Winterton (1986) — h_tp = E·h_l + S·h_pool

    E = 1 + 24000·Bo^1.16 + 1.37·(1/Xtt)^0.86
    S = 1 / (1 + 1.15e-6 · E² · Re_l^1.17)

    Validated against 3693 data points.
    """
    x = max(0.001, min(x, 0.999))
    mu_l = ref.mu_l(P); k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    P_r = ref.P_r(P); h_fg = ref.h_fg(P)

    Re_l = max(G * (1 - x) * Di / mu_l, 100)
    h_l = 0.023 * Re_l ** 0.8 * Pr_l ** 0.4 * k_l / Di

    Bo = max(q_flux / (G * h_fg), 1e-8) if (G * h_fg) > 0 else 1e-6
    Xtt = ref.Xtt(x, P)
    inv_Xtt = 1.0 / max(Xtt, 1e-10)

    # Enhancement factor
    E = 1.0 + 24000 * Bo ** 1.16 + 1.37 * inv_Xtt ** 0.86

    # Suppression factor
    S = 1.0 / (1.0 + 1.15e-6 * E ** 2 * Re_l ** 1.17)

    # Pool boiling (Cooper 1984)
    M_mol = 44.0
    try:
        import CoolProp.CoolProp as CP
        M_mol = CP.PropsSI("M", ref.fluid) * 1000
    except:
        pass
    log_Pr = -math.log10(max(P_r, 1e-6))
    h_pool = 55.0 * P_r ** 0.12 * max(log_Pr, 0.01) ** (-0.55) * \
             M_mol ** (-0.5) * max(q_flux, 100) ** 0.67

    h_tp = E * h_l + S * h_pool
    return max(h_tp, 100.0)


def h_evap_kandlikar1990(x, G, Di, ref, P, q_flux=5000.0, **kw):
    """
    Kandlikar (1990) — Co/Bo based, two-region model.

    Convection number: Co = [(1-x)/x]^0.8 × (ρ_v/ρ_l)^0.5
    Boiling number: Bo = q'' / (G·h_fg)

    h_tp = max(h_NBD, h_CBD) × h_lo

    NBD (nucleate boiling dominant):
      h_NBD = 0.6683·Co^(-0.2)·(1-x)^0.8·f₂(Ffl) + 1058·Bo^0.7·(1-x)^0.8·Ffl
    CBD (convective boiling dominant):
      h_CBD = 1.136·Co^(-0.9)·(1-x)^0.8·f₂(Ffl) + 667.2·Bo^0.7·(1-x)^0.8·Ffl
    """
    x = max(0.001, min(x, 0.999))
    mu_l = ref.mu_l(P); k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P); h_fg = ref.h_fg(P)

    Re_lo = max(G * Di / mu_l, 100)
    h_lo = 0.023 * Re_lo ** 0.8 * Pr_l ** 0.4 * k_l / Di

    Co = ((1 - x) / x) ** 0.8 * (rho_v / rho_l) ** 0.5
    Bo = max(q_flux / (G * h_fg), 1e-8) if (G * h_fg) > 0 else 1e-6

    # Fluid-surface parameter Ffl (depends on refrigerant)
    Ffl = 1.0  # default
    fluid_upper = ref.fluid.upper() if hasattr(ref, 'fluid') else ""
    ffl_map = {"R134A": 1.63, "R410A": 1.0, "R22": 2.2, "R290": 1.1,
               "R32": 1.0, "R1234YF": 1.0, "R1234ZE(E)": 1.0, "R404A": 1.55}
    for k, v in ffl_map.items():
        if k in fluid_upper:
            Ffl = v; break

    f2 = 0.0  # for vertical: f2=0, for horizontal: f2 depends on Fr
    # Horizontal tube correction
    Fr_lo = G ** 2 / (rho_l ** 2 * 9.81 * Di) if (rho_l > 0 and Di > 0) else 100
    if Fr_lo < 0.04:
        f2 = (25 * Fr_lo) ** 0.3
    else:
        f2 = 1.0

    ox8 = (1 - x) ** 0.8

    h_NBD = (0.6683 * Co ** (-0.2) * ox8 * f2 + 1058.0 * Bo ** 0.7 * ox8 * Ffl) * h_lo
    h_CBD = (1.136 * Co ** (-0.9) * ox8 * f2 + 667.2 * Bo ** 0.7 * ox8 * Ffl) * h_lo

    return max(max(h_NBD, h_CBD), 100.0)


def h_evap_kim_mudawar_2013(x, G, Dh, q_flux, ref, P, P_H=1.0, P_F=1.0, **kw):
    """Kim & Mudawar (2013) — mini/micro channel. h_tp = √(h_nb² + h_cb²)."""
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P); mu_l = ref.mu_l(P)
    k_l = ref.k_l(P); Pr_l = ref.Pr_l(P); h_fg = ref.h_fg(P)
    sigma_val = ref.sigma(P); P_r = ref.P_r(P)
    Re_fo = max(G * Dh / mu_l, 100)
    h_f = 0.023 * Re_fo ** 0.8 * Pr_l ** 0.4 * k_l / Dh
    Bo = max(q_flux / (G * h_fg), 1e-8) if (G * h_fg) > 0 else 1e-6
    We_fo = G ** 2 * Dh / (rho_l * sigma_val) if (rho_l * sigma_val) > 0 else 100
    Xtt = ref.Xtt(x, P)
    pr = P_H / P_F if P_F > 0 else 0.75
    h_nb = 2345 * (Bo * pr) ** 0.7 * P_r ** 0.38 * (1 - x) ** (-0.51) * h_f
    h_cb = (5.2 * (Bo * pr) ** 0.08 * We_fo ** (-0.54) +
            3.5 / max(Xtt, 1e-6) ** 0.94 * (rho_v / rho_l) ** 0.25) * h_f
    return max(math.sqrt(h_nb ** 2 + h_cb ** 2), 100.0)


def h_evap_bertsch2009(x, G, Di, ref, P, q_flux=5000.0, **kw):
    """
    Bertsch et al. (2009) — Mini/micro channel evaporation.
    h_tp = S·h_nb + F·h_conv_tp

    h_conv_tp = h_l·(1-x) + h_v·x  (liquid/vapor weighted average)
    S = f(Co_conf) — suppression, decreases with Re
    F = 1 + a·(Co_conf) — enhancement from confined bubble
    """
    x = max(0.001, min(x, 0.999))
    Dh = kw.get("Dh", Di)
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    k_l = ref.k_l(P); k_v = ref.k_v(P)
    Pr_l = ref.Pr_l(P); Pr_v = ref.Pr_v(P)
    P_r = ref.P_r(P)
    h_fg = ref.h_fg(P); sigma_val = ref.sigma(P)

    # Confinement number
    Co_conf = (sigma_val / (9.81 * max(rho_l - rho_v, 0.1) * Dh ** 2)) ** 0.5 \
        if Dh > 0 else 1.0

    # Single-phase liquid & vapor HTC
    Re_l = max(G * (1 - x) * Dh / mu_l, 100)
    Re_v = max(G * x * Dh / mu_v, 100)
    h_l = 0.023 * Re_l ** 0.8 * Pr_l ** 0.4 * k_l / Dh
    h_v = 0.023 * Re_v ** 0.8 * Pr_v ** 0.4 * k_v / Dh

    # Two-phase convective: weighted average
    h_conv_tp = h_l * (1 - x) + h_v * x

    # Pool boiling (Cooper 1984)
    M_mol = 44.0
    try:
        import CoolProp.CoolProp as CP
        M_mol = CP.PropsSI("M", ref.fluid) * 1000
    except: pass
    log_Pr = -math.log10(max(P_r, 1e-6))
    h_nb = 55.0 * P_r ** 0.12 * max(log_Pr, 0.01) ** (-0.55) * \
           M_mol ** (-0.5) * max(q_flux, 100) ** 0.67

    # Suppression factor: decreases as Re increases
    Re_tp = G * Dh / mu_l
    S = (1 - x) / (1 + 2.56e-6 * Re_tp ** 1.17)
    S = max(S, 0.01)

    # Enhancement factor: confined bubble promotes convection
    F = 1 + 80 * (x ** 2 - x ** 6) * math.exp(-0.6 * Co_conf)

    h_tp = S * h_nb + F * h_conv_tp
    return max(h_tp, 100.0)


def h_evap_sun_mishima2009(x, G, Di, ref, P, q_flux=5000.0, **kw):
    """
    Sun & Mishima (2009) — Modified Lazarek-Black for mini/micro channels.
    Based on 2505 data points, Dh = 0.21~6.5 mm.

    h_tp = 6 × Re_l^1.05 × Bo^0.54 × (We_l)^(-0.191) × (ρ_l/ρ_v)^(-0.142) × k_l/Dh

    where Re_l = G(1-x)Dh/μ_l, We_l = G²(1-x)²Dh/(ρ_l·σ)
    """
    x = max(0.001, min(x, 0.999))
    Dh = kw.get("Dh", Di)
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); k_l = ref.k_l(P)
    h_fg = ref.h_fg(P); sigma_val = ref.sigma(P)

    Re_l = max(G * (1 - x) * Dh / mu_l, 10)
    Bo = max(q_flux / (G * h_fg), 1e-8) if (G * h_fg) > 0 else 1e-6
    We_l = G ** 2 * (1 - x) ** 2 * Dh / (rho_l * sigma_val) if (rho_l * sigma_val) > 0 else 100
    rho_ratio = rho_l / max(rho_v, 0.1)

    Nu = 6.0 * Re_l ** 1.05 * Bo ** 0.54 * max(We_l, 0.01) ** (-0.191) * rho_ratio ** (-0.142)

    h = Nu * k_l / Dh
    return max(h, 100.0)


# ── Dryout model ──

def dryout_factor(x, G, Di, ref, P):
    """
    Dryout quality estimation and h reduction.
    Based on Wojtan et al. (2005) simplified approach.

    x_di: dryout inception quality
    x_de: dryout completion quality
    Between x_di and x_de: linear interpolation of h
    Above x_de: vapor-phase h only
    """
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    sigma_val = ref.sigma(P); h_fg = ref.h_fg(P)
    Di_mm = Di * 1000

    # Simplified dryout inception (Wojtan 2005 / Thome 2004)
    # x_di depends on G, Di, fluid — higher G → higher x_di
    We_l = G ** 2 * Di / (rho_l * sigma_val) if (rho_l * sigma_val) > 0 else 100
    # Approximate: x_di ≈ 0.58 + 0.002×(G-200) for Di~5-10mm
    x_di = 0.80 + 0.15 * math.tanh((G - 300) / 200)
    x_di = max(0.5, min(x_di, 0.95))

    x_de = min(x_di + 0.10, 0.99)  # dryout completion

    if x <= x_di:
        return 1.0, x_di, x_de  # no dryout
    elif x >= x_de:
        return 0.0, x_di, x_de  # full dryout → use vapor h
    else:
        # Linear interpolation
        frac = (x - x_di) / (x_de - x_di)
        return 1.0 - frac, x_di, x_de


# ── CONDENSATION CORRELATIONS ──

def h_cond_shah1979(x, G, Di, ref, P, **kw):
    """Shah (1979) — original form with corrected expression."""
    x = max(0.001, min(x, 0.999))
    mu_l = ref.mu_l(P); k_l = ref.k_l(P); Pr_l = ref.Pr_l(P); P_r = ref.P_r(P)
    Re_lo = max(G * Di / mu_l, 100)
    h_lo = 0.023 * Re_lo ** 0.8 * Pr_l ** 0.4 * k_l / Di

    # Shah correlation: h = h_lo × [(1-x)^0.8 + 3.8×x^0.76×(1-x)^0.04 / P_r^0.38]
    h = h_lo * ((1 - x) ** 0.8 + 3.8 * x ** 0.76 * (1 - x) ** 0.04 / max(P_r, 0.001) ** 0.38)
    return max(h, 100.0)


def h_cond_cavallini2006(x, G, Di, ref, P, **kw):
    """
    Cavallini et al. (2006) — Flow regime dependent.

    Two regimes separated by J_G_T (dimensionless vapor velocity transition):
    - ΔT-independent (annular): high vapor velocity
    - ΔT-dependent (stratified/slug): low vapor velocity, gravity effects

    J_G = x·G / [g·Di·ρ_v·(ρ_l-ρ_v)]^0.5
    J_G_T = [(7.5 / (4.3·Xtt^1.111 + 1))^(-3) + C_T^(-3)]^(-1/3)
    """
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    cp_l = ref.cp_l(P); h_fg = ref.h_fg(P)

    g = 9.81
    Re_lo = max(G * Di / mu_l, 100)
    h_lo = 0.023 * Re_lo ** 0.8 * Pr_l ** 0.4 * k_l / Di

    Xtt = ref.Xtt(x, P)

    # Dimensionless vapor velocity
    denom = max(g * Di * rho_v * (rho_l - rho_v), 1e-6) ** 0.5
    J_G = x * G / denom

    # Transition criterion
    C_T = 1.6 if rho_l / rho_v > 6 else 2.6
    J_G_T_inner = (7.5 / (4.3 * Xtt ** 1.111 + 1)) ** (-3) + C_T ** (-3)
    J_G_T = J_G_T_inner ** (-1.0 / 3.0)

    if J_G >= J_G_T:
        # ΔT-independent regime (annular)
        # h_A = h_lo × [1 + 1.128·x^0.817·(ρ_l/ρ_v)^0.3685·(μ_l/μ_v)^0.2363·(1-μ_v/μ_l)^2.144·Pr_l^(-0.1)]
        mu_ratio = mu_l / mu_v if mu_v > 0 else 10
        rho_ratio = rho_l / rho_v if rho_v > 0 else 10
        h_A = h_lo * (1 + 1.128 * x ** 0.817 * rho_ratio ** 0.3685 *
                       mu_ratio ** 0.2363 * max(1 - mu_v / mu_l, 0.01) ** 2.144 *
                       Pr_l ** (-0.1))
        return max(h_A, 100.0)
    else:
        # ΔT-dependent regime (stratified/wavy)
        # h_strat from Nusselt film condensation + forced convection
        h_A_T = h_lo * (1 + 1.128 * x ** 0.817 * (rho_l / max(rho_v, 0.1)) ** 0.3685 *
                         (mu_l / max(mu_v, 1e-7)) ** 0.2363 *
                         max(1 - mu_v / mu_l, 0.01) ** 2.144 * Pr_l ** (-0.1))

        # Film condensation contribution
        T_sat = ref.T_sat(P)
        dT_film = max(kw.get("dT_wall", 5.0), 0.5)  # wall subcooling estimate
        h_strat = 0.725 * (g * rho_l * (rho_l - rho_v) * k_l ** 3 * h_fg /
                           (mu_l * Di * dT_film)) ** 0.25 if (mu_l * Di * dT_film) > 0 else h_lo

        # Blend at transition: use J_G/J_G_T ratio
        ratio = J_G / max(J_G_T, 1e-6)
        h_D = h_A_T * ratio ** 0.8 + h_strat * (1 - ratio ** 0.8)
        return max(h_D, 100.0)


def h_cond_dobson_chato1998(x, G, Di, ref, P, **kw):
    """
    Dobson & Chato (1998) — Horizontal tube condensation.
    Annular flow (x > x_transition) + Stratified-wavy (x < x_transition).
    """
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    g = 9.81

    Re_l = max(G * (1 - x) * Di / mu_l, 100)
    Xtt = ref.Xtt(x, P)

    # Froude number for transition
    Fr_so = 0.025 * Re_l ** 1.59 * (1.0 / max(1 + 1.09 * Xtt ** 0.039, 1)) / \
            max((rho_l / rho_v) ** 1.5 * (9.81 * Di ** 3 * rho_l ** 2 / mu_l ** 2), 1)

    # Annular flow correlation (Dobson)
    h_l = 0.023 * Re_l ** 0.8 * Pr_l ** 0.4 * k_l / Di
    h_ann = h_l * (2.22 / max(Xtt, 0.01) ** 0.89 + 1)

    # Stratified-wavy correction for low x
    Ga = g * rho_l * (rho_l - rho_v) * Di ** 3 / mu_l ** 2 if mu_l > 0 else 1e10
    Ja = cp_l = ref.cp_l(P)  # just use cp_l as proxy for Ja effect

    # Simple: use annular for x > 0.3, stratified blend below
    if x > 0.3:
        return max(h_ann, 100.0)
    else:
        # Nusselt film + forced convection blend
        h_fg = ref.h_fg(P)
        dT = max(kw.get("dT_wall", 5.0), 0.5)
        h_film = 0.555 * (g * rho_l * (rho_l - rho_v) * k_l ** 3 * h_fg /
                          (mu_l * Di * dT)) ** 0.25 if (mu_l * Di * dT) > 0 else h_l
        w = x / 0.3
        return max(w * h_ann + (1 - w) * h_film, 100.0)


def h_cond_kim_mudawar_2012(x, G, Dh, ref, P, **kw):
    """Kim & Mudawar (2012) — mini/micro channel condensation."""
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    k_l = ref.k_l(P); Pr_l = ref.Pr_l(P); sigma_val = ref.sigma(P)
    Re_l = max(G * (1 - x) * Dh / mu_l, 10)
    Re_v = max(G * x * Dh / mu_v, 10)
    h_f = 0.023 * (G * Dh / mu_l) ** 0.8 * Pr_l ** 0.4 * k_l / Dh
    We_star = 2.45 * (mu_v / mu_l) ** 0.64 * (rho_v / rho_l) ** 0.3 * Re_v ** 0.79
    We_lo = G ** 2 * Dh / (rho_l * sigma_val) if (rho_l * sigma_val) > 0 else 100
    Xtt = ref.Xtt(x, P)
    h_ann = h_f * 0.048 * Re_l ** 0.69 * Pr_l ** 0.34 * (rho_v / rho_l) ** 0.12 / max(Xtt, 0.01) ** 0.5
    if We_star > We_lo:
        return max(h_ann, 100.0)
    h_slug = (h_ann ** 2 + (h_f * 5.7 * (rho_l * sigma_val * Dh / mu_l ** 2) ** 0.25) ** 2) ** 0.5
    return max(h_slug, 100.0)


def h_cond_koyama2003(x, G, Di, ref, P, **kw):
    """
    Koyama et al. (2003) — Multi-port mini-channel condensation.
    h = √(h_forced² + h_grav²)

    h_forced: shear-driven (annular film) — dominates at high x
    h_grav: gravity-driven (film drainage) — dominates at low x

    Validated for R134a in Dh = 0.8~1.11mm multi-port tubes.
    """
    x = max(0.001, min(x, 0.999))
    Dh = kw.get("Dh", Di)
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    k_l = ref.k_l(P); Pr_l = ref.Pr_l(P)
    h_fg = ref.h_fg(P)
    g = 9.81

    # Void fraction (Zivi 1964 — simple slip-ratio model)
    Sr = (rho_l / max(rho_v, 0.1)) ** (1.0 / 3.0)
    alpha_void = 1.0 / (1.0 + Sr * (1 - x) / max(x, 0.001) * rho_v / rho_l)
    alpha_void = max(0.01, min(alpha_void, 0.999))

    # Liquid Reynolds number (annular film)
    Re_l = max(G * (1 - x) * Dh / mu_l, 10)

    # Lockhart-Martinelli
    Xtt = ref.Xtt(x, P)

    # Two-phase multiplier (Koyama)
    phi_v_sq = 1 + 21 * (1 - math.exp(-0.319 * Dh * 1000)) / max(Xtt, 0.01) + 1 / max(Xtt ** 2, 1e-6)

    # Forced convection component
    f_l = 0.079 / max(Re_l, 10) ** 0.25 if Re_l > 0 else 0.01
    h_forced = 0.0152 * Re_l ** 0.77 * Pr_l ** (1.0 / 3.0) * phi_v_sq ** 0.5 * k_l / Dh

    # Gravity component (film condensation in tube)
    Ga = g * rho_l * (rho_l - rho_v) * Dh ** 3 / mu_l ** 2 if mu_l > 0 else 1e10
    Ja_inv = h_fg / (ref.cp_l(P) * max(kw.get("dT_wall", 5.0), 0.5))  # inverse Jakob
    h_grav = 0.725 * (Ga * Pr_l * Ja_inv) ** 0.25 * alpha_void ** (-0.5) * k_l / Dh

    h = math.sqrt(h_forced ** 2 + h_grav ** 2)
    return max(h, 100.0)


# ── SINGLE PHASE ──

def h_single_gnielinski(Re, Pr, k, Di):
    """Gnielinski (1976) — turbulent + laminar."""
    if Re < 2300:
        return 3.66 * k / Di
    f = (0.790 * math.log(Re) - 1.64) ** (-2)
    Nu = max((f / 8) * (Re - 1000) * Pr / (1 + 12.7 * math.sqrt(f / 8) * (Pr ** (2/3) - 1)), 3.66)
    return Nu * k / Di


# ====================================================================
# REFRIGERANT-SIDE PRESSURE DROP
# ====================================================================

REFSIDE_DP_CORRELATIONS = {
    # ── FT (conventional tube) ──
    "friedel1979": {
        "name": "Friedel (1979)",
        "ref": "European Two-Phase Flow Group Meeting, Ispra",
        "note": "가장 범용. 25000+ data. μ_l/μ_v<1000, 전건도.",
        "hx_type": ["FT", "MCHX"],
    },
    "lockhart_martinelli1949": {
        "name": "Lockhart-Martinelli (1949)",
        "ref": "Chem. Eng. Prog. 45(1), 39-48",
        "note": "고전. Chisholm C계수. 단순하지만 저건도 과대예측.",
        "hx_type": ["FT"],
    },
    "muller_steinhagen1986": {
        "name": "Müller-Steinhagen & Heck (1986)",
        "ref": "Can. J. Chem. Eng. 64, 297-304",
        "note": "단순+정확. 9300 data. 고건도에서도 안정적.",
        "hx_type": ["FT", "MCHX"],
    },
    "kim_mudawar_dp2012": {
        "name": "Kim & Mudawar (2012) dp",
        "ref": "IJHMT 55, 3246-3261",
        "note": "미니채널 전용. Suratman 기반 C계수. Dh<3mm.",
        "hx_type": ["MCHX"],
    },
}


def _f_darcy(Re, Di, roughness=1.5e-6):
    """Churchill (1977) friction factor — all regimes."""
    if Re < 10:
        return 64.0 / max(Re, 1)
    e_D = roughness / Di
    A = (2.457 * math.log(1.0 / ((7.0 / Re) ** 0.9 + 0.27 * e_D))) ** 16
    B = (37530.0 / Re) ** 16
    f = 8 * ((8.0 / Re) ** 12 + 1.0 / (A + B) ** 1.5) ** (1.0 / 12.0)
    return f


def dp_single_phase(G, Di, L, ref, P, x_or_phase="liquid"):
    """Single-phase frictional dp [Pa] for a tube segment."""
    if x_or_phase == "liquid" or x_or_phase == "l":
        mu = ref.mu_l(P); rho = ref.rho_l(P)
    else:
        mu = ref.mu_v(P); rho = ref.rho_v(P)
    Re = max(G * Di / mu, 10) if mu > 0 else 100
    f = _f_darcy(Re, Di)
    dp = f * L / Di * G ** 2 / (2 * rho) if (Di > 0 and rho > 0) else 0
    return max(dp, 0)


def dp_friedel1979(x, G, Di, L, ref, P, **kw):
    """
    Friedel (1979) — Two-phase frictional pressure drop.
    
    dp_tp = dp_lo × φ²_lo
    φ²_lo = E + 3.24·F·H / (Fr^0.045 · We^0.035)
    
    E = (1-x)² + x²·(ρ_l·f_vo)/(ρ_v·f_lo)
    F = x^0.78 · (1-x)^0.224
    H = (ρ_l/ρ_v)^0.91 · (μ_v/μ_l)^0.19 · (1-μ_v/μ_l)^0.7
    """
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    sigma_val = ref.sigma(P)

    Re_lo = max(G * Di / mu_l, 10)
    Re_vo = max(G * Di / mu_v, 10)
    f_lo = _f_darcy(Re_lo, Di)
    f_vo = _f_darcy(Re_vo, Di)

    # dp_lo (all liquid)
    dp_lo = f_lo * L / Di * G ** 2 / (2 * rho_l) if (Di > 0 and rho_l > 0) else 0

    # Void fraction (homogeneous for Fr/We)
    rho_tp = 1.0 / (x / rho_v + (1 - x) / rho_l) if (rho_v > 0 and rho_l > 0) else rho_l

    # Froude number
    Fr = G ** 2 / (9.81 * Di * rho_tp ** 2) if (Di > 0 and rho_tp > 0) else 100
    # Weber number
    We = G ** 2 * Di / (rho_tp * sigma_val) if (rho_tp > 0 and sigma_val > 0) else 100

    E = (1 - x) ** 2 + x ** 2 * (rho_l * f_vo) / max(rho_v * f_lo, 1e-10)
    F_val = x ** 0.78 * (1 - x) ** 0.224
    mu_ratio = mu_v / mu_l if mu_l > 0 else 0.1
    rho_ratio = rho_l / max(rho_v, 0.1)
    H = rho_ratio ** 0.91 * mu_ratio ** 0.19 * max(1 - mu_ratio, 0.01) ** 0.7

    phi2 = E + 3.24 * F_val * H / (max(Fr, 0.01) ** 0.045 * max(We, 0.01) ** 0.035)
    return max(dp_lo * phi2, 0)


def dp_lockhart_martinelli1949(x, G, Di, L, ref, P, **kw):
    """
    Lockhart-Martinelli (1949) with Chisholm C parameter.
    
    φ²_l = 1 + C/Xtt + 1/Xtt²
    C = 20 (turbulent-turbulent), 12 (laminar-turbulent), etc.
    dp_tp = dp_l × φ²_l
    """
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); mu_l = ref.mu_l(P)

    Re_l = max(G * (1 - x) * Di / mu_l, 10)
    f_l = _f_darcy(Re_l, Di)
    dp_l = f_l * L / Di * (G * (1 - x)) ** 2 / (2 * rho_l) if (Di > 0 and rho_l > 0) else 0

    Xtt = ref.Xtt(x, P)

    # Chisholm C parameter
    Re_v = max(G * x * Di / ref.mu_v(P), 10) if ref.mu_v(P) > 0 else 100
    if Re_l > 2300 and Re_v > 2300:
        C = 20
    elif Re_l < 2300 and Re_v > 2300:
        C = 12
    elif Re_l > 2300 and Re_v < 2300:
        C = 10
    else:
        C = 5

    phi2_l = 1 + C / max(Xtt, 0.001) + 1 / max(Xtt ** 2, 1e-6)
    return max(dp_l * phi2_l, 0)


def dp_muller_steinhagen1986(x, G, Di, L, ref, P, **kw):
    """
    Müller-Steinhagen & Heck (1986) — Simple + accurate.
    
    (dp/dz)_tp = A·(1-x)^(1/3) + B·x³
    A = (dp/dz)_lo + 2·[(dp/dz)_vo - (dp/dz)_lo]·x
    B = (dp/dz)_vo
    """
    x = max(0.001, min(x, 0.999))
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)

    Re_lo = max(G * Di / mu_l, 10)
    Re_vo = max(G * Di / mu_v, 10)
    f_lo = _f_darcy(Re_lo, Di)
    f_vo = _f_darcy(Re_vo, Di)

    dpdz_lo = f_lo / Di * G ** 2 / (2 * rho_l) if (Di > 0 and rho_l > 0) else 0
    dpdz_vo = f_vo / Di * G ** 2 / (2 * rho_v) if (Di > 0 and rho_v > 0) else 0

    A = dpdz_lo + 2 * (dpdz_vo - dpdz_lo) * x
    B = dpdz_vo

    dpdz_tp = A * (1 - x) ** (1.0 / 3.0) + B * x ** 3
    return max(dpdz_tp * L, 0)


def dp_kim_mudawar_dp2012(x, G, Di, L, ref, P, **kw):
    """
    Kim & Mudawar (2012) dp — Mini/micro channel.
    Suratman-number based C coefficient in L-M framework.
    
    φ²_l = 1 + C/Xtt + 1/Xtt²
    C depends on laminar/turbulent regime + Su_vo
    """
    x = max(0.001, min(x, 0.999))
    Dh = kw.get("Dh", Di)
    rho_l = ref.rho_l(P); rho_v = ref.rho_v(P)
    mu_l = ref.mu_l(P); mu_v = ref.mu_v(P)
    sigma_val = ref.sigma(P)

    Re_l = max(G * (1 - x) * Dh / mu_l, 10)
    Re_v = max(G * x * Dh / mu_v, 10)

    # Suratman number (liquid)
    Su_vo = rho_v * sigma_val * Dh / mu_v ** 2 if mu_v > 0 else 1e6

    # C coefficient based on flow regime
    if Re_l >= 2000 and Re_v >= 2000:
        C = 0.39 * Re_lo_val ** 0.03 if False else 0.39 * (Re_l / (1 - x)) ** 0.03 * Su_vo ** 0.10 * (rho_l / rho_v) ** 0.35
    elif Re_l < 2000 and Re_v >= 2000:
        C = 8.7e-4 * (Re_l / (1 - x)) ** 0.17 * Su_vo ** 0.50 * (rho_l / rho_v) ** 0.14
    elif Re_l >= 2000 and Re_v < 2000:
        C = 0.0015 * (Re_l / (1 - x)) ** 0.59 * Su_vo ** 0.19 * (rho_l / rho_v) ** 0.36
    else:
        C = 3.5e-5 * (Re_l / max(1 - x, 0.001)) ** 0.44 * Su_vo ** 0.50 * (rho_l / rho_v) ** 0.48

    f_l = _f_darcy(Re_l, Dh)
    dp_l = f_l * L / Dh * (G * (1 - x)) ** 2 / (2 * rho_l) if (Dh > 0 and rho_l > 0) else 0
    Xtt = ref.Xtt(x, P)
    phi2_l = 1 + C / max(Xtt, 0.001) + 1 / max(Xtt ** 2, 1e-6)
    return max(dp_l * phi2_l, 0)


# ── DP DISPATCHER ──

_DP_DISPATCH = {
    "friedel1979": dp_friedel1979,
    "lockhart_martinelli1949": dp_lockhart_martinelli1949,
    "muller_steinhagen1986": dp_muller_steinhagen1986,
    "kim_mudawar_dp2012": dp_kim_mudawar_dp2012,
}


def compute_dp_ref_seg(corr_id, x, G, Di, L, ref, P, **kw):
    """Compute refrigerant dp [Pa] for one segment."""
    if x > 1.0 or x < 0.0:
        phase = "vapor" if x > 1 else "liquid"
        return dp_single_phase(G, Di, L, ref, P, phase)
    fn = _DP_DISPATCH.get(corr_id, dp_friedel1979)
    return fn(x=x, G=G, Di=Di, L=L, ref=ref, P=P, **kw)


def recommend_dp_ref_correlation(hx_type="FT"):
    """Recommend dp correlation."""
    if hx_type == "MCHX":
        return "kim_mudawar_dp2012"
    return "friedel1979"


def get_available_dp_correlations(hx_type="FT"):
    """Get available dp correlations filtered by hx_type."""
    return [k for k, v in REFSIDE_DP_CORRELATIONS.items()
            if hx_type in v.get("hx_type", ["FT", "MCHX"])]

_EVAP_DISPATCH = {
    "chen1966": h_evap_chen1966,
    "gungor_winterton1986": h_evap_gungor_winterton1986,
    "kandlikar1990": h_evap_kandlikar1990,
    "kim_mudawar2013": h_evap_kim_mudawar_2013,
    "bertsch2009": h_evap_bertsch2009,
    "sun_mishima2009": h_evap_sun_mishima2009,
}

_COND_DISPATCH = {
    "shah1979": h_cond_shah1979,
    "cavallini2006": h_cond_cavallini2006,
    "dobson_chato1998": h_cond_dobson_chato1998,
    "kim_mudawar2012": h_cond_kim_mudawar_2012,
    "koyama2003": h_cond_koyama2003,
}


def compute_h_evap(corr_id, x, G, Di, ref, P, q_flux=5000.0, **kw):
    """Compute evaporation h with optional dryout."""
    fn = _EVAP_DISPATCH.get(corr_id)
    if fn is None:
        fn = h_evap_chen1966
    h = fn(x=x, G=G, Di=Di, ref=ref, P=P, q_flux=q_flux, **kw)

    # Apply dryout reduction
    if kw.get("apply_dryout", True) and x > 0.5:
        factor, x_di, x_de = dryout_factor(x, G, Di, ref, P)
        if factor < 1.0:
            T_sat = ref.T_sat(P)
            pv = ref.props_single(T_sat + 2.0, P)
            h_v = h_single_gnielinski(G * Di / pv["mu"], pv["Pr"], pv["k"], Di)
            h = factor * h + (1 - factor) * h_v
    return max(h, 50.0)


def compute_h_cond(corr_id, x, G, Di, ref, P, **kw):
    """Compute condensation h."""
    fn = _COND_DISPATCH.get(corr_id)
    if fn is None:
        fn = h_cond_shah1979
    return max(fn(x=x, G=G, Di=Di, ref=ref, P=P, **kw), 50.0)


def recommend_ref_correlation(mode, x, G, Di, hx_type="FT"):
    """Recommend best refrigerant-side correlation based on quality, geometry, and HX type."""
    if mode == "evap":
        if hx_type == "MCHX" or Di < 0.003:
            # MCHX: surface tension dominant, confined bubble
            if x < 0.3:
                return "bertsch2009"      # confined bubble, nucleate boiling
            elif x < 0.7:
                return "kim_mudawar2013"  # best overall for mini-ch
            else:
                return "sun_mishima2009"  # We-based, high quality
        else:
            # FT: gravity dominant, conventional tube
            if x < 0.3:
                return "chen1966"               # nucleate boiling dominant
            elif x < 0.8:
                return "gungor_winterton1986"    # mixed region
            else:
                return "kandlikar1990"           # high quality
    else:  # cond
        if hx_type == "MCHX" or Di < 0.003:
            if x < 0.4:
                return "koyama2003"       # gravity term important at low x
            else:
                return "kim_mudawar2012"  # annular shear dominant
        else:
            if x > 0.5:
                return "shah1979"         # annular, Shah is good
            else:
                return "cavallini2006"    # stratified, Cavallini better


# ====================================================================
# TRANSITION BLENDING — updated with dryout
# ====================================================================

def h_with_transition(x, G, Di, q_flux, ref, P,
                      mode="evap", hx_type="FT", P_H=1.0, P_F=1.0,
                      evap_corr=None, cond_corr=None):
    """h_i with transition blending at x boundaries and dryout."""
    T_sat = ref.T_sat(P)

    # Determine correlation
    if evap_corr is None:
        evap_corr = "kim_mudawar2013" if (hx_type == "MCHX" or Di < 0.003) else "chen1966"
    if cond_corr is None:
        cond_corr = "kim_mudawar2012" if (hx_type == "MCHX" or Di < 0.003) else "shah1979"

    if mode == "evap":
        if 0.0 < x < 0.90:
            return compute_h_evap(evap_corr, x, G, Di, ref, P, q_flux,
                                  P_H=P_H, P_F=P_F, Dh=Di)
        elif 0.90 <= x <= 1.05:
            x_2ph = min(x, 0.999)
            h_2ph = compute_h_evap(evap_corr, x_2ph, G, Di, ref, P, q_flux,
                                   P_H=P_H, P_F=P_F, Dh=Di)
            pv = ref.props_single(T_sat + 1.0, P)
            h_v = h_single_gnielinski(G * Di / pv["mu"], pv["Pr"], pv["k"], Di)
            w = max(0, min((x - 0.90) / 0.15, 1))
            return (1 - w) * h_2ph + w * h_v
        elif x > 1.05:
            pv = ref.props_single(T_sat + 5.0, P)
            return h_single_gnielinski(G * Di / pv["mu"], pv["Pr"], pv["k"], Di)
        else:
            pl = ref.props_single(T_sat - 5.0, P)
            return h_single_gnielinski(G * Di / pl["mu"], pl["Pr"], pl["k"], Di)
    else:
        if 0.05 < x < 1.0:
            return compute_h_cond(cond_corr, x, G, Di, ref, P, Dh=Di)
        elif 0.0 <= x <= 0.05:
            x_2ph = max(x, 0.001)
            h_2ph = compute_h_cond(cond_corr, x_2ph, G, Di, ref, P, Dh=Di)
            pl = ref.props_single(T_sat - 1.0, P)
            h_sub = h_single_gnielinski(G * Di / pl["mu"], pl["Pr"], pl["k"], Di)
            w = max(0, min((0.05 - x) / 0.05, 1))
            return (1 - w) * h_2ph + w * h_sub
        elif x < 0:
            pl = ref.props_single(T_sat - 5.0, P)
            return h_single_gnielinski(G * Di / pl["mu"], pl["Pr"], pl["k"], Di)
        else:
            pv = ref.props_single(T_sat + 1.0, P)
            return h_single_gnielinski(G * Di / pv["mu"], pv["Pr"], pv["k"], Di)


# ====================================================================
# AUTO-SELECTION (backward compatible)
# ====================================================================

def select_correlations(hx_type, Di, fin_type="plain", Pt=0.0254, Pl=0.022):
    """Legacy auto-select. Returns dict with default correlation IDs."""
    result = {"single_phase": "gnielinski"}
    if hx_type == "FT":
        if fin_type == "plain":
            result["air_j"] = "wang2000_plain"
        elif fin_type == "wavy":
            result["air_j"] = "wang2002_wavy"
        elif fin_type == "louver":
            result["air_j"] = "chang2000_louver"
        elif fin_type == "slit":
            result["air_j"] = "wang2001_slit"
        else:
            result["air_j"] = "wang2000_plain"
        result["evap"] = "chen1966"
        result["cond"] = "shah1979"
    elif hx_type == "MCHX":
        result["air_j"] = "chang_wang2006"
        result["evap"] = "kim_mudawar2013" if Di < 0.003 else "chen1966"
        result["cond"] = "kim_mudawar2012" if Di < 0.003 else "shah1979"
    return result


def get_available_ref_correlations(mode, hx_type="FT"):
    """Get available refrigerant correlations filtered by mode and hx_type."""
    registry = REFSIDE_EVAP_CORRELATIONS if mode == "evap" else REFSIDE_COND_CORRELATIONS
    return [cid for cid, info in registry.items()
            if hx_type in info.get("hx_type", ["FT", "MCHX"])]
