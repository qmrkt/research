# Active LP Result Snapshot

- Results: 530
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01224610141832410092305956179
- Mean max quote divergence vs reference: 4.398408899363372180105783115E-27
- Mean max NAV/deposit divergence vs reference: 7.377358490566037735849056604E-29
- Invariant failures: 0

## Run Families

- `adversarial`: results=384, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.577798065821499461805632873E-29, invariant_failures=0
- `deterministic`: results=18, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.711904072262239939115243739E-30, invariant_failures=0
- `monte_carlo`: results=128, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=9.245680842660050132422100703E-30, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #2: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #3: `paper_quick_adv_0040` (adversarial) fairness_gap=0.1013818647304912334936279088
- `positive` #4: `paper_quick_adv_0040` (adversarial) fairness_gap=0.1013818647304912334936279088
- `positive` #5: `paper_quick_adv_0088` (adversarial) fairness_gap=0.1008166892686887833882601907
- `negative` #1: `paper_quick_mc_0040` (monte_carlo) fairness_gap=-0.0637629538366293352534342638
- `negative` #2: `paper_quick_mc_0040` (monte_carlo) fairness_gap=-0.0637629538366293352534342636
- `negative` #3: `paper_quick_adv_0041` (adversarial) fairness_gap=-0.0611068760198373333840159201
- `negative` #4: `paper_quick_adv_0041` (adversarial) fairness_gap=-0.0611068760198373333840159197
- `negative` #5: `paper_quick_adv_0089` (adversarial) fairness_gap=-0.0599764144382116280161425843
