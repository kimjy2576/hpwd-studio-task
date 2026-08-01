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
    Real f_cmd "실효 목표 주파수 [Hz]. 35Hz 유지 전에는 f_hold 이상";
  equation
    // 유지 중이면 0, 아니면 구간별 상승률
    // 2026-07-31: 목표가 현재보다 낮으면 감속한다.
    //   35Hz 강제 유지 후 목표가 30Hz 이면 내려가야 하는데
    //   기존 der(f)=if f>=f_target then 0 은 35Hz 에 머물렀다.
    //   상승·하강 모두 rate_slow 로 움직인다(유지 중에는 0).
    rate = if time < t_hold_end then 0.0
           elseif f < f_min then rate_fast
           else rate_slow;
    // 2026-07-31: 35Hz 강제 유지는 설정 Hz 와 무관하다.
    //   목표가 30Hz 여도 일단 f_hold(35Hz)까지 올라가 2분 유지한 뒤
    //   목표로 내려온다. 그래서 유지를 마치기 전의 실효 목표는 f_hold 다.
    //   (실측: 이 처리가 없으면 30Hz 에서 멈춰 35Hz 유지가 발동하지 않았다)
    //   f_cmd 를 정확히 f_hold 로 두면 f 가 35.0 에서 멈춰
    //   when (f >= f_hold) 이 이산 전이를 만들지 못한다(실측: done_start 가
    //   끝까지 false). 아주 조금 넘어서도록 여유를 준다.
    f_cmd = if done_start then f_target else max(f_target, f_hold) + 0.01;
    //   감속에도 유지(rate=0)가 적용돼야 한다. rate 는 유지 중 0 이므로
    //   부호만 바꿔 쓴다. -rate_slow 를 직접 쓰면 유지 중에도 내려간다.
    der(f) = if abs(f - f_cmd) < 1e-6 then 0.0
             elseif f < f_cmd then rate
             else -rate;
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


  model EEV_Sequencer "EEV 단계별 제어 — 실제 로직 (2026-07-31)

    docs/CONTROL_LOGIC.md 참조. 숫자는 전부 파라미터다.

    1단계 초기 450 pulse (완전 개방)
    2단계 압축기 기동 기점 hold_init(2분) 유지
    3단계 SH <= sh_close(5K) 가 될 때마다 dt_close(10s) 주기로 d_close(50) 감소
    4단계 마지막 100 pulse 구간에서는 n_min(75) 으로 감소
    5단계 n_min 도달 후 SH >= sh_open(15K) 이면 dt_open(30s)마다 d_open(4) 증가,
          n_max5(300) 상한
    6단계 기동 후 hold_init 경과 && SH < sh_open -> 정상제어
          rate_norm(5 pulse/s), 목표 sh_set(4K)
          데드밴드 비대칭: SH >= sh_hi(6K) 면 열고, SH <= sh_lo(3K) 면 닫는다

    구현 메모
      단계 진행이 시간이 아니라 SH 조건에 걸려 있으므로 when 절 상태기계다.
      n 은 이산(pulse)이지만 opening 은 연속 출력이라 적분기가 다루기 쉽다.
      정상제어(6단계)만 매 스텝 연속 이동하고, 3~5단계는 주기적 이산 이동이다.
  "
    parameter Real n_full   = 450.0 "전체 스트로크 [pulse]";
    parameter Real n_init   = 450.0 "초기 개도 [pulse]";
    parameter Real n_min    =  75.0 "최소 개도 [pulse]";
    parameter Real n_max5   = 300.0 "5단계 상한 [pulse]";
    parameter Real hold_init = 120.0 "기동 후 유지 시간 [s]";
    parameter Real sh_close =  5.0 "3단계 조임 판정 과열도 [K]";
    parameter Real sh_open  = 15.0 "5단계 개방 판정 과열도 [K]";
    parameter Real sh_set   =  4.0 "정상제어 목표 과열도 [K]";
    parameter Real sh_hi    =  6.0 "정상제어 여는 기준 [K]";
    parameter Real sh_lo    =  3.0 "정상제어 닫는 기준 [K]";
    parameter Real d_close  = 50.0 "3단계 감소량 [pulse]";
    parameter Real d_open   =  4.0 "5단계 증가량 [pulse]";
    parameter Real dt_close = 10.0 "3단계 주기 [s]";
    parameter Real dt_open  = 30.0 "5단계 주기 [s]";
    parameter Real rate_norm = 5.0 "정상제어 최대 속도 [pulse/s]. PI 출력의 포화 한계";
    parameter Real Kp_eev = 2.5 "EEV PI 비례게인 [pulse/s/K]. 오차 2K 에서 최대속도";
    parameter Real Ki_eev = 0.05 "EEV PI 적분게인 [pulse/s/K/s]";
    parameter Real db_smooth = 0.3
      "데드밴드 경계 완화폭 [K] (2026-07-31). 0 에 가까울수록 계단에 가깝다";
    parameter Real t_comp_on =  0.0 "압축기 기동 시각 [s]";

    Modelica.Blocks.Interfaces.RealInput SH "측정 과열도 [K]";
    Modelica.Blocks.Interfaces.RealOutput opening "개도 [%]";
    Real n_pulse "현재 개도 [pulse]";
    discrete Real n_step(start=450.0, fixed=true) "이산 단계에서 정한 개도";
    discrete Boolean at_min(start=false, fixed=true) "n_min 도달 (5단계 진입)";
    discrete Real t_min_reached(start=-1e9, fixed=true) "n_min 도달 시각 [s]";
    discrete Boolean normal(start=false, fixed=true) "6단계 정상제어 진입";
    Real n_cont(start=0.0, fixed=true) "정상제어 누적 이동량 [pulse]";
    Real v_norm "정상제어 이동 속도 [pulse/s]";
    Real db_active "데드밴드 밖 여부 [0~1] (2026-07-31)";
    Real err_sh "과열도 오차 [K]";
    Real v_pi "PI 가 요구하는 속도 [pulse/s] (포화 전)";
    Real I_eev(start=0.0, fixed=true) "PI 적분 상태";
  equation
    // 6단계 정상제어: 비대칭 데드밴드. 사이(3~6K)에서는 멈춘다.
    // 2026-07-31: 데드밴드 경계를 매끄럽게.
    //   기존 if 문은 SH 가 sh_hi/sh_lo 를 지날 때마다 v_norm 이
    //   0 <-> ±rate_norm 으로 계단 변화해 이벤트를 만든다.
    //   6단계 진입(t=210) 순간 SH 8.6K > sh_hi 6K 라 v_norm 이
    //   0 에서 +5 로 튀며 적분이 멈췄다(실측: 단일 식으로 바꿔도 동일).
    //   tanh 로 폭 db_smooth 만큼 부드럽게 잇는다. 데드밴드 자체는 유지된다.
    // 2026-07-31 정정: 목표는 sh_set(4K)이고 데드밴드는 '언제 움직일지'만 정한다.
    //   기존은 sh_hi/sh_lo 를 목표처럼 써서 SH 8.6K 에서 무조건 열었다.
    //   사양: 4K 를 향해 제어하되, 3~6K 안에서는 멈춘다(헌팅 방지).
    //     SH > sh_hi(6K) -> 4K 로 내리려면 개도를 연다 (증발량↑ -> SH↓)
    //     SH < sh_lo(3K) -> 4K 로 올리려면 개도를 닫는다
    //     3~6K           -> 정지
    //   방향은 (SH - sh_set)의 부호로 정하고, 크기는 데드밴드 밖일 때만 산다.
    //   active 는 tanh 로 매끄럽게 이어 이벤트를 만들지 않는다.
    // 2026-07-31: rate_norm 은 '최대' 속도다. 항상 그 속도로 움직이는 것이
    //   아니라 PI 가 요구하는 속도를 그 값으로 제한한다.
    //   기존 tanh 식은 데드밴드 밖이면 곧바로 최대 속도가 되어
    //   목표 근처에서 과도하게 움직였다(헌팅 원인).
    //     v_pi   = Kp*(SH - sh_set) + Ki*I     오차에 비례
    //     v_norm = 데드밴드 밖일 때만, ±rate_norm 으로 포화
    //   데드밴드 안에서는 적분도 멈춘다(와인드업 방지).
    db_active = 0.5*(1.0 + tanh((SH - sh_hi)/db_smooth))
              + 0.5*(1.0 + tanh((sh_lo - SH)/db_smooth));
    err_sh = SH - sh_set;
    v_pi = Kp_eev*err_sh + Ki_eev*I_eev;
    der(I_eev) = if normal then db_active*err_sh else 0.0;
    v_norm = if not normal then 0.0
             else db_active*max(-rate_norm, min(rate_norm, v_pi));
    der(n_cont) = v_norm;
    // 2026-07-31: 6단계 진입 시 n_pulse 가 n_step -> n_base+n_cont 로
    //   갈아타며 불연속이 생겨 적분이 멈췄다(실측: t=210 에서 이벤트 반복).
    //   n_base 를 진입 시점 n_step 으로 잡고 n_cont 를 0 에서 시작하므로
    //   값은 이어지지만, OMC 가 두 식 사이의 전환을 이벤트로 처리한다.
    //   noEvent 로 감싸 전환에서 이벤트를 만들지 않게 한다.
    // 2026-07-31: 두 식 사이 전환 자체를 없앤다.
    //   noEvent 로 감싸도 when 절이 이벤트를 만들어 t=210 정체가 반복됐다.
    //   n_step(이산 단계) + n_cont(정상제어 누적)를 항상 더하는 하나의 식으로
    //   두면 전환이 사라진다. 정상제어 전에는 n_cont=0 이므로 값은 동일하다.
    n_pulse = min(max(n_step + n_cont, n_min), n_full);
    opening = n_pulse/n_full*100.0;

  algorithm
    // 3~4단계: 기동 유지가 끝난 뒤, SH 가 낮으면 주기적으로 조인다
    when sample(t_comp_on + hold_init, dt_close) then
      if (not at_min) and (not normal) and SH <= sh_close then
        // 마지막 100 pulse 구간은 한 번에 n_min 으로 (4단계)
        n_step := if n_step - d_close <= n_min + d_close
                  then n_min else n_step - d_close;
      end if;
      if n_step <= n_min and not at_min then
        at_min := true;
        t_min_reached := time;
      end if;
    end when;

    // 5단계: n_min 도달 후 과열도가 높으면 조금씩 연다
    when sample(t_comp_on + hold_init, dt_open) then
      if at_min and (not normal) and SH >= sh_open then
        n_step := min(n_step + d_open, n_max5);
      end if;
    end when;

    // 6단계 진입: 기동 유지 경과 && 과열도가 5단계 기준 아래
    //   reinit 은 algorithm 에서 쓸 수 없으므로 진입 시점의 n_step 을
    //   기준값으로 잡고 n_cont 는 그로부터의 변화량으로 둔다.
    //   at_min 도달과 동시에 진입하면 5단계를 건너뛴다.
    //   사양은 '75 pulse 도달 시 SH>=15K 이면 5단계, 그 판정을 거친 뒤
    //   SH<15K 이면 정상제어' 이므로 최소 한 주기(dt_open)는 5단계에 머문다.
    when at_min and (time > t_min_reached + dt_open)
         and (time > t_comp_on + hold_init) and SH < sh_open then
      normal := true;
    end when;
  end EEV_Sequencer;


  model EEV_Test "EEV_Sequencer 단독 시험 — SH 시나리오 주입 (2026-07-31)"
    HPWDctrl.EEV_Sequencer eev;
    Real SH_in;
  equation
    // 시나리오: 기동 직후 SH 낮음(조임) -> 과열 급등(5단계) -> 정상권
    SH_in = if time < 130 then 2.0
            elseif time < 230 then 3.0      // 3단계 조임 진행
            elseif time < 320 then 20.0     // 5단계 개방
            else 5.0;                        // 6단계 정상제어
    eev.SH = SH_in;
  end EEV_Test;

end HPWDctrl;
