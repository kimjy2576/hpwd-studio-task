within ;
package HPWDevapC "PH4-A 보존형 staggered FV HX — 병행 모델 (2026-08-02 S2 골격)

  설계: docs/PH4A_STAGGERED_DESIGN.md. 기존 Evap_On_Dyn 은 무수정 (병행 원칙).
  S2 범위: 냉매측 보존식 + 면 유량 + upwind. 공기측은 UA 스텁 (S3 에서 습식 배선).
"

  model Evap_On_DynC "보존형 증발기 골격 — 상태 (p_hx, h[N]), 면 유량 미지수"
    replaceable package Medium = R290Medium "냉매 물성";
    parameter Integer N = 12 "셀 수";
    parameter Real V_cell = 2.0e-5 "셀 내용적 [m3] (S3 에서 기하 연결)";
    parameter Real UA_stub = 12.0 "셀당 공기측 UA 스텁 [W/K] (S3 에서 습식 체인으로 대체)";
    parameter Real m_eps = 1.0e-4 "upwind 전환 폭 [kg/s] — noEvent 매끄러운 상류 선택";
    parameter Real p_start = 5.0e5, h_start = 4.0e5;
    parameter Boolean steadyInit = false;

    HPWD.RefPort port_a "입구", port_b "출구";
    Modelica.Blocks.Interfaces.RealInput T_air "공기 온도 스텁 [degC]";

    // ── 상태 (D2 Phase 1) ──
    Real p_hx(start=p_start, fixed=not steadyInit, nominal=1.0e6) "HX 압력 [Pa] (D1: 단일)";
    Real h[N](each start=h_start, each fixed=not steadyInit, each nominal=4.0e5) "셀 엔탈피 [J/kg]";

    // ── 면 유량 (미지수): mdot[1]=입구면(port_a), mdot[N+1]=출구면(port_b) ──
    Real mdot[N + 1](each nominal=1.0e-2) "면 질량유량 [kg/s], 흐름 방향 양수";
    Real h_face[N + 1] "면 상류 엔탈피 [J/kg] (매끄러운 upwind)";

    // ── 셀 물성·장부 ──
    Real rho[N](each nominal=50.0), drdp[N], drdh[N];
    Real T_c[N] "셀 온도 [degC]";
    Real M_c[N](each nominal=1.0e-3), M_tot "질량 장부 [kg]";
    Real Q_ref[N] "셀 열입력 [W]";
    Real h_in_b "입구 경계 엔탈피 [J/kg]";
  initial equation
    if steadyInit then
      der(p_hx) = 0;
      for k in 1:N loop der(h[k]) = 0; end for;
    end if;
  equation
    // 경계 배선 (D4): Δp 내부 마찰은 S3 — 골격은 0 스텁
    port_a.p = p_hx;
    port_b.p = p_hx;
    mdot[1] = port_a.m_flow;
    mdot[N + 1] = -port_b.m_flow;
    h_in_b = inStream(port_a.h_outflow);
    port_a.h_outflow = h[1];
    port_b.h_outflow = h[N];

    // 매끄러운 upwind (D3): w→1 이면 상류(왼쪽) 값
    h_face[1] = (0.5*(1.0 + tanh(mdot[1]/m_eps)))*h_in_b
              + (1.0 - 0.5*(1.0 + tanh(mdot[1]/m_eps)))*h[1];
    for k in 2:N loop
      h_face[k] = (0.5*(1.0 + tanh(mdot[k]/m_eps)))*h[k - 1]
                + (1.0 - 0.5*(1.0 + tanh(mdot[k]/m_eps)))*h[k];
    end for;
    h_face[N + 1] = (0.5*(1.0 + tanh(mdot[N + 1]/m_eps)))*h[N]
                  + (1.0 - 0.5*(1.0 + tanh(mdot[N + 1]/m_eps)))*inStream(port_b.h_outflow);

    // 셀 보존식 — 질량 (EOS 전개형, 해석 도함수 명시 사용)
    for k in 1:N loop
      rho[k] = Medium.rho_ph(p_hx, h[k]);
      drdp[k] = Medium.rho_ph_der(p_hx, h[k], 1.0, 0.0);
      drdh[k] = Medium.rho_ph_der(p_hx, h[k], 0.0, 1.0);
      M_c[k] = rho[k]*V_cell;
      V_cell*(drdp[k]*der(p_hx) + drdh[k]*der(h[k])) = mdot[k] - mdot[k + 1];
    end for;

    // 셀 보존식 — 에너지: d(U)/dt = Ḣ차 + Q, U = M·h − p·V
    //   der(M) 을 질량식으로 치환하면
    //   M·der(h) − V·der(p) = ṁ_in·(h_face,in − h) − ṁ_out·(h_face,out − h) + Q
    //   (V·dp/dt 압력일 항이 현행 Dyn 대비 새로 포함되는 지점)
    for k in 1:N loop
      T_c[k] = Medium.T_ph(p_hx, h[k]) - 273.15;
      Q_ref[k] = UA_stub*(T_air - T_c[k]);
      M_c[k]*der(h[k]) - V_cell*der(p_hx)
        = mdot[k]*(h_face[k] - h[k]) - mdot[k + 1]*(h_face[k + 1] - h[k]) + Q_ref[k];
    end for;

    M_tot = sum(M_c);
  end Evap_On_DynC;

  model PlugC "밀폐 캡 — m_flow=0 경계 (stream 규약 준수용)"
    HPWD.RefPort port;
    parameter Real h_amb = 4.0e5;
  equation
    port.m_flow = 0.0;
    port.h_outflow = h_amb;
  end PlugC;

  model G0_Sealed "G0 게이트 — 포트 밀폐 + 공기 가열/냉각 스텝, 질량 폐합 검사"
    Evap_On_DynC hx(N=12, h_start=5.6e5, p_start=5.0e5);
    PlugC capA, capB;
    Real drift_rel "질량 장부 상대 편차 (판정 변수)";
  protected
    parameter Real M0(fixed=false);
  initial equation
    M0 = hx.M_tot;
  equation
    connect(hx.port_a, capA.port);
    connect(hx.port_b, capB.port);
    hx.T_air = if time < 200.0 then 40.0 elseif time < 400.0 then 5.0 else 40.0;
    drift_rel = (hx.M_tot - M0)/M0;
  end G0_Sealed;

end HPWDevapC;
