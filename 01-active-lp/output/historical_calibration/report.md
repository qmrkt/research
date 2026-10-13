# Expanded historical calibration comparison

This retrospective repair gives both formulas a continuous nonnegative parameter range and selects only on the original +20-funded training data. It does not change the fresh 96-path publication suite or identify an information-timing effect.

The original ordinary training and test packs each contain 192 MC duration variants (64 base histories, durations 12/48/168) plus 96 designed adversarial rows. The adversarial parity split separates terminal policies of related strategy histories and is not independent held-out behavior. Row weighting is preserved for comparability; no population confidence intervals are attached.

## Train-only selection

The primary objective is absolute mean late-minus-founder terminal NAV/deposit gap, as in the original calibration. Every training row's gap is checked to be nonincreasing in lambda. A nonnegative root is bracketed, then solved by 60 bisections. Mean absolute gap and duration heterogeneity are reported, not silently substituted as selection objectives.

| Formula | Selected lambda |
| --- | ---: |
| event | 0.003636166087 |
| normalized | 0.139227125962 |

## Original test pack and funding ablation

The floor diagnostic reuses the +20-trained parameter; no parameter is refit to the floor-funded paths.

| Split | Funding | Rule | Rows | Mean gap | Mean absolute gap | Min | Max |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| train | fixed_20 | flat | 288 | 0.087833577 | 0.087833577 | 0.039187669 | 0.206863237 |
| train | fixed_20 | event_selected | 288 | -0.000000000 | 0.096328478 | -0.345138144 | 0.197992125 |
| train | fixed_20 | normalized_selected | 288 | 0.000000000 | 0.041794043 | -0.088550156 | 0.190666421 |
| train | fixed_20 | event_0.0025 | 288 | 0.022473703 | 0.083407705 | -0.253173834 | 0.199090070 |
| train | fixed_20 | event_0.025 | 288 | -0.191373146 | 0.224685696 | -1.033926885 | 0.180972059 |
| train | fixed_20 | normalized_0.15 | 288 | -0.006080752 | 0.044719090 | -0.097542455 | 0.189928820 |
| train | floor | flat | 288 | -0.017290630 | 0.017290630 | -0.103055778 | 0.000000000 |
| train | floor | event_selected | 288 | -0.102725839 | 0.102725839 | -0.479143614 | -0.003258200 |
| train | floor | normalized_selected | 288 | -0.101516672 | 0.101516672 | -0.220363821 | -0.009890175 |
| train | floor | event_0.0025 | 288 | -0.080863501 | 0.080863501 | -0.385661383 | -0.002264227 |
| train | floor | event_0.025 | 288 | -0.288700650 | 0.288700650 | -1.144181899 | -0.018666503 |
| train | floor | normalized_0.15 | 288 | -0.107349254 | 0.107349254 | -0.228549186 | -0.010557928 |
| test | fixed_20 | flat | 288 | 0.088043872 | 0.088043872 | 0.040703636 | 0.185969259 |
| test | fixed_20 | event_selected | 288 | 0.001623251 | 0.091764158 | -0.336059996 | 0.157753733 |
| test | fixed_20 | normalized_selected | 288 | -0.000638951 | 0.037479158 | -0.074564162 | 0.140330050 |
| test | fixed_20 | event_0.0025 | 288 | 0.023646804 | 0.080319890 | -0.242570686 | 0.166425653 |
| test | fixed_20 | event_0.025 | 288 | -0.184660334 | 0.213107538 | -1.053582560 | 0.131719386 |
| test | fixed_20 | normalized_0.15 | 288 | -0.006767418 | 0.039359183 | -0.082523745 | 0.139421763 |
| test | floor | flat | 288 | -0.015287533 | 0.015287533 | -0.079816759 | 0.000000000 |
| test | floor | event_selected | 288 | -0.099462556 | 0.099462556 | -0.427091707 | -0.003512696 |
| test | floor | normalized_selected | 288 | -0.100501207 | 0.100501207 | -0.204840156 | -0.010664902 |
| test | floor | event_0.0025 | 288 | -0.078013114 | 0.078013114 | -0.326885299 | -0.002441009 |
| test | floor | event_0.025 | 288 | -0.280629927 | 0.280629927 | -1.150257985 | -0.020134228 |
| test | floor | normalized_0.15 | 288 | -0.106390953 | 0.106390953 | -0.213779808 | -0.011385199 |

## Duration slices

The unscaled adversarial rows are a separate family, not a duration treatment. MC restamps preserve economic requests and only alter the clock. Dividing by the total active span reduces dependence on clock units, but the one-unit offsets in the numerator and denominator and integer restamp rounding prevent exact affine clock invariance. Reduced duration sensitivity in these slices is a portability result, not evidence that the calibrated allocation is economically fair.

