# Active LP Result Snapshot

- Results: 1682
- Run families: adversarial, deterministic, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 1.331354052328818386740688393E-28
- Mean fairness gap (late minus early NAV/deposit): 0.01218597664321143936008790251
- Mean max quote divergence vs reference: 4.400939685230003720194712416E-27
- Mean max NAV/deposit divergence vs reference: 8.014268727705112960760998811E-29
- Invariant failures: 0

## Run Families

- `adversarial`: results=1152, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=8.732059201195012562457481753E-30, invariant_failures=0
- `deterministic`: results=18, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.711904072262239939115243739E-30, invariant_failures=0
- `monte_carlo`: results=512, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=1.380017256426418299967540737E-29, invariant_failures=0

## Fairness Extremes

- `positive` #1: `paper_core_adv_0040` (adversarial) fairness_gap=0.1214577385637370339949307856
- `positive` #2: `paper_core_adv_0040` (adversarial) fairness_gap=0.1214577385637370339949307855
- `positive` #3: `paper_core_adv_0184` (adversarial) fairness_gap=0.1208248870715991751342775927
- `positive` #4: `paper_core_adv_0184` (adversarial) fairness_gap=0.1208248870715991751342775926
- `positive` #5: `paper_core_adv_0088` (adversarial) fairness_gap=0.1205465731222711464979713603
- `negative` #1: `paper_core_mc_0248` (monte_carlo) fairness_gap=-0.0841403043176575594631289574
- `negative` #2: `paper_core_mc_0248` (monte_carlo) fairness_gap=-0.0841403043176575594631289565
- `negative` #3: `paper_core_mc_0040` (monte_carlo) fairness_gap=-0.0771907635967673105732608476
- `negative` #4: `paper_core_mc_0040` (monte_carlo) fairness_gap=-0.0771907635967673105732608476
- `negative` #5: `paper_core_adv_0185` (adversarial) fairness_gap=-0.0764897089611710594662278063
