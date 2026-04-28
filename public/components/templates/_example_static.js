/* ════════════════════════════════════════════════════════════════════
 *  EXAMPLE: 정적 (Static) 컴포넌트 — Compressor
 *  ─────────────────────────────────────────────
 *  - 입력 → 즉시 출력 (시간 효과 없음)
 *  - state 없음
 *  - "한 timestep 안에 평형 도달"하는 모든 컴포넌트는 이 패턴을 따름
 *
 *  유사 컴포넌트: Fan, EEV, TXV, Pump, Valve, 단순 HX
 * ════════════════════════════════════════════════════════════════════ */

const ExampleCompressor = {

  // ════════ Identity ════════
  typeNo: 100,
  name: 'Compressor',
  category: 'refrigerant',
  icon: undefined,                        // 실제로는 lucide-react Cog 등
  color: '#475569',
  image: './images/compressor.png',


  // ════════ Model Description ════════
  modelDescription: {
    modelType: 'on-design',
    fidelity: 0.4,
    description: '왕복동 압축기 — 체적효율·등엔트로피 효율 기반 단순 모델',

    variables: [
      // ─── Parameters ───
      {
        name: 'V_disp', causality: 'parameter', type: 'Real',
        start: 10, unit: 'mL/rev', min: 0.1, max: 1000,
        description: '체적 (cylinder displacement)',
      },
      {
        name: 'RPM', causality: 'parameter', type: 'Real',
        start: 3000, unit: 'rpm', min: 0, max: 6000,
        description: '회전수',
      },
      {
        name: 'eta_v', causality: 'parameter', type: 'Real',
        start: 0.85, unit: '-', min: 0.3, max: 1.0,
        description: '체적효율 (volumetric efficiency)',
      },
      {
        name: 'eta_is', causality: 'parameter', type: 'Real',
        start: 0.7, unit: '-', min: 0.3, max: 1.0,
        description: '등엔트로피 효율 (isentropic efficiency)',
      },
      {
        name: 'PR', causality: 'parameter', type: 'Real',
        start: 3.5, unit: '-', min: 1.0, max: 20.0,
        description: '압축비 (pressure ratio)',
      },

      // ─── Inputs ───
      {
        name: 'P_suc', causality: 'input', type: 'Real',
        unit: 'kPa', min: 100, max: 3000,
        description: '흡입 압력',
      },
      {
        name: 'T_suc', causality: 'input', type: 'Real',
        unit: '°C', min: -40, max: 80,
        description: '흡입 온도',
      },

      // ─── Outputs ───
      {
        name: 'm_dot', causality: 'output', type: 'Real',
        unit: 'g/s', description: '냉매 질량유량',
      },
      {
        name: 'T_dis', causality: 'output', type: 'Real',
        unit: '°C', description: '토출 온도',
      },
      {
        name: 'P_dis', causality: 'output', type: 'Real',
        unit: 'kPa', description: '토출 압력',
      },
      {
        name: 'W_comp', causality: 'output', type: 'Real',
        unit: 'W', description: '압축 일',
      },

      // states 없음 — 정적 컴포넌트
    ],

    capabilities: { canDoStep: true, canGetDerivatives: false },

    validRange: {
      P_suc: { min: 200, max: 1500 },
      T_suc: { min: -20, max: 30 },
    },
  },


  // ════════ State Initialization ════════
  // 정적이라 빈 객체
  initState: () => ({}),


  // ════════ Computation ════════
  step: (input, params, state, dt) => {
    const { P_suc, T_suc } = input;
    const { V_disp, RPM, eta_v, eta_is, PR } = params;

    // 토출 압력
    const P_dis = P_suc * PR;

    // 질량유량 (단순 체적효율 모델)
    // V_disp는 mL/rev → m³/rev로 변환 (×1e-6)
    // 가정: 흡입 밀도 1.2 kg/m³ (초기 추정 — semi-empirical에선 CoolProp 호출)
    const rho_suc = 1.2;
    const m_dot = (V_disp * 1e-6) * (RPM / 60) * eta_v * rho_suc * 1000; // g/s

    // 토출 온도 (등엔트로피 + 효율 보정)
    const k = 1.286;                      // 비열비 (R134a 근사)
    const T_dis = (T_suc + 273.15) * Math.pow(PR, (k - 1) / (k * eta_is)) - 273.15;

    // 압축 일 (energy balance)
    const cp = 1.0;                       // kJ/kg·K (근사)
    const W_comp = (m_dot / 1000) * cp * (T_dis - T_suc) * 1000; // W

    return {
      outputs: { m_dot, T_dis, P_dis, W_comp },
      newState: state,                    // 정적 — 변경 없음
    };
  },


  // ════════ Validation ════════
  validate: (params) => {
    const errors = [];
    if (params.eta_v <= 0 || params.eta_v > 1) {
      errors.push({ key: 'eta_v', msg: '체적효율은 0~1 범위' });
    }
    if (params.eta_is <= 0 || params.eta_is > 1) {
      errors.push({ key: 'eta_is', msg: '등엔트로피 효율은 0~1 범위' });
    }
    if (params.PR < 1) {
      errors.push({ key: 'PR', msg: '압축비는 1 이상 (압축기는 압력을 올림)' });
    }
    if (params.V_disp <= 0) {
      errors.push({ key: 'V_disp', msg: '체적은 양수' });
    }
    if (params.RPM < 0) {
      errors.push({ key: 'RPM', msg: 'RPM은 음수 안 됨' });
    }
    return errors;
  },

};

// (현 single-file 구조에서는 export 대신 TYPES 객체에 등록)
