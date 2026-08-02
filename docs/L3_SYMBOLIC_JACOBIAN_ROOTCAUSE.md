# L3 기호 야코비안 빌드 실패 — 근본원인과 빌드 레시피

**작성** 2026-08-02 · 대상 `HPWDcycle.Cycle_L3_coldstart_charge`
**환경** Ubuntu 24.04 · OpenModelica **1.27.0** (apt `release`) · MSL `omlibrary` 1.27.0 · vCPU 1 · RAM 4 GB

이 문서는 두 가지를 기록합니다. 하나는 **검증된 빌드 레시피**이고, 다른 하나는
`docs/HANDOFF_2026-07-31.md` §3 이 지목한 원인이 **틀렸다는 측정 결과**입니다.

---

## 1. 검증된 빌드 레시피 — 테이블 물성 + 기본 야코비안

### 핵심 규칙

> **`setCommandLineOptions` 를 쓰지 않습니다.**

빌드 스크립트가 유실된 뒤 재구성하면서 `--tearingMethod=minimalTearing` 과
`--generateDynamicJacobian=numeric` 을 추가했더니 **해석이 초기화에서 즉사**했습니다.

| 빌드 옵션 | 빌드 | 해석 |
|---|---|---|
| `minimalTearing` + `Jacobian=numeric` | 성공 70 s | **초기화 즉사** — NLS 1198(크기 1198, 밀도 0.01) |
| 옵션 없음 | 성공 65 s | **600 s 완주** |

초기화 실패 시 로그는 `KINSOL: Ill input ERROR -2` 로 나오지만, 이는 증상입니다.
`-nlssMaxDensity=0.0` 으로 sparse 선택을 끄면 `residualFunc1198 failed at time=0`
이 드러납니다. `-nls=hybrid|newton` 은 sparse 자동선택이 우선하여 **적용되지 않습니다.**

### 빌드 스크립트

```modelica
loadModel(Modelica); getErrorString();
// modelica/*.mo 31 개를 절대경로로 loadFile (verify/load_all.mos 와 동일 목록)
buildModel(HPWDcycle.Cycle_L3_coldstart_charge,
           stopTime=600, tolerance=1e-3, method="dassl", outputFormat="csv",
           variableFilter="(M_total|Pc_bar|Pe_bar|SH|comp.N|vol4.M|
                            oil.M_eq|oil.T_shell|eevctl.n_pulse|seq.f)");
```

`variableFilter` 는 **빌드 시점 옵션**입니다. 843 점이라는 출력 규모와 217 초라는
소요시간은 이 필터를 전제로 합니다. 필터 없이 2016 변수를 모두 출력하면
시간도 판정 기준도 달라집니다.

### 실행 명령과 재현 지문

```bash
./HPWDcycle.Cycle_L3_coldstart_charge -s dassl -stopTime=600 -tolerance=1e-3 \
  -override=use_real_ctrl=true,f_target_Hz=30.0 -r=base.csv
```

| 항목 | 2026-07-31 | 2026-08-02 재현 | 판정 |
|---|---|---|---|
| 완주 | 600 s | 600 s, RC=0 | 일치 |
| 소요 | 216 s | **217 s** | 일치 |
| 출력점 | 843 | **843** | 일치 |
| 질량 드리프트 min | −0.0844 % | **−0.0844 %** | 일치 |
| 질량 드리프트 max | +0.0127 % | **+0.0127 %** | 일치 |

드리프트는 `M_total` 기준 `(M − M[0])/M[0]×100`, `M[0] = 0.1 kg` 입니다.
소수 넷째 자리까지 일치하므로 이 값을 **기준선 지문**으로 사용합니다.

---

## 2. 기호 야코비안 실패의 근본원인

### 재현

`setCommandLineOptions("--generateDynamicJacobian=symbolic")` **한 줄만** 추가하면
`_12jac.c`(15 MB) 생성 후 clang 에서 실패합니다.

```
_12jac.c:67230: error: statement requires expression of integer type
                ('modelica_real' (aka 'double') invalid)
```

### 실제 원인 — 테이블 물성의 배열 룩업

실패 지점의 생성 코드입니다.

```c
/* equation index: 11754
   cond.hl.$pDERA.dummyVarA = vshell.p.$pDERA.dummyVarA
        * ( ... {0.37908, 0.3021627, ...}[$cse1657] ... ) */
switch(jacobian->tmpVars[2315] /* $cse1657 JACOBIAN_TMP_VAR */)
{ /* ASUB */
```

`cond.hl` 은 `R290Tab.hl(P)` 입니다. 테이블 물성은 선형보간을 위해 **정수 배열 첨자**를
계산하고, OMC 는 이를 공통부분식 `$cse1657` 로 추출합니다. 그런데 야코비안 코드의
`jacobian->tmpVars` 는 **`modelica_real` 배열**이므로 정수 첨자가 double 로 저장되고,
그 위에 `switch` 가 생성되어 타입 에러가 납니다.

### 규모 — 448 건 전수 귀속

