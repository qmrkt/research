# Active LP Result Snapshot

- Results: 340
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.001585219310883530098470708873
- Mean max quote divergence vs reference: 4.734706486157641424049560435E-27
- Mean max NAV/deposit divergence vs reference: 6.5E-29
- Invariant failures: 0

## Run Families

- `adversarial`: results=192, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.592131587494917525145622839E-30, invariant_failures=0
- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=128, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.108452592562668941510363842E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_0032_mc_0028` (monte_carlo) fairness_gap=0.1930807997225016044612122274
- `positive` #2: `linear_lambda_0032_mc_0028` (monte_carlo) fairness_gap=0.1930807997225016044612122274
- `positive` #3: `linear_lambda_0032_mc_0056` (monte_carlo) fairness_gap=0.1804020254928164393026813981
- `positive` #4: `linear_lambda_0032_mc_0056` (monte_carlo) fairness_gap=0.1804020254928164393026813981
- `positive` #5: `linear_lambda_0032_mc_0027` (monte_carlo) fairness_gap=0.1192230817590854090473010780
- `negative` #1: `linear_lambda_0032_mc_0037` (monte_carlo) fairness_gap=-0.2041151532732801966439905304
- `negative` #2: `linear_lambda_0032_mc_0037` (monte_carlo) fairness_gap=-0.2041151532732801966439905301
- `negative` #3: `linear_lambda_0032_mc_0038` (monte_carlo) fairness_gap=-0.2032079611595507985189555609
- `negative` #4: `linear_lambda_0032_mc_0038` (monte_carlo) fairness_gap=-0.2032079611595507985189555602
- `negative` #5: `linear_lambda_0032_mc_0008` (monte_carlo) fairness_gap=-0.1801554673049550813387729691
