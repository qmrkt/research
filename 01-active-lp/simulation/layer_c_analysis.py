from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.active_lp.adversarial_search import AdversarialSearchConfig, generate_adversarial_bundles
from research.active_lp.experiments import ExperimentResult, ExperimentRunner, write_experiment_results
from research.active_lp.figures import write_figure_pack
from research.active_lp.layer_c_fixed_point import FP_ENTRY_SAFETY_MARGIN, FP_PRICE_FLOOR
from research.active_lp.monte_carlo import MonteCarloSweepConfig, generate_monte_carlo_bundles
from research.active_lp.reporting import AggregatedReport, aggregate_results, write_aggregated_report
from research.active_lp.scenarios import (
    ScenarioBundle,
    build_deterministic_scenarios,
    deterministic_scenario_names,
)
from research.active_lp.types import MechanismVariant

LAYER_C_MECHANISMS = (
    MechanismVariant.REFERENCE_PARALLEL_LMSR,
    MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT,
)
LAYER_C_DETERMINISTIC_NAMES = tuple(
    name for name in deterministic_scenario_names() if name != "reserve_residual_claim_ordering"
)


@dataclass(slots=True)
class LayerCParameterSet:
    name: str
    price_floor_fp: int = FP_PRICE_FLOOR
    entry_safety_margin: int = FP_ENTRY_SAFETY_MARGIN


@dataclass(slots=True)
class LayerCTargetConfig:
    parameter_set: LayerCParameterSet
    monte_carlo: MonteCarloSweepConfig
    adversarial: AdversarialSearchConfig
    deterministic_names: tuple[str, ...] | None = None
    adversarial_limit: int | None = None


def build_layer_c_target_config(
    parameter_set: LayerCParameterSet | None = None,
    *,
    deterministic_names: tuple[str, ...] | None = None,
    adversarial_limit: int | None = None,
) -> LayerCTargetConfig:
    return LayerCTargetConfig(
        parameter_set=parameter_set or LayerCParameterSet(name="default"),
        deterministic_names=deterministic_names,
        adversarial_limit=adversarial_limit,
        monte_carlo=MonteCarloSweepConfig(
            name="layer_c_mc",
            seed=41,
            num_trials=24,
            num_outcomes_choices=(3, 5, 8),
            initial_depth_choices=(Decimal("80"), Decimal("100"), Decimal("140")),
            fee_bps_choices=(Decimal("50"), Decimal("100"), Decimal("150")),
            protocol_fee_bps_choices=(Decimal("0"), Decimal("25")),
            lp_delta_b_choices=(Decimal("20"), Decimal("35"), Decimal("50")),
            trade_count_range=(5, 9),
            active_lp_entry_count_choices=(1, 2, 3),
            sell_probability=0.25,
            cancel_probability=0.15,
            mechanisms=LAYER_C_MECHANISMS,
        ),
        adversarial=AdversarialSearchConfig(
            name="layer_c_adv",
            num_outcomes_choices=(3, 8),
            initial_depth_choices=(Decimal("100"),),
            fee_bps_choices=(Decimal("100"),),
            protocol_fee_bps_choices=(Decimal("25"),),
            late_delta_b_choices=(Decimal("20"), Decimal("50")),
            pre_entry_shares_choices=(Decimal("6"), Decimal("20")),
            post_entry_shares_choices=(Decimal("0"), Decimal("12")),
            counterflow_ratio_choices=(Decimal("0"), Decimal("0.25")),
            post_entry_modes=("idle", "reversion"),
            winner_policies=("favorite", "hedge"),
            mechanisms=LAYER_C_MECHANISMS,
        ),
    )