| 출처 | 건수 |
|---|---|
| 셀별 `T_ph`/`rho_ph` 공통부분식 (`$cse546`~`$cse966`, 72 개 × 6) | 432 |
| `cond.*` 물성 (`hl`, `hv`, `rho_l`, `rho_v`) | 8 |
| `evap.*` 물성 | 8 |
| `vol4.*` (어큐) | 4 |
| **합계** | **448** |

- 448 건 **전부** `R290Tab` 테이블 물성 룩업입니다.
- 본체 C 파일에는 이 패턴이 **0 건**입니다. 그래서 수치 야코비안은 정상 빌드·완주합니다.
- clang 은 `-ferror-limit` 으로 20 건에서 멈추므로, 로그만 보면 응축기 4 개 변수처럼
  보입니다. 파일 전체를 세어야 규모가 드러납니다.

---

## 3. HANDOFF 2026-07-31 §3 의 원인 지목은 틀렸습니다

핸드오프는 범인을 `HPWDevap.mo` 의 **증발기 `w_wet` 습표면 블렌딩**으로 지목했습니다.
측정 결과 **`w_wet` 은 448 건 중 0 건**이며, 함께 의심했던 `SH` 부호화도 0 건입니다.

### 왜 이분 탐색이 빗나갔는가

`git diff feat/analytic-props main -- modelica/HPWDevap.mo` 에는 **세 갈래**가
한 덩어리로 섞여 있습니다.

| 축 | `feat/analytic-props` | `main` |
|---|---|---|
| **A. 물성 호출부** | `R290Tab.Tsat_a(P)` (해석) | `R290Tab.Tsat(P)` (테이블) |
| B. 증발기 `w_wet` | 없음 | 있음 |
| C. `SH` 정의 | smooth-max | 부호 있는 `if`/`max` |

`feat/analytic-props` 워크트리가 빌드에 성공한 것은 **축 A** 때문입니다. 해석 함수에는
배열 룩업이 없습니다. 여기에 `main` 의 `HPWDevap.mo` 를 얹으면 호출부가 평문 테이블
함수로 되돌아가고, 그 순간 448 건이 되살아납니다.

**파일 지목은 맞았으나 기전을 잘못 귀속했습니다.** 같은 파일에 마침 눈에 띄는 신규
코드(`w_wet`)가 있었던 것이 함정이었습니다. 이는 핸드오프 §6 이 스스로 적어둔
"증상을 보고 가설을 세우면 빗나간다"의 또 한 사례입니다.

### 따라서 `w_wet` 절제는 하지 않습니다

빌드 복구와 무관합니다. 효과가 없었다는 별개 사안은 별도로 판단합니다.

---

## 4. 처방과 판정 (2026-08-02 확정)

### 기전의 정밀화 — 인라인 vs 함수호출이 본질입니다

`derivative=` 어노테이션은 모든 물성 함수에 이미 있었습니다. 실패 원인은
한 줄짜리 `lin1` 기반 `_d` 함수를 OMC 가 **자동 인라인**하여 야코비안 식에
전개하는 것이었습니다. 덩치 큰 `rho_ph_d`/`T_ph_d` 는 함수 호출로 남아
무사했습니다(jac 파일에서 289/244회 호출 실측). 즉 "테이블 vs 해석"이
아니라 "인라인 vs 함수호출"의 문제입니다.

### 적용된 수정 (커밋 3eccde5)

소형 `_d` 함수 12건(`lin1_d`, 포화선 11종)에
`annotation(Inline=false, LateInline=false)`.

| 검증 | 결과 |
|---|---|
| 기호 빌드 `_12jac.c` switch(real) | 448 → **0건**, 컴파일 통과 |
| 본체 무영향 (60 s 창) | 6.19 s ↔ 6.14 s, 야코비안 65회 동일 |
| 지문 보존 (600 s, 옵션 없는 빌드) | 223 s / 843점 / **−0.0844~+0.0127 %** 일치 |

### 그러나 기호 야코비안 경로는 이중으로 막혀 있습니다

| 문제 | 측정 |
|---|---|
| (a) 기호 야코비안 자체가 느림 | 60 s 창에서 야코비안 평가 4.03 s → **150.3 s (37배)** |
| (b) symbolic 빌드 플래그가 본체 오염 | `coloredNumerical` 강제해도 **t=252 정체** (지문 실패). 어노테이션 단독 빌드는 통과하므로 귀속은 플래그 자체 |
| (c) 런타임 자동 선택 | 기호 야코비안이 빌드에 존재하면 플래그 없이도 그쪽이 잡힘 |

**운영 바이너리는 반드시 옵션 없는 빌드를 사용합니다.**
`--generateDynamicJacobian=symbolic` 은 진단 목적 외에는 쓰지 않습니다.

### `_a` 해석물성 이식의 지위

빌드 복구 수단으로는 **불필요**해졌습니다. (b) 때문에 "해석+기호" 조합도
성립하지 않습니다. 남은 명분은 "수치 야코비안 하에서 테이블 룩업보다
다항식 평가가 빠른가" 하나이며, 이는 낮은 우선순위의 별도 속도 실험입니다.
야코비안이 60 s 창 시간의 65 %(4.03/6.19 s)이므로 이론 상한도 약 3배입니다.

