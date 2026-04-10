# Active LP Research Trace Index

This index is the paper-facing map of simulator outputs for the active-LP LMSR research program.
Each entry points to a concrete output directory with manifests, raw results, and derived summaries.

## How To Use This Index

- Use the directory path as the canonical citation target in paper drafts and internal notes.
- Prefer `report.md` for quick interpretation.
- Prefer `manifest.json` and `results.jsonl` when the paper needs reproducible run inputs and raw rows.
- Prefer `aggregate.json`, `scenario_summary.csv`, and `fairness_extremes.csv` for tables and figure generation.

## Core Mechanism Validation

### Layer B Compare Quick

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_b_compare_quick`
- Purpose: first direct comparison of the exact parallel benchmark against the compressed global-state candidate
- Headline:
  - price continuity pass rate `1`
  - slippage improvement pass rate `1`
  - solvency pass rate `1`
  - candidate/reference quote and NAV divergence effectively zero in high precision

### Layer B Compare Core

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_b_compare_core`
- Purpose: heavier comparison pack for the same Layer A vs Layer B question
- Headline:
  - high-precision Layer B remains effectively exact versus the reference benchmark

### FPMM Compare Normalized Core

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/fpmm_compare_normalized_core`
- Purpose: matched resolved-only head-to-head between the normalized-default active-LP mechanism and a Gnosis-style FPMM pool-share baseline
- Headline:
  - the comparison now uses the held-out normalized default `linear_lambda_normalized_0150000`
  - ordinary and moderately adversarial slices remain mixed, but active-LP is slightly more neutral overall
  - the high-skew boundary strongly favors the normalized active-LP design

## Fixed-Point / AVM Feasibility

### Layer C Compare Target

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_compare_target`
- Purpose: main fixed-point regime comparison against the high-precision reference
- Headline:
  - mechanically stable
  - small but nonzero quote and NAV drift

### Layer C Sell Heavy Compare

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_sell_heavy_compare`
- Purpose: stress Layer C under sell-heavy and accounting-sensitive paths
- Headline:
  - fixed-point drift is larger than the target pack but still bounded

### Layer C Low Tail Compare

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_low_tail_compare`
- Purpose: extreme low-probability / many-outcome stress pack
- Headline:
  - exposed sponsor-solvency issues in the strong cohort-isolation framing
  - primary evidence that residual accounting, not just fixed-point arithmetic, is the hard edge case

### Layer C Parameter Sweep Core

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_parameter_sweep_core`
- Purpose: sweep `p_min` and safety-margin settings in the normal regime
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_parameter_sweep_core/parameter_summary.csv`

### Layer C Parameter Sweep Stress

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_parameter_sweep_stress`
- Purpose: sweep `p_min` and safety-margin settings in harder stress regimes
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/layer_c_parameter_sweep_stress/parameter_summary.csv`

## Fairness Exploration Before Reserve Reform

### Paper Quick

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_quick`
- Purpose: first integrated deterministic + Monte Carlo campaign for the active-LP model
- Headline:
  - mechanism looked viable
  - fairness tails became visible and measurable

### Paper Core

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_core`
- Purpose: heavier integrated campaign before reserve-based residual redesign
- Headline:
  - mechanics remained strong
  - fairness dispersion became the dominant economic question

### Adversarial Default

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/adversarial_default`
- Purpose: targeted adversarial search for fairness tails
- Headline:
  - strongest evidence that entry timing matters economically even when mechanics stay clean

## Reserve-Based Residual Release

### Reserve Residual Quick

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/reserve_residual_quick`
- Purpose: validate reserve-based residual release and claim-order safety
- Headline:
  - simple reserve release is claim-order safe
  - unweighted reserve residual systematically favors later LPs

