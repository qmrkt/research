# Active LP Result Snapshot

- Results: 84
- Run families: deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 7.709329093858397694245009934E-29
- Mean fairness gap (late minus early NAV/deposit): -0.4131138844787970284329420144
- Mean max quote divergence vs reference: 4.262764670243647235709142852E-27
- Mean max NAV/deposit divergence vs reference: 8.809523809523809523809523810E-29
- Invariant failures: 0

## Run Families

- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=64, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=9.818290262799437823107770773E-30, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_025_mc_0028` (monte_carlo) fairness_gap=0.125555726923138143114578983
- `positive` #2: `linear_lambda_025_mc_0028` (monte_carlo) fairness_gap=0.125555726923138143114578983
- `positive` #3: `linear_lambda_025_mc_0027` (monte_carlo) fairness_gap=0.0269295599980746750063036604
- `positive` #4: `linear_lambda_025_mc_0027` (monte_carlo) fairness_gap=0.0269295599980746750063036604
- `positive` #5: `zero_flow_nav_invariance` (deterministic) fairness_gap=0.0000857418094000871563931488
- `negative` #1: `linear_lambda_025_mc_0010` (monte_carlo) fairness_gap=-0.8695600227346693691831703904
- `negative` #2: `linear_lambda_025_mc_0010` (monte_carlo) fairness_gap=-0.8695600227346693691831703903
- `negative` #3: `linear_lambda_025_mc_0009` (monte_carlo) fairness_gap=-0.8161955448953188473031352340
- `negative` #4: `linear_lambda_025_mc_0009` (monte_carlo) fairness_gap=-0.8161955448953188473031352339
- `negative` #5: `linear_lambda_025_mc_0019` (monte_carlo) fairness_gap=-0.7927441308122129265012490381
