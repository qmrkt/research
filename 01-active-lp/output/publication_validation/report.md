# Active-LP publication validation

Fixed diagnostic comparison; synthetic reference-engine results, not a fairness optimum or deployment validation.

Independent holdout histories: 96; seeds 41000–41095; 40–100 requested trades each. Funding is paired by identical requests. Guard-rejected requests remain in the logs; actual execution can differ across funding regimes. Normalized lambda .15 is frozen, not fit to these data.

## Fresh randomized holdout

Intervals are percentile bootstrap 95% intervals on history-level means. No restamps are counted as independent observations. Tail statistics are empirical sample tails.

| Funding | Residual allocation | Mean late−founder gap | 95% CI | Mean absolute gap | 95% CI | Mean LP ROI |
| --- | --- | ---: | --- | ---: | --- | ---: |
| floor | flat | -0.145240 | [-0.167081, -0.124282] | 0.145240 | [0.124282, 0.167081] | -0.004691 |
| floor | normalized_015 | -0.231880 | [-0.256932, -0.209110] | 0.231880 | [0.209110, 0.256932] | -0.004691 |
| floor | capital_accounts | -0.003001 | [-0.032408, 0.027008] | 0.112583 | [0.092997, 0.133103] | -0.004691 |
| fixed_20 | flat | -0.027142 | [-0.049689, -0.005880] | 0.076421 | [0.061168, 0.092435] | -0.004721 |
| fixed_20 | normalized_015 | -0.117618 | [-0.142781, -0.094197] | 0.133109 | [0.112393, 0.154840] | -0.004721 |
| fixed_20 | capital_accounts | -0.002188 | [-0.028240, 0.023700] | 0.098308 | [0.081082, 0.116877] | -0.004721 |
| proportional_20pct | flat | 0.033974 | [0.012005, 0.054634] | 0.086381 | [0.073915, 0.099915] | -0.004010 |
| proportional_20pct | normalized_015 | -0.058974 | [-0.083136, -0.036767] | 0.091482 | [0.073117, 0.111307] | -0.004010 |
| proportional_20pct | capital_accounts | -0.003201 | [-0.028151, 0.021654] | 0.092438 | [0.076273, 0.109912] | -0.004010 |

The gap is a distributional diagnostic, not a risk-adjusted fairness criterion. Capital accounts use each component's contributed capital, routed trade cash and winning liability; they are resolved-only counterfactual bookkeeping, not NAV-priced entry or a production change. Fee rights are identical across comparisons.

### Tails

| Funding/rule | Gap p05 | Gap p95 | Gap min | Gap max | Mean worst 5% | Mean best 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| floor/flat | -0.368557 | -0.042811 | -0.574070 | -0.000107 | -0.486087 | -0.017996 |
| floor/normalized_015 | -0.461051 | -0.091044 | -0.690046 | -0.009962 | -0.587009 | -0.035323 |
| floor/capital_accounts | -0.256729 | 0.287166 | -0.342763 | 0.449236 | -0.304030 | 0.362545 |
| fixed_20/flat | -0.247757 | 0.104643 | -0.412179 | 0.210063 | -0.340602 | 0.135540 |
| fixed_20/normalized_015 | -0.355729 | 0.056169 | -0.503011 | 0.184929 | -0.443514 | 0.105931 |
| fixed_20/capital_accounts | -0.209170 | 0.263855 | -0.309772 | 0.399581 | -0.261284 | 0.320671 |
| proportional_20pct/flat | -0.188784 | 0.144921 | -0.368548 | 0.204237 | -0.288577 | 0.171717 |
| proportional_20pct/normalized_015 | -0.300199 | 0.078350 | -0.486739 | 0.192837 | -0.392832 | 0.150489 |
| proportional_20pct/capital_accounts | -0.206221 | 0.236142 | -0.313102 | 0.374363 | -0.248847 | 0.301424 |

### Cancellation reserve guard

0 sell requests were blocked in 0 of 288 holdout path/funding runs. Minimum recorded refundable-basis margin: 86.118995896969842952567664186003870629464031186940907638636628459795047309608482. Minimum recorded all-outcome margin: 54.46446106613013343531935696771556299911335017738824290053221352701430250973774.

Blocked quoted proceeds are forgone immediate liquidation opportunity, not measured welfare loss. Each rejected request, share amount, quote and reserve shortfall is preserved in rejections.jsonl. The guard restricts sell availability; solvency is not costless.

## Designed stress pack

807 terminal outcome/funding/allocation rows, including all 64 low-tail branches, concentrated flow, zero-flow bootstrap dilution, 32 small LP cohorts and the cancellation counterexample. These are designed cases, not independent random observations and have no population confidence intervals.