## 4b. P0 실험 — t=252 정체의 진범과 테이블의 구조적 한계 (2026-08-02)

§4 의 "(b) symbolic 플래그가 본체 오염" 귀속은 **틀렸습니다.** 정정합니다.

### 실험

포화선 `_d` 5종(Tsat_d, hl_d, hv_d, rhol_d, rhov_d)만 교체했습니다.
구판은 별도 도함수 테이블 보간(`lin1(SATdTsdp,p)`) — 값과 원리적으로
불일치하지만 매끄럽습니다. 신판은 값 보간식의 정확한 기울기
(`lin1_d(SATTsat,p)`) — 값과 일치하지만 격자점마다 계단(구간상수)입니다.
`rho_ph_d` 가 2026-07-26 에 받은 것과 같은 수술입니다.

### 결과 — 4분면 전수 측정

| 도함수 \ 빌드 | 옵션 없음(수치 야코비안) | symbolic + coloredNumerical |
|---|---|---|
| 불일치·매끄러움 (main) | **217 s 완주** — 확정 경로 | **t=252 정체** |
| 일치·계단 (P0) | **t=349 정체** | **316 s 완주**, 드리프트 −0.287 % / 896점 |

### 해석

1. **t=252 정체의 진범은 도함수 불일치입니다.** symbolic 빌드는 본체
   미분식(더미 도함수)이 `_d` 를 실제로 사용하는 코드를 만들고, 값과 어긋난
   도함수가 민감 구간에서 적분을 무너뜨립니다. 플래그는 불일치를 드러낸
   매개였을 뿐입니다. (커밋 3eccde5 메시지의 (b) 항은 이 문서로 정정합니다.)
2. **선형보간 테이블은 "값-도함수 일치"와 "도함수 매끄러움"을 동시에 줄 수
   없습니다.** 일치를 고르면 도함수가 60개 격자점마다 계단이라 수치 경로가
   t=349 에서 죽고, 매끄러움을 고르면 불일치 때문에 symbolic 경로가 t=252
   에서 죽습니다. 어느 쪽을 골라도 한 경로가 죽는 구조적 한계입니다.
3. **P0 변경은 커밋하지 않고 되돌렸습니다.** 확정 경로(테이블+수치)를
   깨뜨리기 때문입니다. 진단 실험으로서만 유효합니다.

### 결론 — `_a` 해석물성의 근거 격상

`_a` 다항식은 값이 C∞ 이고 도함수가 정확하며 매끄럽습니다. 두 성질을
동시에 충족하는 유일한 선택지입니다. `_a` 이식의 근거는 "ASUB 회피"
(§4 에서 어노테이션으로 이미 해소)가 아니라 **테이블 미분 병리의 유일한
해소책**입니다. 이것이 해석물성 + 기호 야코비안 경로를 계속 추진하는
이유입니다.

## 5. 컨테이너 재구성 절차

컨테이너는 세션 간에 초기화됩니다. `/tmp/tb` 빌드 캐시와 `runnum.mos` 는 남지 않습니다.

```bash
# OpenModelica
curl -fsSL https://build.openmodelica.org/apt/openmodelica.asc \
  | gpg --dearmor -o /usr/share/keyrings/openmodelica-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/openmodelica-keyring.gpg] \
  https://build.openmodelica.org/apt noble release" \
  > /etc/apt/sources.list.d/openmodelica.list
apt-get update && apt-get install -y --no-install-recommends omc omlibrary
```

- `omlibrary` 를 빠뜨리면 `Modelica.Units.SI.Pressure not found` 가 납니다.
- apt 에는 **1.27.0(release) / 1.27.0~4(stable) / 1.28.0-dev(nightly)** 만 있습니다.
  1.26.x 는 받을 수 없습니다.
- `verify/load_all.mos` 는 절대경로가 `/home/claude/repo/modelica/` 로 하드코딩되어
  있으므로, 작업 디렉터리를 그 경로로 맞추면 그대로 쓸 수 있습니다.
- `HPWD.mo`, `Cycle.mo` 등이 외부 `HelmholtzMedia` 를 참조하지만 `loadFile` 은 파싱만
  하므로, 대상 모델이 해당 클래스를 인스턴스화하지 않는 한 없어도 빌드됩니다.
- 기호 야코비안 빌드는 첫 실행이 **로그 없이 조용히 중단**되는 일이 있습니다.
  같은 명령을 다시 실행하면 진행됩니다(오브젝트 재사용). 2 회차 소요 139 초.

---

## 6. 미해결

| 항목 | 상태 |
|---|---|
| `_a` 함수군 이식 | 미착수 |
| `T_ph_a` DTB 블렌딩 | 미착수 |
| 호출부 `_a` 전환 (146 건) | 미착수 |
| 해석물성 기호 야코비안 빌드 | 미측정 |
| `w_wet` 의 물리적 효과 | 별개 사안. 빌드와 무관함이 확인됨 |
