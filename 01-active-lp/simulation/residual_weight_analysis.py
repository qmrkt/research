from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.active_lp.adversarial_search import AdversarialSearchConfig, generate_adversarial_bundles
from research.active_lp.experiments import ExperimentRunner, write_experiment_results
from research.active_lp.monte_carlo import MonteCarloSweepConfig, generate_monte_carlo_bundles
from research.active_lp.reporting import aggregate_results, write_aggregated_report
from research.active_lp.scenarios import build_deterministic_scenarios
from research.active_lp.types import MechanismVariant

RESERVE_MECHANISMS = (
    MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
    MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL,
)


@dataclass(slots=True)
class ResidualWeightParameterSet:
    name: str
    scheme: str
    linear_lambda: Decimal = Decimal("1")


def default_residual_weight_parameter_sets() -> list[ResidualWeightParameterSet]:
    return [
        ResidualWeightParameterSet(name="flat", scheme="flat"),
        ResidualWeightParameterSet(name="linear", scheme="linear"),
        ResidualWeightParameterSet(name="sqrt", scheme="sqrt"),
        ResidualWeightParameterSet(name="log1p", scheme="log1p"),
        ResidualWeightParameterSet(name="linear_lambda_025", scheme="linear_lambda", linear_lambda=Decimal("0.25")),
        ResidualWeightParameterSet(name="linear_lambda_050", scheme="linear_lambda", linear_lambda=Decimal("0.50")),
    ]


def _apply_parameter_set(bundle, parameter_set: ResidualWeightParameterSet):
    return replace(
        bundle,
        config=replace(
            bundle.config,
            mechanisms=RESERVE_MECHANISMS,
            residual_weight_scheme=parameter_set.scheme,
            residual_linear_lambda=parameter_set.linear_lambda,
        ),
    )


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


def run_residual_weight_sweep(
    parameter_sets: list[ResidualWeightParameterSet] | None = None,
    *,
    monte_carlo_trials: int = 16,
    adversarial_limit: int | None = None,
    output_dir: str | Path | None = None,
    runner: ExperimentRunner | None = None,
) -> list[dict[str, object]]:
    experiment_runner = runner or ExperimentRunner()
    rows: list[dict[str, object]] = []
    out_dir = Path(output_dir) if output_dir is not None else None
    base_deterministic = build_deterministic_scenarios()

    for parameter_set in parameter_sets or default_residual_weight_parameter_sets():
        deterministic_bundles = [_apply_parameter_set(bundle, parameter_set) for bundle in base_deterministic]
        monte_carlo_bundles = [
            _apply_parameter_set(bundle, parameter_set)
            for bundle in generate_monte_carlo_bundles(
                MonteCarloSweepConfig(
                    name=f"{parameter_set.name}_mc",
                    seed=211,
                    num_trials=monte_carlo_trials,
                    mechanisms=RESERVE_MECHANISMS,
                )
            )
        ]
        adversarial_bundles = [
            _apply_parameter_set(bundle, parameter_set)
            for bundle in generate_adversarial_bundles(
                AdversarialSearchConfig(
                    name=f"{parameter_set.name}_adv",
                    mechanisms=RESERVE_MECHANISMS,
                )
            )
        ]
        if adversarial_limit is not None:
            adversarial_bundles = adversarial_bundles[:adversarial_limit]
        results = []
        results.extend(experiment_runner.run_bundles(deterministic_bundles, run_family="deterministic"))
        results.extend(experiment_runner.run_bundles(monte_carlo_bundles, run_family="monte_carlo"))
        if adversarial_bundles:
            results.extend(experiment_runner.run_bundles(adversarial_bundles, run_family="adversarial"))
        report = aggregate_results(results)

        fairness_values = [Decimal(str(row["fairness_gap_nav_per_deposit"])) for row in report.scenario_rows]
        positive_count = sum(value > 0 for value in fairness_values)
        negative_count = sum(value < 0 for value in fairness_values)
        near_zero_count = sum(abs(value) <= Decimal("0.02") for value in fairness_values)

        rows.append(
            {
                "name": parameter_set.name,
                "scheme": parameter_set.scheme,
                "linear_lambda": str(parameter_set.linear_lambda),
                "result_count": report.overview["result_count"],
                "price_continuity_pass_rate": report.overview["price_continuity_pass_rate"],
                "slippage_pass_rate": report.overview["slippage_pass_rate"],
                "solvency_pass_rate": report.overview["solvency_pass_rate"],
                "mean_fairness_gap_nav_per_deposit": report.overview["mean_fairness_gap_nav_per_deposit"],
                "max_abs_fairness_gap_nav_per_deposit": report.overview["max_abs_fairness_gap_nav_per_deposit"],
                "positive_fairness_rows": positive_count,
                "negative_fairness_rows": negative_count,
                "near_zero_fairness_rows": near_zero_count,
                "mean_divergence_max_nav_per_deposit_diff_vs_reference": report.overview[
                    "mean_divergence_max_nav_per_deposit_diff_vs_reference"
                ],
                "invariant_failure_count": report.overview["invariant_failure_count"],
            }
        )

        if out_dir is not None:
            param_dir = out_dir / parameter_set.name
            write_experiment_results(results, param_dir, manifest_label=parameter_set.name)
            write_aggregated_report(report, param_dir)

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(out_dir / "parameter_summary.csv", rows)
    return rows
