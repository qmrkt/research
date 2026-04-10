# Active LP Result Snapshot

- Results: 84
- Run families: deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 7.709329093858397694245009934E-29
- Mean fairness gap (late minus early NAV/deposit): -0.3628069857983688696345315551
- Mean max quote divergence vs reference: 4.262764670243647235709142852E-27
- Mean max NAV/deposit divergence vs reference: 9.166666666666666666666666667E-29
- Invariant failures: 0

## Run Families

- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=64, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=9.818290262799437823107770773E-30, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_020_mc_0028` (monte_carlo) fairness_gap=0.1331572832835792415814944948
- `positive` #2: `linear_lambda_020_mc_0028` (monte_carlo) fairness_gap=0.1331572832835792415814944948
- `positive` #3: `linear_lambda_020_mc_0027` (monte_carlo) fairness_gap=0.0395627649950864195190713805
- `positive` #4: `linear_lambda_020_mc_0027` (monte_carlo) fairness_gap=0.0395627649950864195190713805
- `positive` #5: `zero_flow_nav_invariance` (deterministic) fairness_gap=0.0000857418094000871563931488
- `negative` #1: `linear_lambda_020_mc_0010` (monte_carlo) fairness_gap=-0.7710010245363408093637778765
- `negative` #2: `linear_lambda_020_mc_0010` (monte_carlo) fairness_gap=-0.7710010245363408093637778764
- `negative` #3: `linear_lambda_020_mc_0009` (monte_carlo) fairness_gap=-0.7355339176526750877171683093
- `negative` #4: `linear_lambda_020_mc_0009` (monte_carlo) fairness_gap=-0.7355339176526750877171683093
- `negative` #5: `linear_lambda_020_mc_0019` (monte_carlo) fairness_gap=-0.7092900077994628196010068735
