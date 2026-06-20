import numpy as np, CoolProp.CoolProp as CP
from CoolProp.CoolProp import AbstractState
import CoolProp.constants as K

# 운전 envelope (clamp [1.5,35]bar와 정합) + 여유
P = np.linspace(1.5e5, 35e5, 60)
H = np.linspace(120e3, 720e3, 140)
nP, nH = len(P), len(H)
AS = AbstractState("HEOS", "Propane")

# --- 1D 포화 테이블 sat(p) ---
sat = {k: np.zeros(nP) for k in
       ['Tsat','hl','hv','rhol','rhov','mul','kl','cpl','muv','kv','cpv','dTs_dp','dhl_dp','dhv_dp','drhol_dp','drhov_dp']}
for i,p in enumerate(P):
    AS.update(K.PQ_INPUTS, p, 0.0)
    sat['Tsat'][i]=AS.T(); sat['hl'][i]=AS.hmass(); sat['rhol'][i]=AS.rhomass()
    sat['mul'][i]=AS.viscosity(); sat['kl'][i]=AS.conductivity(); sat['cpl'][i]=AS.cpmass()
    sat['dTs_dp'][i]=AS.first_saturation_deriv(K.iT, K.iP); sat['dhl_dp'][i]=AS.first_saturation_deriv(K.iHmass,K.iP); sat['drhol_dp'][i]=AS.first_saturation_deriv(K.iDmass,K.iP)
    AS.update(K.PQ_INPUTS, p, 1.0)
    sat['hv'][i]=AS.hmass(); sat['rhov'][i]=AS.rhomass()
    sat['muv'][i]=AS.viscosity(); sat['kv'][i]=AS.conductivity(); sat['cpv'][i]=AS.cpmass(); sat['dhv_dp'][i]=AS.first_saturation_deriv(K.iHmass,K.iP); sat['drhov_dp'][i]=AS.first_saturation_deriv(K.iDmass,K.iP)

# --- 2D (p,h) 테이블 ---
T2=np.full((nP,nH),np.nan); rho2=np.full((nP,nH),np.nan)
drdp=np.full((nP,nH),np.nan); drdh=np.full((nP,nH),np.nan)
mu2=np.full((nP,nH),np.nan); k2=np.full((nP,nH),np.nan); cp2=np.full((nP,nH),np.nan)
dTdp=np.full((nP,nH),np.nan); dTdh=np.full((nP,nH),np.nan)
phase=np.full((nP,nH),np.nan)  # 0=2상, 1=과냉액, 2=과열증기
nfail=0
for i,p in enumerate(P):
    hl,hv=sat['hl'][i],sat['hv'][i]
    mul,muv,kl,kv,cpl,cpv=(sat[x][i] for x in ['mul','muv','kl','kv','cpl','cpv'])
    for j,h in enumerate(H):
        try:
            AS.update(K.HmassP_INPUTS, h, p)
            T2[i,j]=AS.T(); rho2[i,j]=AS.rhomass()
            drdp[i,j]=AS.first_partial_deriv(K.iDmass,K.iP,K.iHmass)
            drdh[i,j]=AS.first_partial_deriv(K.iDmass,K.iHmass,K.iP)
            dTdp[i,j]=AS.first_partial_deriv(K.iT,K.iP,K.iHmass)
            dTdh[i,j]=AS.first_partial_deriv(K.iT,K.iHmass,K.iP)
            ph=AS.phase()
            if ph==K.iphase_twophase:
                Q=(h-hl)/(hv-hl); phase[i,j]=0
                mu2[i,j]=(1-Q)*mul+Q*muv; k2[i,j]=(1-Q)*kl+Q*kv; cp2[i,j]=(1-Q)*cpl+Q*cpv
            else:
                phase[i,j]=1 if h<hl else 2
                mu2[i,j]=AS.viscosity(); k2[i,j]=AS.conductivity(); cp2[i,j]=AS.cpmass()
        except Exception:
            nfail+=1
np.savez('r290_table.npz', P=P,H=H, T=T2,rho=rho2,drdp=drdp,drdh=drdh,dTdp=dTdp,dTdh=dTdh,mu=mu2,k=k2,cp=cp2,phase=phase, **{f'sat_{k}':v for k,v in sat.items()})
print(f"격자 {nP}x{nH}={nP*nH}  실패점={nfail} ({100*nfail/(nP*nH):.1f}%)")
print(f"NaN: T={np.isnan(T2).sum()} rho={np.isnan(rho2).sum()} drdh={np.isnan(drdh).sum()}")
print(f"P범위 {P[0]/1e5:.1f}~{P[-1]/1e5:.1f}bar  H범위 {H[0]/1e3:.0f}~{H[-1]/1e3:.0f}kJ/kg")
