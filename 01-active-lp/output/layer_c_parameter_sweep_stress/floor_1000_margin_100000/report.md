# Active LP Result Snapshot

- Results: 106
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01478059706724177125460442434
- Mean max quote divergence vs reference: 0.0001727671945871665100176528292
- Mean max NAV/deposit divergence vs reference: 0.0005217105997284831118094461755
- Invariant failures: 0

## Run Families

- `adversarial`: results=64, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.518426317498983505029124564E-29, invariant_failures=0
- `deterministic`: results=18, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.711904072262239939115243739E-30, invariant_failures=0
- `monte_carlo`: results=24, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.079991760555132770318069405E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1141896878868264463342288263
- `positive` #2: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #3: `sweep_floor_1000_margin_100000_adv_0026` (adversarial) fairness_gap=0.1030036798608631487107382268
- `positive` #4: `sweep_floor_1000_margin_100000_adv_0058` (adversarial) fairness_gap=0.1014502813770336484498351865
- `positive` #5: `sweep_floor_1000_margin_100000_adv_0026` (adversarial) fairness_gap=0.1013818647304912334936279088
- `negative` #1: `sweep_floor_1000_margin_100000_adv_0027` (adversarial) fairness_gap=-0.0611068760198373333840159197
- `negative` #2: `sweep_floor_1000_margin_100000_adv_0059` (adversarial) fairness_gap=-0.0599764144382116280161425843
- `negative` #3: `sweep_floor_1000_margin_100000_adv_0027` (adversarial) fairness_gap=-0.0594848747546575571683110360
- `negative` #4: `sweep_floor_1000_margin_100000_adv_0059` (adversarial) fairness_gap=-0.0593426751442028305820301509
- `negative` #5: `sweep_floor_1000_margin_100000_adv_0049` (adversarial) fairness_gap=-0.0553796248386019507090109061
