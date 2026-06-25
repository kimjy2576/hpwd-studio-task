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
      hpath[k + 1]=min(hpath[k] + Q[rowOf[k], segOf[k]]/m_ref_col, h_max);
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
end HPWDevap;
