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

  model PI_Controller_Pulse "SH PI 제어 + EEV 스텝모터 펄스 (2026-07-27)

    실제 EEV 는 연속 개도가 아니라 스텝모터 구동이다.
      - 개도가 정수 스텝(이산)
      - 초당 최대 펄스(pps)로 변화율 제한
      - 제어 주기마다만 갱신
      - 데드밴드로 헌팅 방지
    이 특성 때문에 과도구간에서 SH 가 목표에 고정되지 않고 진동하며,
    SH<0(2상 출구)이 되어 어큐에 액이 쌓이는 구간이 실제로 발생한다.
    use_pulse=false 로 두면 기존 연속 개도와 동일(하위호환).
  "
    parameter Real SH_target = 6.0;
    parameter Real Kp = 2.0;
    parameter Real Ki = 0.5;
    parameter Real opening_init = 50.0;
    parameter Real opening_min = 5.0, opening_max = 100.0;
    parameter Real T_aw = 1.0;
    parameter Boolean use_pulse = true;
    parameter Integer n_max = 500 "EEV 전체 스텝수 (실측)";
    parameter Real pps_max = 30.0 "초당 최대 펄스 [step/s] (실측)";
    parameter Real T_ctrl = 1.0 "제어 주기 [s]";
    parameter Real deadband = 0.5 "데드밴드 [K]";
    Modelica.Blocks.Interfaces.RealInput SH_meas;
    Modelica.Blocks.Interfaces.RealOutput opening;
    Real I(start = opening_init) "적분 상태";
    Real err, opening_raw, opening_cont;
    discrete Real n_act(start = opening_init/100.0*500);
  equation
    err = SH_meas - SH_target;
    der(I) = Ki*err + (opening - opening_raw)/T_aw;
    opening_raw = Kp*err + I;
    opening_cont = max(opening_min, min(opening_max, opening_raw));
    opening = if use_pulse then n_act/n_max*100.0 else opening_cont;
  algorithm
    when sample(0, T_ctrl) then
      n_act := if abs(err) <= deadband then pre(n_act)
               else pre(n_act) + max(-pps_max*T_ctrl,
                      min(pps_max*T_ctrl, opening_cont/100.0*n_max - pre(n_act)));
      n_act := max(opening_min/100.0*n_max,
                   min(opening_max/100.0*n_max, integer(n_act + 0.5)));
    end when;
  end PI_Controller_Pulse;

  model PI_Test "가상 플랜트 폐루프 (opening↑ → SH↓)"
    PI_Controller ctrl(SH_target=5.0, Kp=2.0, Ki=0.5, opening_init=50.0);
    Real SH_plant;
  equation
    SH_plant = 12.0 - 0.1*ctrl.opening;  // opening 70% → SH 5K (정상상태 해)
    ctrl.SH_meas = SH_plant;
  end PI_Test;

end HPWDctrl;
