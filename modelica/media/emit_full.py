import numpy as np, os
d=np.load('r290_table.npz'); P,H=d['P'],d['H']; nP,nH=len(P),len(H)
def a1(F): return "{"+",".join(f"{x:.7g}" for x in F)+"}"
def a2(F): return "{"+",\n".join("{"+",".join(f"{x:.7g}" for x in row)+"}" for row in F)+"}"
def a2i(F): return "{"+",\n".join("{"+",".join(str(int(x)) for x in row)+"}" for row in F)+"}"

# 공개함수 (도함수 주석 포함)
funcs = r'''
  // ===== 인덱스/보간 헬퍼 =====
  function idxP
    input Real p; output Integer i;
  algorithm
    i := min(max(integer(floor((min(max(p,P0),P1)-P0)/dP))+1,1),nP-1);
  end idxP;
  function idxH
    input Real h; output Integer j;
  algorithm
    j := min(max(integer(floor((min(max(h,H0),H1)-H0)/dH))+1,1),nH-1);
  end idxH;
  function lin1
    input Real F[nP]; input Real p; output Real y;
  protected
    Integer i; Real t;
  algorithm
    i := idxP(p); t := (p-(P0+(i-1)*dP))/dP; y := (1-t)*F[i]+t*F[i+1];
  end lin1;
  function bilin
    input Real F[nP,nH]; input Real p; input Real h; output Real y;
  protected
    Integer i,j; Real tp,th;
  algorithm
    i := idxP(p); j := idxH(h); tp := (p-(P0+(i-1)*dP))/dP; th := (h-(H0+(j-1)*dH))/dH;
    y := (1-tp)*(1-th)*F[i,j]+tp*(1-th)*F[i+1,j]+(1-tp)*th*F[i,j+1]+tp*th*F[i+1,j+1];
  end bilin;
  function bilinC
    input Real F[nP,nH]; input Real satF[nP]; input Integer want; input Real p; input Real h; output Real y;
  protected
    Integer i,j; Real tp,th,c00,c10,c01,c11;
  algorithm
    i := idxP(p); j := idxH(h); tp := (p-(P0+(i-1)*dP))/dP; th := (h-(H0+(j-1)*dH))/dH;
    c00 := if PHg[i,j]==want then F[i,j] else satF[i];
    c10 := if PHg[i+1,j]==want then F[i+1,j] else satF[i+1];
    c01 := if PHg[i,j+1]==want then F[i,j+1] else satF[i];
    c11 := if PHg[i+1,j+1]==want then F[i+1,j+1] else satF[i+1];
    y := (1-tp)*(1-th)*c00+tp*(1-th)*c10+(1-tp)*th*c01+tp*th*c11;
  end bilinC;

  // ===== 포화 접근자 (도함수 주석) =====
  function Tsat input Real p; output Real y; algorithm y:=lin1(SATTsat,p); annotation(derivative=Tsat_d); end Tsat;
  function Tsat_d input Real p; input Real dp; output Real dy; algorithm dy:=lin1(SATdTsdp,p)*dp; end Tsat_d;
  function hl input Real p; output Real y; algorithm y:=lin1(SAThl,p); annotation(derivative=hl_d); end hl;
  function hl_d input Real p; input Real dp; output Real dy; algorithm dy:=lin1(SATdhldp,p)*dp; end hl_d;
  function hv input Real p; output Real y; algorithm y:=lin1(SAThv,p); annotation(derivative=hv_d); end hv;
  function hv_d input Real p; input Real dp; output Real dy; algorithm dy:=lin1(SATdhvdp,p)*dp; end hv_d;
  function rhol input Real p; output Real y; algorithm y:=lin1(SATrhol,p); annotation(derivative=rhol_d); end rhol;
  function rhol_d input Real p; input Real dp; output Real dy; algorithm dy:=lin1(SATdrholdp,p)*dp; end rhol_d;
  function rhov input Real p; output Real y; algorithm y:=lin1(SATrhov,p); annotation(derivative=rhov_d); end rhov;
  function rhov_d input Real p; input Real dp; output Real dy; algorithm dy:=lin1(SATdrhovdp,p)*dp; end rhov_d;

  // ===== 포화 수송물성 (액/증기) =====
  function mul input Real p; output Real y; algorithm y:=lin1(SATmul,p); end mul;
  function kl  input Real p; output Real y; algorithm y:=lin1(SATkl,p);  end kl;
  function cpl input Real p; output Real y; algorithm y:=lin1(SATcpl,p); end cpl;
  function muv input Real p; output Real y; algorithm y:=lin1(SATmuv,p); end muv;
  function kv  input Real p; output Real y; algorithm y:=lin1(SATkv,p);  end kv;
  function cpv input Real p; output Real y; algorithm y:=lin1(SATcpv,p); end cpv;

  // ===== ρ(p,h), T(p,h) — 영역인지 + 해석 도함수 =====
  function rho_ph
    input Real p; input Real h; output Real rho;
  protected
    Real hL,hV,rL,rV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then
      rL:=lin1(SATrhol,p); rV:=lin1(SATrhov,p); x:=(h-hL)/(hV-hL); rho:=1.0/((1.0-x)/rL+x/rV);
    elseif h<=hL then rho:=bilinC(TBLrho,SATrhol,1,p,h);
    else rho:=bilinC(TBLrho,SATrhov,2,p,h); end if;
    annotation(derivative=rho_ph_d);
  end rho_ph;
  function rho_ph_d
    input Real p; input Real h; input Real dp; input Real dh; output Real drho;
  protected
    Real hL,hV,rL,rV,x,rho,dvdh,dvdp,dxdp;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then
      rL:=lin1(SATrhol,p); rV:=lin1(SATrhov,p); x:=(h-hL)/(hV-hL); rho:=1.0/((1.0-x)/rL+x/rV);
      dvdh:=(1.0/rV-1.0/rL)/(hV-hL);
      dxdp:=(-lin1(SATdhldp,p)*(hV-hL)-(h-hL)*(lin1(SATdhvdp,p)-lin1(SATdhldp,p)))/((hV-hL)*(hV-hL));
      dvdp:=dxdp*(1.0/rV-1.0/rL)-(1.0-x)/(rL*rL)*lin1(SATdrholdp,p)-x/(rV*rV)*lin1(SATdrhovdp,p);
      drho:=-rho*rho*(dvdh*dh+dvdp*dp);
    else
      drho:=bilin(TBLdrdp,p,h)*dp+bilin(TBLdrdh,p,h)*dh;
    end if;
  end rho_ph_d;

  function T_ph
    input Real p; input Real h; output Real T;
  protected
    Real hL,hV;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then T:=lin1(SATTsat,p);
    elseif h<=hL then T:=bilinC(TBLT,SATTsat,1,p,h);
    else T:=bilinC(TBLT,SATTsat,2,p,h); end if;
    annotation(derivative=T_ph_d);
  end T_ph;
  function T_ph_d
    input Real p; input Real h; input Real dp; input Real dh; output Real dT;
  protected
    Real hL,hV;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then
      dT:=lin1(SATdTsdp,p)*dp;
    else
      dT:=bilin(TBLdTdp,p,h)*dp+bilin(TBLdTdh,p,h)*dh;
    end if;
  end T_ph_d;

  // ===== 단일상 수송물성 (영역인지, 값) =====
  function mu_ph
    input Real p; input Real h; output Real mu;
  protected
    Real hL,hV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then x:=(h-hL)/(hV-hL); mu:=(1-x)*lin1(SATmul,p)+x*lin1(SATmuv,p);
    elseif h<=hL then mu:=bilinC(TBLmu,SATmul,1,p,h);
    else mu:=bilinC(TBLmu,SATmuv,2,p,h); end if;
  end mu_ph;
  function k_ph
    input Real p; input Real h; output Real k;
  protected
    Real hL,hV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then x:=(h-hL)/(hV-hL); k:=(1-x)*lin1(SATkl,p)+x*lin1(SATkv,p);
    elseif h<=hL then k:=bilinC(TBLk,SATkl,1,p,h);
    else k:=bilinC(TBLk,SATkv,2,p,h); end if;
  end k_ph;
  function cp_ph
    input Real p; input Real h; output Real cp;
  protected
    Real hL,hV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then x:=(h-hL)/(hV-hL); cp:=(1-x)*lin1(SATcpl,p)+x*lin1(SATcpv,p);
    elseif h<=hL then cp:=bilinC(TBLcp,SATcpl,1,p,h);
    else cp:=bilinC(TBLcp,SATcpv,2,p,h); end if;
  end cp_ph;

  // ===== 엔트로피 / cv / gamma / 등엔트로피 (컴프용) =====
  function s_ph "엔트로피 s(p,h) [J/kgK] — 영역인지"
    input Real p; input Real h; output Real s;
  protected
    Real hL,hV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then x:=(h-hL)/(hV-hL); s:=(1-x)*lin1(SATsl,p)+x*lin1(SATsv,p);
    elseif h<=hL then s:=bilinC(TBLs,SATsl,1,p,h);
    else s:=bilinC(TBLs,SATsv,2,p,h); end if;
  end s_ph;

  function cv_ph "정적비열 cv(p,h) — 영역인지"
    input Real p; input Real h; output Real cv;
  protected
    Real hL,hV,x;
  algorithm
    hL:=lin1(SAThl,p); hV:=lin1(SAThv,p);
    if h>hL and h<hV then x:=(h-hL)/(hV-hL); cv:=(1-x)*lin1(SATcvl,p)+x*lin1(SATcvv,p);
    elseif h<=hL then cv:=bilinC(TBLcv,SATcvl,1,p,h);
    else cv:=bilinC(TBLcv,SATcvv,2,p,h); end if;
  end cv_ph;

  function gamma_ph "비열비 cp/cv"
    input Real p; input Real h; output Real g;
  algorithm
    g:=cp_ph(p,h)/cv_ph(p,h);
  end gamma_ph;

  function h_ps "등엔트로피: (p, s_target) -> h. s_ph에 Newton 역산 (ds=dh/T)"
    input Real p; input Real s_target; output Real h;
  protected
    Real sN,T; Integer it;
  algorithm
    h := lin1(SAThv,p) + lin1(SATTsat,p)*(s_target - lin1(SATsv,p));
    for it in 1:8 loop
      sN := s_ph(p,h); T := T_ph(p,h);
      h := h + (s_target - sN)*T;
    end for;
  end h_ps;
'''

