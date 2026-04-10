# Active LP Result Snapshot

- Results: 340
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.03848783875572365904047665409
- Mean max quote divergence vs reference: 4.734706486157641424049560435E-27
- Mean max NAV/deposit divergence vs reference: 7.147058823529411764705882353E-29
- Invariant failures: 0

## Run Families

- `adversarial`: results=192, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.592131587494917525145622839E-30, invariant_failures=0
- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=128, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.108452592562668941510363842E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_0020_mc_0028` (monte_carlo) fairness_gap=0.2024992876114914472650003524
- `positive` #2: `linear_lambda_0020_mc_0028` (monte_carlo) fairness_gap=0.2024992876114914472650003524
- `positive` #3: `linear_lambda_0020_mc_0056` (monte_carlo) fairness_gap=0.1904544640480993165501604534
- `positive` #4: `linear_lambda_0020_mc_0056` (monte_carlo) fairness_gap=0.1904544640480993165501604534
- `positive` #5: `linear_lambda_0020_mc_0011` (monte_carlo) fairness_gap=0.1349170926306584672609317422
- `negative` #1: `linear_lambda_0020_mc_0037` (monte_carlo) fairness_gap=-0.1175124456626400942720847091
- `negative` #2: `linear_lambda_0020_mc_0037` (monte_carlo) fairness_gap=-0.1175124456626400942720847085
- `negative` #3: `linear_lambda_0020_mc_0038` (monte_carlo) fairness_gap=-0.1154333812974578549709001071
- `negative` #4: `linear_lambda_0020_mc_0038` (monte_carlo) fairness_gap=-0.1154333812974578549709001070
- `negative` #5: `linear_lambda_0020_mc_0008` (monte_carlo) fairness_gap=-0.1009863836280613598222500549
