package HXCorr "HX Moving-Boundary correlation 함수 라이브러리 (Python 원본 충실 포팅)"
  // correlation = 순수 수학 함수(물성·기하 입력). 물성은 모델이 HelmholtzMedia(냉매)/
  // 아래 공기 transport 함수로 계산해 전달 → media-in-function 스코프 문제 회피.
  // 각 함수는 Python backend/components 와 동일 입력으로 1:1 교차검증됨.

  // ════════════ 냉매측 단상 HTC ════════════
  function dittus_boelter
    "단상 난류 HTC — Dittus-Boelter (Nu=0.023·Re^0.8·Pr^n). single_phase.py와 동일."
    input Real mu "점성 [Pa·s]";
    input Real k "열전도도 [W/m·K]";
    input Real cp "정압비열 [J/kg·K]";
    input Real m_dot "질량유량 [kg/s]";
    input Modelica.Units.SI.Diameter D_i;
    input Boolean heating = true "증발=true(n=0.4), 응축=false(n=0.3)";
    output Real alpha "[W/m²·K]";
  protected
    Real G, Re, Pr, Nu, n;
  algorithm
    G := m_dot/(Modelica.Constants.pi/4.0*D_i^2);
    Re := G*D_i/mu;
    Pr := mu*cp/k;
    n := if heating then 0.4 else 0.3;
    Nu := 0.023*Re^0.8*Pr^n;
    alpha := max(Nu*k/D_i, 50.0);
  end dittus_boelter;

  // ════════════ 핀 효율 (Schmidt 1949) ════════════
  function fin_equivalent_radius "Schmidt 등가 핀반지름비 r_e/r (hexagonal/rect cell)"
    input Real D_o, P_t, P_l;
    input String layout = "staggered";
    output Real r_e_over_r;
  protected
    Real M_, L_, beta_1, psi;
  algorithm
    if layout == "staggered" then
      M_ := P_t/2.0;
      L_ := sqrt((P_t/2.0)^2 + P_l^2)/2.0;
      beta_1 := L_/max(M_, 1e-9);
      psi := M_/max(D_o/2.0, 1e-9);
      r_e_over_r := 1.27*psi*sqrt(max(beta_1 - 0.3, 0.01));
    else
      psi := (P_t/2.0)/max(D_o/2.0, 1e-9);
      beta_1 := (P_l/2.0)/max(P_t/2.0, 1e-9);
      r_e_over_r := 1.28*psi*sqrt(max(beta_1 - 0.2, 0.01));
    end if;
    r_e_over_r := max(r_e_over_r, 1.01);
  end fin_equivalent_radius;

  function eta_circular_fin "원형핀 효율 η = tanh(m·r·φ)/(m·r·φ)"
    input Real r_e_over_r, D_o, t_fin, k_fin, alpha_o;
    output Real eta;
  protected
    Real r, phi, m, m_r;
  algorithm
    r := D_o/2.0;
    phi := (r_e_over_r - 1.0)*(1.0 + 0.35*log(r_e_over_r));
    m := if k_fin*t_fin > 0.0 then sqrt(2.0*alpha_o/(k_fin*t_fin)) else 0.0;
    m_r := m*r*phi;
    eta := if m_r > 0.0 then tanh(m_r)/m_r else 1.0;
    eta := max(0.1, min(1.0, eta));
  end eta_circular_fin;

  function schmidt_fin "Schmidt(1949) 핀효율 = eta_circular_fin(등가반지름). fin_efficiency.py와 동일."
    input Real D_o, P_t, P_l, t_fin, k_fin, alpha_o;
    input String layout = "staggered";
    output Real eta;
  algorithm
    eta := eta_circular_fin(fin_equivalent_radius(D_o, P_t, P_l, layout), D_o, t_fin, k_fin, alpha_o);
  end schmidt_fin;

  // ════════════ 공기 transport (CoolProp 'Air' fit, 270~350K, <0.01%) ════════════
  function mu_air "건공기 점성 [Pa·s]"
    input Modelica.Units.SI.Temperature T;
    output Real mu;
  algorithm
    mu := (-3.25932978e-11)*T^2 + 6.77706008e-08*T + 1.13920139e-06;
  end mu_air;

  function k_air "건공기 열전도도 [W/m·K]"
    input Modelica.Units.SI.Temperature T;
    output Real k;
  algorithm
    k := (-3.87827090e-08)*T^2 + 9.75720314e-05*T + 6.02888049e-04;
  end k_air;

  function Pr_air "건공기 Prandtl"
    input Modelica.Units.SI.Temperature T;
    output Real Pr;
  algorithm
    Pr := 4.81463177e-07*T^2 - 4.16079061e-04*T + 7.88559225e-01;
  end Pr_air;

  function cp_air_moist "습공기 정압비열 [J/kg dry air·K] ≈ 1006 + 1860·W"
    input Real W "humidity ratio [kg/kg]";
    output Real cp;
  algorithm
    cp := 1006.0 + 1860.0*W;
  end cp_air_moist;

  // ════════════ 습공기 포화 (Magnus; _W_sat/_h_air_sat/_b_slope 폴백과 동일) ════════════
  function Psat_water "물 유효 포화압 [Pa] (Buck×enhancement, CoolProp HAPropsSI <0.1%)"
    input Real T_C;
    output Real Ps;
  algorithm
    Ps := 1.0045*611.21*exp((18.678 - T_C/234.5)*(T_C/(257.14 + T_C)));
  end Psat_water;

  function W_sat "포화 습도비 [kg/kg]"
    input Real T_C "온도 [°C]";
    input Real P_atm = 101325.0;
    output Real Ws;
  protected
    Real Psat;
  algorithm
    Psat := Psat_water(T_C);
    Ws := 0.622*Psat/(P_atm - Psat);
  end W_sat;

  function Tdp_corr "노점온도 [°C] from W (Buck 포화압 Newton 역산)"
    input Real W;
    input Real P_atm = 101325.0;
    output Real Tdp;
  protected
    Real Pv, Tc, Ps, fval, dPs;
  algorithm
    Pv := W*P_atm/(0.622 + W);
    Tc := 15.0;
    for i in 1:40 loop
      Ps := Psat_water(Tc);
      fval := Ps - Pv;
      dPs := Ps*((-1.0/234.5)*(Tc/(257.14 + Tc)) + (18.678 - Tc/234.5)*(257.14/(257.14 + Tc)^2));
      Tc := Tc - fval/dPs;
    end for;
    Tdp := Tc;
  end Tdp_corr;

  function h_air_sat "포화 공기 비엔탈피 [J/kg dry air]"
    input Real T_C;
    input Real P_atm = 101325.0;
    output Real h;
  protected
    Real Ws;
  algorithm
    Ws := W_sat(T_C, P_atm);
    h := 1006.0*T_C + Ws*(2501e3 + 1860.0*T_C);
  end h_air_sat;

  function b_slope "포화 엔탈피 곡선 기울기 b [J/kg·K] (Mirth-Ramadhyani m_w*용)"
    input Real T1_C, T2_C;
    input Real P_atm = 101325.0;
    output Real b;
  algorithm
    if abs(T2_C - T1_C) < 0.1 then
      b := (h_air_sat(T1_C + 0.5, P_atm) - h_air_sat(T1_C - 0.5, P_atm))/1.0;
    else
      b := (h_air_sat(T2_C, P_atm) - h_air_sat(T1_C, P_atm))/(T2_C - T1_C);
    end if;
  end b_slope;

  // ════════════ 공기측 j-factor (Wang et al. 2000, plain fin) ════════════
  function Dh_approx "근사 수력직경 (j-factor용). correlations.py와 동일."
    input Real Dc, Fp, delta;
    output Real Dh;
  algorithm
    Dh := max(4.0*(Fp - delta)*(Dc*0.5)/(2.0*((Fp - delta) + Dc*0.5)), 1e-6);
  end Dh_approx;

  function j_wang2000_plain
    "Wang et al.(2000) IJHMT 43(15) plain-fin j-factor, Nr별 모델. correlations.py와 동일."
    input Real Re_Dc;
    input Integer Nr "tube row 수";
    input Real Dc "fin collar 직경 [m]";
    input Real Pt "transverse pitch [m]";
    input Real Pl "longitudinal pitch [m]";
    input Real FPI "fins per inch";
    input Real fin_thickness "[m]";
    output Real j;
  protected
    Real Fp, Re, P1, P2, P3, P4, P5, P6, Nr_r;
  algorithm
    Fp := 0.0254/FPI;
    Re := max(Re_Dc, 10.0);
    Nr_r := Nr;
    if Nr == 1 then
      P1 := 1.9 - 0.23*log(Re);
      P2 := -0.236 + 0.126*log(Re);
      j := 0.108*Re^(-0.29)*(Pt/Pl)^P1*(Fp/Dc)^(-1.084)*(Fp/(Fp - fin_thickness))^(-0.786)*(Fp/Pt)^P2;
    else
      P3 := -0.361 - 0.042*Nr_r/log(Re) + 0.158*log(Nr_r*(Fp/Dc)^0.41);
      P4 := -1.224 - 0.076*(Pl/Dh_approx(Dc, Fp, fin_thickness))^1.42/log(Re);
      P5 := -0.083 + 0.058*Nr_r/log(Re);
      P6 := -5.735 + 1.21*log(Re/Nr_r);
      j := 0.086*Re^P3*Nr_r^P4*(Fp/Dc)^P5*(Fp/(Fp - fin_thickness))^P6*(Fp/Pt)^(-0.93);
    end if;
    j := max(j, 1e-6);
  end j_wang2000_plain;

  // ════════════ 냉매측 2상 비등 (Chen 1966) ════════════
  function h_evap_chen1966
    "Chen(1966) 2상 비등 HTC = F·h_l + S·h_pool(Cooper). correlations.py와 동일.
     물성은 model이 HelmholtzMedia saturation서 계산해 전달(순수 수식)."
    input Real x "quality";
    input Real G "mass flux [kg/m2.s]";
    input Real Di "[m]";
    input Real q_flux "[W/m2]";
    input Real mu_l "액 점성 [Pa.s]";
    input Real k_l "액 열전도 [W/m.K]";
    input Real Pr_l "액 Prandtl";
    input Real rho_l "액 밀도 [kg/m3]";
    input Real rho_v "증기 밀도 [kg/m3]";
    input Real mu_v "증기 점성 [Pa.s] (Xtt용)";
    input Real P_r "P/P_crit";
    input Real M_mol "molar mass [g/mol]";
    output Real h_tp;
  protected
    Real xx, Re_l, h_l, Xtt, inv_Xtt, F, Re_tp, S, log_Pr, h_pool;
  algorithm
    xx := max(0.001, min(x, 0.999));
    Re_l := max(G*(1.0 - xx)*Di/mu_l, 100.0);
    h_l := 0.023*Re_l^0.8*Pr_l^0.4*k_l/Di "Dittus-Boelter 액단상";
    // Lockhart-Martinelli (properties.py Xtt 가드 동일)
    if xx <= 0.001 then
      Xtt := 1e6;
    elseif xx >= 0.999 then
      Xtt := 1e-6;
    else
      Xtt := ((1.0 - xx)/xx)^0.9*(rho_v/rho_l)^0.5*(mu_l/mu_v)^0.1;
    end if;
    inv_Xtt := 1.0/max(Xtt, 1e-10);
    F := if inv_Xtt > 0.1 then 2.35*(0.213 + inv_Xtt)^0.736 else 1.0;
    F := max(F, 1.0);
    Re_tp := Re_l*F^1.25;
    S := 1.0/(1.0 + 2.53e-6*Re_tp^1.17) "억제인자";
    log_Pr := -log10(max(P_r, 1e-6));
    h_pool := 55.0*P_r^0.12*max(log_Pr, 0.01)^(-0.55)*M_mol^(-0.5)*max(q_flux, 100.0)^0.67
      "Cooper(1984) pool boiling";
    h_tp := max(F*h_l + S*h_pool, 100.0);
  end h_evap_chen1966;

  // ════════════ 압력강하 ΔP (pressure_drop.py) ════════════
  function churchill_friction "Churchill(1977) Fanning 마찰계수 (laminar~turbulent). pressure_drop.py와 동일."
    input Real Re;
    input Real eps_over_D = 0.0;
    output Real f_fanning;
  protected
    Real Re_safe, A, B, f_darcy;
  algorithm
    if Re < 1 then
      f_fanning := 0.5;
    else
      Re_safe := max(Re, 1.0);
      A := (-2.457*log((7.0/Re_safe)^0.9 + 0.27*eps_over_D))^16;
      B := (37530.0/Re_safe)^16;
      f_darcy := 8.0*((8.0/Re_safe)^12 + 1.0/(A + B)^1.5)^(1.0/12.0);
      f_fanning := max(f_darcy/4.0, 1e-5);
    end if;
  end churchill_friction;

  function single_phase_dp "단상 마찰 ΔP (Churchill). 물성(rho,mu)은 model이 전달."
    input Real rho "[kg/m3]";
    input Real mu "[Pa.s]";
    input Real m_dot "tube당 [kg/s]";
    input Real D_i "[m]";
    input Real L "[m]";
    input Real eps_over_D = 0.0;
    output Real dP "[Pa] (양수=손실)";
  protected
    Real A_cross, G, Re, f;
  algorithm
    A_cross := 3.141592653589793*D_i^2/4.0;
    G := m_dot/max(A_cross, 1e-12);
    Re := if mu > 0 then G*D_i/mu else 1.0;
    f := churchill_friction(Re, eps_over_D);
    dP := max(4.0*f*(L/D_i)*G^2/(2.0*rho), 0.0);
  end single_phase_dp;

  function msh_2phase "Müller-Steinhagen-Heck(1986) 2상 마찰 ΔP, N_sub 사다리꼴 적분. pressure_drop.py와 동일."
    input Real rho_l "[kg/m3]";
    input Real mu_l "[Pa.s]";
    input Real rho_v "[kg/m3]";
    input Real mu_v "[Pa.s]";
    input Real x_in;
    input Real x_out;
    input Real m_dot "tube당 [kg/s]";
    input Real D_i "[m]";
    input Real L "[m]";
    input Integer N_sub = 10;
    output Real dP "[Pa]";
  protected
    Real A_cross, G, Re_lo, f_lo, Acoef, Re_vo, f_vo, Bcoef, L_per_sub, x_lo, x_hi, x_mid, G_M, dpdz, dP_total;
  algorithm
    A_cross := 3.141592653589793*D_i^2/4.0;
    G := m_dot/max(A_cross, 1e-12);
    Re_lo := if mu_l > 0 then G*D_i/mu_l else 1.0;
    f_lo := churchill_friction(Re_lo, 0.0);
    Acoef := 4.0*f_lo*G^2/(2.0*rho_l*D_i) "액 only 구배 [Pa/m]";
    Re_vo := if mu_v > 0 then G*D_i/mu_v else 1.0;
    f_vo := churchill_friction(Re_vo, 0.0);
    Bcoef := 4.0*f_vo*G^2/(2.0*rho_v*D_i) "증기 only 구배 [Pa/m]";
    dP_total := 0.0;
    L_per_sub := L/N_sub;
    for i in 0:N_sub - 1 loop
      x_lo := x_in + (x_out - x_in)*i/N_sub;
      x_hi := x_in + (x_out - x_in)*(i + 1)/N_sub;
      x_mid := max(0.0, min(1.0, (x_lo + x_hi)/2.0));
      G_M := Acoef + 2.0*(Bcoef - Acoef)*x_mid;
      dpdz := G_M*(1.0 - x_mid)^(1.0/3.0) + Bcoef*x_mid^3;
      dP_total := dP_total + dpdz*L_per_sub;
    end for;
    dP := max(dP_total, 0.0);
  end msh_2phase;

  function acceleration_dp "Homogeneous 가속 ΔP (boiling +, condensation -). 부호 유지. pressure_drop.py와 동일."
    input Real rho_l "[kg/m3]";
    input Real rho_v "[kg/m3]";
    input Real x_in;
    input Real x_out;
    input Real m_dot "tube당 [kg/s]";
    input Real D_i "[m]";
    output Real dP_a "[Pa]";
  protected
    Real A_cross, G, xi, xo, v_in, v_out;
  algorithm
    A_cross := 3.141592653589793*D_i^2/4.0;
    G := m_dot/max(A_cross, 1e-12);
    xi := max(0.0, min(1.0, x_in));
    xo := max(0.0, min(1.0, x_out));
    v_in := xi/rho_v + (1.0 - xi)/rho_l;
    v_out := xo/rho_v + (1.0 - xo)/rho_l;
    dP_a := G^2*(v_out - v_in);
  end acceleration_dp;

  // ════════════ 보이드율 (void_fraction.py, charge holdup용) ════════════
  function void_homogeneous "homogeneous void β (S=1). void_fraction.py와 동일."
    input Real x, rho_l, rho_v;
    output Real beta;
  algorithm
    if x <= 0 then
      beta := 0.0;
    elseif x >= 1 then
      beta := 1.0;
    else
      beta := 1.0/(1.0 + (1.0 - x)/x*(rho_v/rho_l));
    end if;
  end void_homogeneous;

  function void_slip "slip-ratio 보이드율 α = 1/(1+S·(1-x)/x·ρv/ρl). void_fraction.py와 동일."
    input Real x, rho_l, rho_v, S;
    output Real alpha;
  algorithm
    if x <= 0 then
      alpha := 0.0;
    elseif x >= 1 then
      alpha := 1.0;
    else
      alpha := 1.0/(1.0 + S*(1.0 - x)/x*(rho_v/rho_l));
    end if;
  end void_slip;

  function void_premoli "Premoli(1971) slip-ratio 보이드율. void_fraction.py와 동일."
    input Real x;
    input Real rho_l "[kg/m3]";
    input Real rho_v "[kg/m3]";
    input Real mu_l "[Pa.s]";
    input Real sigma "표면장력 [N/m]";
    input Real m_dot "tube당 [kg/s]";
    input Real D_i "[m]";
    output Real alpha;
  protected
    Real A_cross, G, Re, We, rr, E1, E2, beta, y, s_arg, S;
  algorithm
    if x <= 0 then
      alpha := 0.0;
    elseif x >= 1 then
      alpha := 1.0;
    else
      A_cross := 3.141592653589793*D_i^2/4.0;
      G := m_dot/max(A_cross, 1e-12);
      Re := G*D_i/max(mu_l, 1e-9) "전체 G, 액 점성";
      We := G^2*D_i/max(sigma*rho_l, 1e-12) "액 기준 Weber";
      rr := rho_l/max(rho_v, 1e-6);
      E1 := 1.578*Re^(-0.19)*rr^0.22;
      E2 := 0.0273*We*Re^(-0.51)*rr^(-0.08);
      beta := void_homogeneous(x, rho_l, rho_v);
      y := beta/max(1.0 - beta, 1e-9);
      s_arg := y/(1.0 + y*E2) - y*E2;
      S := 1.0 + E1*sqrt(max(s_arg, 0.0));
      alpha := max(0.0, min(void_slip(x, rho_l, rho_v, S), 1.0));
    end if;
  end void_premoli;

  function void_mean_density "2상 평균밀도 ρ_tp = α·ρv + (1-α)·ρl. void_fraction.py와 동일."
    input Real alpha, rho_l, rho_v;
    output Real rho_tp;
  algorithm
    rho_tp := alpha*rho_v + (1.0 - alpha)*rho_l;
  end void_mean_density;

  // ════════════ 습공기 추가 헬퍼 (MB 공기측, CoolProp HAPropsSI 규약 매칭) ════════════
  function W_humid "습도비 W [kg/kg] from (Tc,RH). Buck×enhancement. ≈HAPropsSI('W')."
    input Real T_C;
    input Real RH "0~1";
    input Real P_atm = 101325.0;
    output Real W;
  protected
    Real Psat, pv;
  algorithm
    Psat := Psat_water(T_C);
    pv := max(0.001, min(0.999, RH))*Psat;
    W := 0.622*pv/(P_atm - pv);
  end W_humid;

  function h_moist "습공기 비엔탈피 [J/kg dry air] = 1006·Tc + W·(2501e3+1860·Tc). ≈HAPropsSI('H')."
    input Real T_C;
    input Real W;
    output Real h;
  algorithm
    h := 1006.0*T_C + W*(2501e3 + 1860.0*T_C);
  end h_moist;

  function T_moist_from_h "h_moist 역산 → T_C. ≈HAPropsSI('T','H',h,'W',W)-273.15."
    input Real h;
    input Real W;
    output Real T_C;
  algorithm
    T_C := (h - W*2501e3)/(1006.0 + 1860.0*W);
  end T_moist_from_h;

  function cp_ha_moist "습공기 정압비열 [J/kg humid·K] = (1006+1860W)/(1+W). ≈HAPropsSI('cp_ha')=('Cha')."
    input Real W;
    output Real cp;
  algorithm
    cp := (1006.0 + 1860.0*W)/(1.0 + W);
  end cp_ha_moist;

  function rho_humid_air "습공기 밀도 [kg humid/m3] = P(1+W)/(Rda·Tk·(1+1.6078W)). ≈1/HAPropsSI('Vha')."
    input Real T_C;
    input Real W;
    input Real P_atm = 101325.0;
    output Real rho;
  protected
    Real T_K;
  algorithm
    T_K := T_C + 273.15;
    rho := P_atm*(1.0 + W)/(287.055*T_K*(1.0 + 1.6078*W));
  end rho_humid_air;

  function Tdew "이슬점 [°C] from (Tc,RH). Magnus 역산. ≈HAPropsSI('Tdp')-273.15."
    input Real T_C;
    input Real RH "0~1";
    input Real P_atm = 101325.0;
    output Real T_dp;
  protected
    Real Psat, pv, lnr;
  algorithm
    Psat := 611.2*exp(17.62*T_C/(243.12 + T_C));
    pv := max(0.001, min(0.999, RH))*Psat;
    lnr := log(pv/611.2);
    T_dp := 243.12*lnr/(17.62 - lnr);
  end Tdew;

  // ════════════ 응축 2상 HTC (correlations.py) ════════════
  function h_cond_shah1979
    "Shah(1979) 응축 HTC = h_lo·[(1-x)^0.8 + 3.8·x^0.76·(1-x)^0.04/P_r^0.38]. correlations.py와 동일.
     h_lo = all-liquid Dittus-Boelter. 물성은 model이 saturation서 계산해 전달(순수 수식)."
    input Real x "quality";
    input Real G "mass flux [kg/m2.s]";
    input Real Di "[m]";
    input Real mu_l "액 점성 [Pa.s]";
    input Real k_l "액 열전도 [W/m.K]";
    input Real Pr_l "액 Prandtl";
    input Real P_r "P/P_crit";
    output Real h;
  protected
    Real xx, Re_lo, h_lo;
  algorithm
    xx := max(0.001, min(x, 0.999));
    Re_lo := max(G*Di/mu_l, 100.0);
    h_lo := 0.023*Re_lo^0.8*Pr_l^0.4*k_l/Di;
    h := h_lo*((1.0 - xx)^0.8 + 3.8*xx^0.76*(1.0 - xx)^0.04/max(P_r, 0.001)^0.38);
    h := max(h, 100.0);
  end h_cond_shah1979;

  function gnielinski "Gnielinski(1976) 단상 난류 HTC. correlations.py h_single_gnielinski와 동일."
    input Real Re "Reynolds";
    input Real Pr "Prandtl";
    input Real k "열전도 [W/m.K]";
    input Real Di "[m]";
    output Real alpha;
  protected
    Real f, Nu;
  algorithm
    if Re < 2300 then
      alpha := 3.66*k/Di;
    else
      f := (0.790*log(Re) - 1.64)^(-2);
      Nu := max((f/8)*(Re - 1000)*Pr/(1.0 + 12.7*sqrt(f/8)*(Pr^(2.0/3.0) - 1.0)), 3.66);
      alpha := Nu*k/Di;
    end if;
  end gnielinski;
end HXCorr;
