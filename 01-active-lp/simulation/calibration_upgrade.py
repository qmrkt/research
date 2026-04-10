from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.active_lp.adversarial_search import AdversarialSearchConfig, generate_adversarial_bundles
from research.active_lp.experiments import ExperimentResult, ExperimentRunner, write_experiment_results
from research.active_lp.high_skew_boundary import (
    build_high_skew_adversarial_config,
    build_high_skew_monte_carlo_config,
    summarize_high_skew_thresholds,
)
from research.active_lp.layer_c_analysis import build_layer_c_low_tail_config
from research.active_lp.monte_carlo import MonteCarloSweepConfig, generate_monte_carlo_bundles
from research.active_lp.reporting import AggregatedReport, aggregate_results, write_aggregated_report
from research.active_lp.residual_weight_analysis import ResidualWeightParameterSet
from research.active_lp.scenarios import (
    ScenarioBundle,
    build_deterministic_scenarios,
    restamp_bundle_duration,
)
from research.active_lp.sweep_presets import build_sweep_preset
from research.active_lp.types import MechanismVariant

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
TRAIN_EVENT_CLOCK_DIRNAME = "residual_weight_train_event_clock"
TEST_EVENT_CLOCK_DIRNAME = "residual_weight_test_event_clock"
TRAIN_NORMALIZED_DIRNAME = "residual_weight_train_normalized"
TEST_NORMALIZED_DIRNAME = "residual_weight_test_normalized"
BOUNDARY_DIRNAME = "residual_weight_boundary_validation"
ORDINARY_RUN_FAMILIES = frozenset({"monte_carlo", "adversarial"})
RESERVE_MECHANISMS = (
    MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
    MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL,
)
CURRENT_PROVISIONAL_EVENT_CLOCK = Decimal("0.03250")


