# ThermoPower 레퍼런스 분석 — 초기화 강건성 기법

2026-07-26. `Cycle_L3_ssinit` 정상상태 초기화가 `cond.h_ref[1]` 발산으로 실패해
레퍼런스 구현을 분석함.

대상: ThermoPower (Casella, github.com/casella/ThermoPower)
비교: ThermoCycle (github.com/thermocycle/ThermoCycle-library)

## 0. 먼저 확인한 것 — OMC 는 병목이 아님

```
Modelica.Fluid.Examples.DrumBoiler (IF97 물/증기 2상, 5400s)
→ 같은 OMC 1.27.0 에서 22초 완주, 적분 실패 0건
```
레퍼런스 2상 열유체 모델이 멀쩡히 돌아감. 문제는 우리 모델 정식화 쪽.

`homotopy(` 사용 횟수: ThermoPower **133회** / ThermoCycle **0회**.
→ 초기화 강건성 레퍼런스는 ThermoPower 를 볼 것.

## 1. homotopy 적용 지점 (그대로 이식 가능)

### (a) 셀 유량 — 우리 `cond.h_ref[1]` 발산에 직결
```modelica
parameter Boolean fixedMassFlowSimplified = false
  "Fix flow rate = wnom for simplified homotopy model";
...
if fixedMassFlowSimplified then
  wbar[j] = homotopy(infl.m_flow/Nt - sum(dMdt[1:j-1]) - dMdt[j]/2,   // actual
                     wnom/Nt);                                        // simplified
else
  wbar[j] = infl.m_flow/Nt - sum(dMdt[1:j-1]) - dMdt[j]/2;
end if;
```
단순화 모델이 **셀별 질량축적 항 dMdt 를 통째로 끊고 공칭유량 균일**로 둠.
우리 Cond_On_Dyn 의 `M_c[k]=rho_ph(P,h)*V_cell` + 집중 질량보존이 만드는
셀간 강결합이 초기화 비선형계를 어렵게 하는 것과 정확히 같은 구조.

### (b) 압력강하 — 2차 → 선형
```modelica
pin - pout = homotopy(smooth(1, Kf_a*squareReg(w, wnom*wnf))/rho,  // actual (2차)
                      dpnom/wnom*w);                                // simplified (선형)
```

### (c) 스트림 엔탈피 — 역류 분기 제거
```modelica
hi = homotopy(if not allowFlowReversal then inStream(inlet.h_outflow)
              else actualStream(inlet.h_outflow),
              inStream(inlet.h_outflow));
```

공통 원리: **단순화 모델은 공칭값(wnom, dpnom) 기반의 선형/상수 관계**.
따라서 이식하려면 우리 HX·EEV·압축기에 공칭 유량/차압 파라미터가 필요함
(현재 없음).

## 2. 초기화 아키텍처

```modelica
// 전역 전파: inner/outer
inner ThermoPower.System system(initOpt = Choices.Init.Options.steadyState);
// 각 컴포넌트: outer System system;  ... initOpt = system.initOpt
```

옵션 열거형:
```
noInit          초기 방정식 없음
fixedState      상태 start 값 고정          ← 우리가 계속 쓰던 것
steadyState     der(x)=0
steadyStateNoP  압력 제외 정상초기화 (deprecated)
```

## 3. 폐루프 특이성 처리 — 우리 방식이 deprecated 였음

Flow1DFV 초기화부:
```modelica
elseif initOpt == steadyState then
  der(htilde) = zeros(N-1);
  if (not Medium.singleState) and not noInitialPressure then
    der(p) = 0;
  end if;
elseif initOpt == steadyStateNoP then
  der(htilde) = zeros(N-1);
  assert(false, "initOpt = steadyStateNoP deprecated, "
                "use steadyState and noInitialPressure", AssertionLevel.warning);
```

즉 특별한 초기화 모드를 만드는 게 아니라 **컴포넌트별 플래그**로 해결:
```modelica
parameter Boolean noInitialPressure = false "Remove initial equation on pressure";
parameter Boolean noInitialEnthalpy = false "Remove initial equation on enthalpy";
```
폐루프에서는 `initOpt=steadyState` 를 전역으로 걸고,
**정확히 하나의 컴포넌트에만 `noInitialPressure=true`** 를 준다.
(Examples.mo 4곳에서 그렇게 사용)

우리 `Accumulator_L3.initMode=3` (der(h)=0 만, p 는 충전량이 결정)은
바로 이 deprecated `steadyStateNoP` 와 같은 발상이었음.
→ `noInitialPressure` 플래그 형태로 바꾸는 게 맞음.

## 4. 우리 코드에 옮길 항목 (우선순위)

1. **HX 셀 유량에 homotopy** — `fixedMassFlowSimplified` 패턴.
   Cond_On_Dyn/Evap_On_Dyn 에 `w_nom` 파라미터 추가 후
   셀 질량수지의 결합항을 단순화 모델에서 제거.
   → `cond.h_ref[1]` 발산의 직접 대응책.
2. **EEV/압축기 유량식에 homotopy** — 단순화는 선형 `w = dpnom/wnom` 관계.
3. **초기화 플래그 정리** — `initMode=3` → `noInitialPressure` 로 개명,
   Volume_L3/Accumulator_L3 양쪽에 `noInitialEnthalpy` 도 추가.
4. **공칭값 파라미터 정비** — wnom, dpnom 이 있어야 단순화 모델을 쓸 수 있음.
5. (선택) `inner System` 도입해 initOpt 전역 전파. 모델 수가 늘면 가치 있음.

## 5. 참고 — ThermoCycle

homotopy 미사용. 대신 `Cell1DimInc` 등에서 `steadystate` 부울로
`der=0` 을 켜고 끄는 방식. 초기화 난제 대응은 ThermoPower 가 앞섬.
