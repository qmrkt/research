# Active LP Result Snapshot

- Results: 88
- Run families: adversarial, deterministic, high_skew
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.06861437000781081713638783844
- Mean absolute fairness gap: 0.1152509403646060068138026081
- Mean max quote divergence vs reference: 0
- Mean max NAV/deposit divergence vs reference: 0
- Invariant failures: 0

## Run Families

- `adversarial`: results=48, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=4.406728410520278580243690248E-29, invariant_failures=0
- `deterministic`: results=16, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=2.93974505586351014613581185E-29, invariant_failures=0
- `high_skew`: results=24, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.111214347214029749153866117E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `fpmm_compare_high_skew_0011` (high_skew) fairness_gap=0.9962473197442573067850386437
- `positive` #2: `fpmm_compare_high_skew_0003` (high_skew) fairness_gap=0.9926809593188826047210197254
- `positive` #3: `fpmm_compare_high_skew_0007` (high_skew) fairness_gap=0.9926809593188826047210197243
- `positive` #4: `fpmm_compare_high_skew_0002` (high_skew) fairness_gap=0.7445299999541575936874539055
- `positive` #5: `fpmm_compare_high_skew_0006` (high_skew) fairness_gap=0.7445299999541575936874539053
- `negative` #1: `fpmm_compare_high_skew_0007` (high_skew) fairness_gap=-0.3364714645046705262225710062
- `negative` #2: `fpmm_compare_high_skew_0003` (high_skew) fairness_gap=-0.1935970525146330416798639513
- `negative` #3: `fpmm_compare_high_skew_0006` (high_skew) fairness_gap=-0.1370074869530081975177940629
- `negative` #4: `fpmm_compare_high_skew_0011` (high_skew) fairness_gap=-0.1326886218966466057674338971
- `negative` #5: `fpmm_compare_high_skew_0002` (high_skew) fairness_gap=-0.1053550649128290322877925213
