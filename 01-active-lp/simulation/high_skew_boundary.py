from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.active_lp.adversarial_search import AdversarialSearchConfig, generate_adversarial_bundles
from research.active_lp.experiments import ExperimentResult, ExperimentRunner, write_experiment_results
from research.active_lp.monte_carlo import MonteCarloSweepConfig, generate_monte_carlo_bundles
from research.active_lp.reporting import aggregate_results, write_aggregated_report
from research.active_lp.scenarios import ScenarioBundle
from research.active_lp.types import MechanismVariant

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DEFAULT_LINEAR_LAMBDA = Decimal("0.03250")
HIGH_SKEW_MECHANISMS = (
    MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
    MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL,
)


@dataclass(slots=True)
class HighSkewBoundaryConfig:
    linear_lambda: Decimal = DEFAULT_LINEAR_LAMBDA
    monte_carlo_trials: int = 16
    adversarial_limit: int | None = None


def build_high_skew_monte_carlo_config(*, num_trials: int = 16) -> MonteCarloSweepConfig:
    return MonteCarloSweepConfig(
        name="high_skew_boundary_mc",
        seed=109,
        num_trials=num_trials,
        num_outcomes_choices=(16, 32, 64),
        initial_depth_choices=(Decimal("100"),),
        fee_bps_choices=(Decimal("100"),),
        protocol_fee_bps_choices=(Decimal("25"),),
        lp_delta_b_choices=(Decimal("20"), Decimal("50")),
        trade_count_range=(1, 2),
        active_lp_entry_count_choices=(1,),
        max_trade_share_choices=(Decimal("50"), Decimal("100"), Decimal("250"), Decimal("500")),
        sell_probability=0.0,
        cancel_probability=0.0,
        mechanisms=HIGH_SKEW_MECHANISMS,
    )


def build_high_skew_adversarial_config() -> AdversarialSearchConfig:
    return AdversarialSearchConfig(
        name="high_skew_boundary_adv",
        num_outcomes_choices=(16, 32, 64),
        initial_depth_choices=(Decimal("100"),),
        fee_bps_choices=(Decimal("100"),),
        protocol_fee_bps_choices=(Decimal("25"),),
        late_delta_b_choices=(Decimal("20"), Decimal("50")),
        pre_entry_shares_choices=(Decimal("50"), Decimal("100"), Decimal("250"), Decimal("500")),
        post_entry_shares_choices=(Decimal("0"),),
        counterflow_ratio_choices=(Decimal("0"),),
        post_entry_modes=("idle",),
        winner_policies=("favorite",),
        mechanisms=HIGH_SKEW_MECHANISMS,
    )


def _with_affine_residual(bundle: ScenarioBundle, linear_lambda: Decimal) -> ScenarioBundle:
    return replace(
        bundle,
        config=replace(
            bundle.config,
            mechanisms=HIGH_SKEW_MECHANISMS,
            residual_weight_scheme="linear_lambda",
            residual_linear_lambda=linear_lambda,
            precision_mode="decimal",
        ),
    )


def _reference_rows(results: list[ExperimentResult]) -> list[dict[str, Decimal]]:
    rows: list[dict[str, Decimal]] = []
    for result in results:
        if result.mechanism is not MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL:
            continue
        entries = result.evaluation.price_continuity.get("entries", [])
        fairness_rows = result.evaluation.lp_fairness_by_entry_time.get("rows", [])
        if not entries or len(fairness_rows) < 2:
            continue
        max_entry_probability = max(
            max(Decimal(str(price)) for price in entry.get("before", []))
            for entry in entries
        )
        fairness_gap = Decimal(str(fairness_rows[-1]["nav_per_deposit"])) - Decimal(
            str(fairness_rows[0]["nav_per_deposit"])
        )
        rows.append(
            {
                "max_entry_probability": max_entry_probability,
                "fairness_gap_nav_per_deposit": fairness_gap,
            }
        )
    return rows


def summarize_high_skew_thresholds(
    results: list[ExperimentResult],
    *,
    thresholds: tuple[Decimal, ...] = (Decimal("0.8"), Decimal("0.9")),
) -> list[dict[str, object]]:
    rows = _reference_rows(results)
    summary_rows: list[dict[str, object]] = []
    for threshold in thresholds:
        subset = [row for row in rows if row["max_entry_probability"] >= threshold]
        if not subset:
            continue
        summary_rows.append(
            {
                "threshold": str(threshold),
                "scenario_count": len(subset),
                "mean_max_entry_probability": str(
                    sum(row["max_entry_probability"] for row in subset) / len(subset)
                ),
                "max_entry_probability": str(max(row["max_entry_probability"] for row in subset)),
                "mean_fairness_gap_nav_per_deposit": str(
                    sum(row["fairness_gap_nav_per_deposit"] for row in subset) / len(subset)
                ),
                "min_fairness_gap_nav_per_deposit": str(
                    min(row["fairness_gap_nav_per_deposit"] for row in subset)
                ),
                "max_fairness_gap_nav_per_deposit": str(
                    max(row["fairness_gap_nav_per_deposit"] for row in subset)
                ),
            }
        )
    return summary_rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_high_skew_boundary_analysis(
    *,
    config: HighSkewBoundaryConfig | None = None,
    output_dir: str | Path | None = None,
    runner: ExperimentRunner | None = None,
) -> dict[str, Path]:
    analysis_config = config or HighSkewBoundaryConfig()
    out_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_ROOT / "high_skew_boundary_calibrated"
    out_dir.mkdir(parents=True, exist_ok=True)

    experiment_runner = runner or ExperimentRunner()
    mc_bundles = [
        _with_affine_residual(bundle, analysis_config.linear_lambda)
        for bundle in generate_monte_carlo_bundles(
            build_high_skew_monte_carlo_config(num_trials=analysis_config.monte_carlo_trials)
        )
    ]
    adv_bundles = generate_adversarial_bundles(build_high_skew_adversarial_config())
    if analysis_config.adversarial_limit is not None:
        adv_bundles = adv_bundles[: analysis_config.adversarial_limit]
    adv_bundles = [_with_affine_residual(bundle, analysis_config.linear_lambda) for bundle in adv_bundles]

    results: list[ExperimentResult] = []
    results.extend(experiment_runner.run_bundles(mc_bundles, run_family="monte_carlo"))
    results.extend(experiment_runner.run_bundles(adv_bundles, run_family="adversarial"))

    outputs = write_experiment_results(results, out_dir, manifest_label="high_skew_boundary_calibrated")
    report = aggregate_results(results)
    report_paths = write_aggregated_report(report, out_dir)

    threshold_rows = summarize_high_skew_thresholds(results)
    threshold_path = out_dir / "high_skew_threshold_summary.csv"
    _write_csv(threshold_path, threshold_rows)

    return {
        **outputs,
        **report_paths,
        "high_skew_threshold_summary_csv": threshold_path,
    }
