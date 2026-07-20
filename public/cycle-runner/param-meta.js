// 자동생성 — backend modelDescription/source에서 추출 (fidelity별 설계변수 메타)
// 6단계 백엔드 연결 시 GET /component_params API로 대체 예정
window.COMPONENT_PARAM_META = {
"compressor": {
"1": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf"
]
},
{
"name": "V_disp",
"start": 7.5,
"unit": "cm³",
"group": "Geometry",
"desc": "행정체적 (도면 초안에서 대략)",
"type": "Real"
},
{
"name": "eta_vol",
"start": 0.88,
"unit": "-",
"group": "Fitting",
"desc": "체적효율 (추정 ~0.85)",
"type": "Real"
},
{
"name": "eta_isen",
"start": 0.68,
"unit": "-",
"group": "Fitting",
"desc": "등엔트로피효율 (추정 ~0.65)",
"type": "Real"
}
],
"2": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290"
]
},
{
"name": "comp_type",
"start": "reciprocating",
"unit": "-",
"group": "Material",
"desc": "압축기 형태 (정보용 — 알고리즘은 동일)",
"type": "String",
"options": [
"reciprocating",
"scroll"
]
},
{
"name": "T_amb",
"start": 25.0,
"unit": "°C",
"group": "Operating",
"desc": "주변 공기 온도 (외부 열손실 기준)",
"type": "Real"
},
{
"name": "V_disp",
"start": 7.5,
"unit": "cm³",
"group": "Geometry",
"desc": "행정 체적 (배제 용적)",
"type": "Real"
},
{
"name": "rv_in",
"start": 2.5,
"unit": "-",
"group": "Geometry",
"desc": "내부 체적비 (built-in volume ratio)",
"type": "Real"
},
{
"name": "eta_motor",
"start": 0.9,
"unit": "-",
"group": "Geometry",
"desc": "모터 효율 (정격, fitting 가능하지만 보통 데이터시트값)",
"type": "Real"
},
{
"name": "AU_loss",
"start": 5.0,
"unit": "W/K",
"group": "Fitting",
"desc": "외부 열손실 UA (cabinet → 주변 공기)",
"type": "Real"
},
{
"name": "AU_su",
"start": 3.0,
"unit": "W/K",
"group": "Fitting",
"desc": "흡입 가열 UA (T_wall → 흡입 가스). 소형 가전 ~3, 대형 ~30",
"type": "Real"
},
{
"name": "dP_su",
"start": 0.05,
"unit": "-",
"group": "Fitting",
"desc": "흡입 압력 손실 비율 (0=없음, 0.05=5%)",
"type": "Real"
},
{
"name": "V_swept_eff",
"start": 0.95,
"unit": "-",
"group": "Fitting",
"desc": "체적 효율 baseline (clearance 외 손실)",
"type": "Real"
},
{
"name": "clearance_factor",
"start": 0.03,
"unit": "-",
"group": "Fitting",
"desc": "η_v 식의 clearance 항 가중 (η_v = V_se - factor × (rp^(1/γ) - 1))",
"type": "Real"
},
{
"name": "over_comp_factor",
"start": 0.5,
"unit": "-",
"group": "Fitting",
"desc": "Over-comp 손실 가중 (P_int > P_dis 시). 시험으로 fitting",
"type": "Real"
},
{
"name": "W_loss_const",
"start": 30.0,
"unit": "W",
"group": "Fitting",
"desc": "정수 기계 손실",
"type": "Real"
},
{
"name": "alpha_loss",
"start": 0.1,
"unit": "-",
"group": "Fitting",
"desc": "비례 기계 손실 계수 (W_shaft에 곱)",
"type": "Real"
}
],
"3": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290"
]
},
{
"name": "comp_type",
"start": "reciprocating",
"unit": "-",
"group": "Material",
"desc": "압축기 형태",
"type": "String",
"options": [
"reciprocating"
]
},
{
"name": "T_amb",
"start": 25.0,
"unit": "°C",
"group": "Operating",
"desc": "주변 온도",
"type": "Real"
},
{
"name": "V_disp",
"start": 7.5,
"unit": "cm³",
"group": "Geometry",
"desc": "행정 체적 (BDC - TDC 차이)",
"type": "Real"
},
{
"name": "clearance_ratio",
"start": 0.03,
"unit": "-",
"group": "Geometry",
"desc": "Clearance 체적 / V_disp (TDC 잔류 비율)",
"type": "Real"
},
{
"name": "rv_in",
"start": 2.5,
"unit": "-",
"group": "Geometry",
"desc": "내부 체적비 (built-in volume ratio)",
"type": "Real"
},
{
"name": "A_valve_in_mm2",
"start": 8.0,
"unit": "mm²",
"group": "Geometry",
"desc": "흡입 밸브 유효 면적",
"type": "Real"
},
{
"name": "A_valve_out_mm2",
"start": 6.0,
"unit": "mm²",
"group": "Geometry",
"desc": "토출 밸브 유효 면적",
"type": "Real"
},
{
"name": "N_rated",
"start": 1800.0,
"unit": "rpm",
"group": "Geometry",
"desc": "정격 회전수 (누설 RPM 보정의 기준)",
"type": "Real"
},
{
"name": "eta_motor",
"start": 0.9,
"unit": "-",
"group": "Geometry",
"desc": "모터 효율",
"type": "Real"
},
{
"name": "eta_inv",
"start": 0.95,
"unit": "-",
"group": "Geometry",
"desc": "인버터 효율",
"type": "Real"
},
{
"name": "zeta_valve",
"start": 1.5,
"unit": "-",
"group": "Fitting",
"desc": "밸브 손실 계수 (in/out 공통)",
"type": "Real"
},
{
"name": "A_leak_mm2",
"start": 0.02,
"unit": "mm²",
"group": "Fitting",
"desc": "누설 갭 등가 면적",
"type": "Real"
},
{
"name": "Cd_leak",
"start": 0.6,
"unit": "-",
"group": "Fitting",
"desc": "누설 discharge coefficient",
"type": "Real"
},
{
"name": "n_leak_rpm",
"start": 0.5,
"unit": "-",
"group": "Fitting",
"desc": "누설의 RPM 의존성 (저속에서 ↑)",
"type": "Real"
},
{
"name": "over_comp_factor",
"start": 0.3,
"unit": "-",
"group": "Fitting",
"desc": "Over-comp 손실 가중 (P_int > P_dis 시). 시험으로 fitting",
"type": "Real"
},
{
"name": "n_poly_base",
"start": 1.13,
"unit": "-",
"group": "Fitting",
"desc": "폴리트로픽 지수 fallback (CoolProp 실패 시. 정상은 cp/cv 사용)",
"type": "Real"
},
{
"name": "W_f_const",
"start": 20.0,
"unit": "W",
"group": "Fitting",
"desc": "정수 마찰 손실 (오일/베어링)",
"type": "Real"
},
{
"name": "alpha_f_rpm",
"start": 8e-06,
"unit": "W/rpm²",
"group": "Fitting",
"desc": "RPM² 비례 마찰 (점성)",
"type": "Real"
},
{
"name": "AU_loss",
"start": 5.0,
"unit": "W/K",
"group": "Fitting",
"desc": "외부 열손실 UA",
"type": "Real"
}
]
},
"eev": {
"1": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf"
]
},
{
"name": "mode",
"start": "control",
"unit": "-",
"group": "Operating",
"desc": "control: opening→ṁ / measure: ṁ→opening",
"type": "String",
"options": [
"control",
"measure"
]
},
{
"name": "A_orifice",
"start": 0.785,
"unit": "mm²",
"group": "Geometry",
"desc": "Maximum orifice 면적 [mm²] (D=1mm → 0.785 mm²). 내부에서 ×1e-6로 m² 변환",
"type": "Real"
},
{
"name": "opening_min",
"start": 0.0,
"unit": "%",
"group": "Geometry",
"desc": "Minimum opening % (leakage)",
"type": "Real"
},
{
"name": "Cv_rated",
"start": 0.7,
"unit": "-",
"group": "Curve",
"desc": "Cv at fully open (R290 EEV typical: 0.65~0.75)",
"type": "Real"
},
{
"name": "c0",
"start": 0.0,
"unit": "-",
"group": "Curve",
"desc": "Φ(op) = c0 + c1·op + c2·op² + c3·op³ (op in [0,1])",
"type": "Real"
},
{
"name": "c1",
"start": 0.5,
"unit": "-",
"group": "Curve",
"desc": "선형 항 계수",
"type": "Real"
},
{
"name": "c2",
"start": 0.3,
"unit": "-",
"group": "Curve",
"desc": "2차 항 계수 (typical: opening curve 약간 위로 볼록)",
"type": "Real"
},
{
"name": "c3",
"start": 0.2,
"unit": "-",
"group": "Curve",
"desc": "3차 항 계수",
"type": "Real"
}
],
"2": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf"
]
},
{
"name": "mode",
"start": "control",
"unit": "-",
"group": "Operating",
"desc": "control: opening→ṁ / measure: ṁ→opening",
"type": "String",
"options": [
"control",
"measure"
]
},
{
"name": "use_choke",
"start": "on",
"unit": "-",
"group": "Operating",
"desc": "2-phase choke 활성화",
"type": "String",
"options": [
"on",
"off"
]
},
{
"name": "A_orifice",
"start": 0.785,
"unit": "mm²",
"group": "Geometry",
"desc": "Maximum orifice 면적 [mm²] (D=1mm → 0.785 mm²). 내부에서 ×1e-6로 m² 변환",
"type": "Real"
},
{
"name": "opening_min",
"start": 0.0,
"unit": "%",
"group": "Geometry",
"desc": "Minimum opening %",
"type": "Real"
},
{
"name": "Cd_0",
"start": 0.7,
"unit": "-",
"group": "Fitting",
"desc": "Base Cd at high Re, full opening, no subcooling",
"type": "Real"
},
{
"name": "Re_c",
"start": 5000.0,
"unit": "-",
"group": "Fitting",
"desc": "Critical Re for low-Re correction",
"type": "Real"
},
{
"name": "k_sub",
"start": 0.05,
"unit": "-",
"group": "Fitting",
"desc": "Subcooling sensitivity (per 10K subcool)",
"type": "Real"
},
{
"name": "k_op",
"start": 0.15,
"unit": "-",
"group": "Fitting",
"desc": "Low-opening Cd reduction factor",
"type": "Real"
},
{
"name": "Y_crit",
"start": 0.55,
"unit": "-",
"group": "Choke",
"desc": "Critical pressure ratio for choke (R290 typical: 0.5~0.6)",
"type": "Real"
},
{
"name": "cf_A",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "A_eff 보정 factor",
"type": "Real"
}
],
"3": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf"
]
},
{
"name": "needle_material",
"start": "SUS304",
"unit": "-",
"group": "Material",
"desc": "Needle 재질 (정보용, 결과 영향 없음)",
"type": "String",
"options": [
"SUS304",
"SUS316",
"Brass",
"Steel"
]
},
{
"name": "mode",
"start": "control",
"unit": "-",
"group": "Operating",
"desc": "control: opening→m_dot / measure: m_dot→opening",
"type": "String",
"options": [
"control",
"measure"
]
},
{
"name": "use_choke",
"start": "on",
"unit": "-",
"group": "Operating",
"desc": "2-phase choke 활성화 여부",
"type": "String",
"options": [
"on",
"off"
]
},
{
"name": "use_Re_correction",
"start": "on",
"unit": "-",
"group": "Operating",
"desc": "Low-Re Cd 보정 활성화",
"type": "String",
"options": [
"on",
"off"
]
},
{
"name": "needle_profile",
"start": "cone",
"unit": "-",
"group": "Geometry",
"desc": "Needle 형상 — cone (원추), parabolic, linear",
"type": "String",
"options": [
"cone",
"parabolic",
"linear"
]
},
{
"name": "needle_angle",
"start": 30.0,
"unit": "deg",
"group": "Geometry",
"desc": "Needle cone 반각 α/2 (보통 15~45°)",
"type": "Real"
},
{
"name": "D_seat",
"start": 0.001,
"unit": "m",
"group": "Geometry",
"desc": "Seat 내경 = 오리피스 직경 (보통 1.5~3 mm for R290 EEV)",
"type": "Real"
},
{
"name": "stroke_max",
"start": 0.001,
"unit": "m",
"group": "Geometry",
"desc": "Needle 최대 stroke (full-open 시, 보통 0.5~2 mm)",
"type": "Real"
},
{
"name": "L_inlet",
"start": 0.03,
"unit": "m",
"group": "Geometry",
"desc": "Inlet pipe 길이 (시각화용)",
"type": "Real"
},
{
"name": "L_outlet",
"start": 0.03,
"unit": "m",
"group": "Geometry",
"desc": "Outlet pipe 길이 (시각화용)",
"type": "Real"
},
{
"name": "opening_min",
"start": 0.0,
"unit": "%",
"group": "Geometry",
"desc": "Minimum opening % (default 0, leakage 시뮬용)",
"type": "Real"
},
{
"name": "choke_ratio",
"start": 0.5,
"unit": "-",
"group": "Choke",
"desc": "(P_out/P_in)_crit (R290 typical: ~0.5)",
"type": "Real"
},
{
"name": "Cd_base",
"start": 0.7,
"unit": "-",
"group": "Fitting",
"desc": "Cd at fully open + high Re (R290 EEV: 0.65~0.78)",
"type": "Real"
},
{
"name": "Re_transition",
"start": 1000.0,
"unit": "-",
"group": "Fitting",
"desc": "Cd가 0.5×Cd_base까지 떨어지는 Re (low Re 영역)",
"type": "Real"
},
{
"name": "cf_A",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "A_throat 보정 multiplier",
"type": "Real"
}
]
},
"condenser": {
"1": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf",
"R22",
"R407C"
]
},
{
"name": "input_mode",
"start": "UA",
"unit": "-",
"group": "Fitting",
"desc": "UA 직접 입력 vs ε 직접 입력",
"type": "String",
"options": [
"UA",
"epsilon"
]
},
{
"name": "UA_deSH",
"start": 15.5,
"unit": "W/K",
"group": "Fitting",
"desc": "De-superheat 영역 UA (vapor cooling) — HPWD typical 8 W/K",
"type": "Real"
},
{
"name": "UA_2ph",
"start": 280.0,
"unit": "W/K",
"group": "Fitting",
"desc": "2-phase (응축) 영역 UA — 보통 가장 큼, HPWD typical 50 W/K",
"type": "Real"
},
{
"name": "UA_SC",
"start": 0.5,
"unit": "W/K",
"group": "Fitting",
"desc": "Subcool 영역 UA (liquid cooling) — HPWD typical 5 W/K",
"type": "Real"
},
{
"name": "eps_deSH",
"start": 0.4,
"unit": "-",
"group": "Fitting",
"desc": "De-superheat 영역 ε",
"type": "Real"
},
{
"name": "eps_2ph",
"start": 0.85,
"unit": "-",
"group": "Fitting",
"desc": "2-phase 영역 ε",
"type": "Real"
},
{
"name": "eps_SC",
"start": 0.3,
"unit": "-",
"group": "Fitting",
"desc": "Subcool 영역 ε",
"type": "Real"
},
{
"name": "dP_ref",
"start": 0.03,
"unit": "-",
"group": "Fitting",
"desc": "냉매 측 압력 손실 비율 (P_out = P_in × (1 - dP_ref))",
"type": "Real"
}
],
"2": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290"
]
},
{
"name": "D_o",
"start": 0.005,
"unit": "m",
"group": "Geometry",
"desc": "튜브 외경",
"type": "Real"
},
{
"name": "D_i",
"start": 0.0046,
"unit": "m",
"group": "Geometry",
"desc": "튜브 내경",
"type": "Real"
},
{
"name": "L_tube_total",
"start": 5.76,
"unit": "m",
"group": "Geometry",
"desc": "튜브 총 길이",
"type": "Real"
},
{
"name": "N_tubes",
"start": 24.0,
"unit": "-",
"group": "Geometry",
"desc": "튜브 본수",
"type": "Real"
},
{
"name": "N_rows",
"start": 6.0,
"unit": "-",
"group": "Geometry",
"desc": "공기 row 수",
"type": "Real"
},
{
"name": "n_circuits",
"start": 1.0,
"unit": "-",
"group": "Geometry",
"desc": "병렬 냉매 회로 수 (G = ṁ/n_circuits/A_cross). 검증 시 On circuit_mode의 회로수와 일치시킴",
"type": "Real"
},
{
"name": "void_model",
"start": "Premoli",
"unit": "-",
"group": "Geometry",
"desc": "Void fraction 모델 (charge holdup 계산용, default Premoli)",
"type": "String",
"options": [
"Homogeneous",
"Zivi",
"Rigot",
"Hughmark",
"Premoli",
"Rouhani-Axelsson"
]
},
{
"name": "flow_arrangement",
"start": "counter",
"unit": "-",
"group": "Geometry",
"desc": "공기-냉매 흐름 배치 (counter=대향류 default, parallel=평행류). On과 동일",
"type": "String",
"options": [
"counter",
"parallel"
]
},
{
"name": "P_t",
"start": 0.01414,
"unit": "m",
"group": "Geometry",
"desc": "Transverse pitch",
"type": "Real"
},
{
"name": "P_l",
"start": 0.01,
"unit": "m",
"group": "Geometry",
"desc": "Longitudinal pitch",
"type": "Real"
},
{
"name": "t_fin",
"start": 0.00011,
"unit": "m",
"group": "Geometry",
"desc": "핀 두께",
"type": "Real"
},
{
"name": "FPI",
"start": 22.0,
"unit": "fins/inch",
"group": "Geometry",
"desc": "FPI",
"type": "Real"
},
{
"name": "k_fin",
"start": 200.0,
"unit": "W/(m·K)",
"group": "Geometry",
"desc": "핀 열전도율",
"type": "Real"
},
{
"name": "A_o_face",
"start": 0.0135744,
"unit": "m²",
"group": "Geometry",
"desc": "정면 (face) 면적",
"type": "Real"
},
{
"name": "corr_cond",
"start": "shah1979",
"unit": "-",
"group": "Correlation",
"desc": "2-phase condensation correlation (On과 동일 vendor 식)",
"type": "String",
"options": [
"shah1979",
"cavallini2006",
"dobson_chato1998"
]
},
{
"name": "corr_SP",
"start": "Dittus-Boelter",
"unit": "-",
"group": "Correlation",
"desc": "Single-phase (deSH/SC) correlation",
"type": "String",
"options": [
"Dittus-Boelter",
"Gnielinski",
"Petukhov"
]
},
{
"name": "corr_air",
"start": "wang2000_plain",
"unit": "-",
"group": "Correlation",
"desc": "공기측 j-factor correlation (On과 동일 vendor 식)",
"type": "String",
"options": [
"wang2000_plain",
"gray_webb1986"
]
},
{
"name": "corr_fin",
"start": "Schmidt",
"unit": "-",
"group": "Correlation",
"desc": "Fin 효율 correlation",
"type": "String",
"options": [
"Schmidt",
"Sector"
]
},
{
"name": "htc_corr_cond",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Condensation α 보정",
"type": "Real"
},
{
"name": "htc_corr_SP",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Single-phase α 보정",
"type": "Real"
},
{
"name": "htc_corr_air",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "공기측 α 보정",
"type": "Real"
},
{
"name": "dP_ref",
"start": 0.03,
"unit": "-",
"group": "Fitting",
"desc": "냉매 측 압력 손실 비율",
"type": "Real"
}
],
"3": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf",
"R22",
"R407C"
]
},
{
"name": "W",
"start": 0.24,
"unit": "m",
"group": "Geometry",
"desc": "튜브 길이 방향 (코일 width)",
"type": "Real"
},
{
"name": "H",
"start": 0.05656,
"unit": "m",
"group": "Geometry",
"desc": "공기 흐름 face 높이 (코일 height)",
"type": "Real"
},
{
"name": "D",
"start": 0.06,
"unit": "m",
"group": "Geometry",
"desc": "공기 흐름 방향 두께 (코일 depth = N_row×P_l = 6×10mm)",
"type": "Real"
},
{
"name": "D_o",
"start": 0.005,
"unit": "m",
"group": "Tube",
"desc": "튜브 외경",
"type": "Real"
},
{
"name": "D_i",
"start": 0.0046,
"unit": "m",
"group": "Tube",
"desc": "튜브 내경",
"type": "Real"
},
{
"name": "P_t",
"start": 0.01414,
"unit": "m",
"group": "Tube",
"desc": "Transverse pitch (공기 방향 수직)",
"type": "Real"
},
{
"name": "P_l",
"start": 0.01,
"unit": "m",
"group": "Tube",
"desc": "Longitudinal pitch (공기 방향)",
"type": "Real"
},
{
"name": "N_rows",
"start": 6.0,
"unit": "-",
"group": "Tube",
"desc": "공기 흐름 row 수 (응축기 6)",
"type": "Real"
},
{
"name": "N_tubes_per_row",
"start": 4.0,
"unit": "-",
"group": "Tube",
"desc": "Row당 튜브 수 (총 튜브: Nr × Nt)",
"type": "Real"
},
{
"name": "layout",
"start": "staggered",
"unit": "-",
"group": "Tube",
"desc": "튜브 배열: staggered (일반) / inline",
"type": "String",
"options": [
"staggered",
"inline"
]
},
{
"name": "tube_type",
"start": "microfin",
"unit": "-",
"group": "Tube",
"desc": "튜브 내면: smooth / microfin (마이크로핀 내부강화 — Carnavos/Cavallini-Diani EF)",
"type": "String",
"options": [
"smooth",
"microfin"
]
},
{
"name": "n_microfin",
"start": 54.0,
"unit": "-",
"group": "Tube",
"desc": "(microfin) 내부 핀 개수 (둘레)",
"type": "Real"
},
{
"name": "e_microfin",
"start": 0.00015,
"unit": "m",
"group": "Tube",
"desc": "(microfin) 핀 높이",
"type": "Real"
},
{
"name": "helix_angle",
"start": 15.0,
"unit": "deg",
"group": "Tube",
"desc": "(microfin) 나선각",
"type": "Real"
},
{
"name": "FPI",
"start": 22.0,
"unit": "fins/inch",
"group": "Fin",
"desc": "핀 밀도 (응축기 22 FPI)",
"type": "Real"
},
{
"name": "t_fin",
"start": 0.00011,
"unit": "m",
"group": "Fin",
"desc": "핀 두께",
"type": "Real"
},
{
"name": "fin_type",
"start": "slit",
"unit": "-",
"group": "Fin",
"desc": "Fin 타입 — 응축기 Slit",
"type": "String",
"options": [
"plain",
"wavy",
"louver",
"slit"
]
},
{
"name": "k_fin",
"start": 200.0,
"unit": "W/(m·K)",
"group": "Fin",
"desc": "핀 열전도율 (Al~200, Cu~390)",
"type": "Real"
},
{
"name": "edge_type",
"start": "rounded",
"unit": "-",
"group": "Fin",
"desc": "Kc/Ke edge type — sharp(보수적)/rounded(실코일)/chamfered(최소)",
"type": "String",
"options": [
"sharp",
"rounded",
"chamfered"
]
},
{
"name": "wavy_amplitude",
"start": 0.001,
"unit": "m",
"group": "Fin",
"desc": "(wavy) 진폭 (peak-to-peak/2)",
"type": "Real"
},
{
"name": "wavy_wavelength",
"start": 0.01,
"unit": "m",
"group": "Fin",
"desc": "(wavy) 파장",
"type": "Real"
},
{
"name": "louver_pitch",
"start": 0.0017,
"unit": "m",
"group": "Fin",
"desc": "(louver) Lp",
"type": "Real"
},
{
"name": "louver_angle",
"start": 27.0,
"unit": "deg",
"group": "Fin",
"desc": "(louver) θ",
"type": "Real"
},
{
"name": "slit_height",
"start": 0.001,
"unit": "m",
"group": "Fin",
"desc": "(slit) Ss — 슬릿 높이",
"type": "Real"
},
{
"name": "slit_width",
"start": 0.007,
"unit": "m",
"group": "Fin",
"desc": "(slit) Sh — 슬릿 폭",
"type": "Real"
},
{
"name": "n_slits",
"start": 4.0,
"unit": "-",
"group": "Fin",
"desc": "(slit) 슬릿 개수",
"type": "Real"
},
{
"name": "circuit_mode",
"start": "single",
"unit": "-",
"group": "Circuit",
"desc": "Circuit 모드: row_parallel/serpentine_2/serpentine_4/single/custom",
"type": "String",
"options": [
"row_parallel",
"serpentine_2",
"serpentine_4",
"single",
"custom"
]
},
{
"name": "custom_circuits",
"start": "",
"unit": "-",
"group": "Circuit",
"desc": "(custom 모드만) JSON: [[[r,c], ...], ...]  비워두면 row_parallel",
"type": "String"
},
{
"name": "N_seg",
"start": 10.0,
"unit": "-",
"group": "Numerical",
"desc": "튜브당 segment 수 (8~15 권장, default 10)",
"type": "Real"
},
{
"name": "N_seg_auto",
"start": "off",
"unit": "-",
"group": "Numerical",
"desc": "N_seg 자동 추천 (G_ref 기반, 8~15)",
"type": "String",
"options": [
"off",
"on"
]
},
{
"name": "evap_corr",
"start": "chen1966",
"unit": "-",
"group": "Correlations",
"desc": "Evaporation HTC correlation",
"type": "String",
"options": [
"chen1966",
"gungor_winterton1986",
"kandlikar1990"
]
},
{
"name": "cond_corr",
"start": "shah1979",
"unit": "-",
"group": "Correlations",
"desc": "(condenser 모드) Condensation HTC correlation",
"type": "String",
"options": [
"shah1979",
"cavallini2006",
"dobson_chato1998"
]
},
{
"name": "dp_corr",
"start": "friedel1979",
"unit": "-",
"group": "Correlations",
"desc": "Refrigerant dP correlation",
"type": "String",
"options": [
"friedel1979",
"lockhart_martinelli1949",
"muller_steinhagen1986"
]
},
{
"name": "air_j_corr",
"start": "auto",
"unit": "-",
"group": "Correlations",
"desc": "Air-side j-factor (auto = fin_type 기반 자동 선택)",
"type": "String",
"options": [
"auto",
"wang2000_plain",
"gray_webb1986",
"kim1999_plain",
"kayansayan1993",
"wang1999_wavy",
"wang2002_wavy",
"beecher_fagan1987",
"kim1997_wavy",
"jang1996_wavy",
"wang2000_louver",
"chang2000_louver",
"achaichia_cowell1988",
"davenport1983",
"wang2001_slit",
"manglik_bergles1995",
"nakayama_xu1983",
"du_wang2000"
]
},
{
"name": "void_model",
"start": "Premoli",
"unit": "-",
"group": "Correlations",
"desc": "Void fraction 모델 (charge holdup 계산용, default Premoli)",
"type": "String",
"options": [
"Homogeneous",
"Zivi",
"Rigot",
"Hughmark",
"Premoli",
"Rouhani-Axelsson"
]
},
{
"name": "mode",
"start": "cond",
"unit": "-",
"group": "Operating",
"desc": "운전 모드: cond (응축기 default for typeNo 222) / evap",
"type": "String",
"options": [
"evap",
"cond"
]
},
{
"name": "wet_dp_max",
"start": 1.2,
"unit": "-",
"group": "Tuning",
"desc": "Wet coil dP factor max (학계 1.10~1.30, 1.0 = 비활성)",
"type": "Real"
},
{
"name": "K_bend",
"start": 0.75,
"unit": "-",
"group": "Tuning",
"desc": "U-bend loss coefficient (Idelchik 0.5~1.0)",
"type": "Real"
},
{
"name": "cf_j",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Air j-factor 보정 multiplier",
"type": "Real"
},
{
"name": "cf_f",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Air f-factor (friction) 보정",
"type": "Real"
},
{
"name": "cf_hi",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "냉매측 HTC 보정",
"type": "Real"
},
{
"name": "cf_dp_ref",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "냉매측 dP 보정",
"type": "Real"
}
]
},
"evaporator": {
"1": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290"
]
},
{
"name": "wet_coil",
"start": "auto",
"unit": "-",
"group": "Operating",
"desc": "Wet-coil 응축 처리: auto=threshold 자동, off=무시(dry-coil)",
"type": "String",
"options": [
"auto",
"off"
]
},
{
"name": "input_mode",
"start": "UA",
"unit": "-",
"group": "Fitting",
"desc": "UA 직접 입력 vs ε 직접 입력 (UA가 일반적)",
"type": "String",
"options": [
"UA",
"epsilon"
]
},
{
"name": "UA_2ph",
"start": 15.9,
"unit": "W/K",
"group": "Fitting",
"desc": "2-phase 영역 UA (input_mode=UA 시 사용) — HPWD typical 25 W/K",
"type": "Real"
},
{
"name": "UA_SH",
"start": 2.2,
"unit": "W/K",
"group": "Fitting",
"desc": "Superheat 영역 UA (input_mode=UA 시 사용) — HPWD typical 4 W/K",
"type": "Real"
},
{
"name": "eps_2ph",
"start": 0.85,
"unit": "-",
"group": "Fitting",
"desc": "2-phase 영역 ε (input_mode=epsilon 시 사용)",
"type": "Real"
},
{
"name": "eps_SH",
"start": 0.5,
"unit": "-",
"group": "Fitting",
"desc": "Superheat 영역 ε (input_mode=epsilon 시 사용)",
"type": "Real"
},
{
"name": "dP_ref",
"start": 0.02,
"unit": "-",
"group": "Fitting",
"desc": "냉매 측 압력 손실 비율 (P_out = P_in × (1 - dP_ref))",
"type": "Real"
}
],
"2": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290"
]
},
{
"name": "wet_coil_mode",
"start": "auto",
"unit": "-",
"group": "Operating",
"desc": "Wet-coil 처리: auto=bypass factor, off=dry-coil",
"type": "String",
"options": [
"auto",
"off"
]
},
{
"name": "D_o",
"start": 0.005,
"unit": "m",
"group": "Geometry",
"desc": "튜브 외경",
"type": "Real"
},
{
"name": "D_i",
"start": 0.0046,
"unit": "m",
"group": "Geometry",
"desc": "튜브 내경",
"type": "Real"
},
{
"name": "L_tube_total",
"start": 3.84,
"unit": "m",
"group": "Geometry",
"desc": "튜브 총 길이 (모든 튜브 합)",
"type": "Real"
},
{
"name": "N_tubes",
"start": 16.0,
"unit": "-",
"group": "Geometry",
"desc": "튜브 본수 (병렬 회로 기준 분포)",
"type": "Real"
},
{
"name": "n_circuits",
"start": 1.0,
"unit": "-",
"group": "Geometry",
"desc": "병렬 냉매 회로 수 (G = ṁ/n_circuits/A_cross). 검증 시 On circuit_mode의 회로수와 일치시킴",
"type": "Real"
},
{
"name": "N_rows",
"start": 4.0,
"unit": "-",
"group": "Geometry",
"desc": "공기 흐름 방향 row 수",
"type": "Real"
},
{
"name": "P_t",
"start": 0.01414,
"unit": "m",
"group": "Geometry",
"desc": "튜브 transverse pitch (공기 방향 수직)",
"type": "Real"
},
{
"name": "P_l",
"start": 0.01,
"unit": "m",
"group": "Geometry",
"desc": "튜브 longitudinal pitch (공기 방향)",
"type": "Real"
},
{
"name": "t_fin",
"start": 0.00011,
"unit": "m",
"group": "Geometry",
"desc": "핀 두께",
"type": "Real"
},
{
"name": "FPI",
"start": 20.0,
"unit": "fins/inch",
"group": "Geometry",
"desc": "핀 밀도 (FPI=12 → P_fin ≈ 2.12mm)",
"type": "Real"
},
{
"name": "k_fin",
"start": 200.0,
"unit": "W/(m·K)",
"group": "Geometry",
"desc": "핀 열전도율 (Al~200, Cu~390)",
"type": "Real"
},
{
"name": "A_o_face",
"start": 0.0135744,
"unit": "m²",
"group": "Geometry",
"desc": "정면 (face) 면적 — V_max 계산용",
"type": "Real"
},
{
"name": "corr_2ph",
"start": "chen1966",
"unit": "-",
"group": "Geometry",
"desc": "2-phase boiling correlation (On과 동일 vendor 식)",
"type": "String",
"options": [
"chen1966",
"gungor_winterton1986",
"kandlikar1990"
]
},
{
"name": "corr_SH",
"start": "Dittus-Boelter",
"unit": "-",
"group": "Geometry",
"desc": "SH (single-phase gas) correlation",
"type": "String",
"options": [
"Dittus-Boelter",
"Gnielinski",
"Petukhov"
]
},
{
"name": "corr_air",
"start": "wang2000_plain",
"unit": "-",
"group": "Geometry",
"desc": "공기측 j-factor correlation (On과 동일 vendor 식)",
"type": "String",
"options": [
"wang2000_plain",
"gray_webb1986"
]
},
{
"name": "corr_fin",
"start": "Schmidt",
"unit": "-",
"group": "Geometry",
"desc": "Fin 효율 correlation",
"type": "String",
"options": [
"Schmidt",
"Sector"
]
},
{
"name": "corr_dp_2ph",
"start": "MSH",
"unit": "-",
"group": "Geometry",
"desc": "2-phase 압력강하 correlation (Acceleration은 항상 포함, Hydrostatic 제외)",
"type": "String",
"options": [
"MSH",
"Friedel",
"Lockhart-Martinelli",
"Chisholm"
]
},
{
"name": "void_model",
"start": "Premoli",
"unit": "-",
"group": "Geometry",
"desc": "Void fraction 모델 (charge holdup 계산용, default Premoli)",
"type": "String",
"options": [
"Homogeneous",
"Zivi",
"Rigot",
"Hughmark",
"Premoli",
"Rouhani-Axelsson"
]
},
{
"name": "flow_arrangement",
"start": "counter",
"unit": "-",
"group": "Geometry",
"desc": "공기-냉매 흐름 배치 (counter=대향류 default, parallel=평행류). On과 동일",
"type": "String",
"options": [
"counter",
"parallel"
]
},
{
"name": "eps_over_D",
"start": 0.0,
"unit": "-",
"group": "Geometry",
"desc": "튜브 내면 거칠기/직경 (0=smooth, 1.5e-6/D ~ 0.0002 일반 stainless)",
"type": "Real"
},
{
"name": "htc_corr_2ph",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "2-phase α 보정 (실험 값 / correlation 값)",
"type": "Real"
},
{
"name": "htc_corr_SH",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "SH α 보정",
"type": "Real"
},
{
"name": "htc_corr_air",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "공기측 α 보정",
"type": "Real"
},
{
"name": "dp_corr_2ph",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "2-phase 마찰 dP 보정",
"type": "Real"
},
{
"name": "dp_corr_SH",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "SH 마찰 dP 보정",
"type": "Real"
}
],
"3": [
{
"name": "fluid",
"start": "R290",
"unit": "-",
"group": "Material",
"desc": "냉매 종류",
"type": "String",
"options": [
"R290",
"R134a",
"R410A",
"R32",
"R1234yf",
"R22",
"R407C"
]
},
{
"name": "W",
"start": 0.24,
"unit": "m",
"group": "Geometry",
"desc": "튜브 길이 방향 (코일 width)",
"type": "Real"
},
{
"name": "H",
"start": 0.05656,
"unit": "m",
"group": "Geometry",
"desc": "공기 흐름 face 높이 (코일 height)",
"type": "Real"
},
{
"name": "D",
"start": 0.04,
"unit": "m",
"group": "Geometry",
"desc": "공기 흐름 방향 두께 (코일 depth, 4row)",
"type": "Real"
},
{
"name": "D_o",
"start": 0.005,
"unit": "m",
"group": "Tube",
"desc": "튜브 외경",
"type": "Real"
},
{
"name": "D_i",
"start": 0.0046,
"unit": "m",
"group": "Tube",
"desc": "튜브 내경",
"type": "Real"
},
{
"name": "P_t",
"start": 0.01414,
"unit": "m",
"group": "Tube",
"desc": "Transverse pitch (공기 방향 수직)",
"type": "Real"
},
{
"name": "P_l",
"start": 0.01,
"unit": "m",
"group": "Tube",
"desc": "Longitudinal pitch (공기 방향)",
"type": "Real"
},
{
"name": "N_rows",
"start": 4.0,
"unit": "-",
"group": "Tube",
"desc": "공기 흐름 row 수 (증발기 4)",
"type": "Real"
},
{
"name": "N_tubes_per_row",
"start": 4.0,
"unit": "-",
"group": "Tube",
"desc": "Row당 튜브 수 (총 튜브: Nr × Nt)",
"type": "Real"
},
{
"name": "layout",
"start": "staggered",
"unit": "-",
"group": "Tube",
"desc": "튜브 배열: staggered (일반) / inline",
"type": "String",
"options": [
"staggered",
"inline"
]
},
{
"name": "tube_type",
"start": "microfin",
"unit": "-",
"group": "Tube",
"desc": "튜브 내면: smooth / microfin (마이크로핀 내부강화 — Carnavos/Cavallini-Diani EF)",
"type": "String",
"options": [
"smooth",
"microfin"
]
},
{
"name": "n_microfin",
"start": 54.0,
"unit": "-",
"group": "Tube",
"desc": "(microfin) 내부 핀 개수 (둘레)",
"type": "Real"
},
{
"name": "e_microfin",
"start": 0.00015,
"unit": "m",
"group": "Tube",
"desc": "(microfin) 핀 높이",
"type": "Real"
},
{
"name": "helix_angle",
"start": 15.0,
"unit": "deg",
"group": "Tube",
"desc": "(microfin) 나선각",
"type": "Real"
},
{
"name": "FPI",
"start": 20.0,
"unit": "fins/inch",
"group": "Fin",
"desc": "핀 밀도 (FPI=12 → P_fin ≈ 2.12mm)",
"type": "Real"
},
{
"name": "t_fin",
"start": 0.00011,
"unit": "m",
"group": "Fin",
"desc": "핀 두께",
"type": "Real"
},
{
"name": "fin_type",
"start": "plain",
"unit": "-",
"group": "Fin",
"desc": "Fin 타입 — plain/wavy/louver/slit",
"type": "String",
"options": [
"plain",
"wavy",
"louver",
"slit"
]
},
{
"name": "k_fin",
"start": 200.0,
"unit": "W/(m·K)",
"group": "Fin",
"desc": "핀 열전도율 (Al~200, Cu~390)",
"type": "Real"
},
{
"name": "edge_type",
"start": "rounded",
"unit": "-",
"group": "Fin",
"desc": "Kc/Ke edge type — sharp(보수적)/rounded(실코일)/chamfered(최소)",
"type": "String",
"options": [
"sharp",
"rounded",
"chamfered"
]
},
{
"name": "wavy_amplitude",
"start": 0.001,
"unit": "m",
"group": "Fin",
"desc": "(wavy) 진폭 (peak-to-peak/2)",
"type": "Real"
},
{
"name": "wavy_wavelength",
"start": 0.01,
"unit": "m",
"group": "Fin",
"desc": "(wavy) 파장",
"type": "Real"
},
{
"name": "louver_pitch",
"start": 0.0017,
"unit": "m",
"group": "Fin",
"desc": "(louver) Lp",
"type": "Real"
},
{
"name": "louver_angle",
"start": 27.0,
"unit": "deg",
"group": "Fin",
"desc": "(louver) θ",
"type": "Real"
},
{
"name": "slit_height",
"start": 0.001,
"unit": "m",
"group": "Fin",
"desc": "(slit) Ss — 슬릿 높이",
"type": "Real"
},
{
"name": "slit_width",
"start": 0.007,
"unit": "m",
"group": "Fin",
"desc": "(slit) Sh — 슬릿 폭",
"type": "Real"
},
{
"name": "n_slits",
"start": 4.0,
"unit": "-",
"group": "Fin",
"desc": "(slit) 슬릿 개수",
"type": "Real"
},
{
"name": "circuit_mode",
"start": "single",
"unit": "-",
"group": "Circuit",
"desc": "Circuit 모드: row_parallel/serpentine_2/serpentine_4/single/custom",
"type": "String",
"options": [
"row_parallel",
"serpentine_2",
"serpentine_4",
"single",
"custom"
]
},
{
"name": "custom_circuits",
"start": "",
"unit": "-",
"group": "Circuit",
"desc": "(custom 모드만) JSON: [[[r,c], ...], ...]  비워두면 row_parallel",
"type": "String"
},
{
"name": "N_seg",
"start": 10.0,
"unit": "-",
"group": "Numerical",
"desc": "튜브당 segment 수 (8~15 권장, default 10)",
"type": "Real"
},
{
"name": "N_seg_auto",
"start": "off",
"unit": "-",
"group": "Numerical",
"desc": "N_seg 자동 추천 (G_ref 기반, 8~15)",
"type": "String",
"options": [
"off",
"on"
]
},
{
"name": "evap_corr",
"start": "chen1966",
"unit": "-",
"group": "Correlations",
"desc": "Evaporation HTC correlation",
"type": "String",
"options": [
"chen1966",
"gungor_winterton1986",
"kandlikar1990"
]
},
{
"name": "cond_corr",
"start": "shah1979",
"unit": "-",
"group": "Correlations",
"desc": "(condenser 모드) Condensation HTC correlation",
"type": "String",
"options": [
"shah1979",
"cavallini2006",
"dobson_chato1998"
]
},
{
"name": "dp_corr",
"start": "friedel1979",
"unit": "-",
"group": "Correlations",
"desc": "Refrigerant dP correlation",
"type": "String",
"options": [
"friedel1979",
"lockhart_martinelli1949",
"muller_steinhagen1986"
]
},
{
"name": "air_j_corr",
"start": "auto",
"unit": "-",
"group": "Correlations",
"desc": "Air-side j-factor (auto = fin_type 기반 자동 선택)",
"type": "String",
"options": [
"auto",
"wang2000_plain",
"gray_webb1986",
"kim1999_plain",
"kayansayan1993",
"wang1999_wavy",
"wang2002_wavy",
"beecher_fagan1987",
"kim1997_wavy",
"jang1996_wavy",
"wang2000_louver",
"chang2000_louver",
"achaichia_cowell1988",
"davenport1983",
"wang2001_slit",
"manglik_bergles1995",
"nakayama_xu1983",
"du_wang2000"
]
},
{
"name": "void_model",
"start": "Premoli",
"unit": "-",
"group": "Correlations",
"desc": "Void fraction 모델 (charge holdup 계산용, default Premoli)",
"type": "String",
"options": [
"Homogeneous",
"Zivi",
"Rigot",
"Hughmark",
"Premoli",
"Rouhani-Axelsson"
]
},
{
"name": "mode",
"start": "evap",
"unit": "-",
"group": "Operating",
"desc": "운전 모드: evap (증발기) / cond (응축기)",
"type": "String",
"options": [
"evap",
"cond"
]
},
{
"name": "wet_dp_max",
"start": 1.2,
"unit": "-",
"group": "Tuning",
"desc": "Wet coil dP factor max (학계 1.10~1.30, 1.0 = 비활성)",
"type": "Real"
},
{
"name": "K_bend",
"start": 0.75,
"unit": "-",
"group": "Tuning",
"desc": "U-bend loss coefficient (Idelchik 0.5~1.0)",
"type": "Real"
},
{
"name": "cf_j",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Air j-factor 보정 multiplier",
"type": "Real"
},
{
"name": "cf_f",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "Air f-factor (friction) 보정",
"type": "Real"
},
{
"name": "cf_hi",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "냉매측 HTC 보정",
"type": "Real"
},
{
"name": "cf_dp_ref",
"start": 1.0,
"unit": "-",
"group": "Fitting",
"desc": "냉매측 dP 보정",
"type": "Real"
}
]
},
"fan": {
"1": [
{
"name": "D2",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b2",
"start": 0.04,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Z",
"start": 40,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "beta2",
"start": 150.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eta_h",
"start": 0.78,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eta_mech",
"start": 0.95,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "N",
"start": 3000.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_exit",
"start": 0.008,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"2": [
{
"name": "D2",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b2",
"start": 0.04,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "D1",
"start": 0.075,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b1",
"start": 0.045,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Z",
"start": 40,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "beta2",
"start": 150.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "beta1",
"start": 35.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_inc",
"start": 0.6,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_fric",
"start": 0.8,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_scroll",
"start": 0.25,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eta_mech",
"start": 0.95,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "N",
"start": 3000.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_exit",
"start": 0.008,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"3": [
{
"name": "D1",
"start": 120.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "D2",
"start": 175.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b1",
"start": 60.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b2",
"start": 50.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "beta1",
"start": 30.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "beta2",
"start": 145.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Z",
"start": 36.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "RPM",
"start": 1400.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "tBlade",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "cutoffGap",
"start": 8.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Rtongue",
"start": 5.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "wrapAngle",
"start": 360.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "scrollExpRate",
"start": 0.12,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "diffAngle",
"start": 7.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "diffLength",
"start": 40.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_inc",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_fric",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_rec",
"start": 0.0085,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "DR_crit",
"start": 0.5,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_disk",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_jw",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_sc_mix",
"start": 0.2,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_tongue_a",
"start": 0.82,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_tongue_b",
"start": 0.7,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "w_rec",
"start": 0.02,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "c_wake",
"start": 0.12,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "r_scroll_w",
"start": 1.1,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "c_scroll_v",
"start": 0.7,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "c_tongue_loss",
"start": 0.3,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eps_leak_max",
"start": 0.25,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
]
},
"drum": {
"1": [
{
"name": "m_cl_dry",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "c_p_cl",
"start": 1500.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_eff",
"start": 10.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "h_a",
"start": 50.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_drum",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "K_drum",
"start": 30.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "UA_amb",
"start": 0.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "T_amb",
"start": 298.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eps_dry",
"start": 0.001,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fabric",
"start": "cotton",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "M_dry",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "X0",
"start": 0.6,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "zone_fractions",
"start": "(0.25",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "T_fabric_init",
"start": 25.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"2": [
{
"name": "m_cl_dry",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "c_p_cl",
"start": 1500.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_eff",
"start": 10.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "h_a",
"start": 50.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_drum",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "K_drum",
"start": 30.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "UA_amb",
"start": 0.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "T_amb",
"start": 298.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "X_cr",
"start": 0.2,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "a_sorp",
"start": 0.25,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "n_sorp",
"start": 2.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fabric",
"start": "cotton",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "M_dry",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "X0",
"start": 0.6,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "zone_fractions",
"start": "(0.25",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "T_fabric_init",
"start": 25.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"3": [
{
"name": "fabric",
"start": "cotton",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "M_dry",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "zone_fractions",
"start": "(0.25",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "diffusion_S_exponent",
"start": 0.5,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "brooks_corey_exponent",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_wet_exponent",
"start": 0.5,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "L_char_multiplier",
"start": 3.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "S_critical",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_exchange_sliding",
"start": 0.05,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_exchange_cascading",
"start": 0.3,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "k_exchange_high",
"start": 0.02,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "eps_free",
"start": 0.01,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "drum_radius",
"start": 0.27,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "drum_length",
"start": 0.45,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "RPM",
"start": 45.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_rear_hole",
"start": 0.012,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_side_hole",
"start": 0.006,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "gap_width",
"start": 0.008,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "L_side_hole",
"start": 0.15,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "seal_depth",
"start": 0.03,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "C_d",
"start": 0.62,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Fr_opt",
"start": 0.3,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "Fr_sigma",
"start": 0.25,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fill_optimal",
"start": 0.6,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_conv_sliding",
"start": 0.7,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_conv_peak",
"start": 1.7,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "f_conv_centrifuge",
"start": 0.3,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "hA_multiplier",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "bypass_multiplier",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "X0",
"start": 0.6,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "T_fabric_init",
"start": 25.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L3",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
]
},
"filter": {
"1": [
{
"name": "K",
"start": 20.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_face",
"start": 0.05,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "r_pleat",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "theta_face",
"start": 0.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L1",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"2": [
{
"name": "a_visc",
"start": 50000.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "b_inert",
"start": 17.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_face",
"start": 0.05,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "r_pleat",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "theta_face",
"start": 0.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L1",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
],
"3": [
{
"name": "cf_ergun",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "layers",
"start": "[",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "A_face",
"start": 0.05,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "r_pleat",
"start": 1.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "theta_face",
"start": 0.0,
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
},
{
"name": "fidelity",
"start": "L1",
"unit": "-",
"group": "General",
"desc": "",
"type": "Real"
}
]
}
};