### Time Weighted Reserve Quick

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/time_weighted_reserve_quick`
- Purpose: test fully linear time-weighted residual release
- Headline:
  - linear time weighting overcorrects sharply in favor of earlier LPs

## Residual Weight Calibration

### Residual Weight Sweep Core

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_core`
- Purpose: coarse sweep across flat, linear, concave, and affine time-weight rules
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_core/parameter_summary.csv`
- Headline:
  - the fairness-neutral region is near a mild affine premium, not strong linear weighting

### Residual Weight Sweep Fine

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_fine`
- Purpose: first affine refinement around the coarse-sweep crossover
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_fine/parameter_summary.csv`

### Residual Weight Sweep Tune

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_tune`
- Purpose: second affine refinement around the apparent zero-crossing
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_sweep_tune/parameter_summary.csv`
- Headline:
  - quick-pack crossover appears near `linear_lambda ≈ 0.025`

### Residual Weight Paper Candidates

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_candidates`
- Purpose: heavier paper-oriented comparison of the most plausible affine weights
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_candidates/parameter_summary.csv`
- Parameters:
  - `linear_lambda_0020`
  - `linear_lambda_0025`
  - `linear_lambda_0030`
- Headline:
  - all three are mechanically clean
  - the heavier run shifts the best candidate upward
  - `linear_lambda_0030` is the best of this batch, with mean fairness gap about `+0.00749`

### Residual Weight Paper Tight

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_tight`
- Purpose: tighter calibration around the heavier-run winner
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_tight/parameter_summary.csv`
- Parameters:
  - `linear_lambda_0031`
  - `linear_lambda_0032`
  - `linear_lambda_0033`
- Headline:
  - all three remain mechanically clean
  - the current fairness-neutral bracket is tightly bounded between `linear_lambda_0032` and `linear_lambda_0033`
  - `linear_lambda_0032` still leaves a small positive late-entry premium
  - `linear_lambda_0033` slightly overcorrects toward early LPs

### Residual Weight Paper Midpoint

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_midpoint`
- Purpose: midpoint calibration inside the tight paper bracket
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_midpoint/parameter_summary.csv`
- Parameters:
  - `linear_lambda_003225`
  - `linear_lambda_003250`
  - `linear_lambda_003275`
- Headline:
  - all three remain mechanically clean
  - `linear_lambda_003250` is the current best paper-default candidate
- `linear_lambda_003250` produces mean fairness gap about `+0.00012`
- this is the closest current result to entry-time neutrality on the paper-style calibration pack

### Residual Weight Train Event Clock

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_train_event_clock`
- Purpose: held-out calibration upgrade, event-step clock family, train split
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_train_event_clock/parameter_summary.csv`
- Headline:
  - best train winner is `linear_lambda_0025000`
  - even the best event-step candidate remains strongly duration-sensitive

### Residual Weight Test Event Clock

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_test_event_clock`
- Purpose: held-out calibration upgrade, event-step clock family, test split
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_test_event_clock/parameter_summary.csv`
- Headline:
  - best held-out event-step row still has mean fairness gap about `-0.18466`
  - mean absolute fairness gap about `0.21311`
  - duration-bucket max absolute mean gap about `0.53009`

### Residual Weight Train Normalized

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_train_normalized`
- Purpose: held-out calibration upgrade, normalized lifetime-exposure family, train split
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_train_normalized/parameter_summary.csv`
- Headline:
  - best train winner is `linear_lambda_normalized_0150000`
  - normalized candidates remain mechanically clean while substantially reducing duration drift

### Residual Weight Test Normalized

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_test_normalized`
- Purpose: held-out calibration upgrade, normalized lifetime-exposure family, test split
- Key file: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_test_normalized/parameter_summary.csv`
- Headline:
  - held-out winner `linear_lambda_normalized_0150000` keeps mean fairness gap near zero at about `-0.00677`
  - mean absolute fairness gap is about `0.03936`
  - duration-bucket max absolute mean gap is about `0.02227`
  - this is the current best protocol-facing residual-weight default

### Residual Weight Boundary Validation

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_boundary_validation`
- Purpose: compare the historical event-step default against the selected normalized default on the high-skew boundary packs
- Key files:
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_boundary_validation/boundary_summary.csv`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_boundary_validation/high_skew/linear_lambda_normalized_0150000/high_skew_threshold_summary.csv`
- Headline:
  - the normalized default preserves the high-skew late-entry gate
  - above entry-time max probability `0.8`, mean late-minus-early gap is about `-0.24449`
  - above `0.9`, mean gap is about `-0.32580`
  - no new mechanical failures appear in the Decimal reserve packs

## Suggested Paper Citation Pattern

For each figure or table in the paper, cite both:

- the narrative source directory, such as:
  `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_candidates/linear_lambda_0030`
- and the specific machine-readable file used to build the figure, such as:
  `/Users/andrei/Projects26/question/contracts/research/active_lp/output/residual_weight_paper_candidates/parameter_summary.csv`

## Derived Paper Artifacts

### Paper Artifacts

- Directory: `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts`
- Purpose: paper-facing derived artifacts built from the traced sweep outputs
- Key files:
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/residual_weight_calibration.svg`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/residual_weight_calibration_points.csv`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/paper_artifacts_overview.json`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/residual_rule_comparison.svg`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/layer_c_regime_comparison.svg`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/low_tail_failure_trace.svg`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/paper_tables.md`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/table_layer_b_equivalence.csv`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/table_residual_rule_comparison.csv`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/table_layer_c_regime_comparison.csv`
  - `/Users/andrei/Projects26/question/contracts/research/active_lp/output/paper_artifacts/table_low_tail_failure_trace.csv`
- Headline:
  - contains the current paper-facing calibration figure
  - preserves the original event-step calibration figure that highlights `linear_lambda_003250`
  - the residual-rule summary now includes both the historical event-step crossover and the current normalized default
  - the current protocol-facing residual-weight default is documented in the held-out normalized calibration outputs
  - now also contains a representative low-tail failure trace showing pooled reserve safety versus cohort-attribution failure
  - and machine-readable paper tables for the manuscript

## Minimum Files To Preserve

For every output directory intended for citation, preserve:

- `manifest.json`
- `results.jsonl`
- `aggregate.json`
- `report.md`
- `scenario_summary.csv`
- `fairness_extremes.csv`

These are the minimum trace artifacts needed to reconstruct paper tables, sanity-check claims, and rerun or audit the experiment family later.
