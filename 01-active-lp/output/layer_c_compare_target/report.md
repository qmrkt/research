# Active LP Result Snapshot

- Results: 194
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 0.9948453608247422680412371134
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01544488694828455511539286607
- Mean max quote divergence vs reference: 0.0001669035844851525865301528151
- Mean max NAV/deposit divergence vs reference: 0.0004716779241726825687121267629
- Invariant failures: 0

## Run Families

- `adversarial`: results=128, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.592131587494917525145622822E-30, invariant_failures=0
- `deterministic`: results=18, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.711904072262239939115243739E-30, invariant_failures=0
- `monte_carlo`: results=48, price_pass=1, slippage_pass=0.9791666666666666666666666667, solvency_pass=1, mean_max_price_change=1.046210704322302801993277304E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1141896878868264463342288263
- `positive` #2: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #3: `layer_c_adv_0026` (adversarial) fairness_gap=0.1030036798608631487107382268
- `positive` #4: `layer_c_adv_0058` (adversarial) fairness_gap=0.1014502813770336484498351865
- `positive` #5: `layer_c_adv_0026` (adversarial) fairness_gap=0.1013818647304912334936279088
- `negative` #1: `layer_c_adv_0027` (adversarial) fairness_gap=-0.0611068760198373333840159197
- `negative` #2: `layer_c_adv_0059` (adversarial) fairness_gap=-0.0599764144382116280161425843
- `negative` #3: `layer_c_adv_0027` (adversarial) fairness_gap=-0.0594848747546575571683110360
- `negative` #4: `layer_c_adv_0059` (adversarial) fairness_gap=-0.0593426751442028305820301509
- `negative` #5: `layer_c_adv_0049` (adversarial) fairness_gap=-0.0553796248386019507090109061
