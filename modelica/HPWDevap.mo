within ;
package HPWDevap "L3 증발기 2D 컬럼 (Nr×N_seg, 동적 습/건, 공기 행진행)"
  // 사행 경로 매핑 (counter, row_parallel): path k(0-based) → (물리행 p, 세그 s) [1-based]
  function pathRow "path index → 물리행 (1-based, p=Nr는 공기-출구측=냉매입구)"
    input Integer k0, Nr, Nseg; output Integer p;
  algorithm
    p := Nr - div(k0, Nseg);
  end pathRow;

  function pathSeg "path index → 세그 (1-based, pass 짝수 정방향)"
    input Integer k0, Nr, Nseg; output Integer s;
  protected
    Integer pp, j;
  algorithm
    pp := div(k0, Nseg); j := mod(k0, Nseg);
    s := if mod(pp, 2) == 0 then j + 1 else Nseg - j;
  end pathSeg;

  function cellK "셀 (p,s) → path index (0-based)"
    input Integer p, s, Nr, Nseg; output Integer k;
  protected
    Integer pp, j;
  algorithm
    pp := Nr - p; j := if mod(pp, 2) == 0 then s - 1 else Nseg - s;
    k := pp*Nseg + j;
  end cellK;

  model Evap_On_Column "증발기 1컬럼 2D — Nr행×N_seg세그, 동적 습/건, 공기 행진행"
    // ── 운전점 ──
    parameter Real P=584218.0 "냉매압력 [Pa]";
    parameter Real h_in=0.0 "냉매 입구 비엔탈피 [J/kg] (<=1이면 x_in 사용)";
    parameter Real x_in=0.2 "입구 quality (h_in 미지정 시)";
    parameter Real m_ref_col=0.0016667 "컬럼당 냉매유량 [kg/s]";
    parameter Real T_air_in=35.0 "공기 입구온도 [degC]";
    parameter Real RH_in=0.5;
    parameter Real m_air_seg=0.00286454 "(col,seg)당 공기유량 [kg/s]";
    parameter Real h_o=105.98144 "공기측 HTC [W/m2K] (입구기준 1회)";
    // ── 기하 ──
    parameter Integer Nr=4, Nseg=10;
    parameter Real Di=0.00822, G_ref=31.4062;
    parameter Real A_i_seg=0.0012911946, A_o_seg=0.0249040267;
    parameter Real Dc=0.00976, Xm=0.0127, XL=0.01270128, k_fin=200.0, fin_t=0.12e-3;
    parameter Real A_fin_ratio=0.9424260735;
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    // ── 냉매 물성 (P 고정) ──
    parameter Real T_satC=R290Tab.Tsat(P) - 273.15;
    parameter Real hl=R290Tab.hl(P), hv=R290Tab.hv(P), h_fg=hv - hl;
    parameter Real mu_l=R290Tab.mul(P), k_l=R290Tab.kl(P), cp_l=R290Tab.cpl(P), Pr_l=cp_l*mu_l/k_l;
    parameter Real rho_l=R290Tab.rhol(P), rho_v=R290Tab.rhov(P), mu_v=R290Tab.muv(P), P_r=P/Pcrit;
    parameter Real muv=R290Tab.muv(P), kv=R290Tab.kv(P), cpv=R290Tab.cpv(P), Prv=cpv*muv/kv;
    parameter Real h_v_gni=HXCorr.gnielinski(G_ref*Di/muv, Prv, kv, Di);
    parameter Real h_max=hv + cpv*(T_air_in - T_satC) "냉매 물리상한 (공기온도 과열증기, 근사)";
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    // ── 공기 입구 ──
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real T_dp=HXCorr.Tdp_corr(Wi, Patm);
    // ── 경로 매핑 (parameter) ──
    parameter Integer M=Nr*Nseg;
    parameter Integer rowOf[M]={pathRow(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer segOf[M]={pathSeg(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer kOf[Nr,Nseg]={{cellK(p, s, Nr, Nseg) for s in 1:Nseg} for p in 1:Nr};
    parameter Real h_in_eff=if h_in > 1.0 then h_in else hl + x_in*h_fg;
    // ── 변수 ──
    Real hpath[M + 1] "냉매 경로 엔탈피 (path 0..M)";
    Real Q[Nr,Nseg], Q_lat[Nr,Nseg], T_w[Nr,Nseg](each start=15.0), h_i[Nr,Nseg];
    Real eta_o[Nr,Nseg], b[Nr,Nseg], T_fin[Nr,Nseg];
    Real xq[Nr,Nseg], T_ref_g[Nr,Nseg], cp_a[Nr,Nseg], h_air_c[Nr,Nseg], h_ref_c[Nr,Nseg];
    Boolean is_wet[Nr,Nseg];
    Real T_aen[Nr + 1,Nseg](each start=30.0) "공기 진입온도 (행1=입구)";
    Real W_aen[Nr + 1,Nseg](each start=0.017);
    Real Q_total, Q_lat_total, x_out, T_air_out;
  equation
    // 냉매 경로 체이닝
    hpath[1]=h_in_eff;
    for k in 1:M loop
      hpath[k + 1]=min(hpath[k] + Q[rowOf[k], segOf[k]]/max(m_ref_col, 1e-5), h_max);
    end for;
    // 공기 입구 (행 1)
    for s in 1:Nseg loop
      T_aen[1,s]=T_air_in;
      W_aen[1,s]=Wi;
    end for;
    // 셀 (물리행 p, 세그 s)
    for p in 1:Nr loop
      for s in 1:Nseg loop
        h_ref_c[p,s]=hpath[kOf[p,s] + 1];
        xq[p,s]=(h_ref_c[p,s] - hl)/h_fg;
        T_ref_g[p,s]=if xq[p,s] < 1.0 then T_satC else min(R290Tab.T_ph(P, h_ref_c[p,s]) - 273.15, T_aen[p,s]);
        is_wet[p,s]=T_w[p,s] < T_dp;
        cp_a[p,s]=HXCorr.cp_air_moist(W_aen[p,s]);
        h_air_c[p,s]=HXCorr.h_moist(T_aen[p,s], W_aen[p,s]);
        h_i[p,s]=HPWDon.hi_dispatch_evap(xq[p,s], G_ref, Di, abs(T_aen[p,s] - T_w[p,s])*h_o,
                                         mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_r, M_mol, h_v_gni);
        T_fin[p,s]=T_aen[p,s] - eta_o[p,s]*(T_aen[p,s] - T_w[p,s]);
        b[p,s]=if is_wet[p,s] then max(1.0 + HPWDon.hfgWater(T_fin[p,s])*HPWDon.dWsdT(T_fin[p,s], Patm)/cp_a[p,s], 1.0) else 1.0;
        eta_o[p,s]=if is_wet[p,s] then HPWDon.finEffWet(h_o, b[p,s], Dc, Xm, XL, k_fin, fin_t, A_fin_ratio) else eta_o_dry;
        Q[p,s]=if is_wet[p,s] then eta_o[p,s]*h_o*A_o_seg/cp_a[p,s]*(h_air_c[p,s] - HXCorr.h_air_sat(T_w[p,s], Patm))
               else (1.0/(1.0/(eta_o[p,s]*h_o*A_o_seg) + 1.0/(h_i[p,s]*A_i_seg)))*(T_aen[p,s] - T_ref_g[p,s]);
        T_w[p,s]=T_ref_g[p,s] + Q[p,s]/(h_i[p,s]*A_i_seg);
        Q_lat[p,s]=if is_wet[p,s] then max(Q[p,s] - eta_o[p,s]*h_o*A_o_seg*(T_aen[p,s] - T_w[p,s]), 0.0) else 0.0;
        // 공기 행진행 (행 p → p+1)
        W_aen[p + 1,s]=max(W_aen[p,s] - Q_lat[p,s]/(m_air_seg*HPWDon.hfgWater(T_aen[p,s])), 0.0);
        T_aen[p + 1,s]=(h_air_c[p,s] - Q[p,s]/m_air_seg - W_aen[p + 1,s]*2501e3)/(1006.0 + 1860.0*W_aen[p + 1,s]);
      end for;
    end for;
    Q_total=sum(Q);
    Q_lat_total=sum(Q_lat);
    x_out=(hpath[M + 1] - hl)/h_fg;
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nseg)/Nseg;
  end Evap_On_Column;
  model Evap_On "L3 증발기 — RefPort 음함수 컴포넌트 (1컬럼×Nt, 공기 경계)"
    HPWD.RefPort port_a "냉매 입구";
    HPWD.RefPort port_b "냉매 출구";
    parameter Real T_air_in=35.0 "공기 입구온도 [degC]";
    parameter Real RH_in=0.5;
    parameter Real m_air_seg=0.00286454 "(col,seg)당 공기유량 [kg/s]";
    parameter Real h_o=105.98144 "공기측 HTC [W/m2K]";
    parameter Integer Nr=4, Nseg=10, Nt=12;
    parameter Real Di=0.00822;
    parameter Real A_i_seg=0.0012911946, A_o_seg=0.0249040267;
    parameter Real Dc=0.00976, Xm=0.0127, XL=0.01270128, k_fin=200.0, fin_t=0.12e-3;
    parameter Real A_fin_ratio=0.9424260735;
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    parameter Real A_cs=Modelica.Constants.pi*Di^2/4.0;
    parameter Real K_bend=0.75 "U-bend 손실계수";
    parameter Real L_seg=A_i_seg/(Modelica.Constants.pi*Di) "세그 길이 [m]";
    parameter Real L_path=M*L_seg "컬럼 냉매경로 길이 [m]";
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real T_dp=HXCorr.Tdp_corr(Wi, Patm);
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    parameter Integer M=Nr*Nseg;
    parameter Integer rowOf[M]={pathRow(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer segOf[M]={pathSeg(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer kOf[Nr,Nseg]={{cellK(p, s, Nr, Nseg) for s in 1:Nseg} for p in 1:Nr};
    Real P, m_ref_col, G_ref, h_in;
    Real T_satC, hl, hv, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, P_r;
    Real muv, kv, cpv, Prv, h_v_gni, h_max;
    Real hpath[M + 1];
    Real Q[Nr,Nseg], Q_lat[Nr,Nseg], T_w[Nr,Nseg](each start=10.0, each min=-40.0, each max=90.0), h_i[Nr,Nseg];
    Real eta_o[Nr,Nseg](each start=0.75, each min=0.05, each max=1.0), b[Nr,Nseg](each start=1.05, each min=1.0, each max=8.0), T_fin[Nr,Nseg](each start=15.0);
    Real xq[Nr,Nseg], T_ref_g[Nr,Nseg], cp_a[Nr,Nseg], h_air_c[Nr,Nseg], h_ref_c[Nr,Nseg];
    Boolean is_wet[Nr,Nseg];
    Real T_aen[Nr + 1,Nseg](each start=30.0, each min=-30.0, each max=80.0), W_aen[Nr + 1,Nseg](each start=0.017, each min=0.0, each max=0.1);
    Real Q_total, Q_lat_total, x_out, T_air_out, h_out, SH;
    Real x_in_q, dp_fric, dp_accel, dp_bend, dp_total, rho_mix, x_mid;
    // micro-fin 내부강화 (EF, 기하만 의존 → parameter). smooth면 ψ=1 → EF=1 (하위호환).
    parameter String tube_type="smooth" "튜브 내면: smooth / microfin";
    parameter Integer n_microfin=0 "(microfin) 내부 핀 개수";
    parameter Real e_microfin=0.0 "(microfin) 핀 높이 [m]";
    parameter Real helix_angle=0.0 "(microfin) 나선각 [deg]";
    parameter Real psi_mf=if tube_type=="microfin" then HXCorr.microfin_area_ratio(n_microfin, e_microfin, helix_angle, Di) else 1.0;
    parameter Real EF_2ph=HXCorr.microfin_ef("evap", psi_mf, helix_angle);
    parameter Real EF_sgl=HXCorr.microfin_ef("single", psi_mf, helix_angle);
  equation
    P=port_a.p;
    port_a.m_flow + port_b.m_flow=0;
    m_ref_col=port_a.m_flow/Nt;
    G_ref=m_ref_col/A_cs;
    h_in=inStream(port_a.h_outflow);
    T_satC=R290Tab.Tsat(P) - 273.15; hl=R290Tab.hl(P); hv=R290Tab.hv(P); h_fg=hv - hl;
    mu_l=R290Tab.mul(P); k_l=R290Tab.kl(P); cp_l=R290Tab.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=R290Tab.rhol(P); rho_v=R290Tab.rhov(P); mu_v=R290Tab.muv(P); P_r=P/Pcrit;
    muv=R290Tab.muv(P); kv=R290Tab.kv(P); cpv=R290Tab.cpv(P); Prv=cpv*muv/kv;
    h_v_gni=HXCorr.gnielinski(G_ref*Di/muv, Prv, kv, Di);
    h_max=hv + cpv*(T_air_in - T_satC);
    hpath[1]=h_in;
    for k in 1:M loop
      hpath[k + 1]=min(hpath[k] + Q[rowOf[k], segOf[k]]/max(m_ref_col, 1e-5), h_max);
    end for;
    for s in 1:Nseg loop
      T_aen[1,s]=T_air_in; W_aen[1,s]=Wi;
    end for;
    for p in 1:Nr loop
      for s in 1:Nseg loop
        h_ref_c[p,s]=hpath[kOf[p,s] + 1];
        xq[p,s]=(h_ref_c[p,s] - hl)/h_fg;
        T_ref_g[p,s]=if xq[p,s] < 1.0 then T_satC else min(R290Tab.T_ph(P, h_ref_c[p,s]) - 273.15, T_aen[p,s]);
        is_wet[p,s]=T_w[p,s] < T_dp;
        cp_a[p,s]=HXCorr.cp_air_moist(W_aen[p,s]);
        h_air_c[p,s]=HXCorr.h_moist(T_aen[p,s], W_aen[p,s]);
        h_i[p,s]=HPWDon.hi_dispatch_evap(xq[p,s], G_ref, Di, abs(T_aen[p,s] - T_w[p,s])*h_o,
                                         mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_r, M_mol, h_v_gni)*(if xq[p,s] > 0.0 and xq[p,s] < 1.0 then EF_2ph else EF_sgl);
        T_fin[p,s]=T_aen[p,s] - eta_o[p,s]*(T_aen[p,s] - T_w[p,s]);
        b[p,s]=if is_wet[p,s] then max(1.0 + HPWDon.hfgWater(T_fin[p,s])*HPWDon.dWsdT(T_fin[p,s], Patm)/cp_a[p,s], 1.0) else 1.0;
        eta_o[p,s]=if is_wet[p,s] then HPWDon.finEffWet(h_o, b[p,s], Dc, Xm, XL, k_fin, fin_t, A_fin_ratio) else eta_o_dry;
        Q[p,s]=if is_wet[p,s] then eta_o[p,s]*h_o*A_o_seg/cp_a[p,s]*(h_air_c[p,s] - HXCorr.h_air_sat(T_w[p,s], Patm))
               else (1.0/(1.0/(eta_o[p,s]*h_o*A_o_seg) + 1.0/(h_i[p,s]*A_i_seg)))*(T_aen[p,s] - T_ref_g[p,s]);
        T_w[p,s]=T_ref_g[p,s] + Q[p,s]/(h_i[p,s]*A_i_seg);
        Q_lat[p,s]=if is_wet[p,s] then max(Q[p,s] - eta_o[p,s]*h_o*A_o_seg*(T_aen[p,s] - T_w[p,s]), 0.0) else 0.0;
        W_aen[p + 1,s]=max(W_aen[p,s] - Q_lat[p,s]/(m_air_seg*HPWDon.hfgWater(T_aen[p,s])), 0.0);
        T_aen[p + 1,s]=(h_air_c[p,s] - Q[p,s]/m_air_seg - W_aen[p + 1,s]*2501e3)/(1006.0 + 1860.0*W_aen[p + 1,s]);
      end for;
    end for;
    Q_total=Nt*sum(Q); Q_lat_total=Nt*sum(Q_lat);
    h_out=hpath[M + 1];
    x_out=(h_out - hl)/h_fg;
    SH=max(R290Tab.T_ph(P, h_out) - R290Tab.Tsat(P), 0.0) "증발기 출구 과열도 [K]";
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nseg)/Nseg;
    // 냉매측 dp: 2상 마찰(MSH) + 가속 + U-bend
    x_in_q=(h_in - hl)/h_fg;
    dp_fric=HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, x_in_q, min(x_out, 0.999), m_ref_col, Di, L_path, 40);
    dp_accel=HXCorr.acceleration_dp(rho_l, rho_v, x_in_q, min(x_out, 0.999), m_ref_col, Di);
    x_mid=(x_in_q + min(x_out, 0.999))/2.0;
    rho_mix=1.0/(x_mid/rho_v + (1.0 - x_mid)/rho_l);
    dp_bend=(Nr - 1)*K_bend*G_ref^2/(2.0*rho_mix);
    dp_total=dp_fric + dp_accel + dp_bend;
    port_b.p=P - dp_total;
    port_b.h_outflow=h_out;
    port_a.h_outflow=h_in;
  end Evap_On;

  model FlowSource "유량+엔탈피+압력 지정 소스 (입구 BC)"
    HPWD.RefPort port;
    parameter Real m_dot=0.02, h=290.0e3, p=584218.0;
  equation
    port.m_flow=-m_dot;
    port.h_outflow=h;
    port.p=p;
  end FlowSource;

  model OpenSink "출구 흡수 (압력 미고정, 컴포넌트가 p_out 결정)"
    HPWD.RefPort port;
    parameter Real h=400.0e3;
  equation
    port.h_outflow=h;
  end OpenSink;

  model TestEvapOn "Evap_On RefPort 컴포넌트 검증 (입구 P 고정, dp 적용)"
    FlowSource src(m_dot=0.02, h=290651.6, p=584218.0);
    Evap_On evap;
    OpenSink snk(h=574000.0);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end TestEvapOn;

  model Cond_On "L3 응축기 — RefPort 음함수 컴포넌트 (dry, Shah 응축, 공기 가열)"
    HPWD.RefPort port_a "냉매 입구 (과열증기)";
    HPWD.RefPort port_b "냉매 출구 (2상/과냉)";
    parameter Real T_air_in=25.0 "공기 입구온도 [degC]";
    parameter Real RH_in=0.4;
    parameter Real m_air_seg=0.00296086 "(col,seg)당 공기유량 [kg/s]";
    parameter Real h_o=108.59150 "공기측 HTC [W/m2K]";
    parameter Integer Nr=4, Nseg=10, Nt=12;
    parameter Real Di=0.00822;
    parameter Real A_i_seg=0.0012911946, A_o_seg=0.0249040267;
    parameter Real Dc=0.00976, Xm=0.0127, XL=0.01270128, k_fin=200.0, fin_t=0.12e-3;
    parameter Real A_fin_ratio=0.9424260735;
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    parameter Real A_cs=Modelica.Constants.pi*Di^2/4.0;
    parameter Real K_bend=0.75, L_seg=A_i_seg/(Modelica.Constants.pi*Di), L_path=Nr*Nseg*L_seg;
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real cp_a_dry=HXCorr.cp_air_moist(Wi) "건공기 cp (응축기는 dry)";
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    parameter Integer M=Nr*Nseg;
    parameter Integer rowOf[M]={pathRow(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer segOf[M]={pathSeg(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer kOf[Nr,Nseg]={{cellK(p, s, Nr, Nseg) for s in 1:Nseg} for p in 1:Nr};
    Real P, m_ref_col, G_ref, h_in;
    Real T_satC, hl, hv, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, k_v, cp_v, Pr_v, P_r, h_min;
    Real hpath[M + 1];
    Real Q[Nr,Nseg], h_i[Nr,Nseg], UA[Nr,Nseg], xq[Nr,Nseg], T_ref_g[Nr,Nseg], h_ref_c[Nr,Nseg];
    Real T_aen[Nr + 1,Nseg](each start=27.0, each min=15.0, each max=160.0);
    Real Q_total, x_out, T_air_out, h_out, x_in_q, dp_fric, dp_bend, dp_total, rho_mix, x_mid;
    // micro-fin 내부강화 (EF, 기하만 의존 → parameter). smooth면 ψ=1 → EF=1 (하위호환).
    parameter String tube_type="smooth" "튜브 내면: smooth / microfin";
    parameter Integer n_microfin=0 "(microfin) 내부 핀 개수";
    parameter Real e_microfin=0.0 "(microfin) 핀 높이 [m]";
    parameter Real helix_angle=0.0 "(microfin) 나선각 [deg]";
    parameter Real psi_mf=if tube_type=="microfin" then HXCorr.microfin_area_ratio(n_microfin, e_microfin, helix_angle, Di) else 1.0;
    parameter Real EF_2ph=HXCorr.microfin_ef("cond", psi_mf, helix_angle);
    parameter Real EF_sgl=HXCorr.microfin_ef("single", psi_mf, helix_angle);
  equation
    P=port_a.p;
    port_a.m_flow + port_b.m_flow=0;
    m_ref_col=port_a.m_flow/Nt;
    G_ref=m_ref_col/A_cs;
    h_in=inStream(port_a.h_outflow);
    T_satC=R290Tab.Tsat(P) - 273.15; hl=R290Tab.hl(P); hv=R290Tab.hv(P); h_fg=hv - hl;
    mu_l=R290Tab.mul(P); k_l=R290Tab.kl(P); cp_l=R290Tab.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=R290Tab.rhol(P); rho_v=R290Tab.rhov(P); mu_v=R290Tab.muv(P); P_r=P/Pcrit;
    k_v=R290Tab.kv(P); cp_v=R290Tab.cpv(P); Pr_v=cp_v*mu_v/k_v;
    h_min=hl - cp_l*(T_satC - T_air_in);
    hpath[1]=h_in;
    for k in 1:M loop
      hpath[k + 1]=max(hpath[k] - Q[rowOf[k], segOf[k]]/max(m_ref_col, 1e-5), h_min);
    end for;
    for s in 1:Nseg loop
      T_aen[1,s]=T_air_in;
    end for;
    for p in 1:Nr loop
      for s in 1:Nseg loop
        h_ref_c[p,s]=hpath[kOf[p,s] + 1];
        xq[p,s]=(h_ref_c[p,s] - hl)/h_fg;
        T_ref_g[p,s]=max(R290Tab.T_ph(P, h_ref_c[p,s]) - 273.15, T_aen[p,s]);
        h_i[p,s]=HPWDon.hi_dispatch_cond(xq[p,s], G_ref, Di, mu_l, k_l, Pr_l, mu_v, k_v, Pr_v, P_r)*(if xq[p,s] > 0.0 and xq[p,s] < 1.0 then EF_2ph else EF_sgl);
        UA[p,s]=1.0/(1.0/(eta_o_dry*h_o*A_o_seg) + 1.0/(h_i[p,s]*A_i_seg));
        Q[p,s]=UA[p,s]*(T_ref_g[p,s] - T_aen[p,s]);
        T_aen[p + 1,s]=T_aen[p,s] + Q[p,s]/(m_air_seg*cp_a_dry);
      end for;
    end for;
    Q_total=Nt*sum(Q);
    h_out=hpath[M + 1];
    x_out=(h_out - hl)/h_fg;
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nseg)/Nseg;
    x_in_q=(h_in - hl)/h_fg;
    dp_fric=HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, max(x_out, 0.001), min(x_in_q, 0.999), m_ref_col, Di, L_path, 40);
    x_mid=(min(x_in_q, 1.0) + max(x_out, 0.0))/2.0;
    rho_mix=1.0/(x_mid/rho_v + (1.0 - x_mid)/rho_l);
    dp_bend=(Nr - 1)*K_bend*G_ref^2/(2.0*rho_mix);
    dp_total=dp_fric + dp_bend;
    port_b.p=P - dp_total;
    port_b.h_outflow=h_out;
    port_a.h_outflow=h_in;
  end Cond_On;

  model TestCondOn "Cond_On RefPort 검증 vs hx_sim"
    FlowSource src(m_dot=0.02, h=662208.6, p=1907172.2);
    Cond_On cond;
    OpenSink snk(h=540000.0);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end TestCondOn;

  model Cond_On_Dyn "L3 응축기 — 동적 유한체적 (냉매 엔탈피 h_ref + 벽온도 T_w 상태). 폐루프/콜드스타트용."
    HPWD.RefPort port_a "냉매 입구 (과열증기)";
    HPWD.RefPort port_b "냉매 출구 (2상/과냉)";
    parameter Real T_air_in=25.0 "공기 입구온도 [degC]";
    parameter Real RH_in=0.4;
    parameter Real m_air_seg=0.00296086 "(col,seg)당 공기유량 [kg/s]";
    parameter Real h_o=108.59150 "공기측 HTC [W/m2K]";
    parameter Integer Nr=4, Nseg=10, Nt=12;
    parameter Real Di=0.00822;
    parameter Real A_i_seg=0.0012911946, A_o_seg=0.0249040267;
    parameter Real Dc=0.00976, Xm=0.0127, XL=0.01270128, k_fin=200.0, fin_t=0.12e-3;
    parameter Real A_fin_ratio=0.9424260735;
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    parameter Real A_cs=Modelica.Constants.pi*Di^2/4.0;
    parameter Real K_bend=0.75, L_seg=A_i_seg/(Modelica.Constants.pi*Di), L_path=Nr*Nseg*L_seg;
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real cp_a_dry=HXCorr.cp_air_moist(Wi) "건공기 cp";
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    parameter Integer M=Nr*Nseg;
    parameter Integer rowOf[M]={pathRow(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer segOf[M]={pathSeg(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer kOf[Nr,Nseg]={{cellK(p, s, Nr, Nseg) for s in 1:Nseg} for p in 1:Nr};
    // ── 동특성 파라미터 ──
    parameter Real rho_ref_nom=300.0 "냉매 공칭밀도 [kg/m3] (셀 홀드업 산정용)";
    parameter Real C_wall_cell=5.0 "셀당 벽(튜브+핀) 열용량 [J/K]";
    parameter Real K_lam=1.0e5 "저유량 층류 정규화 [Pa·s/kg] (flow=0 야코비안 특이점 회피)";
    parameter Real V_cell=A_cs*L_seg "셀 냉매 체적 [m3]";
    parameter Real M_cell=rho_ref_nom*V_cell "셀당 냉매 질량 [kg]";
    // 콜드스타트 초기조건 (rest)
    parameter Real h_ref_start=270e3 "냉매 엔탈피 초기값 [J/kg]";
    parameter Real T_w_start=T_air_in "벽온도 초기값 [degC]";
    // ── 상태 (fixed=true → init 비선형계 제거) ──
    Real h_ref[M](each start=h_ref_start, each fixed=true) "냉매 엔탈피/셀 [J/kg]";
    Real T_w[M](each start=T_w_start, each fixed=true, each min=-40.0, each max=160.0) "벽온도/셀 [degC]";
    // ── 대수 ──
    Real P, m_ref_col, G_ref, h_in;
    Real T_satC, hl, hv, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, k_v, cp_v, Pr_v, P_r;
    Real T_ref[M], xq[M], h_i[M], Q_ref[M], Q_air[M];
    Real T_aen[Nr + 1,Nseg](each start=27.0);
    Real Q_total, h_out, x_out, T_air_out, x_in_q, dp_fric, dp_bend, dp_total, rho_mix, x_mid;
  equation
    P=port_a.p;
    port_a.m_flow + port_b.m_flow=0;
    m_ref_col=port_a.m_flow/Nt;
    G_ref=m_ref_col/A_cs;
    h_in=inStream(port_a.h_outflow);
    T_satC=R290Tab.Tsat(P) - 273.15; hl=R290Tab.hl(P); hv=R290Tab.hv(P); h_fg=hv - hl;
    mu_l=R290Tab.mul(P); k_l=R290Tab.kl(P); cp_l=R290Tab.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=R290Tab.rhol(P); rho_v=R290Tab.rhov(P); mu_v=R290Tab.muv(P); P_r=P/Pcrit;
    k_v=R290Tab.kv(P); cp_v=R290Tab.cpv(P); Pr_v=cp_v*mu_v/k_v;
    // 셀별 냉매 상태/열전달 (상태 h_ref,T_w 로부터 전부 명시적)
    for k in 1:M loop
      T_ref[k]=R290Tab.T_ph(P, h_ref[k]) - 273.15;
      xq[k]=(h_ref[k] - hl)/h_fg;
      h_i[k]=HPWDon.hi_dispatch_cond(xq[k], G_ref, Di, mu_l, k_l, Pr_l, mu_v, k_v, Pr_v, P_r);
      Q_ref[k]=h_i[k]*A_i_seg*(T_ref[k] - T_w[k]);
    end for;
    // 냉매 엔탈피 동특성 (upwind, path 순서; 응축기 방열 → −Q_ref)
    M_cell*der(h_ref[1])=m_ref_col*(h_in - h_ref[1]) - Q_ref[1];
    for k in 2:M loop
      M_cell*der(h_ref[k])=m_ref_col*(h_ref[k - 1] - h_ref[k]) - Q_ref[k];
    end for;
    // 공기측 march (행 방향) + Q_air (벽→공기)
    for s in 1:Nseg loop
      T_aen[1,s]=T_air_in;
    end for;
    for p in 1:Nr loop
      for s in 1:Nseg loop
        Q_air[kOf[p,s] + 1]=eta_o_dry*h_o*A_o_seg*(T_w[kOf[p,s] + 1] - T_aen[p,s]);
        T_aen[p + 1,s]=T_aen[p,s] + Q_air[kOf[p,s] + 1]/(m_air_seg*cp_a_dry);
      end for;
    end for;
    // 벽 동특성 (냉매에서 받고 공기로 버림)
    for k in 1:M loop
      C_wall_cell*der(T_w[k])=Q_ref[k] - Q_air[k];
    end for;
    Q_total=Nt*sum(Q_ref);
    h_out=h_ref[M];
    x_out=(h_out - hl)/h_fg;
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nseg)/Nseg;
    // dp (명시적 — 미분 불필요)
    x_in_q=(h_in - hl)/h_fg;
    dp_fric=HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, max(x_out, 0.001), min(x_in_q, 0.999), m_ref_col, Di, L_path, 40);
    x_mid=(min(x_in_q, 1.0) + max(x_out, 0.0))/2.0;
    rho_mix=1.0/(x_mid/rho_v + (1.0 - x_mid)/rho_l);
    dp_bend=(Nr - 1)*K_bend*G_ref^2/(2.0*rho_mix);
    dp_total=dp_fric + dp_bend + K_lam*m_ref_col "+ 층류 정규화";
    port_b.p=P - dp_total;
    port_b.h_outflow=h_out;
    port_a.h_outflow=h_in;
  end Cond_On_Dyn;

  model TestCondOnDyn "Cond_On_Dyn 동적 응축기 단독 과도 검증 (rest → steady)"
    FlowSource src(m_dot=0.02, h=662208.6, p=1907172.2);
    Cond_On_Dyn cond(h_ref_start=270e3, T_w_start=25.0);
    OpenSink snk(h=540000.0);
  equation
    connect(src.port, cond.port_a);
    connect(cond.port_b, snk.port);
  end TestCondOnDyn;

  model Evap_On_Dyn "L3 증발기 — 동적 유한체적 (냉매 엔탈피 h_ref + 벽온도 T_w 상태), 습코일. 폐루프/콜드스타트용."
    HPWD.RefPort port_a "냉매 입구";
    HPWD.RefPort port_b "냉매 출구";
    parameter Real T_air_in=35.0 "공기 입구온도 [degC]";
    parameter Real RH_in=0.5;
    parameter Real m_air_seg=0.00286454 "(col,seg)당 공기유량 [kg/s]";
    parameter Real h_o=105.98144 "공기측 HTC [W/m2K]";
    parameter Integer Nr=4, Nseg=10, Nt=12;
    parameter Real Di=0.00822;
    parameter Real A_i_seg=0.0012911946, A_o_seg=0.0249040267;
    parameter Real Dc=0.00976, Xm=0.0127, XL=0.01270128, k_fin=200.0, fin_t=0.12e-3;
    parameter Real A_fin_ratio=0.9424260735;
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    parameter Real A_cs=Modelica.Constants.pi*Di^2/4.0;
    parameter Real K_bend=0.75 "U-bend 손실계수";
    parameter Real L_seg=A_i_seg/(Modelica.Constants.pi*Di) "세그 길이 [m]";
    parameter Real L_path=M*L_seg "컬럼 냉매경로 길이 [m]";
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real T_dp=HXCorr.Tdp_corr(Wi, Patm);
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    parameter Integer M=Nr*Nseg;
    parameter Integer rowOf[M]={pathRow(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer segOf[M]={pathSeg(k - 1, Nr, Nseg) for k in 1:M};
    parameter Integer kOf[Nr,Nseg]={{cellK(p, s, Nr, Nseg) for s in 1:Nseg} for p in 1:Nr};
    // ── 동특성 파라미터 ──
    parameter Real rho_ref_nom=100.0 "냉매 공칭밀도 [kg/m3] (증발기 2상~과열, 셀 홀드업 산정)";
    parameter Real C_wall_cell=5.0 "셀당 벽(튜브+핀) 열용량 [J/K]";
    parameter Real K_lam=1.0e5 "저유량 층류 정규화 [Pa·s/kg] (flow=0 야코비안 특이점 회피)";
    parameter Real V_cell=A_cs*L_seg "셀 냉매 체적 [m3]";
    parameter Real M_cell=rho_ref_nom*V_cell "셀당 냉매 질량 [kg]";
    // 콜드스타트 초기조건 (rest)
    parameter Real h_ref_start=400e3 "냉매 엔탈피 초기값 [J/kg]";
    parameter Real T_w_start=T_air_in "벽온도 초기값 [degC]";
    // ── 상태 (fixed=true → init 비선형계 제거) ──
    Real h_ref[M](each start=h_ref_start, each fixed=true) "냉매 엔탈피/셀 [J/kg]";
    Real T_w[M](each start=T_w_start, each fixed=true, each min=-40.0, each max=90.0) "벽온도/셀 [degC]";
    // ── 대수 ──
    Real P, m_ref_col, G_ref, h_in;
    Real T_satC, hl, hv, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, P_r;
    Real muv, kv, cpv, Prv, h_v_gni;
    Real xq_c[Nr,Nseg], T_ref_c[Nr,Nseg], h_i_c[Nr,Nseg], cp_a[Nr,Nseg], h_air_c[Nr,Nseg];
    Real eta_o[Nr,Nseg], b[Nr,Nseg], T_fin[Nr,Nseg], Q_air_c[Nr,Nseg], Q_ref_c[Nr,Nseg], Q_lat_c[Nr,Nseg];
    Boolean is_wet[Nr,Nseg];
    Real T_aen[Nr + 1,Nseg](each start=30.0, each min=-30.0, each max=80.0);
    Real W_aen[Nr + 1,Nseg](each start=0.017, each min=0.0, each max=0.1);
    Real Q_ref[M];
    Real Q_total, Q_lat_total, h_out, x_out, T_air_out, SH;
    Real x_in_q, dp_fric, dp_accel, dp_bend, dp_total, rho_mix, x_mid;
  equation
    P=port_a.p;
    port_a.m_flow + port_b.m_flow=0;
    m_ref_col=port_a.m_flow/Nt;
    G_ref=m_ref_col/A_cs;
    h_in=inStream(port_a.h_outflow);
    T_satC=R290Tab.Tsat(P) - 273.15; hl=R290Tab.hl(P); hv=R290Tab.hv(P); h_fg=hv - hl;
    mu_l=R290Tab.mul(P); k_l=R290Tab.kl(P); cp_l=R290Tab.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=R290Tab.rhol(P); rho_v=R290Tab.rhov(P); mu_v=R290Tab.muv(P); P_r=P/Pcrit;
    muv=R290Tab.muv(P); kv=R290Tab.kv(P); cpv=R290Tab.cpv(P); Prv=cpv*muv/kv;
    h_v_gni=HXCorr.gnielinski(G_ref*Di/muv, Prv, kv, Di);
    // 공기 입구 (행 1)
    for s in 1:Nseg loop
      T_aen[1,s]=T_air_in; W_aen[1,s]=Wi;
    end for;
    // 셀별 (공기 march 순서 p,s) — 상태 h_ref,T_w 로부터 전부 명시적
    for p in 1:Nr loop
      for s in 1:Nseg loop
        xq_c[p,s]=(h_ref[kOf[p,s] + 1] - hl)/h_fg;
        T_ref_c[p,s]=R290Tab.T_ph(P, h_ref[kOf[p,s] + 1]) - 273.15;
        is_wet[p,s]=T_w[kOf[p,s] + 1] < T_dp;
        cp_a[p,s]=HXCorr.cp_air_moist(W_aen[p,s]);
        h_air_c[p,s]=HXCorr.h_moist(T_aen[p,s], W_aen[p,s]);
        h_i_c[p,s]=HPWDon.hi_dispatch_evap(xq_c[p,s], G_ref, Di, abs(T_aen[p,s] - T_w[kOf[p,s] + 1])*h_o,
                                           mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_r, M_mol, h_v_gni);
        // ★ 습핀 b를 T_fin 대신 T_w(상태)에서 평가 → 루프 차단, eta_o 명시화
        b[p,s]=if is_wet[p,s] then 1.0 + HPWDon.hfgWater(T_w[kOf[p,s] + 1])*HPWDon.dWsdT(T_w[kOf[p,s] + 1], Patm)/cp_a[p,s] else 1.0 "dWs/dT>0 → 습할때 항상 b>1, max 불필요";
        eta_o[p,s]=if is_wet[p,s] then HPWDon.finEffWet(h_o, b[p,s], Dc, Xm, XL, k_fin, fin_t, A_fin_ratio) else eta_o_dry;
        T_fin[p,s]=T_aen[p,s] - eta_o[p,s]*(T_aen[p,s] - T_w[kOf[p,s] + 1]) "진단용";
        // 공기→벽 열전달 (습: 엔탈피 포텐셜 총열량 / 건: 현열)
        Q_air_c[p,s]=if is_wet[p,s] then eta_o[p,s]*h_o*A_o_seg/cp_a[p,s]*(h_air_c[p,s] - HXCorr.h_air_sat(T_w[kOf[p,s] + 1], Patm))
                     else eta_o[p,s]*h_o*A_o_seg*(T_aen[p,s] - T_w[kOf[p,s] + 1]);
        // 벽→냉매 열전달
        Q_ref_c[p,s]=h_i_c[p,s]*A_i_seg*(T_w[kOf[p,s] + 1] - T_ref_c[p,s]);
        // 잠열 = 총열량 − 현열
        Q_lat_c[p,s]=if is_wet[p,s] then max(Q_air_c[p,s] - eta_o[p,s]*h_o*A_o_seg*(T_aen[p,s] - T_w[kOf[p,s] + 1]), 0.0) else 0.0;
        // 공기 march
        W_aen[p + 1,s]=W_aen[p,s] - Q_lat_c[p,s]/(m_air_seg*HPWDon.hfgWater(T_aen[p,s])) "Q_lat_c>=0 → 단조감소, max 불필요(OMC 역산 가능)";
        T_aen[p + 1,s]=(h_air_c[p,s] - Q_air_c[p,s]/m_air_seg - W_aen[p + 1,s]*2501e3)/(1006.0 + 1860.0*W_aen[p + 1,s]);
      end for;
    end for;
    // path-order Q_ref 조립 + 벽 동특성
    for k in 1:M loop
      Q_ref[k]=Q_ref_c[rowOf[k], segOf[k]];
      C_wall_cell*der(T_w[k])=Q_air_c[rowOf[k], segOf[k]] - Q_ref[k];
    end for;
    // 냉매 엔탈피 동특성 (upwind, path 순서; 증발기 흡열 → +Q_ref)
    M_cell*der(h_ref[1])=m_ref_col*(h_in - h_ref[1]) + Q_ref[1];
    for k in 2:M loop
      M_cell*der(h_ref[k])=m_ref_col*(h_ref[k - 1] - h_ref[k]) + Q_ref[k];
    end for;
    Q_total=Nt*sum(Q_ref); Q_lat_total=Nt*sum(Q_lat_c);
    h_out=h_ref[M];
    x_out=(h_out - hl)/h_fg;
    SH=max(R290Tab.T_ph(P, h_out) - R290Tab.Tsat(P), 0.0) "출구 과열도 [K]";
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nseg)/Nseg;
    // 냉매측 dp (명시적)
    x_in_q=(h_in - hl)/h_fg;
    dp_fric=HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, x_in_q, min(x_out, 0.999), m_ref_col, Di, L_path, 40);
    dp_accel=HXCorr.acceleration_dp(rho_l, rho_v, x_in_q, min(x_out, 0.999), m_ref_col, Di);
    x_mid=(x_in_q + min(x_out, 0.999))/2.0;
    rho_mix=1.0/(x_mid/rho_v + (1.0 - x_mid)/rho_l);
    dp_bend=(Nr - 1)*K_bend*G_ref^2/(2.0*rho_mix);
    dp_total=dp_fric + dp_accel + dp_bend + K_lam*m_ref_col "+ 층류 정규화";
    port_b.p=P - dp_total;
    port_b.h_outflow=h_out;
    port_a.h_outflow=h_in;
  end Evap_On_Dyn;

  model TestEvapOnDyn "Evap_On_Dyn 동적 증발기 단독 과도 검증 (rest → steady)"
    FlowSource src(m_dot=0.02, h=290651.6, p=584218.0);
    Evap_On_Dyn evap(h_ref_start=400e3, T_w_start=35.0);
    OpenSink snk(h=574000.0);
  equation
    connect(src.port, evap.port_a);
    connect(evap.port_b, snk.port);
  end TestEvapOnDyn;

end HPWDevap;
