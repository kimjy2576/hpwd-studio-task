within ;
package ProbeSat "P3'-b - saturation 5 x 12cells: table / _a func / inline (2026-08-02)"
  partial model Base
    parameter Integer M = 100;
    Real p[M](each start=5e5, each fixed=true, each nominal=1e6);
    Real Tsat_c[M], hl_c[M], hv_c[M], rhol_c[M], rhov_c[M];
  protected
    Real pl[M], pr[M];
  equation
    for k in 1:M loop
      pl[k] = p[if k == 1 then M else k - 1];
      pr[k] = p[if k == M then 1 else k + 1];
      // 물성 의존 확산 + 빠른 강제 + 물성 되먹임: 강성 유발로 야코비안 재계산 다발
      der(p[k]) = 0.8*(rhov_c[k]/10.0)*(pl[k] - 2.0*p[k] + pr[k])
                  + 8e4*sin(3.0*time + 0.7*k)
                  + 30.0*(310.0 - Tsat_c[k])*(1.0 + 0.05*(rhol_c[k]/500.0))
                  + 2e-2*(hv_c[k] - hl_c[k] - 3.0e5);
    end for;
  end Base;

  model STab
    extends Base;
  equation
    for k in 1:M loop
      Tsat_c[k]=R290Tab.Tsat(p[k]); hl_c[k]=R290Tab.hl(p[k]); hv_c[k]=R290Tab.hv(p[k]);
      rhol_c[k]=R290Tab.rhol(p[k]); rhov_c[k]=R290Tab.rhov(p[k]);
    end for;
  end STab;

  model SAna
    extends Base;
  equation
    for k in 1:M loop
      Tsat_c[k]=R290Tab.Tsat_a(p[k]); hl_c[k]=R290Tab.hl_a(p[k]); hv_c[k]=R290Tab.hv_a(p[k]);
      rhol_c[k]=R290Tab.rhol_a(p[k]); rhov_c[k]=R290Tab.rhov_a(p[k]);
    end for;
  end SAna;

  model SInl
    extends Base;
  protected
    Real xk[M];
  equation
    for k in 1:M loop
      xk[k] = log(noEvent(min(max(p[k], 1.5e5), 3.5e6)));
      Tsat_c[k] = (((((((-5.8568321336e-03*xk[k] + 5.4409513135e-01)*xk[k] + 2.1658325307e+01)*xk[k] + 4.7889496682e+02)*xk[k] + 6.3523509732e+03)*xk[k] + 5.0547784191e+04)*xk[k] + 2.2340371167e+05)*xk[k] + 4.2318837646e+05);
      hl_c[k] = (((((((2.7527849399e+02*xk[k] + 2.5757436934e+04)*xk[k] + 1.0325452903e+06)*xk[k] + 2.2986758475e+07)*xk[k] + 3.0691577333e+08)*xk[k] + 2.4576645156e+09)*xk[k] + 1.0928382824e+10)*xk[k] + 2.0816551755e+10);
      hv_c[k] = (((((((-4.7098627826e+02*xk[k] + 4.4039861081e+04)*xk[k] + 1.7642198471e+06)*xk[k] + 3.9248300940e+07)*xk[k] + 5.2367709839e+08)*xk[k] + 4.1905574981e+09)*xk[k] + 1.8621451030e+10)*xk[k] + 3.5447252901e+10);
      rhol_c[k] = exp(((((((((-1.5211024121e-03*xk[k] + 1.6356747427e-01)*xk[k] + 7.6920313393e+00)*xk[k] + 2.0661839230e+02)*xk[k] + 3.4673185972e+03)*xk[k] + 3.7222944840e+04)*xk[k] + 2.4964092463e+05)*xk[k] + 9.5628426417e+05)*xk[k] + 1.6018993622e+06));
      rhov_c[k] = exp(((((((((2.0984743019e-03*xk[k] + 2.2546473416e-01)*xk[k] + 1.0594223781e+01)*xk[k] + 2.8434982363e+02)*xk[k] + 4.7680705855e+03)*xk[k] + 5.1148546077e+04)*xk[k] + 3.4278385052e+05)*xk[k] + 1.3121435612e+06)*xk[k] + 2.1964816850e+06));
    end for;
  end SInl;
end ProbeSat;
