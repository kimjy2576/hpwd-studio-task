import numpy as np, CoolProp.CoolProp as CP
from CoolProp.CoolProp import AbstractState
import CoolProp.constants as K
P = np.linspace(1.5e5, 35e5, 60); H = np.linspace(120e3, 720e3, 140)
nP, nH = len(P), len(H); AS = AbstractState("HEOS", "Propane")
satk=['Tsat','hl','hv','rhol','rhov','mul','kl','cpl','muv','kv','cpv','sl','sv','cvl','cvv',
      'dTs_dp','dhl_dp','dhv_dp','drhol_dp','drhov_dp']
sat={k:np.zeros(nP) for k in satk}
for i,p in enumerate(P):
    AS.update(K.PQ_INPUTS,p,0.0)
    sat['Tsat'][i]=AS.T(); sat['hl'][i]=AS.hmass(); sat['rhol'][i]=AS.rhomass()
    sat['mul'][i]=AS.viscosity(); sat['kl'][i]=AS.conductivity(); sat['cpl'][i]=AS.cpmass()
    sat['sl'][i]=AS.smass(); sat['cvl'][i]=AS.cvmass()
    sat['dTs_dp'][i]=AS.first_saturation_deriv(K.iT,K.iP); sat['dhl_dp'][i]=AS.first_saturation_deriv(K.iHmass,K.iP); sat['drhol_dp'][i]=AS.first_saturation_deriv(K.iDmass,K.iP)
    AS.update(K.PQ_INPUTS,p,1.0)
    sat['hv'][i]=AS.hmass(); sat['rhov'][i]=AS.rhomass()
    sat['muv'][i]=AS.viscosity(); sat['kv'][i]=AS.conductivity(); sat['cpv'][i]=AS.cpmass()
    sat['sv'][i]=AS.smass(); sat['cvv'][i]=AS.cvmass()
    sat['dhv_dp'][i]=AS.first_saturation_deriv(K.iHmass,K.iP); sat['drhov_dp'][i]=AS.first_saturation_deriv(K.iDmass,K.iP)
F=lambda:np.full((nP,nH),np.nan)
T2,rho2,drdp,drdh,dTdp,dTdh,s2,cv2,mu2,k2,cp2=(F() for _ in range(11))
phase=F(); nfail=0
for i,p in enumerate(P):
    hl,hv=sat['hl'][i],sat['hv'][i]
    mul,muv,kl,kv,cpl,cpv=(sat[x][i] for x in ['mul','muv','kl','kv','cpl','cpv'])
    for j,h in enumerate(H):
        try:
            AS.update(K.HmassP_INPUTS,h,p)
            T2[i,j]=AS.T(); rho2[i,j]=AS.rhomass(); s2[i,j]=AS.smass(); cv2[i,j]=AS.cvmass()
            drdp[i,j]=AS.first_partial_deriv(K.iDmass,K.iP,K.iHmass); drdh[i,j]=AS.first_partial_deriv(K.iDmass,K.iHmass,K.iP)
            dTdp[i,j]=AS.first_partial_deriv(K.iT,K.iP,K.iHmass); dTdh[i,j]=AS.first_partial_deriv(K.iT,K.iHmass,K.iP)
            if AS.phase()==K.iphase_twophase:
                Q=(h-hl)/(hv-hl); phase[i,j]=0
                mu2[i,j]=(1-Q)*mul+Q*muv; k2[i,j]=(1-Q)*kl+Q*kv; cp2[i,j]=(1-Q)*cpl+Q*cpv
            else:
                phase[i,j]=1 if h<hl else 2
                mu2[i,j]=AS.viscosity(); k2[i,j]=AS.conductivity(); cp2[i,j]=AS.cpmass()
        except Exception: nfail+=1
np.savez('r290_table.npz', P=P,H=H, T=T2,rho=rho2,drdp=drdp,drdh=drdh,dTdp=dTdp,dTdh=dTdh,
         s=s2,cv=cv2, mu=mu2,k=k2,cp=cp2,phase=phase, **{f'sat_{k}':v for k,v in sat.items()})
print(f"격자 {nP}x{nH}  실패={nfail}  s,cv NaN: {np.isnan(s2).sum()},{np.isnan(cv2).sum()}")
print(f"s 범위: {np.nanmin(s2):.0f}~{np.nanmax(s2):.0f} J/kgK")
