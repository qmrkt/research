# Active LP Result Snapshot

- Results: 340
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.726236382983195709702754400E-28
- Mean fairness gap (late minus early NAV/deposit): 0.02267138148336782542275468296
- Mean max quote divergence vs reference: 4.734706486157641424049560435E-27
- Mean max NAV/deposit divergence vs reference: 7.647058823529411764705882353E-29
- Invariant failures: 0

## Run Families

- `adversarial`: results=192, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.592131587494917525145622839E-30, invariant_failures=0
- `deterministic`: results=20, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=7.179945996230535009539316455E-30, invariant_failures=0
- `monte_carlo`: results=128, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.108452592562668941510363842E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `linear_lambda_0025_mc_0028` (monte_carlo) fairness_gap=0.1983976234235545761904366513
- `positive` #2: `linear_lambda_0025_mc_0028` (monte_carlo) fairness_gap=0.1983976234235545761904366513
- `positive` #3: `linear_lambda_0025_mc_0056` (monte_carlo) fairness_gap=0.1861446254491102209026780537
- `positive` #4: `linear_lambda_0025_mc_0056` (monte_carlo) fairness_gap=0.1861446254491102209026780537
- `positive` #5: `linear_lambda_0025_mc_0011` (monte_carlo) fairness_gap=0.1263879924659336384073178010
- `negative` #1: `linear_lambda_0025_mc_0037` (monte_carlo) fairness_gap=-0.1551570294732945603398726924
- `negative` #2: `linear_lambda_0025_mc_0037` (monte_carlo) fairness_gap=-0.1551570294732945603398726917
- `negative` #3: `linear_lambda_0025_mc_0038` (monte_carlo) fairness_gap=-0.1539617152237537792037530466
- `negative` #4: `linear_lambda_0025_mc_0038` (monte_carlo) fairness_gap=-0.1539617152237537792037530464
- `negative` #5: `linear_lambda_0025_mc_0008` (monte_carlo) fairness_gap=-0.1353839855014703560673600111
