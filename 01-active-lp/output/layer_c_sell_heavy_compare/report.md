# Active LP Result Snapshot

- Results: 114
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 0.9736842105263157894736842105
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01214414918335909034177822934
- Mean max quote divergence vs reference: 0.0002265283189783836980172207382
- Mean max NAV/deposit divergence vs reference: 0.001624364930627452133072145347
- Invariant failures: 0

## Run Families

- `adversarial`: results=32, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.518426317498983505029124564E-29, invariant_failures=0
- `deterministic`: results=18, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.711904072262239939115243739E-30, invariant_failures=0
- `monte_carlo`: results=64, price_pass=1, slippage_pass=0.953125, solvency_pass=1, mean_max_price_change=1.448035152151413651072015597E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1141896878868264463342288263
- `positive` #2: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #3: `layer_c_sell_heavy_adv_0000` (adversarial) fairness_gap=0.1030036798608631487107382268
- `positive` #4: `layer_c_sell_heavy_adv_0004` (adversarial) fairness_gap=0.1014502813770336484498351865
- `positive` #5: `layer_c_sell_heavy_adv_0000` (adversarial) fairness_gap=0.1013818647304912334936279088
- `negative` #1: `layer_c_sell_heavy_adv_0001` (adversarial) fairness_gap=-0.0611068760198373333840159197
- `negative` #2: `layer_c_sell_heavy_adv_0005` (adversarial) fairness_gap=-0.0599764144382116280161425843
- `negative` #3: `layer_c_sell_heavy_adv_0001` (adversarial) fairness_gap=-0.0594848747546575571683110360
- `negative` #4: `layer_c_sell_heavy_adv_0005` (adversarial) fairness_gap=-0.0593426751442028305820301509
- `negative` #5: `layer_c_sell_heavy_mc_0018` (monte_carlo) fairness_gap=-0.0477073338817463047754726581