def _lambda_slug(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.000001"))
    digits = format(quantized, "f").replace(".", "")
    return digits.rjust(6, "0")


def _event_clock_parameter_set(value: Decimal) -> ResidualWeightParameterSet:
    return ResidualWeightParameterSet(
        name=f"linear_lambda_{_lambda_slug(value)}",
        scheme="linear_lambda",
        linear_lambda=value,
    )


def _normalized_parameter_set(value: Decimal) -> ResidualWeightParameterSet:
    return ResidualWeightParameterSet(
        name=f"linear_lambda_normalized_{_lambda_slug(value)}",
        scheme="linear_lambda_normalized",
        linear_lambda=value,
    )


def default_event_clock_parameter_sets() -> tuple[ResidualWeightParameterSet, ...]:
    return tuple(
        _event_clock_parameter_set(value)
        for value in (
            Decimal("0.02500"),
            Decimal("0.03000"),
            Decimal("0.03250"),
            Decimal("0.03500"),
            Decimal("0.04000"),
        )
    )


def default_normalized_parameter_sets() -> tuple[ResidualWeightParameterSet, ...]:
    return tuple(
        _normalized_parameter_set(value)
        for value in (
            Decimal("0.050"),
            Decimal("0.075"),
            Decimal("0.100"),
            Decimal("0.125"),
            Decimal("0.150"),
            Decimal("0.175"),
            Decimal("0.200"),
            Decimal("0.225"),
            Decimal("0.250"),
        )
    )


@dataclass(slots=True)
class CalibrationUpgradeConfig:
    event_clock_parameter_sets: tuple[ResidualWeightParameterSet, ...] = default_event_clock_parameter_sets()
    normalized_parameter_sets: tuple[ResidualWeightParameterSet, ...] = default_normalized_parameter_sets()
    duration_buckets: tuple[tuple[str, int], ...] = (
        ("short", 12),
        ("medium", 48),
        ("long", 168),
    )
    train_monte_carlo_seed: int = 1100
    train_monte_carlo_trials: int = 64
    test_monte_carlo_seed: int = 2100
    test_monte_carlo_trials: int = 64
    adversarial_limit: int | None = None
    high_skew_monte_carlo_trials: int = 16
    high_skew_adversarial_limit: int | None = 24
    low_tail_monte_carlo_trials: int = 16
    low_tail_adversarial_limit: int | None = 24


@dataclass(slots=True)
class CalibrationSelection:
    parameter_set: ResidualWeightParameterSet
    train_row: dict[str, object]
    test_row: dict[str, object]


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


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in ("", None):
        return Decimal("0")
    return Decimal(str(value))


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def _quantile(values: list[Decimal], q: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _skew_bucket(entry_max_probability: Decimal) -> str:
    if entry_max_probability < Decimal("0.55"):
        return "lt_055"
    if entry_max_probability < Decimal("0.70"):
        return "055_to_070"
    if entry_max_probability < Decimal("0.85"):
        return "070_to_085"
    return "gte_085"


def _apply_parameter_set(bundle: ScenarioBundle, parameter_set: ResidualWeightParameterSet) -> ScenarioBundle:
    return replace(
        bundle,
        config=replace(
            bundle.config,
            mechanisms=RESERVE_MECHANISMS,
            residual_weight_scheme=parameter_set.scheme,
            residual_linear_lambda=parameter_set.linear_lambda,
        ),
    )


def _reference_ordinary_rows(report: AggregatedReport) -> list[dict[str, object]]:
    return [
        row
        for row in report.scenario_rows
        if row["mechanism"] == MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL.value
        and row["run_family"] in ORDINARY_RUN_FAMILIES
    ]


def _summary_row(
    *,
    pack_name: str,
    parameter_set: ResidualWeightParameterSet,
    report: AggregatedReport,
    subgroup_rows: list[dict[str, object]],
) -> dict[str, object]:
    objective_rows = _reference_ordinary_rows(report)
    fairness_gaps = [_to_decimal(row["fairness_gap_nav_per_deposit"]) for row in objective_rows]
    duration_abs = [
        abs(_to_decimal(row["mean_fairness_gap_nav_per_deposit"]))
        for row in subgroup_rows
        if row["grouping"] == "duration_bucket"
    ]
    outcome_abs = [
        abs(_to_decimal(row["mean_fairness_gap_nav_per_deposit"]))
        for row in subgroup_rows
        if row["grouping"] == "num_outcomes"
    ]
    skew_abs = [
        abs(_to_decimal(row["mean_fairness_gap_nav_per_deposit"]))
        for row in subgroup_rows
        if row["grouping"] == "skew_bucket"
    ]
    return {
        "pack": pack_name,
        "name": parameter_set.name,
        "scheme": parameter_set.scheme,
        "linear_lambda": str(parameter_set.linear_lambda),
        "ordinary_reference_rows": len(objective_rows),
        "result_count": report.overview["result_count"],
        "price_continuity_pass_rate": report.overview["price_continuity_pass_rate"],
        "slippage_pass_rate": report.overview["slippage_pass_rate"],
        "solvency_pass_rate": report.overview["solvency_pass_rate"],
        "invariant_failure_count": report.overview["invariant_failure_count"],
        "mean_gap_nav_per_deposit": str(_mean(fairness_gaps)),
        "mean_abs_gap_nav_per_deposit": str(_mean([abs(gap) for gap in fairness_gaps])),
        "median_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.5"))),
        "p05_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.05"))),
        "p95_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.95"))),
        "worst_positive_gap_nav_per_deposit": str(max(fairness_gaps, default=Decimal("0"))),
        "worst_negative_gap_nav_per_deposit": str(min(fairness_gaps, default=Decimal("0"))),
        "duration_max_abs_mean_gap": str(max(duration_abs, default=Decimal("0"))),
        "outcome_max_abs_mean_gap": str(max(outcome_abs, default=Decimal("0"))),
        "skew_max_abs_mean_gap": str(max(skew_abs, default=Decimal("0"))),
        "mean_divergence_max_quote_diff_vs_reference": report.overview["mean_divergence_max_quote_diff_vs_reference"],
        "mean_divergence_max_nav_per_deposit_diff_vs_reference": report.overview[
            "mean_divergence_max_nav_per_deposit_diff_vs_reference"
        ],
    }


