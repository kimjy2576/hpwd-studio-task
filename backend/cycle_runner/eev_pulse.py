"""eev_pulse — EEV 스텝모터 펄스 제어기 (2026-07-27).

Modelica HPWDctrl.PI_Controller_Pulse 와 동일한 정의.
양쪽 모델이 같은 EEV 거동을 갖도록 파라미터·알고리즘을 일치시킨다.

배경
    실제 EEV 는 연속 개도가 아니라 스텝모터 구동이다.
      - 개도가 정수 스텝(이산)
      - 초당 최대 펄스(pps)로 변화율 제한
      - 제어 주기마다만 갱신
      - 데드밴드로 헌팅 방지
    이 특성 때문에 과도구간에서 SH 가 목표에 고정되지 않고 진동하며,
    SH<0(2상 출구)이 되어 어큐에 액이 쌓이는 구간이 실제로 발생한다.

    정상해석에서는 SH=6 이 맞으나 과도해석에서는 그렇지 않다는 것이
    이 모델의 핵심이다.

Modelica 대응
    PI_Controller_Pulse.n_max, pps_max, T_ctrl, deadband, use_pulse
    와 이름·기본값이 같다.
"""


class EEVPulseController:
    """SH PI 제어 + EEV 스텝모터 펄스.

    사용법
        ctrl = EEVPulseController(SH_target=6.0, opening_init=18.0)
        for each time step:
            opening = ctrl.step(SH_meas, dt)
    """

    def __init__(self, SH_target=6.0, Kp=2.0, Ki=0.5,
                 opening_init=50.0, opening_min=5.0, opening_max=100.0,
                 T_aw=1.0, use_pulse=True,
                 n_max=500, pps_max=30.0, T_ctrl=1.0, deadband=0.5):
        self.SH_target = SH_target
        self.Kp = Kp
        self.Ki = Ki
        self.opening_min = opening_min
        self.opening_max = opening_max
        self.T_aw = T_aw
        self.use_pulse = use_pulse
        self.n_max = n_max
        self.pps_max = pps_max
        self.T_ctrl = T_ctrl
        self.deadband = deadband
        # 상태
        self.I = opening_init                      # 적분 상태
        self.n_act = round(opening_init / 100.0 * n_max)   # 실제 스텝수
        self.opening = opening_init
        self._t_last_ctrl = 0.0
        self._t = 0.0

    def step(self, SH_meas, dt):
        """한 시간 스텝 진행 후 개도 [%] 반환.

        2026-07-30 수정: dt 를 통째로 적분하면 발산한다.
          기존에는 self.I += dt * (...) 로 한 번에 적분했는데,
          동적해의 dt(20~60 s)가 제어 주기 T_ctrl(1 s)보다 훨씬 커서
          적분기가 폭주했다 (실측: I 가 -1.9e3 -> 1.1e5 -> -6.6e6).
          반포화 항 (opening-opening_raw)/T_aw 도 T_aw=1 s 인데 dt=60 이
          곱해져 같이 터졌다.
          => dt 를 T_ctrl 단위로 쪼개 실제 제어 주기대로 여러 번 돈다.
             실제 EEV 도 1초마다 갱신하지 60초를 한 번에 움직이지 않는다.

        Args:
          SH_meas: 측정 과열도 [K] — 2상이면 음수 (부호 있는 SH)
          dt     : 시간 스텝 [s]
        """
        err = SH_meas - self.SH_target
        n_sub = max(1, int(round(dt / self.T_ctrl)))
        h = dt / n_sub          # 실제 적분 간격 (= T_ctrl)

        for _ in range(n_sub):
            self._t += h
            opening_raw = self.Kp * err + self.I
            opening_cont = max(self.opening_min,
                               min(self.opening_max, opening_raw))
            # anti-windup back-calculation (Modelica PI_Controller 와 동일 형태)
            self.I += h * (self.Ki * err
                           + (self.opening - opening_raw) / self.T_aw)
            # 적분 상태도 물리 범위로 제한 — 반포화가 못 잡는 폭주 방지
            self.I = max(-2.0 * self.opening_max,
                         min(2.0 * self.opening_max, self.I))

            if not self.use_pulse:
                self.opening = opening_cont
                continue

            if abs(err) > self.deadband:
                target = opening_cont / 100.0 * self.n_max
                step_lim = self.pps_max * self.T_ctrl
                delta = max(-step_lim, min(step_lim, target - self.n_act))
                self.n_act = self.n_act + delta
            self.n_act = max(self.opening_min / 100.0 * self.n_max,
                             min(self.opening_max / 100.0 * self.n_max,
                                 round(self.n_act)))
            self.opening = self.n_act / self.n_max * 100.0

        return self.opening

    def state(self):
        """진단용 상태."""
        return {'opening': self.opening, 'n_act': self.n_act,
                'I': self.I, 't': self._t}
