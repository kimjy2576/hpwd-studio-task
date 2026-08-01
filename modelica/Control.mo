package HPWDctrl "제어 컴포넌트"

  model PI_Controller "PI 제어기 (SH → EEV opening)"
    Modelica.Blocks.Interfaces.RealInput SH_meas "측정 과열도 [K]";
    Modelica.Blocks.Interfaces.RealOutput opening "EEV 개도 [%]";
    parameter Real SH_target = 6.0 "목표 과열도 [K] (default: L1 운전점)";
    parameter Real Kp = 2.0 "비례 게인";
    parameter Real Ki = 0.5 "적분 게인";
    parameter Real opening_init = 50.0 "적분기 초기값";
    parameter Real opening_min = 5.0, opening_max = 100.0;
    parameter Real T_aw = 1.0 "반포화(back-calculation) 시상수 [s].
      비포화 구간에서는 opening==opening_raw 라 보정항이 0 → 기존 거동 그대로.
      포화 시에만 적분을 클램프 경계로 되끌어옴. (2026-07-25: 반포화 부재로
      콜드스타트 SH=0 구간에서 I 가 -234 까지 발산, 개도가 418샘플 중 417개에서
      최소값 6%% 에 고착 -> 응축기 액범람 -> Pc 25bar 폭주가 재현됐음)";
    Real I(start = opening_init) "적분 상태";
    Real err, opening_raw;
  equation
    err = SH_meas - SH_target;          // SH 과다 → opening 키워 ṁ↑ → SH↓
    der(I) = Ki*err + (opening - opening_raw)/T_aw;
    opening_raw = Kp*err + I;
    opening = max(opening_min, min(opening_max, opening_raw));
  end PI_Controller;

  model PI_Test "가상 플랜트 폐루프 (opening↑ → SH↓)"
    PI_Controller ctrl(SH_target=5.0, Kp=2.0, Ki=0.5, opening_init=50.0);
    Real SH_plant;
  equation
    SH_plant = 12.0 - 0.1*ctrl.opening;  // opening 70% → SH 5K (정상상태 해)
    ctrl.SH_meas = SH_plant;
  end PI_Test;


  model CompStartSequencer "압축기 기동 시퀀서 — 실제 제어 로직 (2026-07-31)

    docs/CONTROL_LOGIC.md 참조. 숫자는 전부 파라미터이므로 바꿀 수 있다.

    1단계  0 -> 최소(f_min)        rate_fast (2 rps/s)
    2단계  최소 도달              rate_slow (1 rps/s) 전환
    3단계  중간1(f_mid1) 도달     hold_mid 유지
    4단계  유지 후                rate_slow 재상승
    최우선 설정 Hz 와 무관하게 기동 시 f_hold(35Hz) 도달하면
           hold_start(2분) 무조건 유지 후 목표로 간다.

    TimeTable 로는 조건부 유지를 표현할 수 없어 상태기계로 구현한다.
    상태는 이산이지만 f 는 연속이므로 적분기가 다루기 쉽다.
  "
    parameter Real f_target = 60.0 "목표 주파수 [Hz]";
    parameter Real f_min    = 30.0 "최소 주파수 [Hz]";
    parameter Real f_hold   = 35.0 "기동 강제 유지 주파수 [Hz]";
    parameter Real f_mid1   = 55.0 "중간1 주파수 [Hz]";
    parameter Boolean use_mid1 = true "중간1 유지 사용";
    parameter Real rate_fast = 2.0 "최소까지 상승률 [rps/s]";
    parameter Real rate_slow = 1.0 "이후 상승률 [rps/s]";
    parameter Real hold_start = 120.0 "f_hold 유지 시간 [s]";
    parameter Real hold_mid   =  60.0 "중간1 유지 시간 [s]";

    Modelica.Blocks.Interfaces.RealOutput N "회전수 [rpm]";
    Real f(start=0, fixed=true) "주파수 [Hz]";
    discrete Real t_hold_end(start=-1, fixed=true) "현재 유지 종료 시각 [s]";
    discrete Boolean done_start(start=false, fixed=true) "35Hz 유지 완료";
    discrete Boolean done_mid1(start=false, fixed=true) "중간1 유지 완료";
    Real rate "현재 상승률 [Hz/s] (rps=Hz)";
  equation
    // 유지 중이면 0, 아니면 구간별 상승률
    rate = if time < t_hold_end then 0.0
           elseif f < f_min then rate_fast
           else rate_slow;
    der(f) = if f >= f_target then 0.0 else rate;
    N = f*60.0;

  algorithm
    // 35Hz 강제 유지 — 다른 어떤 단계보다 우선한다
    when (not done_start) and f >= f_hold then
      t_hold_end := time + hold_start;
      done_start := true;
    end when;
    // 중간1 유지 (35Hz 유지를 마친 뒤에만)
    when use_mid1 and done_start and (not done_mid1) and f >= f_mid1 then
      t_hold_end := time + hold_mid;
      done_mid1 := true;
    end when;
  end CompStartSequencer;

end HPWDctrl;