| Funding | Rule | Duration/family | Rows | Mean gap | Mean absolute gap |
| --- | --- | --- | ---: | ---: | ---: |
| fixed_20 | flat | short | 64 | 0.086438523 | 0.086438523 |
| fixed_20 | flat | medium | 64 | 0.086438523 | 0.086438523 |
| fixed_20 | flat | long | 64 | 0.086438523 | 0.086438523 |
| fixed_20 | flat | unscaled_adversarial | 96 | 0.091254570 | 0.091254570 |
| fixed_20 | event_selected | short | 64 | 0.063586225 | 0.063586225 |
| fixed_20 | event_selected | medium | 64 | -0.007213433 | 0.044598071 |
| fixed_20 | event_selected | long | 64 | -0.171739352 | 0.182083226 |
| fixed_20 | event_selected | unscaled_adversarial | 96 | 0.081780792 | 0.081780792 |
| fixed_20 | normalized_selected | short | 64 | 0.005311831 | 0.041822463 |
| fixed_20 | normalized_selected | medium | 64 | 0.006933510 | 0.040604231 |
| fixed_20 | normalized_selected | long | 64 | 0.007298388 | 0.040484574 |
| fixed_20 | normalized_selected | unscaled_adversarial | 96 | -0.014946005 | 0.030496628 |
| fixed_20 | event_0.025 | short | 64 | -0.048655972 | 0.072737707 |
| fixed_20 | event_0.025 | medium | 64 | -0.296642631 | 0.303833873 |
| fixed_20 | event_0.025 | long | 64 | -0.530085873 | 0.532829271 |
| fixed_20 | event_0.025 | unscaled_adversarial | 96 | 0.029608650 | 0.033055382 |
| fixed_20 | normalized_0.15 | short | 64 | -0.000304370 | 0.043026300 |
| fixed_20 | normalized_0.15 | medium | 64 | 0.001431619 | 0.041537913 |
| fixed_20 | normalized_0.15 | long | 64 | 0.001822118 | 0.041436278 |
| fixed_20 | normalized_0.15 | unscaled_adversarial | 96 | -0.022268498 | 0.034077220 |
| floor | flat | short | 64 | -0.011157675 | 0.011157675 |
| floor | flat | medium | 64 | -0.011157675 | 0.011157675 |
| floor | flat | long | 64 | -0.011157675 | 0.011157675 |
| floor | flat | unscaled_adversarial | 96 | -0.023547247 | 0.023547247 |
| floor | event_selected | short | 64 | -0.033425831 | 0.033425831 |
| floor | event_selected | medium | 64 | -0.102476663 | 0.102476663 |
| floor | event_selected | long | 64 | -0.263007228 | 0.263007228 |
| floor | event_selected | unscaled_adversarial | 96 | -0.032447853 | 0.032447853 |
| floor | normalized_selected | short | 64 | -0.090218272 | 0.090218272 |
| floor | normalized_selected | medium | 64 | -0.088680334 | 0.088680334 |
| floor | normalized_selected | long | 64 | -0.088335097 | 0.088335097 |
| floor | normalized_selected | unscaled_adversarial | 96 | -0.123347819 | 0.123347819 |
| floor | event_0.025 | short | 64 | -0.142823478 | 0.142823478 |
| floor | event_0.025 | medium | 64 | -0.384875457 | 0.384875457 |
| floor | event_0.025 | long | 64 | -0.612934408 | 0.612934408 |
| floor | event_0.025 | unscaled_adversarial | 96 | -0.081467553 | 0.081467553 |
| floor | normalized_0.15 | short | 64 | -0.095692231 | 0.095692231 |
| floor | normalized_0.15 | medium | 64 | -0.094045791 | 0.094045791 |
| floor | normalized_0.15 | long | 64 | -0.093676298 | 0.093676298 |
| floor | normalized_0.15 | unscaled_adversarial | 96 | -0.130229980 | 0.130229980 |

## Reproduction and limits

snapshots.jsonl retains terminal free residuals, cohort deposits/depth/fees and entry clocks, enough to recompute every allocation without replaying trades. paths.jsonl retains the exact requests. selection_trace.csv contains every training objective evaluated during bracketing/bisection; raw_rows.csv retains each path for every reported parameter/funding; config.json and provenance.json record the design and source hashes. The cache is keyed on all economic requests, funding and fee parameters; time-only variants reuse accounting, while each path retains its own clocks.

The +20 founding endowment affects the measured gap. These retrospective results repair the restricted-grid comparison; they do not establish a universal optimal coefficient, risk-adjusted fairness, causal timing advantage, or deployment safety. The original test pack has already been examined and is explicitly historical.