consts = f'''  constant Integer nP={nP};
  constant Integer nH={nH};
  constant Real P0={P[0]:.7g};
  constant Real P1={P[-1]:.7g};
  constant Real H0={H[0]:.7g};
  constant Real H1={H[-1]:.7g};
  constant Real dP=(P1-P0)/(nP-1);
  constant Real dH=(H1-H0)/(nH-1);
  constant Real SATTsat[nP]={a1(d['sat_Tsat'])};
  constant Real SAThl[nP]={a1(d['sat_hl'])};
  constant Real SAThv[nP]={a1(d['sat_hv'])};
  constant Real SATrhol[nP]={a1(d['sat_rhol'])};
  constant Real SATrhov[nP]={a1(d['sat_rhov'])};
  constant Real SATdTsdp[nP]={a1(d['sat_dTs_dp'])};
  constant Real SATdhldp[nP]={a1(d['sat_dhl_dp'])};
  constant Real SATdhvdp[nP]={a1(d['sat_dhv_dp'])};
  constant Real SATdrholdp[nP]={a1(d['sat_drhol_dp'])};
  constant Real SATdrhovdp[nP]={a1(d['sat_drhov_dp'])};
  constant Real SATmul[nP]={a1(d['sat_mul'])};
  constant Real SATkl[nP]={a1(d['sat_kl'])};
  constant Real SATcpl[nP]={a1(d['sat_cpl'])};
  constant Real SATmuv[nP]={a1(d['sat_muv'])};
  constant Real SATkv[nP]={a1(d['sat_kv'])};
  constant Real SATcpv[nP]={a1(d['sat_cpv'])};
  constant Real SATsl[nP]={a1(d['sat_sl'])};
  constant Real SATsv[nP]={a1(d['sat_sv'])};
  constant Real SATcvl[nP]={a1(d['sat_cvl'])};
  constant Real SATcvv[nP]={a1(d['sat_cvv'])};
  constant Real TBLT[nP,nH]={a2(d['T'])};
  constant Real TBLrho[nP,nH]={a2(d['rho'])};
  constant Real TBLdrdp[nP,nH]={a2(d['drdp'])};
  constant Real TBLdrdh[nP,nH]={a2(d['drdh'])};
  constant Real TBLdTdp[nP,nH]={a2(d['dTdp'])};
  constant Real TBLdTdh[nP,nH]={a2(d['dTdh'])};
  constant Real TBLmu[nP,nH]={a2(d['mu'])};
  constant Real TBLk[nP,nH]={a2(d['k'])};
  constant Real TBLcp[nP,nH]={a2(d['cp'])};
  constant Real TBLs[nP,nH]={a2(d['s'])};
  constant Real TBLcv[nP,nH]={a2(d['cv'])};
  constant Integer PHg[nP,nH]={a2i(d['phase'])};
'''
mo=f'''within ;
package R290Tab "R290 tabulated media — (p,h) basis, 2상 안전, 미분가능 (CoolProp/Lemmon2009 기준상태 동일)"
{consts}{funcs}end R290Tab;
'''
open('R290Tab.mo','w').write(mo)
print(f"R290Tab.mo (full): {os.path.getsize('R290Tab.mo')/1024:.0f} KB")