def _subgroup_rows(
    *,
    pack_name: str,
    parameter_set: ResidualWeightParameterSet,
    report: AggregatedReport,
) -> list[dict[str, object]]:
    rows = _reference_ordinary_rows(report)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        keys = {
            ("duration_bucket", str(row["duration_bucket"] or "unknown")),
            ("num_outcomes", str(row["num_outcomes"])),
            ("skew_bucket", _skew_bucket(_to_decimal(row["entry_max_probability"]))),
        }
        for grouping, key in keys:
            grouped.setdefault((grouping, key), []).append(row)

    summary_rows: list[dict[str, object]] = []
    for (grouping, key), subset in sorted(grouped.items()):
        fairness_gaps = [_to_decimal(row["fairness_gap_nav_per_deposit"]) for row in subset]
        summary_rows.append(
            {
                "pack": pack_name,
                "name": parameter_set.name,
                "scheme": parameter_set.scheme,
                "linear_lambda": str(parameter_set.linear_lambda),
                "grouping": grouping,
                "group_value": key,
                "scenario_count": len(subset),
                "mean_fairness_gap_nav_per_deposit": str(_mean(fairness_gaps)),
                "mean_abs_fairness_gap_nav_per_deposit": str(_mean([abs(gap) for gap in fairness_gaps])),
                "p05_fairness_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.05"))),
                "p95_fairness_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.95"))),
                "worst_positive_gap_nav_per_deposit": str(max(fairness_gaps, default=Decimal("0"))),
                "worst_negative_gap_nav_per_deposit": str(min(fairness_gaps, default=Decimal("0"))),
            }
        )
    return summary_rows


def _selection_sort_key(row: dict[str, object]) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    return (
        abs(_to_decimal(row["mean_gap_nav_per_deposit"])),
        _to_decimal(row["mean_abs_gap_nav_per_deposit"]),
        _to_decimal(row["duration_max_abs_mean_gap"]),
        _to_decimal(row["outcome_max_abs_mean_gap"]),
        _to_decimal(row["skew_max_abs_mean_gap"]),
        _to_decimal(row["linear_lambda"]),
    )


def _ordinary_monte_carlo_config(*, name: str, seed: int, num_trials: int) -> MonteCarloSweepConfig:
    preset = build_sweep_preset("paper_quick").monte_carlo
    return replace(
        preset,
        name=name,
        seed=seed,
        num_trials=num_trials,
        mechanisms=RESERVE_MECHANISMS,
    )


def _ordinary_adversarial_config(*, name: str) -> AdversarialSearchConfig:
    preset = build_sweep_preset("paper_quick").adversarial
    if preset is None:
        raise ValueError("paper_quick preset must define an adversarial config")
    return replace(
        preset,
        name=name,
        mechanisms=RESERVE_MECHANISMS,
    )


def _duration_variants(
    bundles: list[ScenarioBundle],
    *,
    duration_buckets: tuple[tuple[str, int], ...],
    split: str,
) -> list[ScenarioBundle]:
    variants: list[ScenarioBundle] = []
    for bundle in bundles:
        for duration_bucket, duration_steps in duration_buckets:
            variants.append(
                restamp_bundle_duration(
                    bundle,
                    duration_steps=duration_steps,
                    duration_bucket=duration_bucket,
                    split=split,
                    name_suffix=f"{split}_{duration_bucket}",
                )
            )
    return variants


def _prepare_deterministic_bundles() -> list[ScenarioBundle]:
    return list(build_deterministic_scenarios())


def _prepare_monte_carlo_bundles(
    *,
    split: str,
    seed: int,
    num_trials: int,
    duration_buckets: tuple[tuple[str, int], ...],
) -> list[ScenarioBundle]:
    base = generate_monte_carlo_bundles(
        _ordinary_monte_carlo_config(
            name=f"calibration_{split}_mc",
            seed=seed,
            num_trials=num_trials,
        )
    )
    return _duration_variants(base, duration_buckets=duration_buckets, split=split)


def _prepare_adversarial_bundles(*, split: str, adversarial_limit: int | None) -> list[ScenarioBundle]:
    base = generate_adversarial_bundles(_ordinary_adversarial_config(name=f"calibration_{split}_adv"))
    chosen = [bundle for index, bundle in enumerate(base) if (index % 2 == 0) == (split == "train")]
    if adversarial_limit is not None:
        chosen = chosen[:adversarial_limit]
    return [
        replace(bundle, config=replace(bundle.config, split=split))
        for bundle in chosen
    ]


