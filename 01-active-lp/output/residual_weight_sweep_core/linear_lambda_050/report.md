# Active LP Result Snapshot

- Results: 84
- Run families: deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 7.709329093858397694245009934E-29
- Mean fairness gap (late minus early NAV/deposit): -0.5569866089004581955310602629
- Mean max quote divergence vs reference: 4.262764670243647235709142852E-27
- Mean max NAV/deposit divergence vs reference: 8.928571428571428571428571429E-29
- Invariant failures: 0

## Run Families

- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=64, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=9.818290262799437823107770773E-30, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_050_mc_0028` (monte_carlo) fairness_gap=0.105648512059920199147410108
- `positive` #2: `linear_lambda_050_mc_0028` (monte_carlo) fairness_gap=0.105648512059920199147410108
- `positive` #3: `zero_flow_nav_invariance` (deterministic) fairness_gap=0.0000857418094000871563931488
- `positive` #4: `zero_flow_nav_invariance` (deterministic) fairness_gap=0.0000857418094000871563931488
- `negative` #1: `linear_lambda_050_mc_0010` (monte_carlo) fairness_gap=-1.151934575855034016027687597
- `negative` #2: `linear_lambda_050_mc_0010` (monte_carlo) fairness_gap=-1.151934575855034016027687597
- `negative` #3: `linear_lambda_050_mc_0009` (monte_carlo) fairness_gap=-1.035595170995309873376965268
- `negative` #4: `linear_lambda_050_mc_0009` (monte_carlo) fairness_gap=-1.035595170995309873376965268
- `negative` #5: `linear_lambda_050_mc_0000` (monte_carlo) fairness_gap=-1.027627633937280644730325474
- `absolute` #1: `linear_lambda_050_mc_0010` (monte_carlo) fairness_gap=-1.151934575855034016027687597
