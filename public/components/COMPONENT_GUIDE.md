# HPWD-Studio 컴포넌트 작성 가이드

이 문서는 HPWD-Studio에 새 컴포넌트 모델을 추가하는 팀원을 위한 가이드입니다.

---

## 시작하기 전에

다음만 알면 됩니다:

- 컴포넌트는 **JS 객체 한 개**로 정의됩니다 (`templates/_template.js` 참고)
- 모든 컴포넌트는 **표준 인터페이스**를 따릅니다 (`modelDescription`, `step`, `validate` 등)
- 플랫폼 인프라(Solver, Engine, Adapter)는 **건드리지 마세요**. 컴포넌트만 추가하면 자동으로 동작합니다.

---

## 1. 정적 vs 동적 결정

가장 먼저 결정할 것: 내 컴포넌트가 **정적**인가 **동적**인가?

### 정적 (Static, stateless)
- 입력이 들어오면 **즉시** 출력 계산
- 시간 효과 없음 (한 timestep 안에 평형)
- state 필요 없음

**예시**: Compressor (단순), EEV, TXV, Fan, 단순 Heat Exchanger

### 동적 (Dynamic, stateful)
- 시간에 따라 **상태가 변함**
- state 변수 필요 (e.g. metal 온도, 직물 수분)
- timestep마다 적분

**예시**: Drum, Heat Exchanger (metal mass 포함), Battery, 직물 건조

### 결정 규칙

> **"이 컴포넌트가 한 timestep 안에 평형에 도달하나?"**
> - YES → 정적
> - NO → 동적

확실하지 않다면 정적부터 시작하세요. 나중에 동적으로 업그레이드 가능.

---

## 2. typeNo 대역 분배

다른 팀원과 충돌 안 나도록 **카테고리별 typeNo 대역**을 따르세요:

| 대역 | 카테고리 | 예시 |
|---|---|---|
| 1~99 | Sources / Sinks | Ambient, Constant, Ramp, Sine |
| 100~199 | **Refrigerant** (냉매) | Compressor(100), Condenser(101), EEV(102), Evap(103), TXV(104) |
| 200~299 | **Air** (공기) | Fan(200), Drum(201), Duct, Damper |
| 300~399 | **Water** (물) | Pump, Tank, Valve |
| 400~499 | **Control** (제어) | PID, Setpoint, Logic |
| 500~599 | **Math** (수학 연산) | Add, Subtract, Multiply |
| 900~999 | **Output / Display** | Plotter, Display, Logger |

자기 카테고리 안에서 **사용 중이지 않은 번호**를 골라 사용하세요.

---

## 3. 공통 변수명 사전 (필수 준수)

다른 컴포넌트와 자동 연결되려면 **공통 변수명**을 따라야 합니다.

| 변수명 | 단위 | 의미 | 예 |
|---|---|---|---|
| `m_dot` | g/s | 질량유량 (냉매) | Compressor → Condenser |
| `m_air` | kg/s | 공기 질량유량 | Fan → Drum |
| `m_water` | kg/s | 물 질량유량 | Pump → Tank |
| `T_in / T_out` | °C | 입구/출구 온도 (cycle 내부) | 모든 fluid 컴포넌트 |
| `T_suc / T_dis` | °C | 흡입/토출 온도 (압축기 한정) | Compressor |
| `P_in / P_out` | kPa | 입구/출구 압력 | 모든 fluid 컴포넌트 |
| `P_suc / P_dis` | kPa | 흡입/토출 압력 (압축기 한정) | Compressor |
| `T_air / T_air_in / T_air_out` | °C | 공기 온도 | 공기 측 |
| `Q` | W | 열전달 | 열교환기 |
| `W` / `W_comp` / `W_fan` | W | 일/전력 | Compressor, Fan |
| `MC` | kg/kg | 수분 함량 | Drum |
| `RH` | % | 상대 습도 | 공기 |
| `SH` | K | Superheat | Evaporator |
| `SC` | K | Subcooling | Condenser |
| `dP` | Pa | 압력 강하 | Duct, HX |

**새 변수명을 만들어야 한다면**: 플랫폼팀과 상의해서 사전에 추가하세요.

---

## 4. 작성 순서 (실제 작업 흐름)

### Step 1. 템플릿 복사
```bash
cp templates/_template.js components/my_component.js
```

### Step 2. Identity 채우기
```js
typeNo: 110,                    // 자기 대역에서 안 쓰는 번호
name: 'My Component',
category: 'refrigerant',         // 위 표 참조
icon: SomeIcon,                  // lucide-react 아이콘
color: '#475569',
image: './images/mycomp.png',    // 선택적
```

### Step 3. modelDescription 채우기

가장 중요. 모든 변수를 명시:

```js
modelDescription: {
  modelType: 'on-design',        // on-design | semi-empirical | off-design
  fidelity: 0.5,                  // 0(단순) ~ 1(상세)
  description: '한 줄 모델 설명',

  variables: [
    // Parameters (시간 무관)
    { name: 'param1', causality: 'parameter', type: 'Real',
      start: 10, unit: 'kPa', min: 0, max: 1000,
      description: '의미 있는 한 줄 설명' },

    // Inputs (다른 컴포넌트에서 받음)
    { name: 'T_in', causality: 'input', type: 'Real',
      unit: '°C', min: -40, max: 100 },

    // Outputs (다른 컴포넌트로 전달)
    { name: 'T_out', causality: 'output', type: 'Real', unit: '°C' },

    // States — 동적 컴포넌트만
    // { name: 'T_metal', causality: 'local', variability: 'continuous',
    //   start: 25, unit: '°C', description: '금속 온도' },
  ],

  capabilities: { canDoStep: true, canGetDerivatives: false },
},
```

