# Active LP Result Snapshot

- Results: 80
- Run families: adversarial, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 7.419422762462116291367197871E-29
- Mean fairness gap (late minus early NAV/deposit): -0.1100579215296421365144080753
- Mean absolute fairness gap: 0.1112026950147825128497271032
- Mean max quote divergence vs reference: 6.52356965837999541957365878E-27
- Mean max NAV/deposit divergence vs reference: 5E-30
- Invariant failures: 0

## Run Families

- `adversarial`: results=48, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.144379769979239088436996348E-30, invariant_failures=0
- `monte_carlo`: results=32, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=2.062373868096549644795695947E-30, invariant_failures=0

## Fairness Extremes

- `positive` #1: `calibration_low_tail_mc_0015` (monte_carlo) fairness_gap=0.013998487464162645134033109
- `positive` #2: `calibration_low_tail_mc_0015` (monte_carlo) fairness_gap=0.013998487464162645134033109
- `positive` #3: `calibration_low_tail_mc_0004` (monte_carlo) fairness_gap=0.0043919843563556118604213921
- `positive` #4: `calibration_low_tail_mc_0004` (monte_carlo) fairness_gap=0.0043919843563556118604213921
- `positive` #5: `calibration_low_tail_mc_0012` (monte_carlo) fairness_gap=0.002269119603071812269511740
- `negative` #1: `calibration_low_tail_mc_0002` (monte_carlo) fairness_gap=-0.4473338238536822170103941108
- `negative` #2: `calibration_low_tail_mc_0002` (monte_carlo) fairness_gap=-0.4473338238536822170103941107
- `negative` #3: `calibration_low_tail_mc_0008` (monte_carlo) fairness_gap=-0.3902044505021342978286055011
- `negative` #4: `calibration_low_tail_mc_0008` (monte_carlo) fairness_gap=-0.3902044505021342978286055011
- `negative` #5: `calibration_low_tail_adv_0007` (adversarial) fairness_gap=-0.3364714645046705262225710062
