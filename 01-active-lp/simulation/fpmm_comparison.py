from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from research.active_lp.adversarial_search import AdversarialSearchConfig, generate_adversarial_bundles
from research.active_lp.experiments import ExperimentResult, ExperimentRunner, write_experiment_results
from research.active_lp.high_skew_boundary import build_high_skew_adversarial_config
from research.active_lp.reporting import aggregate_results, write_aggregated_report
from research.active_lp.scenarios import ScenarioBundle, build_deterministic_scenario
from research.active_lp.types import MechanismVariant

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DEFAULT_LINEAR_LAMBDA = Decimal("0.150")
DEFAULT_RESIDUAL_WEIGHT_SCHEME = "linear_lambda_normalized"
ACTIVE_LP_FPMM_MECHANISMS = (
    MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
    MechanismVariant.FPMM_POOL_SHARE,
)
DEFAULT_DETERMINISTIC_SCENARIOS = (
    "neutral_late_lp",
    "skewed_late_lp",
    "long_tail_late_lp",
    "early_vs_late_same_delta_b",
    "same_final_claims_different_timing",
    "repeated_lp_entries",
    "zero_flow_nav_invariance",
    "same_block_trade_reordering",
)


@dataclass(slots=True)
class FpmmComparisonConfig:
    residual_weight_scheme: str = DEFAULT_RESIDUAL_WEIGHT_SCHEME
    linear_lambda: Decimal = DEFAULT_LINEAR_LAMBDA
    deterministic_names: tuple[str, ...] = DEFAULT_DETERMINISTIC_SCENARIOS
    adversarial_limit: int = 24
    high_skew_limit: int = 12


def _fairness_rows(result: ExperimentResult) -> list[dict[str, object]]:
    return list(result.evaluation.lp_fairness_by_entry_time.get("rows", []))


def _fairness_gap(rows: list[dict[str, object]]) -> Decimal:
    if len(rows) < 2:
        return Decimal("0")
    ordered = sorted(rows, key=lambda row: (int(row["entry_timestamp"]), str(row["cohort_id"])))
    return Decimal(str(ordered[-1]["nav_per_deposit"])) - Decimal(str(ordered[0]["nav_per_deposit"]))


def _with_comparator_mechanisms(
    bundle: ScenarioBundle,
    *,
    residual_weight_scheme: str,
    linear_lambda: Decimal,
) -> ScenarioBundle:
    return replace(
        bundle,
        config=replace(
            bundle.config,
            mechanisms=ACTIVE_LP_FPMM_MECHANISMS,
            residual_weight_scheme=residual_weight_scheme,
            residual_linear_lambda=linear_lambda,
            precision_mode="decimal",
        ),
    )


def build_fpmm_deterministic_bundles(
    *,
    names: tuple[str, ...] = DEFAULT_DETERMINISTIC_SCENARIOS,
    residual_weight_scheme: str = DEFAULT_RESIDUAL_WEIGHT_SCHEME,
    linear_lambda: Decimal = DEFAULT_LINEAR_LAMBDA,
) -> list[ScenarioBundle]:
    return [
        _with_comparator_mechanisms(
            build_deterministic_scenario(name),
            residual_weight_scheme=residual_weight_scheme,
            linear_lambda=linear_lambda,
        )
        for name in names
    ]


def build_fpmm_adversarial_config() -> AdversarialSearchConfig:
    return AdversarialSearchConfig(
        name="fpmm_compare_adv",
        num_outcomes_choices=(3, 8),
        initial_depth_choices=(Decimal("100"), Decimal("140")),
        fee_bps_choices=(Decimal("100"),),
        protocol_fee_bps_choices=(Decimal("25"),),
        late_delta_b_choices=(Decimal("20"), Decimal("50")),
        pre_entry_shares_choices=(Decimal("6"), Decimal("20")),
        post_entry_shares_choices=(Decimal("0"), Decimal("12")),
        counterflow_ratio_choices=(Decimal("0"), Decimal("0.25")),
        post_entry_modes=("idle", "trend", "reversion"),
        winner_policies=("favorite", "hedge"),
        mechanisms=ACTIVE_LP_FPMM_MECHANISMS,
    )