체크리스트:
- [ ] 모든 variable에 `unit` 명시
- [ ] parameter에 `min`, `max` 명시
- [ ] `description` 한 줄씩 (AI가 보고 이해할 수 있게)
- [ ] 정적이면 state 없음, 동적이면 `variability: 'continuous'` state 추가

### Step 4. initState 작성

```js
// 정적 (state 없음)
initState: () => ({}),

// 동적 (state 초기값)
initState: (params) => ({
  T_metal: 25,
  MC_state: params.MC_init ?? 0.8,
}),
```

### Step 5. step 함수 작성 — 핵심 물리식

```js
step: (input, params, state, dt) => {
  // input: 다른 컴포넌트의 outputs
  // params: parameter 값들
  // state: 이전 step의 state (동적만)
  // dt: timestep [s]

  // 1. 물리 계산
  const Q = params.UA * (input.T_in - state.T_metal);
  // ...

  // 2. 동적이면 state 갱신 (Forward Euler)
  const newState = {
    T_metal: state.T_metal + dt * (Q / (params.m * params.cp)),
  };

  // 3. outputs 계산
  const outputs = {
    T_out: input.T_in - Q / (m_dot * cp),
    Q,
  };

  return { outputs, newState };
},
```

### Step 6. validate 작성 — 파라미터 sanity 체크

```js
validate: (params) => {
  const errors = [];

  // 음수 안 됨
  if (params.UA <= 0) {
    errors.push({ key: 'UA', msg: 'UA는 양수여야 함' });
  }

  // 단위 의심
  if (params.P_max < 1000) {
    errors.push({ key: 'P_max', msg: 'kPa인지 Pa인지 확인 (Pa면 1000+ 필요)' });
  }

  // 효율 범위
  if (params.eta < 0 || params.eta > 1) {
    errors.push({ key: 'eta', msg: '효율은 0~1 범위' });
  }

  return errors;
},
```

최소 1개 이상 작성. 사용자/AI가 이상한 값 넣었을 때 방어선.

---

## 5. 로컬 테스트

```js
// 콘솔에서 직접 호출 가능
const result = MyComponent.step(
  { T_in: 25, P_in: 1000 },        // input
  { UA: 150, m: 5, cp: 1000 },     // params
  { T_metal: 25 },                  // state
  1                                 // dt = 1s
);
console.log(result);
// → { outputs: { T_out: ..., Q: ... }, newState: { T_metal: ... } }
```

확인할 것:
- 합리적 수치 나오는지
- dt를 1s, 10s, 60s로 바꿔도 결과 폭주 안 하는지 (동적만)
- 극단 입력 (T_in = 0, T_in = 200)에서 발산 안 하는지

---

## 6. 모델 종류별 작성 팁

### On-design (가장 단순)
- 단일 운전점에서 사양 만족
- 고정 효율, 고정 PR 등
- **Phase 1 디폴트**

### Semi-empirical
- 일부 물리 + 측정 데이터 보정
- AHRI map (10-coefficient polynomial), curve fit
- 광범위 운전 조건 처리
- **계측 데이터 있을 때 추천**

### Off-design (가장 상세)
- 완전한 1D 물리 (NTU-effectiveness, P-V detailed)
- 다양한 state 보유
- **Phase 2 surrogate 학습 데이터 생성 시 사용**

---

## 7. 체크리스트 — 제출 전 마지막 확인

- [ ] typeNo가 다른 컴포넌트와 안 겹침
- [ ] 모든 variable에 `unit` 명시
- [ ] parameter에 `min`, `max` 명시
- [ ] `description` 한 줄씩 작성
- [ ] 공통 변수명 사전 따름 (m_dot, T_in, P_in 등)
- [ ] `validate()` 함수 작성 (최소 1개 sanity 체크)
- [ ] 정적/동적 결정 명확
- [ ] 동적이면 `initState()` + `state` 변수 명시
- [ ] 로컬에서 `step()` 직접 호출해 합리적 수치 확인
- [ ] dt 다양하게 줘봤을 때 안정적

---

## 8. 자주 묻는 질문

### Q. 옛날 형식 (`compute()`)으로 작성된 컴포넌트는?
A. 자동으로 호환됨. 굳이 마이그레이션 안 해도 시뮬은 동작합니다. 다만 새 컴포넌트는 새 형식으로 작성하세요.

### Q. 컴포넌트 안에서 iteration이 필요하면?
A. `step()` 안에서 자유롭게 fixed-point loop 등 사용 가능. 외부 solver와 무관합니다.

```js
step: (input, params, state, dt) => {
  let Q = 100;
  for (let i = 0; i < 50; i++) {
    const Qnew = computeQ(Q);
    if (Math.abs(Qnew - Q) < 0.01) break;
    Q = Qnew;
  }
  return { outputs: { Q, ... }, newState: ... };
},
```

### Q. 다른 컴포넌트의 출력값을 다 입력으로 받아야 하나?
A. 필요한 것만. 자동 매핑이 호환되는 변수만 연결합니다. 사용 안 하는 입력은 modelDescription에 안 적으면 됨.

### Q. AI가 내 컴포넌트를 인식하게 하려면?
A. modelDescription만 잘 작성하면 자동 인식됩니다. 별도 작업 없음.

---

## 9. 도움이 필요하면

- **물리 모델 질문**: 도메인 리드 (열역학/열교환/제어)
- **인터페이스 질문**: 플랫폼팀
- **버그/이상 동작**: GitHub issue
- **예시 코드**: `templates/_example_static.js`, `templates/_example_dynamic.js`

---

**Last updated**: 2026-04
**Maintainer**: HPWD-Studio Platform Team
