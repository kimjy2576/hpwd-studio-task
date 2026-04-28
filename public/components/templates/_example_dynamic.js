/* ════════════════════════════════════════════════════════════════════
 *  EXAMPLE: 동적 (Dynamic) 컴포넌트 — Drum (직물 건조)
 *  ────────────────────────────────────────────────────
 *  - 시간 따라 state(직물 온도, 수분)가 변함
 *  - state 변수 + Forward Euler 적분
 *  - "한 timestep 안에 평형 도달 안 함" 컴포넌트는 이 패턴
 *
 *  유사 컴포넌트: Heat Exchanger (metal mass), Tank, Battery, Cabin
 *
 *  핵심:
 *    initState() — state 초기값
 *    derivatives() — dx/dt 계산 (외부 solver가 호출)
 *    outputs() — state로부터 algebraic outputs 계산
 *    또는 step() — 두 개를 합쳐서 직접 적분
 * ════════════════════════════════════════════════════════════════════ */

const ExampleDrum = {

  // ════════ Identity ════════
  typeNo: 201,
  name: 'Drum',
  category: 'air',
  icon: undefined,                        // RotateCw 등
  color: '#475569',
  image: './images/drum.png',


  // ════════ Model Description ════════
  modelDescription: {
    modelType: 'on-design',
    fidelity: 0.4,
    description: '드럼 — 직물 lumped capacitance 모델 (열·수분)',

    variables: [
      // ─── Parameters ───
      {
        name: 'm_fabric', causality: 'parameter', type: 'Real',
        start: 5, unit: 'kg', min: 0.5, max: 50,
        description: '직물 질량',
      },
      {
        name: 'MC_init', causality: 'parameter', type: 'Real',
        start: 0.8, unit: 'kg/kg', min: 0, max: 2,
        description: '초기 수분 함량 (수분/건중량)',
      },
      {
        name: 'hA', causality: 'parameter', type: 'Real',
        start: 50, unit: 'W/K', min: 5, max: 500,
        description: '대류 열전달계수 × 면적',
      },
      {
        name: 'cp_fab', causality: 'parameter', type: 'Real',
        start: 1500, unit: 'J/kg·K', min: 500, max: 3000,
        description: '직물 비열',
      },
      {
        name: 'h_evap', causality: 'parameter', type: 'Real',
        start: 2400e3, unit: 'J/kg', min: 1e6, max: 3e6,
        description: '증발 잠열',
      },
      {
        name: 'dP_drum', causality: 'parameter', type: 'Real',
        start: 100, unit: 'Pa', min: 0, max: 500,
        description: '드럼 통과 압력 강하',
      },

      // ─── Inputs ───
      {
        name: 'T_air_in', causality: 'input', type: 'Real',
        unit: '°C', min: -10, max: 100,
        description: '드럼 입구 공기 온도',
      },
      {
        name: 'm_air', causality: 'input', type: 'Real',
        unit: 'kg/s', min: 0, max: 1,
        description: '공기 질량유량',
      },

      // ─── Outputs ───
      {
        name: 'T_air_out', causality: 'output', type: 'Real',
        unit: '°C', description: '드럼 출구 공기 온도',
      },
      {
        name: 'MC', causality: 'output', type: 'Real',
        unit: 'kg/kg', description: '현재 직물 수분 함량',
      },
      {
        name: 'm_evap', causality: 'output', type: 'Real',
        unit: 'g/s', description: '수분 증발 속도',
      },
      {
        name: 'Q', causality: 'output', type: 'Real',
        unit: 'W', description: '공기 → 직물 열전달',
      },
      {
        name: 'dP', causality: 'output', type: 'Real',
        unit: 'Pa', description: '드럼 압력 강하',
      },

      // ─── States (★ 동적 컴포넌트의 핵심) ───
      {
        name: 'T_fab', causality: 'local', variability: 'continuous',
        start: 25, unit: '°C',
        description: '직물 온도 (시간 따라 변함)',
      },
      {
        name: 'MC_state', causality: 'local', variability: 'continuous',
        start: 0.8, unit: 'kg/kg',
        description: '직물 수분 함량 (시간 따라 감소)',
      },
    ],

    capabilities: {
      canDoStep: true,
      canGetDerivatives: true,            // ← 동적이라 RK4/Sundials 가능
    },
  },


  // ════════ State Initialization ════════
  initState: (params) => ({
    T_fab: 25,
    MC_state: params.MC_init ?? 0.8,
  }),


  // ════════ Derivatives — dx/dt 계산 (RK4/Sundials용) ════════
  // 외부 solver가 자동으로 적분. step()을 안 쓰는 경우 호출.
  derivatives: (input, params, state) => {
    const { T_air_in, m_air } = input;
    const { m_fabric, hA, cp_fab, h_evap } = params;
    const { T_fab, MC_state } = state;

    // 열전달
    const Q = hA * (T_air_in - T_fab);

    // 수분 증발 (단순 모델: T_fab가 임계점 넘으면 증발 시작)
    const m_evap_rate = MC_state > 0
      ? Math.max(0, 0.001 * Math.max(T_fab - 20, 0) * MC_state) // kg/s
      : 0;

    // dT/dt — 직물 에너지 balance
    const dT_fab = (Q - m_evap_rate * h_evap) / (m_fabric * cp_fab);

    // dMC/dt — 수분 감소
    const dMC_state = -m_evap_rate / m_fabric;

    return { T_fab: dT_fab, MC_state: dMC_state };
  },


  // ════════ Outputs — state로부터 algebraic outputs 계산 ════════
  // RK4/Sundials가 derivatives로 적분 후 이걸 호출해 outputs 계산
  outputs: (input, params, state) => {
    const { T_air_in, m_air } = input;
    const { hA, dP_drum, h_evap } = params;
    const { T_fab, MC_state } = state;

    const Q = hA * (T_air_in - T_fab);
    const m_evap_rate = MC_state > 0
      ? Math.max(0, 0.001 * Math.max(T_fab - 20, 0) * MC_state) * 1000 // g/s
      : 0;

    // 공기 출구 온도 (단순 sensible balance)
    const cp_air = 1005;
    const T_air_out = m_air > 0
      ? T_air_in - Q / (m_air * cp_air)
      : T_air_in;

    return {
      T_air_out,
      MC: MC_state,
      m_evap: m_evap_rate,
      Q,
      dP: dP_drum,
    };
  },


  // ════════ Step — Forward Euler 직접 적분 (디폴트 solver용) ════════
  // derivatives + outputs 있으면 엔진이 자동 합성하므로 step() 생략 가능.
  // 명시하면 약간 더 빠름.
  step: (input, params, state, dt) => {
    const { T_air_in, m_air } = input;
    const { m_fabric, hA, cp_fab, h_evap, dP_drum } = params;
    const { T_fab, MC_state } = state;

    // 열전달 + 증발
    const Q = hA * (T_air_in - T_fab);
    const m_evap_kgs = MC_state > 0
      ? Math.max(0, 0.001 * Math.max(T_fab - 20, 0) * MC_state)
      : 0;
    const m_evap_gs = m_evap_kgs * 1000;

    // Forward Euler 적분
    const newState = {
      T_fab: T_fab + dt * (Q - m_evap_kgs * h_evap) / (m_fabric * cp_fab),
      MC_state: Math.max(0, MC_state + dt * (-m_evap_kgs / m_fabric)),
    };

    // outputs 계산
    const cp_air = 1005;
    const T_air_out = m_air > 0
      ? T_air_in - Q / (m_air * cp_air)
      : T_air_in;

    return {
      outputs: {
        T_air_out,
        MC: newState.MC_state,
        m_evap: m_evap_gs,
        Q,
        dP: dP_drum,
      },
      newState,
    };
  },


  // ════════ Validation ════════
  validate: (params) => {
    const errors = [];
    if (params.m_fabric <= 0) {
      errors.push({ key: 'm_fabric', msg: '직물 질량은 양수' });
    }
    if (params.MC_init < 0 || params.MC_init > 2) {
      errors.push({ key: 'MC_init', msg: '초기 수분율 0~2 범위 (직물 무게 대비)' });
    }
    if (params.hA <= 0) {
      errors.push({ key: 'hA', msg: 'hA는 양수' });
    }
    if (params.cp_fab < 500 || params.cp_fab > 3000) {
      errors.push({ key: 'cp_fab', msg: '직물 비열 500~3000 J/kg·K 범위 (의심)' });
    }
    if (params.h_evap < 1e6) {
      errors.push({ key: 'h_evap', msg: '증발 잠열 단위 확인 (J/kg, 물=2.4e6)' });
    }
    return errors;
  },

};
