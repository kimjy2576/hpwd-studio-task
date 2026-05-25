"""캔버스 → Modelica 브릿지 (canvas→.mo 생성기 + OMC 실행).

캔버스 블록 스펙(= /compute 요청 shape)을 받아 Modelica .mo를 생성하고
OpenModelica로 실행해 결과를 회수한다. Python step() 백엔드와 동일한 출력 키를 반환.

현재: EEV(Off) 단일 컴포넌트 end-to-end 파일럿 (검증 <0.001% vs Python).
확장: COMPONENT_REGISTRY에 (type → modelica model + 파라미터/단위 맵 + 템플릿) 추가.
"""
from .bridge import gen_component_mo, compute_modelica, clear_cache, COMPONENT_REGISTRY