| History | Funding | Rejected sells | Blocked quoted net proceeds |
| --- | --- | ---: | ---: |
| stress_zero_flow_n3 | floor | 0 | 0.000000 |
| stress_zero_flow_n3 | fixed_20 | 0 | 0.000000 |
| stress_zero_flow_n3 | proportional_20pct | 0 | 0.000000 |
| stress_concentrated_n3 | floor | 0 | 0.000000 |
| stress_concentrated_n3 | fixed_20 | 0 | 0.000000 |
| stress_concentrated_n3 | proportional_20pct | 0 | 0.000000 |
| stress_zero_flow_n8 | floor | 0 | 0.000000 |
| stress_zero_flow_n8 | fixed_20 | 0 | 0.000000 |
| stress_zero_flow_n8 | proportional_20pct | 0 | 0.000000 |
| stress_concentrated_n8 | floor | 0 | 0.000000 |
| stress_concentrated_n8 | fixed_20 | 0 | 0.000000 |
| stress_concentrated_n8 | proportional_20pct | 0 | 0.000000 |
| stress_low_tail_n64 | floor | 0 | 0.000000 |
| stress_low_tail_n64 | fixed_20 | 0 | 0.000000 |
| stress_low_tail_n64 | proportional_20pct | 0 | 0.000000 |
| stress_many_cohorts | floor | 0 | 0.000000 |
| stress_many_cohorts | fixed_20 | 0 | 0.000000 |
| stress_many_cohorts | proportional_20pct | 0 | 0.000000 |
| stress_cancel_profit_sells | floor | 1 | 99.573190 |
| stress_cancel_profit_sells | fixed_20 | 1 | 99.573190 |
| stress_cancel_profit_sells | proportional_20pct | 1 | 99.573190 |

## Adaptive LP/trader stress

A greedy actor observes current state, evaluates explicit buy/sell/LP/joint buy+LP candidates against a fixed latent outcome belief and chooses the one-step expected-wealth improvement over waiting. This is an actual state-dependent action policy; it is not a globally optimal adversary, equilibrium, or an estimate of attack incidence. Candidate action sizes are bounded but there is no total attacker budget cap. Positive profit may reflect legitimate informed trading and is not by itself proof of extraction from LPs. All candidate objectives and selected actions are published.

| Funding | Rule | Histories | Mean belief-weighted attacker profit | Worst realized branch | Best realized branch |
| --- | --- | ---: | ---: | ---: | ---: |
| floor | flat | 4 | 10.214699 | -31.140352 | 53.286339 |
| floor | normalized_015 | 4 | 10.214699 | -31.140352 | 53.286339 |
| floor | capital_accounts | 4 | 10.214699 | -31.140352 | 53.286339 |
| fixed_20 | flat | 4 | 11.647746 | -25.236230 | 56.363770 |
| fixed_20 | normalized_015 | 4 | 12.527160 | -24.587198 | 56.738483 |
| fixed_20 | capital_accounts | 4 | 10.214699 | -31.140352 | 53.286339 |
| proportional_20pct | flat | 4 | 13.995137 | -23.486118 | 58.113882 |
| proportional_20pct | normalized_015 | 4 | 14.802018 | -22.803747 | 58.521935 |
| proportional_20pct | capital_accounts | 4 | 10.214699 | -31.140352 | 53.286339 |

## Historical ablation replication

The original paper_quick held-out pack has 192 restamped MC rows from 64 histories plus 96 designed adversarial rows. Historical rows are reported with their original row weighting for comparison; this is not a new independent holdout. The original adversarial parity split separates terminal policies, not strategy histories. Capital-account summaries exclude cancellation rows and are therefore not directly comparable to pooled all-row summaries.

| Funding/rule | Rows | Mean gap | Mean absolute gap |
| --- | ---: | ---: | ---: |
| floor/flat | 288 | -0.015287533 | 0.015287533 |
| floor/normalized_015 | 288 | -0.106390953 | 0.106390953 |
| floor/capital_accounts | 264 | -0.005520933 | 0.012854161 |
| fixed_20/flat | 288 | 0.088043872 | 0.088043872 |
| fixed_20/normalized_015 | 288 | -0.006767418 | 0.039359183 |
| fixed_20/capital_accounts | 264 | -0.004989155 | 0.011638800 |
| proportional_20pct/flat | 288 | 0.172226183 | 0.172226183 |
| proportional_20pct/normalized_015 | 288 | 0.073869605 | 0.074855209 |
| proportional_20pct/capital_accounts | 264 | -0.004980833 | 0.011263641 |

## Artifacts and limits

- config.json records the predetermined design; provenance.json records interpreter, source hashes and configuration hash.
- paths.jsonl contains every requested history; holdout_rows.csv and cohort_rows.jsonl retain outcomes, deposits, fees, returns, elapsed capital time and path/cluster IDs.
- summary.json includes paired bootstrap contrasts, sample tails and secondary outcomes; no policy is selected from these results.
- stress_rows.csv, adaptive_rows.csv, adaptive_decisions.jsonl and rejections.jsonl separate designed attacks from inference.
- historical_rows.csv retains the complete selected historical holdout and its base-path IDs.

The randomized distribution is synthetic and fixed for this study. It does not estimate real-world participation, information arrival, profitability or capital demand. All primary runs resolve; cancellation is checked in a separate explicit guarded stress path. Decimal-accounting checks do not validate fixed-point AVM budgets, rounding, deployed contracts, or proof of universal strategic safety. Small adaptive action grids can miss stronger attacks; capital accounts are a comparator rather than a newly validated mechanism.
