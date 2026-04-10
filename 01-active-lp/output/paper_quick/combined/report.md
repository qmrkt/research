# Active LP Result Snapshot

- Results: 265
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01224610141832410092305956179
- Invariant failures: 0

## Run Families

- `adversarial`: results=192, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=3.155596131642998923611265746E-29, invariant_failures=0
- `deterministic`: results=9, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.342380814452447987823048748E-29, invariant_failures=0
- `monte_carlo`: results=64, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.849136168532010026484420141E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `skewed_late_lp` (deterministic) fairness_gap=0.1139392829117664504807242379
- `positive` #2: `paper_quick_adv_0040` (adversarial) fairness_gap=0.1013818647304912334936279088
- `positive` #3: `paper_quick_adv_0088` (adversarial) fairness_gap=0.1008166892686887833882601907
- `positive` #4: `paper_quick_adv_0024` (adversarial) fairness_gap=0.0986309306945858388024276514
- `positive` #5: `paper_quick_adv_0072` (adversarial) fairness_gap=0.0986309306945858388024276513
- `negative` #1: `paper_quick_mc_0040` (monte_carlo) fairness_gap=-0.0637629538366293352534342638
- `negative` #2: `paper_quick_adv_0041` (adversarial) fairness_gap=-0.0611068760198373333840159197
- `negative` #3: `paper_quick_adv_0089` (adversarial) fairness_gap=-0.0599764144382116280161425843
- `negative` #4: `paper_quick_mc_0025` (monte_carlo) fairness_gap=-0.0572137639846448223423533351
- `negative` #5: `paper_quick_adv_0073` (adversarial) fairness_gap=-0.0553796248386019507090109061