def build_layer_c_sell_heavy_config(
    parameter_set: LayerCParameterSet | None = None,
    *,
    deterministic_names: tuple[str, ...] | None = None,
    adversarial_limit: int | None = None,
) -> LayerCTargetConfig:
    return LayerCTargetConfig(
        parameter_set=parameter_set or LayerCParameterSet(name="default"),
        deterministic_names=deterministic_names,
        adversarial_limit=adversarial_limit,
        monte_carlo=MonteCarloSweepConfig(
            name="layer_c_sell_heavy_mc",
            seed=73,
            num_trials=32,
            num_outcomes_choices=(3, 5, 8),
            initial_depth_choices=(Decimal("80"), Decimal("100"), Decimal("140")),
            fee_bps_choices=(Decimal("50"), Decimal("100"), Decimal("150")),
            protocol_fee_bps_choices=(Decimal("0"), Decimal("25")),
            lp_delta_b_choices=(Decimal("20"), Decimal("35"), Decimal("50"), Decimal("70")),
            trade_count_range=(8, 12),
            active_lp_entry_count_choices=(2, 3, 4),
            sell_probability=0.55,
            cancel_probability=0.10,
            mechanisms=LAYER_C_MECHANISMS,
        ),
        adversarial=AdversarialSearchConfig(
            name="layer_c_sell_heavy_adv",
            num_outcomes_choices=(3, 8),
            initial_depth_choices=(Decimal("100"),),
            fee_bps_choices=(Decimal("100"),),
            protocol_fee_bps_choices=(Decimal("25"),),
            late_delta_b_choices=(Decimal("20"), Decimal("50")),
            pre_entry_shares_choices=(Decimal("20"),),
            post_entry_shares_choices=(Decimal("12"),),
            counterflow_ratio_choices=(Decimal("0"), Decimal("0.25")),
            post_entry_modes=("reversion",),
            winner_policies=("favorite", "hedge"),
            mechanisms=LAYER_C_MECHANISMS,
        ),
    )


def build_layer_c_low_tail_config(
    parameter_set: LayerCParameterSet | None = None,
    *,
    deterministic_names: tuple[str, ...] | None = tuple(),
    adversarial_limit: int | None = None,
) -> LayerCTargetConfig:
    return LayerCTargetConfig(
        parameter_set=parameter_set or LayerCParameterSet(name="default"),
        deterministic_names=deterministic_names,
        adversarial_limit=adversarial_limit,
        monte_carlo=MonteCarloSweepConfig(
            name="layer_c_low_tail_mc",
            seed=109,
            num_trials=16,
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
            mechanisms=LAYER_C_MECHANISMS,
        ),
        adversarial=AdversarialSearchConfig(
            name="layer_c_low_tail_adv",
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
            mechanisms=LAYER_C_MECHANISMS,
        ),
    )


def _with_layer_c_mechanisms(bundle: ScenarioBundle) -> ScenarioBundle:
    return replace(
        bundle,
        config=replace(
            bundle.config,
            mechanisms=LAYER_C_MECHANISMS,
            precision_mode="avm_fixed_point",
        ),
    )


def _layer_c_rows(results: list[ExperimentResult]) -> list[ExperimentResult]:
    return [result for result in results if result.mechanism is MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT]


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


def _parse_adversarial_description(description: str) -> dict[str, str]:
    if ": " not in description:
        return {}
    tail = description.split(": ", 1)[1]
    params: dict[str, str] = {}
    for part in tail.split(", "):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        params[key] = value
    return params


def run_layer_c_target_analysis(
    config: LayerCTargetConfig,
    *,
    runner: ExperimentRunner | None = None,
) -> list[ExperimentResult]:
    experiment_runner = runner or ExperimentRunner()
    results: list[ExperimentResult] = []

    deterministic_names = config.deterministic_names if config.deterministic_names is not None else LAYER_C_DETERMINISTIC_NAMES
    deterministic_bundles = [_with_layer_c_mechanisms(bundle) for bundle in build_deterministic_scenarios(deterministic_names)]
    monte_carlo_bundles = generate_monte_carlo_bundles(config.monte_carlo)
    adversarial_bundles = generate_adversarial_bundles(config.adversarial)
    if config.adversarial_limit is not None:
        adversarial_bundles = adversarial_bundles[: config.adversarial_limit]

    if deterministic_bundles:
        results.extend(experiment_runner.run_bundles(deterministic_bundles, run_family="deterministic"))
    if monte_carlo_bundles:
        results.extend(experiment_runner.run_bundles(monte_carlo_bundles, run_family="monte_carlo"))
    if adversarial_bundles:
        results.extend(experiment_runner.run_bundles(adversarial_bundles, run_family="adversarial"))

    for result in _layer_c_rows(results):
        result.evaluation.exact_vs_simplified_divergence = {
            **result.evaluation.exact_vs_simplified_divergence,
            "parameter_set": config.parameter_set.name,
            "price_floor_fp": config.parameter_set.price_floor_fp,
            "entry_safety_margin": config.parameter_set.entry_safety_margin,
        }
    return results