def _run_parameter_pack(
    *,
    pack_name: str,
    parameter_sets: tuple[ResidualWeightParameterSet, ...],
    deterministic_bundles: list[ScenarioBundle],
    monte_carlo_bundles: list[ScenarioBundle],
    adversarial_bundles: list[ScenarioBundle],
    output_dir: Path,
    runner: ExperimentRunner,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, object]] = []
    subgroup_rows: list[dict[str, object]] = []

    for parameter_set in parameter_sets:
        param_dir = output_dir / parameter_set.name
        results: list[ExperimentResult] = []
        if deterministic_bundles:
            results.extend(
                runner.run_bundles(
                    [_apply_parameter_set(bundle, parameter_set) for bundle in deterministic_bundles],
                    run_family="deterministic",
                )
            )
        if monte_carlo_bundles:
            results.extend(
                runner.run_bundles(
                    [_apply_parameter_set(bundle, parameter_set) for bundle in monte_carlo_bundles],
                    run_family="monte_carlo",
                )
            )
        if adversarial_bundles:
            results.extend(
                runner.run_bundles(
                    [_apply_parameter_set(bundle, parameter_set) for bundle in adversarial_bundles],
                    run_family="adversarial",
                )
            )

        write_experiment_results(results, param_dir, manifest_label=parameter_set.name)
        report = aggregate_results(results)
        write_aggregated_report(report, param_dir)

        parameter_subgroups = _subgroup_rows(pack_name=pack_name, parameter_set=parameter_set, report=report)
        subgroup_rows.extend(parameter_subgroups)
        summary_rows.append(
            _summary_row(
                pack_name=pack_name,
                parameter_set=parameter_set,
                report=report,
                subgroup_rows=parameter_subgroups,
            )
        )

    _write_csv(output_dir / "parameter_summary.csv", summary_rows)
    _write_csv(output_dir / "subgroup_summary.csv", subgroup_rows)
    return summary_rows, subgroup_rows


def _selected_row(
    rows: list[dict[str, object]],
    parameter_sets: tuple[ResidualWeightParameterSet, ...],
) -> tuple[ResidualWeightParameterSet, dict[str, object]]:
    by_name = {parameter_set.name: parameter_set for parameter_set in parameter_sets}
    selected = min(rows, key=_selection_sort_key)
    return by_name[str(selected["name"])], selected


