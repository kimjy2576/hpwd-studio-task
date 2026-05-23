# HPWD 사이클 솔버 — Modelica 채택 의사결정

## 1. 결정

냉매 사이클 정상상태/동특성 솔버를 **Modelica(OpenModelica)** 로 구축한다.
파이썬 컴포넌트는 ground truth(검증 기준)·도구·surrogate 학습·캔버스 백엔드로 유지한다.

## 2. 왜 Modelica인가 (속도 아님, 자동 방정식 구성)

- 지향점은 **완전 임의 배치**(어큐뮬레이터·IHX·리시버 등 자유 조합)를 푸는 솔버.
- 임의 배치 자동 해결 = 그래프에서 방정식을 자동 구성·연립하는 것 = **acausal equation-based modeling = Modelica의 본령**.
- C/Fortran로 직접 짜면 빠르긴 하나, 임의 토폴로지 자동화를 *직접 구현*해야 함 = 미니-Modelica 재구현 = 거대 작업.
- C 컴파일 속도는 Modelica의 부산물(모델을 C로 컴파일). "임의 배치 자동 + 속도"를 둘 다 줌.

## 3. 물성 — HelmholtzMedia (ExternalMedia 회피)

- ExternalMedia+CoolProp은 빌드 체인 3단(CoolProp .so → ExternalMedia → omc 통합)으로 무겁고 불확실.
- **HelmholtzMedia**(순수 Modelica Helmholtz EoS)로 R290 정밀 물성 — 외부 빌드 불필요, omc만으로.
- CoolProp과 같은 reference EoS(Lemmon 2009) 기반 → 정합 검증 결과 **전 영역 0.000% 일치**(과냉액·과열증기·포화·2상).

## 4. 검증 전략 (파이썬 ground truth + 단계적)

- Layer 0: 물성 (HelmholtzMedia vs CoolProp) — 완료, 0.000%
- Layer 1: 컴포넌트 식 (Modelica vs Python, 같은 입력 → 출력 비교) — EEV L1 완료, ṁ 0.00003%
- Layer 2+: 나머지 컴포넌트 동일 패턴
- 사이클: connect로 조립 → acausal 자동 연립
- 한 번에 한 변수만 비교(물성 먼저 분리 → 코드만) → 에러 국소화

## 5. 역할 분담

| 영역 | 담당 |
|---|---|
| 1D 사이클 솔버 (임의 배치) | Modelica (acausal) |
| 물성 | HelmholtzMedia |
| 검증 기준·초기값 공급·도구·surrogate 학습·캔버스 | 파이썬 |
| 3D (CFD/형상) | surrogate AI (별도) |

## 6. Modelica 단점 + 대응

**① 디버깅 난이도 (초기값·해석불가 에러)** — 진짜 리스크
- 정합 검증 하네스(컴포넌트별 표준점 자동 비교 → CI)
- 초기값 생성기(파이썬 정상상태 해 → Modelica `start` 자동 주입)
- DOF/connector balancing 사전 린터(컴파일 전 검사)
- LLM-assisted 디버깅(에러 해석·수정 제안 — HPWD-GPT 활용)

**② 3D/형상 불가 (0D/1D 한계)** — 진영님 케이스 무관
- Modelica는 1D 사이클만, 3D는 surrogate(CFD 대체)가 담당
- 3D 필요부 → OpenFOAM CFD 데이터 → ANN surrogate → Modelica 컴포넌트로 통합(hybrid)

**③ 제어/채터링** — 동특성 단계 주의
- 대부분 제어(PID·on/off·보호)는 Modelica.Blocks/StateGraph (캔버스 제어 모듈도 Modelica 블록)
- 복잡 알고리즘 제어(MPC·AI)만 파이썬 external/FMU
- 채터링은 hysteresis(dead band)·noEvent()로 완화

**④ 상용 의존** — 오픈소스+직접개발로 대응
- 스택: OpenModelica + HelmholtzMedia + (Buildings/ThermoPower 참조) + (CFD는 OpenFOAM)
- 상용(Dymola/TIL)은 비상카드(컴파일 속도·안정성 병목 시)
- 전부 오픈소스 → 공개 repo·재현 가능(포트폴리오 가치)

## 7. 자동화 가능 CFD (surrogate 데이터용)

- **OpenFOAM**(오픈소스): 스크립트/배치 자동화 + 무제한 병렬(라이선스 무료) + PyFoam 파이썬 제어
- Fluent는 batch 가능하나 병렬마다 라이선스 토큰 → 대량 데이터 생성 부적합
- full CFD 직접 구축은 비현실(특정 부품 간이 모델은 가능)

## 8. 로드맵

1. **L1 컴포넌트 변환** (EEV ✓ → 압축기 AHRI → 증발기/응축기 Off ε-NTU) + 컴포넌트별 정합
2. **L2 → L3** 동일 패턴
3. **사이클 조립** (connect, acausal 자동 연립) → **L1/L2/L3 fidelity 비교**
4. (추후) charge balance closure, 동특성(dynamic MB), 제어, surrogate 데이터 생성

## 9. 환경

- OpenModelica 1.26.7 + MSL 4.1.0 + HelmholtzMedia (컨테이너 검증 완료)
- connector: `RefPort` (p potential / m_flow flow / h_outflow stream) — 임의 배치(분기·합류·역류) 대응
