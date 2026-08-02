within ;
package HPWDevapC "PH4-A 보존형 staggered HX — 병행 모델 (S3: Dyn 공기측 전체 이식)"

  model Evap_On_DynC "PH4-A 보존형 staggered — 공기측은 Dyn 텍스트 동일, 냉매측만 보존형 (2026-08-02 S3)"
    replaceable package Medium = R290Medium "냉매 물성 (P4'-3 시범 전환, 2026-08-02)";
    HPWD.RefPort port_a "냉매 입구";
    HPWD.RefPort port_b "냉매 출구";
    parameter Boolean steadyInit = false "true: 정상상태 초기화 der(x)=0. false: start 값 고정 (2026-07-26)";
    parameter Integer initOpt = 0 "0=legacy 1=noInit 2=fixedState 3=steadyState";
    parameter Real w_nom = 2.06e-3 "공칭 회로당 냉매유량 [kg/s] — homotopy 단순화 모델용 (ThermoPower wnom 대응)";
    parameter Real dp_nom = 21338.0 "공칭 압력강하 [Pa] — 단순화 모델의 선형 저항 dp_nom/w_nom*w";
    parameter Real T_air_in=20.0 "공기 입구온도 [degC] (드럼 출구 공기)";
    parameter Real RH_in=0.8;
    // 공기유량 단일 소스 — 팬 체적유량에서 열전달 march와 h_o가 같은 질량유량을 씀.
    // (2026-07-23까지는 m_air_seg 하드코딩 0.00119464(rho 1.1848 상당)과
    //  V_air_CMM의 h_o 체인(HXCorr rho 1.1957)이 0.92% 어긋나 있었음.
    //  Python GT(CoolProp Vha, rho 1.19622)와 대조 결과 h_o 체인 쪽이 맞아 그쪽으로 통일.)
    parameter Real m_air_total=m_air_ho "코일 전체 공기유량 [kg/s]
      기본값은 V_air_CMM × 해당 HX 입구조건 밀도 (단품 검증 BC 규약, Python GT와 0.05% 일치).
      ※ 직렬 덕트(증발기→응축기)로 결합할 때는 건공기 질량이 보존돼야 하므로
        상류에서 계산된 질량유량을 직접 지정할 것.";
    final parameter Real m_air_seg=m_air_total/(1.0 + Wi)/(Ncirc*Nsc) "(col,seg)당 건공기 질량유량 [kg_da/s] — march가 h_moist[J/kg_da]·W[kg/kg_da]를 쓰므로 건공기 기준 (2026-07-25)";
    // ── 1차 형상 (임의 구성 비교의 입력; 파생량은 HXGeom이 산출) ──
    parameter Real W_coil=0.24 "튜브 길이 = 코일 폭 [m]";
    parameter Real H_coil=Nt*P_t "코일 높이 [m] — 기본 Nt·P_t (튜브 열 수 바꾸면 자동 추종)";
    parameter Real D_coil=Nr*P_l "코일 깊이 [m] — 기본 Nr·P_l (행 수 바꾸면 자동 추종)";
    parameter Real Do=0.005 "튜브 외경 [m]";
    // ── 공기측 h_o — 하드코딩 제거, 형상·유동서 산출 (증발기: FPI=20) ──
    parameter Real P_t=14.14e-3, P_l=10e-3 "튜브 피치 [m]";
    parameter Real FPI=20.0 "핀 밀도 [fins/inch]";
    final parameter Real A_o_face=HXGeom.A_face(W_coil, H_coil) "공기측 전면적 [m2]";
    parameter Real V_air_CMM=2.42 "공기 체적유량 [CMM] — 열전달·h_o 공통 단일 소스";
    final parameter Real P_fin_ho=0.0254/FPI;
    final parameter Real gap_ho=P_fin_ho - fin_t;
    final parameter Real sig_c_ho=max((P_t - Dc)*gap_ho/(P_t*P_fin_ho), 0.1);
    final parameter Real A_c_ho=sig_c_ho*A_o_face;
    final parameter Real W_ho=HXCorr.W_humid(T_air_in, RH_in, Patm);
    final parameter Real m_air_ho=HXCorr.rho_humid_air(T_air_in, W_ho, Patm)*(V_air_CMM/60.0);
    final parameter Real G_air_ho=m_air_ho/A_c_ho;
    final parameter Real mu_a_ho=HXCorr.mu_air(T_air_in+273.15);
    final parameter Real Pr_a_ho=HXCorr.Pr_air(T_air_in+273.15);
    final parameter Real cp_a_ho=HXCorr.cp_air_mix(W_ho);
    final parameter Real Re_Dc_ho=G_air_ho*Dc/mu_a_ho;
    final parameter Real j_air_ho=HXCorr.j_wang2000_plain(Re_Dc_ho, Nr, Dc, P_t, P_l, FPI, fin_t);
    final parameter Real h_o=j_air_ho*G_air_ho*cp_a_ho/Pr_a_ho^(2.0/3.0) "공기측 HTC [W/m2K] (형상·유동서 산출)";
    parameter Integer Nr=4, Nseg=10, Nt=4;
    parameter Integer Ncol=Nt "한 회로에 묶는 컬럼 수 (1=row_parallel, 2/4=serpentine_n, Nt=single).
      실물 증발기는 4R4C 단일 회로이므로 기본값 Nt (2026-07-24 사양 확인).";
    final parameter Integer Ncirc=div(Nt, Ncol) "병렬 회로 수";
    final parameter Integer Nsc=Nseg*Ncol "회로당 공기 스트림 수 (=(컬럼,세그) 평탄화)";
    parameter Real Di=0.0046 "튜브 내경 [m]";
    parameter Real k_fin=200.0 "핀 열전도율 [W/mK]";
    parameter Real fin_t=0.11e-3 "핀 두께 [m]";
    // ── 파생 형상 (HXGeom 산출 — 하드코딩 제거) ──
    // 기존 하드코딩 대비 검증: A_i_seg 0.0003468318 / A_o_seg 0.0048955023 /
    //   Dc 0.005220 / Xm 0.007070 / XL 0.00612342 / A_fin_ratio 0.9265582679 재현
    final parameter Real Dc=HXGeom.collarD(Do, fin_t) "핀 칼라 외경 [m]";
    final parameter Real Xm=HXGeom.Xm_schmidt(P_t);
    final parameter Real XL=HXGeom.XL_schmidt(P_t, P_l);
    final parameter Real A_i_seg=HXGeom.A_i_seg(Di, W_coil, Nseg) "세그당 냉매측 면적 [m2]";
    final parameter Real A_o_seg=HXGeom.A_o_seg(W_coil, H_coil, D_coil, Nr, Nt, Nseg, FPI, Do, fin_t)
      "(행,세그)당 공기측 면적 [m2]";
    final parameter Real A_fin_ratio=HXGeom.finRatio(W_coil, H_coil, D_coil, Nr, Nt, FPI, Do, fin_t);
    parameter Real Patm=101325.0, Pcrit=4.2512e6, M_mol=44.0956;
    parameter Real A_cs=Modelica.Constants.pi*Di^2/4.0;
    parameter Real K_bend=0.75 "U-bend 손실계수";
    parameter Real L_seg=A_i_seg/(Modelica.Constants.pi*Di) "세그 길이 [m]";
    parameter Real L_bend=(Nr - 1)*Ncol*Modelica.Constants.pi*P_l/2.0
                          + (Ncol - 1)*Modelica.Constants.pi*P_t/2.0 "리턴밴드 총길이 [m]";
    parameter Real L_path=M*L_seg + L_bend "회로 냉매경로 길이 [m] (직관 + 리턴밴드)";
    parameter Real L_inert=L_path/A_cs "유량 관성계수 [1/m]";
    parameter Real Wi=HXCorr.W_humid(T_air_in, RH_in, Patm);
    parameter Real T_dp=HXCorr.Tdp_corr(Wi, Patm);
    parameter Real eta_o_dry=HPWDon.finEffWet(h_o, 1.0, Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
    parameter Integer M=Nr*Nsc;
    parameter Integer rowOf[M]={HPWDevap.pathCellP(k - 1, Nr, Nseg, Ncol) for k in 1:M};
    parameter Integer segOf[M]={HPWDevap.pathCellS(k - 1, Nr, Nseg, Ncol) for k in 1:M} "공기 스트림 인덱스 sc";
    parameter Integer kOf[Nr,Nsc]=HPWDevap.buildKOf(Nr, Nseg, Ncol);
    // micro-fin 내부강화 (EF, 기하만 의존 → parameter). smooth면 ψ=1 → EF=1.
    parameter String tube_type="microfin" "튜브 내면: smooth / microfin";
    parameter Integer n_microfin=54 "(microfin) 내부 핀 개수";
    parameter Real e_microfin=0.15e-3 "(microfin) 핀 높이 [m]";
    parameter Real helix_angle=15.0 "(microfin) 나선각 [deg]";
    parameter Real psi_mf=if tube_type=="microfin" then HXCorr.microfin_area_ratio(n_microfin, e_microfin, helix_angle, Di) else 1.0;
    parameter Real EF_2ph=HXCorr.microfin_ef("evap", psi_mf, helix_angle);
    parameter Real EF_sgl=HXCorr.microfin_ef("single", psi_mf, helix_angle);
    // ── 동특성 파라미터 ──
    parameter Real rho_ref_nom=100.0 "냉매 공칭밀도 [kg/m3] (증발기 2상~과열, 셀 홀드업 산정)";
    // ── 습/건 연속 전이 (상태이벤트 제거) ──
    // is_wet Boolean(T_w<T_dp)은 셀마다 상태이벤트를 만들어 Nseg>=20에서 채터링
    // (t=15.8~16.4s에 20회, 간격 0.154->0.0024s로 기하수축 → 적분 정지, 2026-07-23 측정).
    // tanh 가중으로 대체 — 부분습윤(partial-wet)은 노점 근방의 실재 영역이라 물리적으로도 타당.
    parameter Real dT_wet=0.2 "습/건 전이대 [K] (→0이면 기존 계단과 동일)";
    parameter Real eps_Q=1.0e-3 "smooth max 정규화 [W] (잠열 음수 클립, 이벤트 회피)";
    parameter Real C_wall_cell=5.0 "셀당 벽(튜브+핀) 열용량 [J/K]";
    parameter Real K_lam=1.0e5 "저유량 층류 정규화 [Pa·s/kg] (flow=0 야코비안 특이점 회피)";
    parameter Real V_cell=A_cs*L_seg "셀 냉매 체적 [m3]";
    // ── 셀 질량 저장 (2026-07-24) ──
    // 기존에는 M_cell 이 상수라 HX 가 질량을 저장하지 않았음(유입=유출 강제).
    // 실제로는 냉매 100g 중 ~38g 이 HX 안에 있고(체적의 39%), 기동 시 재분배의
    // 주된 완충이 HX 다. 완충이 없으니 모든 과도를 작은 체적노드(vol3 3.66cc)가
    // 받아 계가 뻣뻣해졌음. rho_ph 는 derivative=rho_ph_d 어노테이션이 있어
    // 심볼릭 미분 가능.
    parameter Real M_cell_nom=rho_ref_nom*V_cell "셀 질량 초기추정 [kg]";
    Real M_c[M](each start=M_cell_nom) "셀 냉매 질량 [kg]";
    Real M_tot(start=M*M_cell_nom) "회로 총 냉매 질량 [kg]";
    Real m_out "회로 출구 유량 [kg/s]";
    // 콜드스타트 초기조건 (rest)
    parameter Real h_ref_start=400e3 "냉매 엔탈피 초기값 [J/kg]" annotation(Evaluate=false);
    parameter Real T_w_start=T_air_in "벽온도 초기값 [degC]" annotation(Evaluate=false);
    // ── 상태 (fixed=true → init 비선형계 제거) ──
    Real h_ref[M](each start=h_ref_start, each fixed=false) "냉매 엔탈피/셀 [J/kg]";
    Real T_w[M](each start=T_w_start, each fixed=false, each min=-40.0, each max=90.0) "벽온도/셀 [degC]";
    // ── 대수 ──
    // ── PH4-A: P 를 상태로 (D1 단일 압력). 경계가 p 를 주면 알리아스로 강등됨.
    parameter Real p_start=5.0e5 "P 초기값 [Pa]" annotation(Evaluate=false);
    parameter Boolean fix_P_init=false "true: 초기에 P=p_start 고정 (밀폐/무압력경계 전용)";
    Real P(start=p_start, fixed=false, nominal=1.0e6) "HX 압력 [Pa]";
    Real G_ref, h_in;
    parameter Real m_eps=1.0e-4 "면 upwind 전환 폭 [kg/s] (D3, noEvent 성격)";
    Real mdot[M + 1](each nominal=1.0e-2) "면 질량유량 [kg/s]";
    Real h_face[M + 1] "면 upwind 엔탈피 [J/kg]";
    Real drdp[M], drdh[M] "EOS 편도함수 (해석 rho_ph_der)";
    // 유량 관성 (momentum dynamics) — 2026-07-24.
    // 기존 port_b.p = P - dp_total 은 "Δp 를 주고 ṁ 을 푸는" 역산 방정식이라
    // 저유량(기동 직후)에서 dp~ṁ² 이 평탄해져 조건수가 발산했음.
    // ṁ 을 상태로 두면 역산이 사라지고 명시적 ODE 가 된다.
    //   L_inert·d(ṁ)/dt = Δp − dp_total(ṁ),  L_inert = L_path/A_cs [1/m]
    parameter Boolean use_momentum=true
      "true: ṁ 을 상태로(운동량, 사이클용) / false: 대수 dp(유량 BC 고정 단품 검증용)";
    Real m_ref_col(start=w_nom, fixed=false) "회로당 냉매유량 [kg/s]. 정지초기화는 initial equation 에서 처리 (2026-07-26: fixed=true 로 0 고정돼 정상초기화 시 0=-Q_ref 모순 -> h_ref[1] 발산)";
    Real T_satC, hl, hv, h_fg, mu_l, k_l, cp_l, Pr_l, rho_l, rho_v, mu_v, P_r;
    Real muv, kv, cpv, Prv, h_v_gni;
    Real xq_c[Nr,Nsc], T_ref_c[Nr,Nsc], h_i_c[Nr,Nsc], cp_a[Nr,Nsc], h_air_c[Nr,Nsc];
    Real eta_o[Nr,Nsc], b[Nr,Nsc], T_fin[Nr,Nsc], Q_air_c[Nr,Nsc], Q_ref_c[Nr,Nsc], Q_lat_c[Nr,Nsc];
    Real w_wet[Nr,Nsc](each min=0.0, each max=1.0) "습윤 가중 (0=건, 1=습) — 이벤트 없는 연속 전이";
    Real Q_sens_c[Nr,Nsc] "공기→벽 현열 [W] (잠열 분리용)";
    Real T_aen[Nr + 1,Nsc](each start=30.0, each min=-30.0, each max=80.0);
    Real W_aen[Nr + 1,Nsc](each start=0.017, each min=0.0, each max=0.1);
    Real Q_ref[M];
    Real Q_total, Q_lat_total, h_out, x_out, T_air_out, W_air_out, SH;
    Real x_in_q, dp_fric, dp_accel, dp_bend, dp_total, rho_mix, x_mid;
  initial equation
    // 정상상태 초기화: der(x)=0. 폐루프 사이클을 정상해에서 출발시킬 때 사용.
    // 기존 방식(start 고정)은 콜드스타트 전용.
    // initOpt: 0=legacy(steadyInit 따름) 1=noInit 2=fixedState 3=steadyState
    if initOpt == 1 then
      // 초기방정식 없음 (-iif 로 상태를 받을 때)
    elseif initOpt == 3 or (initOpt == 0 and steadyInit) then
      for k in 1:M loop der(h_ref[k])=0; der(T_w[k])=0; end for;
      der(P)=0;
      if use_momentum then der(m_ref_col)=0; end if;
    else
      for k in 1:M loop h_ref[k]=h_ref_start; T_w[k]=T_w_start; end for;
      if fix_P_init then P=p_start; end if;
      if use_momentum then m_ref_col=0.0; end if;
    end if;
  equation
    P=port_a.p;
    M_tot=sum(M_c) "HX 총 질량 (장부 출력 — 보존은 셀 단위로 성립)";
    m_out=mdot[M + 1];
    port_b.m_flow=-Ncirc*m_out;

    G_ref=m_ref_col/A_cs;
    h_in=inStream(port_a.h_outflow);
    T_satC=Medium.Tsat(P) - 273.15; hl=Medium.hl(P); hv=Medium.hv(P); h_fg=hv - hl;
    mu_l=Medium.mul(P); k_l=Medium.kl(P); cp_l=Medium.cpl(P); Pr_l=cp_l*mu_l/k_l;
    rho_l=Medium.rhol(P); rho_v=Medium.rhov(P); mu_v=Medium.muv(P); P_r=P/Pcrit;
    muv=Medium.muv(P); kv=Medium.kv(P); cpv=Medium.cpv(P); Prv=cpv*muv/kv;
    h_v_gni=HXCorr.gnielinski(G_ref*Di/muv, Prv, kv, Di);
    // 공기 입구 (행 1)
    for s in 1:Nsc loop
      T_aen[1,s]=T_air_in; W_aen[1,s]=Wi;
    end for;
    // 셀별 (공기 march 순서 p,s) — 상태 h_ref,T_w 로부터 전부 명시적
    for p in 1:Nr loop
      for s in 1:Nsc loop
        xq_c[p,s]=(h_ref[kOf[p,s] + 1] - hl)/h_fg;
        T_ref_c[p,s]=Medium.T_ph(P, h_ref[kOf[p,s] + 1]) - 273.15;
        w_wet[p,s]=0.5*(1.0 + tanh((T_dp - T_w[kOf[p,s] + 1])/dT_wet)) "습윤 가중 — 계단 대신 연속 전이";
        cp_a[p,s]=HXCorr.cp_air_moist(W_aen[p,s]);
        h_air_c[p,s]=HXCorr.h_moist(T_aen[p,s], W_aen[p,s]);
        h_i_c[p,s]=HPWDon.hi_dispatch_evap(xq_c[p,s], G_ref, Di, abs(T_aen[p,s] - T_w[kOf[p,s] + 1])*h_o,
                                           mu_l, k_l, Pr_l, rho_l, rho_v, mu_v, P_r, M_mol, h_v_gni)*(EF_sgl + (EF_2ph - EF_sgl)*(0.25*(1.0 + tanh(xq_c[p,s]/0.03))*(1.0 + tanh((1.0 - xq_c[p,s])/0.03))));
        // ★ 습핀 b를 T_fin 대신 T_w(상태)에서 평가 → 루프 차단, eta_o 명시화
        b[p,s]=1.0 + w_wet[p,s]*(HPWDon.hfgWater(T_w[kOf[p,s] + 1])*HPWDon.dWsdT(T_w[kOf[p,s] + 1], Patm)/cp_a[p,s]) "w→0이면 b=1 → eta_o=eta_o_dry 정확 일치";
        eta_o[p,s]=HPWDon.finEffWet(h_o, b[p,s], Dc, Xm, XL, k_fin, fin_t, A_fin_ratio);
        T_fin[p,s]=T_aen[p,s] - eta_o[p,s]*(T_aen[p,s] - T_w[kOf[p,s] + 1]) "진단용";
        // 공기→벽 열전달 (습: 엔탈피 포텐셜 총열량 / 건: 현열 — w_wet로 블렌딩)
        Q_sens_c[p,s]=eta_o[p,s]*h_o*A_o_seg*(T_aen[p,s] - T_w[kOf[p,s] + 1]) "현열";
        Q_air_c[p,s]=w_wet[p,s]*(eta_o[p,s]*h_o*A_o_seg/cp_a[p,s]*(h_air_c[p,s] - HXCorr.h_air_sat(T_w[kOf[p,s] + 1], Patm)))
                     + (1.0 - w_wet[p,s])*Q_sens_c[p,s];
        // 벽→냉매 열전달
        Q_ref_c[p,s]=h_i_c[p,s]*A_i_seg*(T_w[kOf[p,s] + 1] - T_ref_c[p,s]);
        // 잠열 = 총열량 − 현열 (smooth max로 음수 클립, max() 이벤트 제거)
        Q_lat_c[p,s]=w_wet[p,s]*0.5*((Q_air_c[p,s] - Q_sens_c[p,s]) + sqrt((Q_air_c[p,s] - Q_sens_c[p,s])^2 + eps_Q^2));
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
    // ── PH4-A 보존형 냉매측: 면 upwind + 질량 EOS 전개 + 에너지 V·dP/dt 항 ──
    h_face[1]=(0.5*(1.0 + tanh(mdot[1]/m_eps)))*h_in
            + (1.0 - 0.5*(1.0 + tanh(mdot[1]/m_eps)))*h_ref[1];
    for k in 2:M loop
      h_face[k]=(0.5*(1.0 + tanh(mdot[k]/m_eps)))*h_ref[k - 1]
              + (1.0 - 0.5*(1.0 + tanh(mdot[k]/m_eps)))*h_ref[k];
    end for;
    h_face[M + 1]=(0.5*(1.0 + tanh(mdot[M + 1]/m_eps)))*h_ref[M]
                + (1.0 - 0.5*(1.0 + tanh(mdot[M + 1]/m_eps)))*inStream(port_b.h_outflow);
    for k in 1:M loop
      M_c[k]=Medium.rho_ph(P, h_ref[k])*V_cell;
      drdp[k]=Medium.rho_ph_der(P, h_ref[k], 1.0, 0.0);
      drdh[k]=Medium.rho_ph_der(P, h_ref[k], 0.0, 1.0);
      V_cell*(drdp[k]*der(P) + drdh[k]*der(h_ref[k]))=mdot[k] - mdot[k + 1] "질량 (EOS 전개형)";
      M_c[k]*der(h_ref[k]) - V_cell*der(P)
        =mdot[k]*(h_face[k] - h_ref[k]) - mdot[k + 1]*(h_face[k + 1] - h_ref[k]) + Q_ref[k]
        "에너지 d(U)/dt, U=M·h−p·V — V·dP/dt 항이 Dyn 대비 신규";
    end for;
    mdot[1]=m_ref_col "입구 면 = 회로 유량 (운동량 상태 또는 포트 BC)";
    Q_total=Ncirc*sum(Q_ref); Q_lat_total=Ncirc*sum(Q_lat_c);
    h_out=h_ref[M];
    x_out=(h_out - hl)/h_fg;
    // smooth max — x_out 이 1.0 을 통과할 때 max() 가 상태이벤트를 만들어
    // 사이클 콜드스타트가 그 지점(t~55s)에서 정지함(2026-07-24 실측).
    SH=Medium.SH_ph(P, h_out) "출구 과열도 [K]";
    T_air_out=sum(T_aen[Nr + 1,s] for s in 1:Nsc)/Nsc;
    W_air_out=sum(W_aen[Nr + 1,s] for s in 1:Nsc)/Nsc "출구 절대습도 [kg/kg] (제습 반영) → 응축기 입력";
    // 냉매측 dp (명시적)
    x_in_q=(h_in - hl)/h_fg;
    dp_fric=HXCorr.msh_2phase(rho_l, mu_l, rho_v, mu_v, x_in_q, min(x_out, 0.999), m_ref_col, Di, L_path, 40);
    dp_accel=HXCorr.acceleration_dp(rho_l, rho_v, x_in_q, min(x_out, 0.999), m_ref_col, Di);
    x_mid=(x_in_q + min(x_out, 0.999))/2.0;
    rho_mix=1.0/(x_mid/rho_v + (1.0 - x_mid)/rho_l);
    dp_bend=(Nr*Ncol - 1)*K_bend*G_ref^2/(2.0*rho_mix);
    dp_total=dp_fric + dp_accel + dp_bend + K_lam*m_ref_col "+ 층류 정규화";
    if use_momentum then
      port_a.m_flow=Ncirc*m_ref_col;
      L_inert*der(m_ref_col)=homotopy((port_a.p - port_b.p) - dp_total,
        (port_a.p - port_b.p) - dp_nom/w_nom*m_ref_col)
        "운동량. 단순화 모델은 선형 저항 (ThermoPower Water.mo:662 패턴)";
    else
      m_ref_col=port_a.m_flow/Ncirc;
      port_b.p=P - dp_total "준정상 (유량 BC 고정 시)";
    end if;
    port_b.h_outflow=h_out;
    port_a.h_outflow=h_in;
    annotation(Documentation(info="<html>
<p><b>솔버 주의</b> — 이 모델은 습/건 전이 때문에 dassl로는 사실상 못 돎.
2026-07-23 실측 (값은 전 솔버 소수 3자리까지 일치):</p>
<pre>
격자        상태수   dassl        ida(+klu)   gbode
n10(40셀)    80      &gt;150s 미완주   25s        1s
n20(80셀)   160      미완주        196s       4s
</pre>
<p>비교: Cond_On_Dyn(60셀, 120상태)은 dassl 0s로 문제 없음 → 규모가 아니라
습/건 전이(tanh 급경사 + 습핀 b 증폭)가 만드는 셀간 시간상수 이질성이 원인으로 추정.
gbode의 bi-rate 적분이 유효한 것으로 보이나 기전은 미확정.</p>
<p><b>지정 방법</b>: <code>__OpenModelica_simulationFlags</code>는 <b>시뮬레이션 대상
최상위 모델에만</b> 적용됨(컴포넌트 클래스에 붙이면 파싱은 되나 무시 — 실측 확인).
따라서 이 모델을 품는 최상위 모델에 붙이거나, 호출측에서
<code>simulate(..., method=\"gbode\")</code>로 지정할 것.
스튜디오는 backend/modelica/bridge.py 의 <code>_SOLVER</code>로 일괄 지정.</p>
</html>"));
  end Evap_On_DynC;

  model PlugC "밀폐 캡"
    HPWD.RefPort port;
    parameter Real h_amb = 4.0e5;
  equation
    port.m_flow = 0.0;
    port.h_outflow = h_amb;
  end PlugC;

  model G0_Sealed "G0-P1 게이트 — 밀폐 + 가열 전이 (2상→과열 통과), 질량 폐합 검사"
    Evap_On_DynC hx(h_ref_start=5.0e5, T_w_start=5.0, T_air_in=45.0,
                    fix_P_init=true, use_momentum=false);
    Real drift_rel;
  protected
    parameter Real M0(fixed=false);
  initial equation
    M0 = hx.M_tot;
  equation
    connect(hx.port_a, capA.port);
    connect(hx.port_b, capB.port);
    drift_rel = (hx.M_tot - M0)/M0;
  public
    PlugC capA, capB;
  end G0_Sealed;

  model G1_AB "G1 게이트 — 동일 (p,h)소스/(p)싱크 경계에서 Dyn vs DynC 준정상 대조"
    parameter Real p_in = 5.6e5, h_in = 4.10e5, p_out = 5.5e5;
    HPWD.Source srcA(p=p_in, h=h_in), srcB(p=p_in, h=h_in);
    HPWD.Sink   snkA(p=p_out), snkB(p=p_out);
    HPWDevap.Evap_On_Dyn  hxA(h_ref_start=4.3e5, T_w_start=20.0, use_momentum=true);
    Evap_On_DynC          hxB(h_ref_start=4.3e5, T_w_start=20.0, use_momentum=true);
    Real dQ_rel, dSH_abs, dM_rel, dmf_rel "A/B 상대 편차 (판정 변수)";
  equation
    connect(srcA.port, hxA.port_a); connect(hxA.port_b, snkA.port);
    connect(srcB.port, hxB.port_a); connect(hxB.port_b, snkB.port);
    dQ_rel  = (hxB.Q_total - hxA.Q_total)/max(abs(hxA.Q_total), 1.0);
    dSH_abs = hxB.SH - hxA.SH;
    dM_rel  = (hxB.M_tot - hxA.M_tot)/max(hxA.M_tot, 1.0e-6);
    dmf_rel = (hxB.m_ref_col - hxA.m_ref_col)/max(abs(hxA.m_ref_col), 1.0e-6);
  end G1_AB;
end HPWDevapC;
