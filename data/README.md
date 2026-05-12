# Data

검증·테스트·캘리브레이션용 데이터 모음.

## 폴더 구조

```
data/
└── validation/                          # 모델 검증 데이터 (synthetic, ground-truth 알려진 데이터)
    ├── winandy_validation_data.csv      # 48-point Winandy compressor 검증 데이터
    ├── winandy_validation_guide.md      # 상세 사용 가이드 + 예상 R²
    └── generate_winandy_data.py         # 재현 스크립트 (seed=42 고정)
```

## Validation 데이터란

- **목적**: Calibration Studio가 정상 동작하는지 검증 + 모델 sanity check
- **출처**: Winandy 모델 자체로 생성 (true params 알려진 상태) + 현실적 측정 노이즈
- **결과**: Calibration이 잘 동작하면 R² ≥ 0.99 도달 가능

실제 시험 데이터가 아니므로 fitting parameter 값을 "실제 부품 식별" 용도로 사용하면 안 됨.
실제 데이터 들어오면 별도 폴더 (`data/measured/` 등)에 정리 권장.

## 재현 방법

```bash
cd hpwd-studio-task
python3 data/validation/generate_winandy_data.py
```

`CoolProp` 필요 (`pip install CoolProp`).

자세한 사용법은 [winandy_validation_guide.md](validation/winandy_validation_guide.md) 참고.
