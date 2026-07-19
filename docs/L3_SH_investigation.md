# L3 HX (Evap/Cond On-Design) SH zone 과열 과대 — 근본원인 조사

## 요약
증발기·응축기 L3(vendor HXSolver 셀 유한체적)의 Q가 OMC 대비 +9%.
차이는 **전부 SH(과열) zone**에서 발생. Python이 과열을 과다하게 냄
(SH_out: Python 17K vs OMC 6K). 근본원인은 **회로 토폴로지 + 공기-냉매
흐름 정렬 차이**로 특정. vendor 백본 수정 사안이라 정량보정은 보류.

## 물리적 판정: OMC(6K)가 옳음
- Python SH zone eps ≈ 0.98 → 과열부가 "거의 무한 UA"로 거동 (냉매 출구
  19.7°C가 공기입구 20°C에 근접). 건증기(HTC 낮음)에서 비현실적.
- OMC eps = 0.34가 건증기 낮은 HTC를 물리적으로 반영.
- 2nd law 상한(냉매출구 ≤ 공기입구 20°C, SH ≤ 17.7K)에 Python이 거의 붙음 = 위험신호.

## 상관식은 원인 아님
- vendor 과열역(x>1.05): h_single_gnielinski = 191.7 W/m²K
- OMC: dittus_boelter × EF_sgl = 200.8 W/m²K
- 거의 동일 → SH_out 3배 차이는 상관식이 아님.

## 근본원인: 회로 토폴로지 + 공기-냉매 흐름 정렬
셀 덤프(320셀 = 16 tube × 20 seg) 분석:
- 과열 셀(x=1.0)이 160개 = 전체의 50%. 과열에 면적 절반 배분 → 과열 과대.
- tube별 입구 x가 0.65~1.0로 제각각. 여러 tube가 이미 과열로 시작.

OMC Evap_On_Dyn:
- pathRow(k0,Nr,Nseg) = Nr − div(k0,Nseg)
- 주석: "p=Nr는 공기-출구측=냉매입구" → **counter-flow serpentine**.
  냉매 과열부(출구)가 공기 입구(20°C, 가장 따뜻)와 정렬되도록 배치.

Python vendor:
- circuit_mode 기본 'single' (공기-row 정렬 로직 OMC와 다름).
- serpentine_1/2로 바꾸면 SH 17K→14K로 개선되나 여전히 OMC 6K와 거리.
- 공기측 흐름 배열이 OMC pathRow와 구조적으로 달라 과열 면적 과대 배분 잔존.

## 판정: 정량보정 보류
- vendor hx_sim은 검증된 백본, 다른 컴포넌트(L2 2상 등)도 공유. 회로/공기흐름
  로직을 OMC에 맞춰 고치면 광범위 영향 + vendor 원 설계 훼손.
- L3의 존재의의는 reference인데, reference에 임의 튜닝은 자기모순 (L2 cf_SH와
  성격 다름 — cf_SH는 이동경계 2존의 명확한 구조근사 보정).

## 권고 (정석 순서)
1. **OMC Evap_On_Dyn을 당장의 L3 기준으로 채택** — 물리적으로 타당(SH 6K),
   냉매측 검증에서 이미 기준 역할 신뢰성 입증. Python L3는 정성/상대비교용.
2. **vendor HXSolver 공기-냉매 흐름 정렬 조사를 별도 과제로** — circuit_mode와
   공기 흐름 배열이 counter-flow serpentine을 정확히 구현하는지 vendor 레벨 점검.
3. **최종 검증은 실측** — 실제 HPWD 증발기 SH를 측정해 6K/17K 판정. 진짜 GT.

## 현황
냉매측 12칸: 10칸 완전일치(<1%), L3 2칸(Evap/Cond, 동일 vendor 엔진)만
회로 토폴로지 구조차로 +9% 보류. 정성 유효, 정량 보류.
