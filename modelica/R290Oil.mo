package R290Oil "R290 - 미네랄오일(SUNISO 5GSD) 용해 냉매 모델

  배경 (2026-07-25):
    사이클 충전량 100g 중 상당분이 압축기 오일에 용해되어 순환하지 않는다.
    Python 정방향(충전량 구속) 해에서 오일 용해량이 84g 으로 전체의 84%.
    Modelica 에는 이 항이 없어 100g 전부를 냉매 회로에 넣었고, 그 결과
    순환 냉매가 실제의 5배가 되어 어큐 범람 -> 응축기 액범람 ->
    Pc 26bar / SH=0 의 잘못된 운전점으로 수렴했다.

  상관식:
    P = gamma(T,x1) * x1 * Psat(T),  gamma = exp(a + b/T + c*x1)
    Wang X., Jia X., Wang D., Int. J. Refrig. 124 (2021) 13-19,
    Table 3 (SUNISO 4GS, 253~333K) 37점 최소자승. 평균오차 3.98%.
    ※ 5GSD 실측 없음. 같은 나프텐계 4GS(VG56) 계수 사용 (5GSD 는 VG100).

  Python 원본: backend/cycle_runner/oil_solubility.py (동일 계수)
"
  constant Real M_R290 = 44.1    "냉매 몰질량 [g/mol]";
  constant Real M_OIL  = 302.87  "오일 몰질량 [g/mol] — 4GS 값";
  constant Real GA = -0.68127    "gamma 회귀 a";
  constant Real GB = 151.00569   "gamma 회귀 b";
  constant Real GC = 0.42058     "gamma 회귀 c";
  constant Real RHO15  = 920.0   "오일 밀도 @15C [kg/m3]";
  constant Real DRHODT = -0.628  "오일 밀도 온도계수 [kg/m3/K]";
  constant Real X1_CLAMP = 0.99  "몰분율 상한 (고정점 발산 방지)";

  function oil_density "오일 밀도 [kg/m3]"
    input Real T_C;
    output Real rho;
  algorithm
    rho := RHO15 + DRHODT*(T_C - 15.0);
    annotation(Inline=true);
  end oil_density;

  function oil_mass "오일 주입체적 [cc] -> 질량 [kg]"
    input Real V_cc;
    input Real T_C = 20.0;
    output Real m;
  algorithm
    m := V_cc*1e-6*oil_density(T_C);
    annotation(Inline=true);
  end oil_mass;

  function Psat "R290 포화압 [Pa] @ T[K] — R290Tab.SATTsat 역보간

    R290Tab 은 Tsat(p) 만 제공하므로 압력격자에서 온도를 역으로 찾는다.
    SATTsat 는 p 에 대해 단조증가이므로 구간 탐색 + 선형보간으로 충분.
    범위 밖은 경계값으로 포화 (외삽 금지).
  "
    input Real T_K;
    output Real p;
  protected
    Integer i;
    Real t;
  algorithm
    if T_K <= R290Tab.SATTsat[1] then
      p := R290Tab.P0;
    elseif T_K >= R290Tab.SATTsat[R290Tab.nP] then
      p := R290Tab.P1;
    else
      i := 1;
      for k in 1:(R290Tab.nP - 1) loop
        if R290Tab.SATTsat[k] <= T_K and T_K < R290Tab.SATTsat[k + 1] then
          i := k;
        end if;
      end for;
      t := (T_K - R290Tab.SATTsat[i])
           /(R290Tab.SATTsat[i + 1] - R290Tab.SATTsat[i]);
      p := (R290Tab.P0 + (i - 1)*R290Tab.dP) + t*R290Tab.dP;
    end if;
  end Psat;

  function gamma "활동도계수"
    input Real T_K;
    input Real x1;
    output Real g;
  algorithm
    g := exp(GA + GB/T_K + GC*x1);
    annotation(Inline=true);
  end gamma;

  function x1_of "냉매 몰분율. P = gamma(T,x1)*x1*Psat(T) 의 고정점 해"
    input Real P_Pa;
    input Real T_K;
    output Real x1;
  protected
    Real Ps, xn;
  algorithm
    Ps := Psat(T_K);
    x1 := min(X1_CLAMP, P_Pa/Ps);
    for k in 1:40 loop
      xn := min(X1_CLAMP, P_Pa/(gamma(T_K, x1)*Ps));
      x1 := 0.5*x1 + 0.5*xn;
    end for;
  end x1_of;

  function w_of "냉매 질량분율 w1 [-]"
    input Real P_Pa;
    input Real T_K;
    output Real w;
  protected
    Real x1;
  algorithm
    x1 := x1_of(P_Pa, T_K);
    w := x1*M_R290/(x1*M_R290 + (1.0 - x1)*M_OIL);
  end w_of;

  function dissolved "오일에 용해된 냉매 질량 [kg].  M = M_oil*w/(1-w)"
    input Real M_oil;
    input Real P_Pa;
    input Real T_K;
    output Real M_dis;
  protected
    Real w;
  algorithm
    w := min(w_of(P_Pa, T_K), 0.95);
    M_dis := M_oil*w/(1.0 - w);
  end dissolved;

  function validity "상관식 유효성. 0=ok, 1=soft(외삽), 2=hard(파탄)

    hard: P >= Psat(T) 이면 섬프에서 냉매가 응축해 '오일에 녹은 냉매'라는
          전제가 깨짐. 또는 x1 이 클램프에 붙어 w/(1-w) 가 발산.
          (실측: Pc=26bar/섬프32C 에서 2114g — 총충전량의 21배)
    soft: 회귀 데이터 범위 밖 추정. 값은 쓰되 불확실성 표시.
  "
    input Real P_Pa;
    input Real T_K;
    output Integer code;
  protected
    Real Ps, ratio, x1;
  algorithm
    Ps := Psat(T_K);
    ratio := P_Pa/Ps;
    x1 := x1_of(P_Pa, T_K);
    code := if ratio >= 1.0 or x1 >= 0.98 then 2
            elseif ratio > 0.95 or x1 > 0.85 then 1
            else 0;
  end validity;
end R290Oil;
