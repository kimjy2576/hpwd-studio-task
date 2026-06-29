"""
Condenser (L3 On-Design / Tube-Segment)
═══════════════════════════════════════════════════════════════════════
Evaporator(L3 typeNo 122)와 동일한 HX-Sim 모델을 응축기 모드(mode='cond')로
호출하는 wrapper.

핵심 설계 원칙:
  • 동일 fin-tube geometry → step 로직은 evaporator_on_design와 100% 공유
  • 차이점은 mode 파라미터와 default 값 + typeNo (222)뿐
  • 결과: code drift 방지, HX-Sim correlation 개선이 양쪽 모두에 자동 적용

차이점 요약 (Evaporator vs Condenser):
  • mode default: 'evap' → 'cond'
  • Refrigerant 측 default correlation: chen1966 → shah1979
  • Operating P range: 저압 (~0.5 MPa for R290) → 고압 (~1.6 MPa for R290)
  • SH/SC 의미: SH (superheat) → SC (subcool)
  • Quality 추세: x_in (액 ~0.2) → x_out 1.0 → x_in 1.0 → x_out 0.0 (subcool)
  • Wet 가정: 보통 무시 (응축기는 건조 가정 — 외기 노출 없음)

구현:
  • evaporator_on_design.step()을 그대로 호출
  • params.setdefault('mode', 'cond')  # cond 강제 default
  • modelDescription만 condenser용으로 일부 override (typeNo, name, default 값)
"""

# Evaporator 모듈 그대로 import — step / validate / _parse_custom_circuits 재사용
from . import evaporator_on_design as _evap_module
from .evaporator_on_design import (
    FLUIDS, FIN_TYPES, EDGE_TYPES, CIRCUIT_MODES, LAYOUTS,
    AIR_J_PLAIN, AIR_J_WAVY, AIR_J_LOUVER, AIR_J_SLIT, AIR_J_ALL,
    REF_EVAP, REF_COND, REF_DP,
)


# ════════ modelDescription ════════
# Evaporator의 description을 base로, 응축기용 default 값/설명만 override
import copy

_evap_md = _evap_module.modelDescription
modelDescription = {
    'typeNo': 222,  # Condenser typeNo
    'name': 'Condenser (On-Design / Tube-Segment)',
    'category': 'refrigerant',
    'modelType': 'on-design',
    'fidelity': 0.95,
    'description': 'HX-Sim Nr×Nt×N_seg tube-segment model for condensation — '
                   '학계 정통 30+ correlation (Shah/Cavallini/Dobson-Chato 등)',
    'backend': 'python',
    'variables': copy.deepcopy(_evap_md['variables']),
}

# ── default 값 override (응축기 사양) ──
# 일반적인 R290 가정 응축기 default:
#   • 응축 mode 기본 (mode='cond')
#   • 외경 face는 입구가 두꺼움 (hot gas), 더 큰 H가 필요할 수 있으나
#     공통 기본은 evaporator와 동일하게 두고 설계자가 조정
#   • Refrigerant 측 default: shah1979 (응축 표준)
#   • inputs default 영역의 mode는 'cond'로
_overrides = {
    'mode': {'start': 'cond',
             'description': '운전 모드: cond (응축기 default for typeNo 222) / evap'},
    # ── 응축기 사양 (블록1): Plain fin, FPI20, N_row4, depth=Nr×Pl ──
    # 공유 튜브(Do5/Di4.6 micro-fin n54/e0.15/15°, Pt14.14/Pl10, Nt4, L_tube=W=240mm,
    #  t_fin0.11, k_fin200, layout staggered, circuit single)는 evaporator default 상속.
    'fin_type': {'start': 'plain', 'description': 'Fin 타입 — 응축기 Plain'},
    'FPI': {'start': 20.0, 'description': '핀 밀도 (응축기 20 FPI)'},
    'N_rows': {'start': 4.0, 'description': '공기 흐름 row 수 (응축기 4)'},
    'D': {'start': 0.04, 'description': '공기 흐름 방향 두께 (코일 depth = N_row×P_l = 4×10mm)'},
    # ref correlation default — cond_corr가 이미 shah1979로 default라 그대로
}

for var in modelDescription['variables']:
    name = var.get('name')
    if name in _overrides:
        var.update(_overrides[name])
    # P_evap → P_cond rename (응축기 의미 명확화).
    # 내부 evap solver는 'P_evap' 키를 읽으므로 step()에서 매핑함.
    if name == 'P_evap':
        var['name'] = 'P_cond'
        var['description'] = '응축 압력 (abs)'


# ════════ step / validate — Evaporator 그대로 재사용 ════════
# mode default를 cond로 덮어씌우는 wrapper
_evap_step = _evap_module.step


def step(input, params, state, dt):
    """Condenser step — evaporator_on_design.step()을 mode='cond' default로 호출.
    
    params에 'mode' 키가 없거나 'evap'이 명시적으로 들어오지 않은 경우
    기본 'cond'로 처리. frontend가 명시적으로 mode='evap'을 보내면 그것 우선.
    """
    # params는 dict (frontend payload). 변형해도 무방하지만 안전을 위해 copy.
    p = dict(params) if params else {}
    p.setdefault('mode', 'cond')
    # P_cond(노출 변수명) → P_evap(내부 solver 키) 매핑.
    # modelDescription은 P_cond으로 노출하나, 공유 evap solver는 P_evap 키를 읽음.
    inp = dict(input) if input else {}
    if 'P_cond' in inp and 'P_evap' not in inp:
        inp['P_evap'] = inp.pop('P_cond')
    return _evap_step(inp, p, state, dt)


def validate(params):
    """Validation — evaporator의 validate 그대로 사용 + cond mode 일관성 체크."""
    issues = list(_evap_module.validate(params))
    
    # mode 일관성: typeNo 222 컴포넌트인데 mode='evap'이면 경고 (사용자 의도 확인)
    mode = params.get('mode', 'cond')
    if mode == 'evap':
        issues.append({
            'key': 'mode',
            'msg': 'Condenser 컴포넌트(typeNo 222)인데 mode=evap. typeNo 122 (Evaporator) 사용 고려',
        })
    
    return issues