def build_layer_c_slice_rows(results: list[ExperimentResult]) -> dict[str, list[dict[str, object]]]:
    layer_c_rows = _layer_c_rows(results)
    slices: dict[str, list[dict[str, object]]] = {}

    run_family_rows: list[dict[str, object]] = []
    grouped_by_family: dict[str, list[ExperimentResult]] = {}
    for result in layer_c_rows:
        grouped_by_family.setdefault(result.run_family, []).append(result)
    for run_family, family_rows in sorted(grouped_by_family.items()):
        quote_divs = [
            Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0))
            for result in family_rows
        ]
        nav_divs = [
            Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0))
            for result in family_rows
        ]
        price_divs = [
            Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_price_entry_diff_vs_reference", 0))
            for result in family_rows
        ]
        run_family_rows.append(
            {
                "run_family": run_family,
                "count": len(family_rows),
                "mean_quote_divergence": str(sum(quote_divs) / Decimal(len(quote_divs))),
                "max_quote_divergence": str(max(quote_divs)),
                "mean_nav_per_deposit_divergence": str(sum(nav_divs) / Decimal(len(nav_divs))),
                "max_nav_per_deposit_divergence": str(max(nav_divs)),
                "mean_price_entry_divergence": str(sum(price_divs) / Decimal(len(price_divs))),
                "max_price_entry_divergence": str(max(price_divs)),
                "slippage_failures": sum(
                    result.evaluation.slippage_improvement.get("all_buy_quotes_improved") is not True
                    for result in family_rows
                ),
            }
        )
    slices["by_run_family"] = run_family_rows

    adversarial_rows: list[dict[str, object]] = []
    adversarial_groups: dict[str, list[ExperimentResult]] = {}
    for result in layer_c_rows:
        if result.run_family != "adversarial":
            continue
        params = _parse_adversarial_description(result.description)
        group_key = (
            f"winner_policy={params.get('winner_policy', '')}|"
            f"pre_entry={params.get('pre_entry', '')}|"
            f"post_entry_mode={params.get('post_entry_mode', '')}"
        )
        adversarial_groups.setdefault(group_key, []).append(result)
    for group_key, group_rows in sorted(adversarial_groups.items()):
        adversarial_rows.append(
            {
                "shape": group_key,
                "count": len(group_rows),
                "mean_quote_divergence": str(
                    sum(
                        Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0))
                        for result in group_rows
                    )
                    / Decimal(len(group_rows))
                ),
                "max_quote_divergence": str(
                    max(
                        Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0))
                        for result in group_rows
                    )
                ),
                "mean_nav_per_deposit_divergence": str(
                    sum(
                        Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0))
                        for result in group_rows
                    )
                    / Decimal(len(group_rows))
                ),
                "max_nav_per_deposit_divergence": str(
                    max(
                        Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0))
                        for result in group_rows
                    )
                ),
            }
        )
    slices["adversarial_shape"] = adversarial_rows

    deterministic_rows = [
        {
            "scenario_name": result.scenario_name,
            "description": result.description,
            "quote_divergence": str(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0)),
            "nav_per_deposit_divergence": str(
                result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0)
            ),
            "price_entry_divergence": str(
                result.evaluation.exact_vs_simplified_divergence.get("max_price_entry_diff_vs_reference", 0)
            ),
            "slippage_pass": str(result.evaluation.slippage_improvement.get("all_buy_quotes_improved", False)),
        }
        for result in layer_c_rows
        if result.run_family == "deterministic"
    ]
    slices["deterministic_scenarios"] = sorted(deterministic_rows, key=lambda row: str(row["scenario_name"]))

    divergence_extremes = sorted(
        [
            {
                "run_family": result.run_family,
                "scenario_name": result.scenario_name,
                "description": result.description,
                "max_quote_divergence": str(
                    result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0)
                ),
                "max_nav_per_deposit_divergence": str(
                    result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0)
                ),
                "max_price_entry_divergence": str(
                    result.evaluation.exact_vs_simplified_divergence.get("max_price_entry_diff_vs_reference", 0)
                ),
            }
            for result in layer_c_rows
        ],
        key=lambda row: max(
            abs(Decimal(str(row["max_quote_divergence"]))),
            abs(Decimal(str(row["max_nav_per_deposit_divergence"]))),
            abs(Decimal(str(row["max_price_entry_divergence"]))),
        ),
        reverse=True,
    )
    slices["divergence_extremes"] = divergence_extremes[:20]
    return slices


