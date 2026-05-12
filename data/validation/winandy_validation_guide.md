# Winandy 모델 검증 데이터 — HPWD R290 Compressor

## 데이터 개요

**대상**: R290 가변속 reciprocating compressor (~10 cc, HPWD typical)
**테스트 포인트**: 48 (T_e × T_c × N = 4 × 4 × 3, superheat 고정 8K)
**측정 노이즈**: ṁ ±0.7%, T_dis ±0.4°C, W_elec ±0.7%

## 운전 조건

| 변수 | 값 | 의미 |
|---|---|---|
| T_e | 0, 5, 10, 15 °C | 증발기 포화온도 (P_suc = R290 포화압력) |
| T_c | 40, 50, 60, 70 °C | 응축기 포화온도 (P_dis = R290 포화압력) |
| N | 1800, 3000, 4200 rpm | 인버터 가변속 |
| Superheat | 8 K | T_suc = T_e + 8 |

압력 범위:
- P_suc: 4.74 ~ 7.32 bar (T_e 0~15°C)
- P_dis: 13.69 ~ 25.87 bar (T_c 40~70°C)
- 압축비 (P_dis/P_suc): 1.87 ~ 5.46 (HPWD 작동 범위 전체)

## 측정 항목 (CSV columns)

| Column | Unit | 의미 |
|---|---|---|
| `test_id` | - | 시험 번호 |
| `P_suc` | bar | 흡입 압력 (input) |
| `T_suc` | °C | 흡입 온도 (input) |
| `P_dis` | bar | 토출 압력 (input) |
| `N` | rpm | 회전수 (input) |
| `m_dot` | kg/s | **냉매 질량 유량 (output, 검증 대상)** |
| `T_dis` | °C | **토출 가스 온도 (output, 검증 대상)** |
| `W_elec` | W | **전력 소비 (output, 검증 대상)** |

## True Parameters (검증용 — calibration이 찾아야 할 값)

```yaml
# Geometry (고정 — 데이터시트값)
V_disp:       10.0 cm³
rv_in:        2.5
eta_motor:    0.92

# Operating
T_amb:        30.0 °C   # HPWD 운전 환경

# Fitting (calibration target)
AU_loss:           6.5   W/K
AU_su:             3.8   W/K
dP_su:             0.045
V_swept_eff:       0.93
clearance_factor:  0.052
over_comp_factor:  0.45
W_loss_const:      28.0  W
alpha_loss:        0.085
```

## R² 예상 결과

### Default params (calibration 시작점, fitting 전)
| Output | R² | RMSE | MAPE |
|---|---|---|---|
| m_dot | 0.9953 | 0.13 g/s | 2.73% |
| T_dis | 0.9989 | 0.86 °C | 0.80% |
| W_elec | 0.9857 | 32.8 W | 5.33% |

### True params (calibration 완벽 수렴 시)
| Output | R² | RMSE | MAPE |
|---|---|---|---|
| m_dot | 0.9999 | 0.02 g/s | 0.36% |
| T_dis | 0.9999 | 0.25 °C | 0.26% |
| W_elec | 0.9999 | 2.4 W | 0.35% |

## Calibration Studio 사용법

1. **Setup**:
   - Component 선택: `compressor_winandy`
   - CSV 업로드: `winandy_validation_data.csv`
   - 자동 매칭 확인: inputs (P_suc, T_suc, P_dis, N) + outputs (m_dot, T_dis, W_elec)

2. **Fit**:
   - Fitting targets 선택 (8개 fitting parameters 모두 또는 일부)
   - 알고리즘: trust-region (scipy lsq trf)
   - Run → 30~60초 (48 points × 8 params × ~30 iter)

3. **Validate**:
   - Parity plots: 측정 vs 시뮬 산점도
   - R² ≥ 0.99 확인 (모든 3개 outputs)
   - RMSE/MAPE 작아야 함 (위 표 참고)

4. **Apply**:
   - "Apply to HPWD Studio" → 시뮬 노드에 적용
   - 또는 JSON 내보내기 → 다른 환경 재사용

## 참고: 운전 조건 grid 분해

```
T_e=0°C, T_c=40°C, N=1800/3000/4200  →  3 points (압축비 2.89)
T_e=0°C, T_c=50°C, N=1800/3000/4200  →  3 points (압축비 3.61)
...
T_e=15°C, T_c=70°C, N=4200            →  마지막 point (압축비 3.53)
```

이 grid는 P_dis/P_suc compression ratio 2.0~5.5 + RPM 1800~4200 을 골고루 커버
→ Winandy 모델의 fitting parameters를 well-conditioned로 estimate 가능.
