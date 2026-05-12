"""
Winandy 모델 validation 데이터 재현 스크립트
═══════════════════════════════════════════════════════════════════════
실행:
  cd backend && python3 ../data/validation/generate_winandy_data.py

출력:
  data/validation/winandy_validation_data.csv

조건 (HPWD R290 ~10cc reciprocating typical):
  - T_e: 0, 5, 10, 15 °C (4 evaporator temps)
  - T_c: 40, 50, 60, 70 °C (4 condenser temps)
  - N: 1800, 3000, 4200 rpm (3 speeds)
  - Superheat: 8K (fixed)
  - Total: 48 test points

True params (calibration이 찾아야 할 값):
  AU_loss=6.5, AU_su=3.8, dP_su=0.045, V_swept_eff=0.93,
  clearance_factor=0.052, over_comp_factor=0.45,
  W_loss_const=28.0, alpha_loss=0.085

측정 노이즈:
  - m_dot: ±0.7%
  - T_dis: ±0.4°C
  - W_elec: ±0.7%
"""
import sys
import os
import math
import random

# backend 경로 추가 (script가 어디서 실행되든)
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, '..', '..', 'backend'))
sys.path.insert(0, backend_dir)

from components import REGISTRY
import CoolProp.CoolProp as CP

random.seed(42)  # 재현성

comp = REGISTRY.get('compressor_winandy')

# True params (HPWD R290 ~10cc reciprocating typical)
params_true = {
    'fluid': 'R290',
    'comp_type': 'reciprocating',
    'T_amb': 30.0,
    'V_disp': 10.0,
    'rv_in': 2.5,
    'eta_motor': 0.92,
    # Fitting (calibration target)
    'AU_loss': 6.5,
    'AU_su': 3.8,
    'dP_su': 0.045,
    'V_swept_eff': 0.93,
    'clearance_factor': 0.052,
    'over_comp_factor': 0.45,
    'W_loss_const': 28.0,
    'alpha_loss': 0.085,
}

# 운전 조건 grid
T_e_list = [0, 5, 10, 15]
T_c_list = [40, 50, 60, 70]
N_list = [1800, 3000, 4200]
SH = 8.0

csv_lines = ["test_id,P_suc,T_suc,P_dis,N,m_dot,T_dis,W_elec"]
test_id = 1
for T_e in T_e_list:
    for T_c in T_c_list:
        for N in N_list:
            P_suc = CP.PropsSI('P', 'T', 273.15 + T_e, 'Q', 1, 'R290') / 1e5
            P_dis = CP.PropsSI('P', 'T', 273.15 + T_c, 'Q', 1, 'R290') / 1e5
            T_suc = T_e + SH

            inp = {'P_suc': P_suc, 'T_suc': T_suc, 'P_dis': P_dis, 'N': N}
            r = comp.step(inp, params_true, {}, dt=1.0)
            o = r['outputs']

            # 측정 노이즈 (현실적)
            m_dot_meas = o['m_dot'] * (1 + random.uniform(-0.007, 0.007))
            T_dis_meas = o['T_dis'] + random.uniform(-0.4, 0.4)
            W_meas = o['W_elec'] * (1 + random.uniform(-0.007, 0.007))

            csv_lines.append(
                f"{test_id},{P_suc:.3f},{T_suc:.2f},{P_dis:.3f},{N},"
                f"{m_dot_meas:.5f},{T_dis_meas:.2f},{W_meas:.2f}"
            )
            test_id += 1

output_path = os.path.join(script_dir, 'winandy_validation_data.csv')
with open(output_path, 'w') as f:
    f.write("\n".join(csv_lines))

print(f"✓ Generated: {output_path}")
print(f"  {test_id - 1} test points")
print(f"  Operating range: T_e {T_e_list[0]}~{T_e_list[-1]}°C, "
      f"T_c {T_c_list[0]}~{T_c_list[-1]}°C, "
      f"N {N_list[0]}~{N_list[-1]} rpm")
