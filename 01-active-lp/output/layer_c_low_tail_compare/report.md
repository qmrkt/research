# Active LP Result Snapshot

- Results: 80
- Run families: adversarial, monte_carlo
- Price continuity pass rate: 1
- Slippage improvement pass rate: 1
- Solvency pass rate: 1
- Max price change at LP entry: 7.419422762462116291367197871E-29
- Mean fairness gap (late minus early NAV/deposit): 0.3302070163146941961769247366
- Mean max quote divergence vs reference: 0.01991391463303688430640173249
- Mean max NAV/deposit divergence vs reference: 0.0005046396421077428787711719249
- Invariant failures: 8

## Run Families

- `adversarial`: results=48, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=6.144379769979239088436996348E-30, invariant_failures=0
- `monte_carlo`: results=32, price_pass=1, slippage_pass=1, solvency_pass=1, mean_max_price_change=2.062373868096549644795695947E-30, invariant_failures=8

## Fairness Extremes

- `positive` #1: `layer_c_low_tail_mc_0002` (monte_carlo) fairness_gap=0.9094574010420938551671558382
- `positive` #2: `layer_c_low_tail_mc_0002` (monte_carlo) fairness_gap=0.9093619250854120004686958495
- `positive` #3: `layer_c_low_tail_adv_0007` (adversarial) fairness_gap=0.8925116549906999942156377147
- `positive` #4: `layer_c_low_tail_adv_0003` (adversarial) fairness_gap=0.8925116549906999942156377145
- `positive` #5: `layer_c_low_tail_adv_0003` (adversarial) fairness_gap=0.8924651006128251048035158231
- `negative` #1: `layer_c_low_tail_mc_0008` (monte_carlo) fairness_gap=-0.297156085429954516446006979
- `negative` #2: `layer_c_low_tail_mc_0008` (monte_carlo) fairness_gap=-0.2971491170080731366866571101
- `negative` #3: `layer_c_low_tail_mc_0009` (monte_carlo) fairness_gap=-0.277070995129956941146426560
- `negative` #4: `layer_c_low_tail_mc_0009` (monte_carlo) fairness_gap=-0.277067903591621502474205186
- `negative` #5: `layer_c_low_tail_mc_0004` (monte_carlo) fairness_gap=-0.0597413264370635740457011699
