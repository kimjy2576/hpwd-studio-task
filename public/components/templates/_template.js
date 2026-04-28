/* ════════════════════════════════════════════════════════════════════
 *  HPWD-Studio Component Template
 *  ───────────────────────────────
 *  사용법:
 *    1. 이 파일을 components/my_component.js로 복사
 *    2. MyComponent를 자신의 컴포넌트 이름으로 변경
 *    3. 빈칸 채우기 — TODO 주석 따라가기
 *    4. COMPONENT_GUIDE.md 참고
 *
 *  도움 예시:
 *    - 정적 컴포넌트: _example_static.js (Compressor)
 *    - 동적 컴포넌트: _example_dynamic.js (Drum)
 * ════════════════════════════════════════════════════════════════════ */

const MyComponent = {

  // ════════ Identity ════════
  typeNo: 999,                            // TODO: 자기 카테고리 대역에서 안 쓰는 번호
  name: 'MyComponent',                    // TODO: 컴포넌트 이름 (Type Library에 표시)
  category: 'refrigerant',                // TODO: 'refrigerant' | 'air' | 'water' | 'control' | 'math'
  icon: undefined,                        // TODO: lucide-react 아이콘 (e.g. Cog, Thermometer)
  color: '#475569',                       // TODO: hex 색
  image: undefined,                       // 선택: './images/mycomp.png'


  // ════════ Model Description (FMI 호환 메타데이터) ════════
  modelDescription: {
    modelType: 'on-design',               // 'on-design' | 'semi-empirical' | 'off-design'
    fidelity: 0.5,                        // 0(단순) ~ 1(상세)
    description: 'TODO: 한 줄 모델 설명',

    variables: [
      // ─── Parameters (시간 무관 상수, 사용자가 Properties에서 설정) ───
      // TODO: 자기 컴포넌트 parameter 추가
      {
        name: 'param1',
        causality: 'parameter',
        type: 'Real',
        start: 10,                        // 기본값
        unit: 'kPa',                      // 단위 (필수)
        min: 0,
        max: 1000,
        description: '의미 있는 한 줄 설명',
      },

      // ─── Inputs (다른 컴포넌트의 outputs에서 받음) ───
      // TODO: 공통 변수명 사전 (T_in, P_in, m_dot 등) 우선 사용
      {
        name: 'T_in',
        causality: 'input',
        type: 'Real',
        unit: '°C',
        min: -40,
        max: 200,
      },

      // ─── Outputs (다른 컴포넌트로 전달) ───
      // TODO: 공통 변수명 사전 따라 작성
      {
        name: 'T_out',
        causality: 'output',
        type: 'Real',
        unit: '°C',
      },

      // ─── States (동적 컴포넌트만 — 시간 따라 변하는 변수) ───
      // 정적 컴포넌트면 이 부분 삭제
      // 동적 예시:
      // {
      //   name: 'T_metal',
      //   causality: 'local',
      //   variability: 'continuous',
      //   start: 25,
      //   unit: '°C',
      //   description: '금속 온도',
      // },
    ],

    capabilities: {
      canDoStep: true,                    // step()으로 적분 가능
      canGetDerivatives: false,           // 동적이면 true (RK4/Sundials용)
      canHandleEvents: false,
    },
  },


  // ════════ State Initialization ════════
  // 정적: 빈 객체 반환
  // 동적: state 변수 초기값
  initState: (params) => ({
    // TODO: 동적이면 state 초기값 설정
    // T_metal: 25,
    // MC_state: params.MC_init ?? 0.8,
  }),


  // ════════ Computation — 핵심 물리식 ════════
  step: (input, params, state, dt) => {
    // TODO: 여기에 모델 작성

    // 1. input / params 분해
    const { /* TODO: T_in, P_in 등 */ } = input;
    const { /* TODO: param1 등 */ } = params;
    // const { T_metal } = state;          // 동적이면

    // 2. 물리 계산
    // TODO: 모델식 작성
    const T_out = 0;                      // 임시 placeholder

    // 3. 동적이면 state 갱신 (Forward Euler 예시)
    const newState = state;               // 정적 — state 그대로
    // const newState = {                  // 동적 예시
    //   T_metal: state.T_metal + dt * (Q / (params.m * params.cp)),
    // };

    // 4. outputs 반환
    return {
      outputs: {
        T_out,                            // TODO: outputs 채우기
      },
      newState,
    };
  },


  // ════════ Validation — 파라미터 sanity 체크 ════════
  validate: (params) => {
    const errors = [];

    // TODO: 최소 1개 sanity 체크 작성
    // if (params.param1 <= 0) {
    //   errors.push({ key: 'param1', msg: '양수여야 함' });
    // }
    // if (params.eta < 0 || params.eta > 1) {
    //   errors.push({ key: 'eta', msg: '효율은 0~1 범위' });
    // }

    return errors;
  },

};

// (현 single-file 구조에서는 export 대신 TYPES 객체에 등록)
// export default MyComponent;
