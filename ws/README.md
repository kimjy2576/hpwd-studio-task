# 워크스테이션 실행 패키지 (2026-08-04)

컨테이너(1vCPU·롤백)에서 못 끝낸 장주기 런 일괄. OMC 1.27 계열 권장
(지문 비교가 아닌 밴드 판정이라 버전 달라도 유효하나 버전 기록할 것).

## 준비 (워크트리 2개)

    git clone https://github.com/kimjy2576/hpwd-studio-task.git hpwd
    cd hpwd && git checkout feat/ph4a-staggered
    git worktree add ../hpwd-v1 feat/analytic-medium

각 .mos 첫 줄의 REPO 경로를 실제 경로로 수정 후 실행.

## WS-A: v1 600s symbolic 완주 (위임 3건 통합 판정)

feat/analytic-medium HEAD(73a7b24)에 PH1·PH6·PH6b(Kp_eev=1.0 기본)가
전부 포함 → 이 런 하나가 P5 완결 + PH1 + PH6b(T1) 드리프트 교차를 판정.

    omc ws_a_v1_symbolic.mos            # 빌드 (~2분)
    ./HPWDcycle.Cycle_L3_coldstart_charge -s dassl -stopTime=600 \
      -tolerance=1e-3 -override=use_real_ctrl=true,f_target_Hz=30.0 \
      -jacobian=coloredSymbolical -r=wsa.csv
    python3 judge.py wsa.csv

판정: 완주 + |드리프트| ≤ 0.05% (P5 실측 0~300s ±0.037% 의 연장 기대).
대조 앵커: 수치판 드리프트 우려(T1 계열 −4% 급) 대비 개선 폭 기록.

## WS-B: G2 B측 — Cycle_L3C 600s (수치 → 기호)

feat/ph4a-staggered 최신 pull (차기 세션이 comp.h_dis 시드 패치를 커밋할
수 있음 — 있으면 포함, 없어도 웍스 성능이면 크롤 회피 가능성 높음.
크롤 재현 시: HPWDcycle.mo 의 Cycle_L3C_coldstart_PI 에서
comp(..., h_dis(start=4.5e5, nominal=4.0e5)) 추가 후 재빌드).

    omc ws_b_l3c.mos                    # 수치 빌드
    ./HPWDcycle.Cycle_L3C_coldstart_charge -s dassl -stopTime=600 \
      -tolerance=1e-3 -override=use_real_ctrl=true,f_target_Hz=30.0 -r=wsb.csv
    python3 judge.py wsb.csv
    omc ws_b_l3c_sym.mos                # 기호 재빌드
    ./HPWDcycle.Cycle_L3C_coldstart_charge ... -jacobian=coloredSymbolical -r=wsb_sym.csv
    python3 judge.py wsb_sym.csv

### A측 기준 (Dyn 동일제어, 컨테이너 실측 — D7 박제)

| 완주 | 드리프트 | M | Pc/Pe | SH | 개도/f |
|---|---|---|---|---|---|
| 600s | −0.160~+0.201% | 100.05g | 9.774/6.419 | −0.336K | 98p/30Hz |

B측 판정: 완주 + |드리프트| ≤0.4%(수치)·기호는 개선 확인 + 종점 대등
(SH ±1K, Pc·Pe ±2%, 개도 ±8p, M ±1%) + wall ≤ A측 2배.
결과 CSV·수치를 다음 세션에 주면 G2 판정 문서화함.
