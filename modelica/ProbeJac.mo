within ;
package ProbeJac "P3' 최소 프로브 — 기호 야코비안 속도: 테이블 vs 해석 물성 (2026-08-02)

  HX 를 최소로 흉내낸다: 12셀 엔탈피 동역학 + 느린 압력 동역학.
  셀마다 rho_ph/T_ph, 공통 포화선 5종을 호출한다. 두 모델은 물성
  호출만 다르고 구조가 같다. symbolic 빌드 후 coloredSymbolical /
  coloredNumerical 속도를 비교한다.
"
  model ProbeTab "테이블 물성판"
    parameter Integer M = 12;
    parameter Real V_cell = 2e-4, m_flow = 0.01, UA = 15.0, T_air = 30.0;
    Real p(start=5e5, fixed=true, nominal=1e6);
    Real h[M](each start=560e3, each fixed=true, each nominal=4e5);
    Real T[M], rho[M], Q[M];
    Real hl_s, hv_s, Tsat_s, rhol_s, rhov_s;
  equation
    hl_s = R290Tab.hl(p); hv_s = R290Tab.hv(p); Tsat_s = R290Tab.Tsat(p);
    rhol_s = R290Tab.rhol(p); rhov_s = R290Tab.rhov(p);
    der(p) = 2e3*sin(0.05*time) + 0.02*(hv_s - h[M]);
    for k in 1:M loop
      T[k] = R290Tab.T_ph(p, h[k]) - 273.15;
      rho[k] = R290Tab.rho_ph(p, h[k]);
      Q[k] = UA*(T_air - T[k])*(1.0 + 0.02*(rhol_s - rho[k])/rhol_s);
      rho[k]*V_cell*der(h[k]) = m_flow*((if k == 1 then hl_s + 2e4 else h[k-1]) - h[k]) + Q[k];
    end for;
  end ProbeTab;

  model ProbeAna "해석 물성판 — 호출만 _a 로 교체"
    parameter Integer M = 12;
    parameter Real V_cell = 2e-4, m_flow = 0.01, UA = 15.0, T_air = 30.0;
    Real p(start=5e5, fixed=true, nominal=1e6);
    Real h[M](each start=560e3, each fixed=true, each nominal=4e5);
    Real T[M], rho[M], Q[M];
    Real hl_s, hv_s, Tsat_s, rhol_s, rhov_s;
  equation
    hl_s = R290Tab.hl_a(p); hv_s = R290Tab.hv_a(p); Tsat_s = R290Tab.Tsat_a(p);
    rhol_s = R290Tab.rhol_a(p); rhov_s = R290Tab.rhov_a(p);
    der(p) = 2e3*sin(0.05*time) + 0.02*(hv_s - h[M]);
    for k in 1:M loop
      T[k] = R290Tab.T_ph_a(p, h[k]) - 273.15;
      rho[k] = R290Tab.rho_ph_a(p, h[k]);
      Q[k] = UA*(T_air - T[k])*(1.0 + 0.02*(rhol_s - rho[k])/rhol_s);
      rho[k]*V_cell*der(h[k]) = m_flow*((if k == 1 then hl_s + 2e4 else h[k-1]) - h[k]) + Q[k];
    end for;
  end ProbeAna;

  model ProbeMed "Medium 계약 경유 — ProbeAna 와 수학 동일, 바인딩만 다름"
    package Medium = R290Medium;
    parameter Integer M = 12;
    parameter Real V_cell = 2e-4, m_flow = 0.01, UA = 15.0, T_air = 30.0;
    Real p(start=5e5, fixed=true, nominal=1e6);
    Real h[M](each start=560e3, each fixed=true, each nominal=4e5);
    Medium.ThermodynamicState st[M];
    Medium.SaturationProperties sat;
    Real T[M], rho[M], Q[M];
    Real hl_s, hv_s, Tsat_s, rhol_s, rhov_s;
  equation
    sat = Medium.setSat_p(p);
    hl_s = Medium.bubbleEnthalpy(sat); hv_s = Medium.dewEnthalpy(sat);
    Tsat_s = sat.Tsat;
    rhol_s = Medium.bubbleDensity(sat); rhov_s = Medium.dewDensity(sat);
    der(p) = 2e3*sin(0.05*time) + 0.02*(hv_s - h[M]);
    for k in 1:M loop
      st[k] = Medium.setState_ph(p, h[k]);
      T[k] = Medium.temperature(st[k]) - 273.15;
      rho[k] = Medium.density(st[k]);
      Q[k] = UA*(T_air - T[k])*(1.0 + 0.02*(rhol_s - rho[k])/rhol_s);
      rho[k]*V_cell*der(h[k]) = m_flow*((if k == 1 then hl_s + 2e4 else h[k-1]) - h[k]) + Q[k];
    end for;
  end ProbeMed;
end ProbeJac;