def build_fpmm_high_skew_bundles(
    *,
    residual_weight_scheme: str = DEFAULT_RESIDUAL_WEIGHT_SCHEME,
    linear_lambda: Decimal = DEFAULT_LINEAR_LAMBDA,
    limit: int = 12,
) -> list[ScenarioBundle]:
    config = build_high_skew_adversarial_config()
    bundles = generate_adversarial_bundles(
        replace(
            config,
            name="fpmm_compare_high_skew",
            mechanisms=ACTIVE_LP_FPMM_MECHANISMS,
        )
    )
    return [
        _with_comparator_mechanisms(
            bundle,
            residual_weight_scheme=residual_weight_scheme,
            linear_lambda=linear_lambda,
        )
        for bundle in bundles[:limit]
    ]


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


def _paired_rows(results: list[ExperimentResult]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[MechanismVariant, ExperimentResult]] = {}
    for result in results:
        grouped.setdefault((result.run_family, result.scenario_name), {})[result.mechanism] = result

    rows: list[dict[str, object]] = []
    for (run_family, scenario_name), bucket in sorted(grouped.items()):
        active = bucket.get(MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL)
        fpmm = bucket.get(MechanismVariant.FPMM_POOL_SHARE)
        if active is None or fpmm is None:
            continue
        active_rows = _fairness_rows(active)
        fpmm_rows = _fairness_rows(fpmm)
        active_gap = _fairness_gap(active_rows)
        fpmm_gap = _fairness_gap(fpmm_rows)
        rows.append(
            {
                "run_family": run_family,
                "scenario_name": scenario_name,
                "active_lp_fairness_gap_nav_per_deposit": str(active_gap),
                "fpmm_fairness_gap_nav_per_deposit": str(fpmm_gap),
                "fpmm_minus_active_lp_gap": str(fpmm_gap - active_gap),
                "active_lp_max_price_change": str(active.evaluation.price_continuity.get("max_abs_change", "")),
                "fpmm_max_price_change": str(fpmm.evaluation.price_continuity.get("max_abs_change", "")),
                "active_lp_slippage_pass": str(active.evaluation.slippage_improvement.get("all_buy_quotes_improved", "")),
                "fpmm_slippage_pass": str(fpmm.evaluation.slippage_improvement.get("all_buy_quotes_improved", "")),
                "active_lp_solvency_pass": str(active.evaluation.solvency.get("passed", "")),
                "fpmm_solvency_pass": str(fpmm.evaluation.solvency.get("passed", "")),
            }
        )
    return rows


def _overview(results: list[ExperimentResult], paired_rows: list[dict[str, object]]) -> dict[str, object]:
    by_mechanism: dict[str, list[Decimal]] = {}
    for result in results:
        by_mechanism.setdefault(result.mechanism.value, []).append(_fairness_gap(_fairness_rows(result)))

    fpmm_minus_active = [Decimal(str(row["fpmm_minus_active_lp_gap"])) for row in paired_rows]
    return {
        "result_count": len(results),
        "paired_scenario_count": len(paired_rows),
        "mechanism_mean_fairness_gap": {
            mechanism: str(sum(values, start=Decimal("0")) / Decimal(len(values))) if values else "0"
            for mechanism, values in by_mechanism.items()
        },
        "mechanism_max_abs_fairness_gap": {
            mechanism: str(max((abs(value) for value in values), default=Decimal("0")))
            for mechanism, values in by_mechanism.items()
        },
        "mean_fpmm_minus_active_lp_gap": str(
            sum(fpmm_minus_active, start=Decimal("0")) / Decimal(len(fpmm_minus_active)) if fpmm_minus_active else Decimal("0")
        ),
        "max_abs_fpmm_minus_active_lp_gap": str(
            max((abs(value) for value in fpmm_minus_active), default=Decimal("0"))
        ),
        "active_lp_beats_fpmm_on_abs_gap_count": sum(
            1
            for row in paired_rows
            if abs(Decimal(str(row["active_lp_fairness_gap_nav_per_deposit"])))
            < abs(Decimal(str(row["fpmm_fairness_gap_nav_per_deposit"])))
        ),
        "fpmm_beats_active_lp_on_abs_gap_count": sum(
            1
            for row in paired_rows
            if abs(Decimal(str(row["fpmm_fairness_gap_nav_per_deposit"])))
            < abs(Decimal(str(row["active_lp_fairness_gap_nav_per_deposit"])))
        ),
    }


