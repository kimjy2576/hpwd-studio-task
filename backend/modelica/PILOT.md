# 캔버스 → Modelica 브릿지 — EEV 파일럿

> 결정(docs/modelica-decision.md): 사이클 솔버는 **Modelica(acausal)**.
> 캔버스는 그래프 → `.mo` 생성 → omc 실행으로 Modelica를 엔진으로 쓴다.
> 이 모듈(`backend/modelica/`)이 그 **canvas→.mo 생성기**의 시작점.

## 현재 상태 (배경)
- 캔버스 "Run"은 *현재* 백엔드 `/compute`로 컴포넌트별 Python `step()`을 호출하고
  프론트가 quasi-steady **sequential substitution**으로 사이클을 푼다 (화면 하단 표기).
- Modelica L1 사이클 솔버는 `modelica/`에 별도 존재(이미 폐루프·SH제어·운전점 확보).
- 즉 L1 EEV가 둘(Python `eev_off_design.py` ↔ Modelica `HPWD.EEV_L1`). **이 브릿지가 둘을 잇는다.**

## 파일럿: EEV(Off, type 130) end-to-end
`bridge.compute_modelica(block)` — `/compute`와 동일 입력 shape를 받아
캔버스 EEV 블록 → `.mo` 생성 → omc 실행 → Python과 동일한 출력 키 반환.

생성기가 처리하는 것:
- **파라미터 단위 변환**: `A_orifice` mm² → m² (×1e-6) ★ 최근 단위변경 반영
- 경계조건 변환: 압력 bar→Pa, 비엔탈피 kJ/kg→J/kg
- canvas 파라미터명 → Modelica 파라미터명 매핑
- Source/Sink 경계 + opening 신호(Constant) 자동 삽입

## 검증 (Modelica bridge vs Python step)
캔버스 EEV(Off) 기본설정, P_in 17 / h_in 280 / P_out 5.84 bar:

| var | Modelica | Python | Δ% |
|---|---|---|---|
| m_dot_ref | 0.0253312 | 0.0253312 | 1.9e-5 |
| phi_op | 0.35 | 0.35 | ~0 |
| rho_in | 485.763 | 485.763 | 3.8e-5 |
| T_out | 6.98713 | 6.9871 | 5.6e-4 |
| x_out | 0.170882 | 0.170882 | 3.6e-4 |

개도(20/50/80%) × 면적(3.14/0.55 mm²) 6조합 전부 **ṁ Δ 1.9e-5%**.
→ HelmholtzMedia·CoolProp 엔탈피 기준점 정렬 확인(T_out·x_out까지 일치).

## 사용
```python
from modelica.bridge import compute_modelica
block = {'component':'eev_off_design',
         'params':{'A_orifice':3.14, 'Cv_rated':0.7, 'c0':0,'c1':0.5,'c2':0.3,'c3':0.2,'opening_min':0},
         'inputs':{'P_in':17.0,'h_in':280.0,'P_out':5.84,'opening':50.0}}
compute_modelica(block)   # -> {'outputs': {'m_dot_ref':..., 'T_out':..., ...}}
```
환경: `omc` PATH, `HELMHOLTZ_PATH`(R290 물성), `HPWD_MODELICA_DIR`(default repo/modelica).

## 다음 (확장 경로)
1. **서버 엔드포인트** `/compute_modelica` (또는 `/compute?engine=modelica`) — 캔버스가 엔진 토글로 호출.
2. **컴포넌트 확장** — `COMPONENT_REGISTRY`에 compressor/HX 추가 (맵+템플릿). 각자 Python과 <0.1% 대조.
3. **사이클 조립** — 단일 컴포넌트 → connect 그래프 자동 생성(캔버스 토폴로지 → `connect` 문).
   여기서부터 sequential substitution 대신 Modelica acausal 연립으로 전환.
4. **제어 신호** — 명시 신호선(SH→ctrl→opening)도 `connect`로 1:1 생성(결정된 "명시 기본" 원칙).
5. rest-평형 init + N ramp 패턴을 생성기가 함께 emit (재현성: STATUS 재현성 레시피 참고).
