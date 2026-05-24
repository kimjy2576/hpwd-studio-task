package HPWDctrl "제어 컴포넌트"

  model PI_Controller "PI 제어기 (SH → EEV opening)"
    Modelica.Blocks.Interfaces.RealInput SH_meas "측정 과열도 [K]";
    Modelica.Blocks.Interfaces.RealOutput opening "EEV 개도 [%]";
    parameter Real SH_target = 6.0 "목표 과열도 [K] (default: L1 운전점)";
    parameter Real Kp = 2.0 "비례 게인";
    parameter Real Ki = 0.5 "적분 게인";
    parameter Real opening_init = 50.0 "적분기 초기값";
    parameter Real opening_min = 5.0, opening_max = 100.0;
    Real I(start = opening_init) "적분 상태";
    Real err, opening_raw;
  equation
    err = SH_meas - SH_target;          // SH 과다 → opening 키워 ṁ↑ → SH↓
    der(I) = Ki*err;
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

end HPWDctrl;