def _named_failure_counts(results: list[ExperimentResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for failure in result.evaluation.exact_vs_simplified_divergence.get("invariant_failures", []):
            name = str(failure.get("name", "unknown"))
            counts[name] = counts.get(name, 0) + 1
    return counts


def _boundary_low_tail_bundles(
    *,
    monte_carlo_trials: int,
    adversarial_limit: int | None,
) -> tuple[list[ScenarioBundle], list[ScenarioBundle]]:
    config = build_layer_c_low_tail_config()
    monte_carlo = generate_monte_carlo_bundles(
        replace(
            config.monte_carlo,
            mechanisms=RESERVE_MECHANISMS,
            num_trials=monte_carlo_trials,
            name="calibration_low_tail_mc",
        )
    )
    adversarial = generate_adversarial_bundles(
        replace(
            config.adversarial,
            mechanisms=RESERVE_MECHANISMS,
            name="calibration_low_tail_adv",
        )
    )
    if adversarial_limit is not None:
        adversarial = adversarial[:adversarial_limit]
    return monte_carlo, adversarial


def _run_boundary_pack(
    *,
    family_name: str,
    parameter_set: ResidualWeightParameterSet,
    monte_carlo_bundles: list[ScenarioBundle],
    adversarial_bundles: list[ScenarioBundle],
    output_dir: Path,
    runner: ExperimentRunner,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ExperimentResult] = []
    if monte_carlo_bundles:
        results.extend(
            runner.run_bundles(
                [_apply_parameter_set(bundle, parameter_set) for bundle in monte_carlo_bundles],
                run_family="monte_carlo",
            )
        )
    if adversarial_bundles:
        results.extend(
            runner.run_bundles(
                [_apply_parameter_set(bundle, parameter_set) for bundle in adversarial_bundles],
                run_family="adversarial",
            )
        )
    write_experiment_results(results, output_dir, manifest_label=f"{family_name}_{parameter_set.name}")
    report = aggregate_results(results)
    report_paths = write_aggregated_report(report, output_dir)

    summary_row = {
        "family": family_name,
        "name": parameter_set.name,
        "scheme": parameter_set.scheme,
        "linear_lambda": str(parameter_set.linear_lambda),
        "result_count": report.overview["result_count"],
        "price_continuity_pass_rate": report.overview["price_continuity_pass_rate"],
        "slippage_pass_rate": report.overview["slippage_pass_rate"],
        "solvency_pass_rate": report.overview["solvency_pass_rate"],
        "mean_gap_nav_per_deposit": report.overview["mean_fairness_gap_nav_per_deposit"],
        "mean_abs_gap_nav_per_deposit": report.overview["mean_abs_fairness_gap_nav_per_deposit"],
        "worst_positive_gap_nav_per_deposit": report.overview["worst_positive_fairness_gap_nav_per_deposit"],
        "worst_negative_gap_nav_per_deposit": report.overview["worst_negative_fairness_gap_nav_per_deposit"],
        "invariant_failure_count": report.overview["invariant_failure_count"],
    }
    named_failures = _named_failure_counts(results)
    for name, count in sorted(named_failures.items()):
        summary_row[f"failure_{name}"] = count

    extra_paths: dict[str, Path] = {}
    if family_name == "high_skew":
        threshold_rows = summarize_high_skew_thresholds(results)
        threshold_path = output_dir / "high_skew_threshold_summary.csv"
        _write_csv(threshold_path, threshold_rows)
        extra_paths["threshold_csv"] = threshold_path

    return {
        "summary_row": summary_row,
        "report_paths": report_paths,
        "extra_paths": extra_paths,
    }


def _selection_summary_rows(
    *,
    event_clock_selection: CalibrationSelection,
    normalized_selection: CalibrationSelection,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for mode, selection in (
        ("event_clock", event_clock_selection),
        ("normalized", normalized_selection),
    ):
        train_row = selection.train_row
        test_row = selection.test_row
        rows.append(
            {
                "mode": mode,
                "name": selection.parameter_set.name,
                "scheme": selection.parameter_set.scheme,
                "linear_lambda": str(selection.parameter_set.linear_lambda),
                "train_mean_gap_nav_per_deposit": train_row["mean_gap_nav_per_deposit"],
                "train_mean_abs_gap_nav_per_deposit": train_row["mean_abs_gap_nav_per_deposit"],
                "train_duration_max_abs_mean_gap": train_row["duration_max_abs_mean_gap"],
                "test_mean_gap_nav_per_deposit": test_row["mean_gap_nav_per_deposit"],
                "test_mean_abs_gap_nav_per_deposit": test_row["mean_abs_gap_nav_per_deposit"],
                "test_duration_max_abs_mean_gap": test_row["duration_max_abs_mean_gap"],
            }
        )
    return rows


def _build_root_report(
    *,
    event_clock_selection: CalibrationSelection,
    normalized_selection: CalibrationSelection,
    boundary_rows: list[dict[str, object]],
) -> str:
    lines = [
        "# Calibration Upgrade Result Snapshot",
        "",
        "## Selected Parameters",
        "",
        f"- Event-clock train winner: `{event_clock_selection.parameter_set.name}` (`lambda={event_clock_selection.parameter_set.linear_lambda}`)",
        f"- Normalized train winner: `{normalized_selection.parameter_set.name}` (`lambda={normalized_selection.parameter_set.linear_lambda}`)",
        "",
        "## Held-out Comparison",
        "",
        f"- Event-clock held-out mean gap: {event_clock_selection.test_row['mean_gap_nav_per_deposit']}",
        f"- Event-clock held-out mean absolute gap: {event_clock_selection.test_row['mean_abs_gap_nav_per_deposit']}",
        f"- Event-clock held-out duration max abs mean gap: {event_clock_selection.test_row['duration_max_abs_mean_gap']}",
        f"- Normalized held-out mean gap: {normalized_selection.test_row['mean_gap_nav_per_deposit']}",
        f"- Normalized held-out mean absolute gap: {normalized_selection.test_row['mean_abs_gap_nav_per_deposit']}",
        f"- Normalized held-out duration max abs mean gap: {normalized_selection.test_row['duration_max_abs_mean_gap']}",
        "",
        "## Boundary Validation",
        "",
    ]
    for row in boundary_rows:
        lines.append(
            f"- `{row['family']}` / `{row['name']}`: mean_gap={row['mean_gap_nav_per_deposit']}, "
            f"mean_abs_gap={row['mean_abs_gap_nav_per_deposit']}, invariant_failures={row['invariant_failure_count']}"
        )
    lines.append("")
    return "\n".join(lines)


def run_calibration_upgrade(
    *,
    config: CalibrationUpgradeConfig | None = None,
    output_root: str | Path | None = None,
    runner: ExperimentRunner | None = None,
) -> dict[str, Path]:
    upgrade_config = config or CalibrationUpgradeConfig()
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    experiment_runner = runner or ExperimentRunner()

    deterministic_bundles = _prepare_deterministic_bundles()
    train_mc_bundles = _prepare_monte_carlo_bundles(
        split="train",
        seed=upgrade_config.train_monte_carlo_seed,
        num_trials=upgrade_config.train_monte_carlo_trials,
        duration_buckets=upgrade_config.duration_buckets,
    )
    test_mc_bundles = _prepare_monte_carlo_bundles(
        split="test",
        seed=upgrade_config.test_monte_carlo_seed,
        num_trials=upgrade_config.test_monte_carlo_trials,
        duration_buckets=upgrade_config.duration_buckets,
    )
    train_adv_bundles = _prepare_adversarial_bundles(
        split="train",
        adversarial_limit=upgrade_config.adversarial_limit,
    )
    test_adv_bundles = _prepare_adversarial_bundles(
        split="test",
        adversarial_limit=upgrade_config.adversarial_limit,
    )

    train_event_rows, _ = _run_parameter_pack(
        pack_name="train_event_clock",
        parameter_sets=upgrade_config.event_clock_parameter_sets,
        deterministic_bundles=deterministic_bundles,
        monte_carlo_bundles=train_mc_bundles,
        adversarial_bundles=train_adv_bundles,
        output_dir=root / TRAIN_EVENT_CLOCK_DIRNAME,
        runner=experiment_runner,
    )
    test_event_rows, _ = _run_parameter_pack(
        pack_name="test_event_clock",
        parameter_sets=upgrade_config.event_clock_parameter_sets,
        deterministic_bundles=deterministic_bundles,
        monte_carlo_bundles=test_mc_bundles,
        adversarial_bundles=test_adv_bundles,
        output_dir=root / TEST_EVENT_CLOCK_DIRNAME,
        runner=experiment_runner,
    )
    train_normalized_rows, _ = _run_parameter_pack(
        pack_name="train_normalized",
        parameter_sets=upgrade_config.normalized_parameter_sets,
        deterministic_bundles=deterministic_bundles,
        monte_carlo_bundles=train_mc_bundles,
        adversarial_bundles=train_adv_bundles,
        output_dir=root / TRAIN_NORMALIZED_DIRNAME,
        runner=experiment_runner,
    )
    test_normalized_rows, _ = _run_parameter_pack(
        pack_name="test_normalized",
        parameter_sets=upgrade_config.normalized_parameter_sets,
        deterministic_bundles=deterministic_bundles,
        monte_carlo_bundles=test_mc_bundles,
        adversarial_bundles=test_adv_bundles,
        output_dir=root / TEST_NORMALIZED_DIRNAME,
        runner=experiment_runner,
    )

    selected_event_param, selected_event_train = _selected_row(
        train_event_rows,
        upgrade_config.event_clock_parameter_sets,
    )
    selected_normalized_param, selected_normalized_train = _selected_row(
        train_normalized_rows,
        upgrade_config.normalized_parameter_sets,
    )
    selected_event_test = next(
        row for row in test_event_rows if row["name"] == selected_event_param.name
    )
    selected_normalized_test = next(
        row for row in test_normalized_rows if row["name"] == selected_normalized_param.name
    )

    event_clock_selection = CalibrationSelection(
        parameter_set=selected_event_param,
        train_row=selected_event_train,
        test_row=selected_event_test,
    )
    normalized_selection = CalibrationSelection(
        parameter_set=selected_normalized_param,
        train_row=selected_normalized_train,
        test_row=selected_normalized_test,
    )

    boundary_dir = root / BOUNDARY_DIRNAME
    high_skew_mc = generate_monte_carlo_bundles(
        build_high_skew_monte_carlo_config(num_trials=upgrade_config.high_skew_monte_carlo_trials)
    )
    high_skew_adv = generate_adversarial_bundles(build_high_skew_adversarial_config())
    if upgrade_config.high_skew_adversarial_limit is not None:
        high_skew_adv = high_skew_adv[: upgrade_config.high_skew_adversarial_limit]

    low_tail_mc, low_tail_adv = _boundary_low_tail_bundles(
        monte_carlo_trials=upgrade_config.low_tail_monte_carlo_trials,
        adversarial_limit=upgrade_config.low_tail_adversarial_limit,
    )

    provisional_event_clock = _event_clock_parameter_set(CURRENT_PROVISIONAL_EVENT_CLOCK)
    boundary_rows: list[dict[str, object]] = []
    boundary_outputs: dict[str, Path] = {}
    for family_name, monte_carlo_bundles, adversarial_bundles in (
        ("high_skew", high_skew_mc, high_skew_adv),
        ("low_tail", low_tail_mc, low_tail_adv),
    ):
        for parameter_set in (provisional_event_clock, selected_normalized_param):
            family_dir = boundary_dir / family_name / parameter_set.name
            outputs = _run_boundary_pack(
                family_name=family_name,
                parameter_set=parameter_set,
                monte_carlo_bundles=monte_carlo_bundles,
                adversarial_bundles=adversarial_bundles,
                output_dir=family_dir,
                runner=experiment_runner,
            )
            boundary_rows.append(outputs["summary_row"])
            if "report_md" in outputs["report_paths"]:
                boundary_outputs[f"{family_name}_{parameter_set.name}_report_md"] = outputs["report_paths"]["report_md"]
            for key, path in outputs["extra_paths"].items():
                boundary_outputs[f"{family_name}_{parameter_set.name}_{key}"] = path

    selection_rows = _selection_summary_rows(
        event_clock_selection=event_clock_selection,
        normalized_selection=normalized_selection,
    )
    selection_json = {
        "event_clock": {
            "parameter": {
                "name": event_clock_selection.parameter_set.name,
                "scheme": event_clock_selection.parameter_set.scheme,
                "linear_lambda": str(event_clock_selection.parameter_set.linear_lambda),
            },
            "train": event_clock_selection.train_row,
            "test": event_clock_selection.test_row,
        },
        "normalized": {
            "parameter": {
                "name": normalized_selection.parameter_set.name,
                "scheme": normalized_selection.parameter_set.scheme,
                "linear_lambda": str(normalized_selection.parameter_set.linear_lambda),
            },
            "train": normalized_selection.train_row,
            "test": normalized_selection.test_row,
        },
    }

    selection_summary_csv = root / "lambda_selection_summary.csv"
    selection_summary_json = root / "lambda_selection_summary.json"
    boundary_summary_csv = boundary_dir / "boundary_summary.csv"
    report_md = root / "calibration_upgrade_report.md"

    _write_csv(selection_summary_csv, selection_rows)
    selection_summary_json.write_text(json.dumps(selection_json, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(boundary_summary_csv, boundary_rows)
    report_md.write_text(
        _build_root_report(
            event_clock_selection=event_clock_selection,
            normalized_selection=normalized_selection,
            boundary_rows=boundary_rows,
        ),
        encoding="utf-8",
    )

    return {
        "train_event_clock_dir": root / TRAIN_EVENT_CLOCK_DIRNAME,
        "test_event_clock_dir": root / TEST_EVENT_CLOCK_DIRNAME,
        "train_normalized_dir": root / TRAIN_NORMALIZED_DIRNAME,
        "test_normalized_dir": root / TEST_NORMALIZED_DIRNAME,
        "boundary_dir": boundary_dir,
        "selection_summary_csv": selection_summary_csv,
        "selection_summary_json": selection_summary_json,
        "boundary_summary_csv": boundary_summary_csv,
        "report_md": report_md,
        **boundary_outputs,
    }