def _build_report(overview: dict[str, object], paired_rows: list[dict[str, object]]) -> str:
    lines = [
        "# Active LP vs FPMM Snapshot",
        "",
        f"- Active-LP residual weighting scheme: {overview['active_lp_residual_weight_scheme']}",
        f"- Active-LP lambda: {overview['active_lp_linear_lambda']}",
        f"- Total result rows: {overview['result_count']}",
        f"- Paired scenarios: {overview['paired_scenario_count']}",
        f"- Mean FPMM minus active-LP fairness gap: {overview['mean_fpmm_minus_active_lp_gap']}",
        f"- Max abs FPMM minus active-LP fairness gap: {overview['max_abs_fpmm_minus_active_lp_gap']}",
        f"- Active LP wins on abs gap in {overview['active_lp_beats_fpmm_on_abs_gap_count']} paired scenarios",
        f"- FPMM wins on abs gap in {overview['fpmm_beats_active_lp_on_abs_gap_count']} paired scenarios",
        "",
        "## Mechanism Means",
        "",
    ]
    mean_rows = overview["mechanism_mean_fairness_gap"]
    max_rows = overview["mechanism_max_abs_fairness_gap"]
    for mechanism, mean_value in mean_rows.items():
        lines.append(
            f"- `{mechanism}`: mean fairness gap={mean_value}, max abs fairness gap={max_rows.get(mechanism, '0')}"
        )
    lines.extend(["", "## Largest Paired Differences", ""])
    for row in sorted(
        paired_rows,
        key=lambda item: abs(Decimal(str(item["fpmm_minus_active_lp_gap"]))),
        reverse=True,
    )[:10]:
        lines.append(
            f"- `{row['scenario_name']}` ({row['run_family']}): active={row['active_lp_fairness_gap_nav_per_deposit']}, "
            f"fpmm={row['fpmm_fairness_gap_nav_per_deposit']}, fpmm-active={row['fpmm_minus_active_lp_gap']}"
        )
    return "\n".join(lines) + "\n"


def run_fpmm_head_to_head(
    *,
    config: FpmmComparisonConfig | None = None,
    output_dir: str | Path | None = None,
    runner: ExperimentRunner | None = None,
) -> dict[str, Path]:
    comparison_config = config or FpmmComparisonConfig()
    out_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_ROOT / "fpmm_compare_core"
    out_dir.mkdir(parents=True, exist_ok=True)
    experiment_runner = runner or ExperimentRunner()

    bundles: list[ScenarioBundle] = []
    bundles.extend(
        build_fpmm_deterministic_bundles(
            names=comparison_config.deterministic_names,
            residual_weight_scheme=comparison_config.residual_weight_scheme,
            linear_lambda=comparison_config.linear_lambda,
        )
    )

    adversarial_bundles = [
        _with_comparator_mechanisms(
            bundle,
            residual_weight_scheme=comparison_config.residual_weight_scheme,
            linear_lambda=comparison_config.linear_lambda,
        )
        for bundle in generate_adversarial_bundles(build_fpmm_adversarial_config())[: comparison_config.adversarial_limit]
    ]
    high_skew_bundles = build_fpmm_high_skew_bundles(
        residual_weight_scheme=comparison_config.residual_weight_scheme,
        linear_lambda=comparison_config.linear_lambda,
        limit=comparison_config.high_skew_limit,
    )

    results: list[ExperimentResult] = []
    results.extend(experiment_runner.run_bundles(bundles, run_family="deterministic"))
    results.extend(experiment_runner.run_bundles(adversarial_bundles, run_family="adversarial"))
    results.extend(experiment_runner.run_bundles(high_skew_bundles, run_family="high_skew"))

    outputs = write_experiment_results(results, out_dir, manifest_label="fpmm_compare_core")
    report_paths = write_aggregated_report(aggregate_results(results), out_dir)
    paired_rows = _paired_rows(results)
    overview = _overview(results, paired_rows)
    overview["active_lp_residual_weight_scheme"] = comparison_config.residual_weight_scheme
    overview["active_lp_linear_lambda"] = str(comparison_config.linear_lambda)

    paired_path = out_dir / "paired_summary.csv"
    overview_path = out_dir / "paired_overview.json"
    report_path = out_dir / "paired_report.md"

    _write_csv(paired_path, paired_rows)
    overview_path.write_text(json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_build_report(overview, paired_rows), encoding="utf-8")

    return {
        **outputs,
        **report_paths,
        "paired_summary_csv": paired_path,
        "paired_overview_json": overview_path,
        "paired_report_md": report_path,
    }