def run_layer_c_parameter_sweep(
    parameter_sets: list[LayerCParameterSet],
    *,
    monte_carlo_trials: int = 8,
    adversarial_limit: int | None = 16,
    output_dir: str | Path | None = None,
    runner: ExperimentRunner | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    experiment_runner = runner or ExperimentRunner()

    for parameter_set in parameter_sets:
        base_config = build_layer_c_target_config(
            parameter_set=parameter_set,
            adversarial_limit=adversarial_limit,
        )
        config = replace(
            base_config,
            monte_carlo=replace(
                base_config.monte_carlo,
                num_trials=monte_carlo_trials,
                name=f"sweep_{parameter_set.name}_mc",
            ),
            adversarial=replace(
                base_config.adversarial,
                name=f"sweep_{parameter_set.name}_adv",
            ),
        )
        results = run_layer_c_target_analysis(config, runner=experiment_runner)
        layer_c_results = _layer_c_rows(results)
        quote_divs = [
            Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0))
            for result in layer_c_results
        ]
        nav_divs = [
            Decimal(result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0))
            for result in layer_c_results
        ]
        row = {
            "parameter_set": parameter_set.name,
            "price_floor_fp": parameter_set.price_floor_fp,
            "entry_safety_margin": parameter_set.entry_safety_margin,
            "result_count": len(layer_c_results),
            "mean_quote_divergence": str(sum(quote_divs) / Decimal(len(quote_divs))),
            "max_quote_divergence": str(max(quote_divs)),
            "mean_nav_per_deposit_divergence": str(sum(nav_divs) / Decimal(len(nav_divs))),
            "max_nav_per_deposit_divergence": str(max(nav_divs)),
            "slippage_failures": sum(
                result.evaluation.slippage_improvement.get("all_buy_quotes_improved") is not True
                for result in layer_c_results
            ),
            "solvency_failures": sum(
                result.evaluation.solvency.get("passed") is not True
                for result in layer_c_results
            ),
        }
        rows.append(row)

        if output_dir is not None:
            parameter_dir = Path(output_dir) / parameter_set.name
            write_layer_c_analysis_pack(results, parameter_dir, manifest_label=f"layer_c_sweep_{parameter_set.name}")

    if output_dir is not None:
        _write_csv(Path(output_dir) / "parameter_summary.csv", rows)
    return rows


def write_layer_c_analysis_pack(
    results: list[ExperimentResult],
    output_dir: str | Path,
    *,
    manifest_label: str,
) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs = write_experiment_results(results, out_dir, manifest_label=manifest_label)
    report: AggregatedReport = aggregate_results(results)
    outputs.update(write_aggregated_report(report, out_dir))
    outputs.update(write_figure_pack(report, out_dir))

    slice_rows = build_layer_c_slice_rows(results)
    for name, rows in slice_rows.items():
        path = out_dir / f"{name}.csv"
        _write_csv(path, rows)
        outputs[f"{name}_csv"] = path
    return outputs


__all__ = [
    "LayerCParameterSet",
    "LayerCTargetConfig",
    "build_layer_c_target_config",
    "build_layer_c_sell_heavy_config",
    "build_layer_c_low_tail_config",
    "build_layer_c_slice_rows",
    "deterministic_scenario_names",
    "run_layer_c_parameter_sweep",
    "run_layer_c_target_analysis",
    "write_layer_c_analysis_pack",
]
