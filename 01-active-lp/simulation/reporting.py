from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.active_lp.experiments import ExperimentResult


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in ("", None):
        return Decimal("0")
    return Decimal(str(value))


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def _quantile(values: list[Decimal], quantile: Decimal) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * Decimal(len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _fairness_gap(row_set: list[dict[str, object]]) -> Decimal:
    if len(row_set) < 2:
        return Decimal("0")
    ordered = sorted(row_set, key=lambda row: (int(row["entry_timestamp"]), str(row["cohort_id"])))
    return _to_decimal(ordered[-1]["nav_per_deposit"]) - _to_decimal(ordered[0]["nav_per_deposit"])


@dataclass(slots=True)
class AggregatedReport:
    overview: dict[str, object]
    run_family_rows: list[dict[str, object]]
    scenario_rows: list[dict[str, object]]
    cohort_rows: list[dict[str, object]]
    fairness_extreme_rows: list[dict[str, object]]
    markdown: str


def aggregate_results(results: list[ExperimentResult]) -> AggregatedReport:
    total_results = len(results)
    price_passes = 0
    slippage_passes = 0
    solvency_passes = 0
    invariant_failure_count = 0
    max_price_change = Decimal("0")
    fairness_gaps: list[Decimal] = []
    divergence_nav_per_deposit_diffs: list[Decimal] = []
    divergence_quote_diffs: list[Decimal] = []
    cohort_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []

    by_family: dict[str, list[ExperimentResult]] = {}
    for result in results:
        by_family.setdefault(result.run_family, []).append(result)

        if result.evaluation.price_continuity.get("all_within_tolerance") is True:
            price_passes += 1
        if result.evaluation.slippage_improvement.get("all_buy_quotes_improved") is True:
            slippage_passes += 1
        if result.evaluation.solvency.get("passed") is True:
            solvency_passes += 1

        failures = result.evaluation.exact_vs_simplified_divergence.get("invariant_failures", [])
        divergence_nav_per_deposit_diffs.append(
            _to_decimal(result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", 0))
        )
        divergence_quote_diffs.append(
            _to_decimal(result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", 0))
        )
        invariant_failure_count += len(failures)
        price_change = _to_decimal(result.evaluation.price_continuity.get("max_abs_change", 0))
        max_price_change = max(max_price_change, price_change)

        fairness_rows = list(result.evaluation.lp_fairness_by_entry_time.get("rows", []))
        fairness_gaps.append(_fairness_gap(fairness_rows))
        price_entries = list(result.evaluation.price_continuity.get("entries", []))
        entry_max_probability = max(
            (
                max((_to_decimal(price) for price in entry.get("before", [])), default=Decimal("0"))
                for entry in price_entries
            ),
            default=Decimal("0"),
        )
        for row in fairness_rows:
            cohort_rows.append(
                {
                    "run_family": result.run_family,
                    "scenario_name": result.scenario_name,
                    "mechanism": result.mechanism.value,
                    "cohort_id": row["cohort_id"],
                    "sponsor_id": row["sponsor_id"],
                    "entry_timestamp": row["entry_timestamp"],
                    "num_outcomes": result.config.num_outcomes,
                    "duration_steps": result.config.duration_steps or "",
                    "duration_bucket": result.config.duration_bucket or "",
                    "clock_mode": result.config.clock_mode,
                    "split": result.config.split or "",
                    "nav": str(row["nav"]),
                    "nav_per_deposit": str(row["nav_per_deposit"]),
                    "nav_per_risk": str(row["nav_per_risk"]),
                }
            )

        scenario_rows.append(
            {
                "run_family": result.run_family,
                "scenario_name": result.scenario_name,
                "mechanism": result.mechanism.value,
                "num_outcomes": result.config.num_outcomes,
                "duration_steps": result.config.duration_steps or "",
                "duration_bucket": result.config.duration_bucket or "",
                "clock_mode": result.config.clock_mode,
                "split": result.config.split or "",
                "price_continuity_pass": result.evaluation.price_continuity.get("all_within_tolerance", False),
                "max_price_change": str(price_change),
                "slippage_pass": result.evaluation.slippage_improvement.get("all_buy_quotes_improved", False),
                "solvency_pass": result.evaluation.solvency.get("passed", False),
                "path_terminal_states": str(result.evaluation.path_dependence.get("terminal_states", "")),
                "path_max_price_diff": str(result.evaluation.path_dependence.get("max_price_diff", "")),
                "path_max_funds_diff": str(result.evaluation.path_dependence.get("max_funds_diff", "")),
                "path_max_residual_claimed_diff": str(result.evaluation.path_dependence.get("max_residual_claimed_diff", "")),
                "fairness_gap_nav_per_deposit": str(fairness_gaps[-1]),
                "entry_max_probability": str(entry_max_probability),
                "reserve_required": str(result.evaluation.residual_release.get("reserve_required", "")),
                "releasable_pool": str(result.evaluation.residual_release.get("releasable_pool", "")),
                "total_residual_claimed": str(result.evaluation.residual_release.get("total_residual_claimed", "")),
                "divergence_max_quote_diff_vs_reference": str(
                    result.evaluation.exact_vs_simplified_divergence.get("max_quote_diff_vs_reference", "")
                ),
                "divergence_max_nav_per_deposit_diff_vs_reference": str(
                    result.evaluation.exact_vs_simplified_divergence.get("max_nav_per_deposit_diff_vs_reference", "")
                ),
                "invariant_failures": len(failures),
            }
        )

    run_family_rows: list[dict[str, object]] = []
    for run_family, family_results in sorted(by_family.items()):
        family_price_changes = [_to_decimal(result.evaluation.price_continuity.get("max_abs_change", 0)) for result in family_results]
        family_failures = sum(
            len(result.evaluation.exact_vs_simplified_divergence.get("invariant_failures", []))
            for result in family_results
        )
        run_family_rows.append(
            {
                "run_family": run_family,
                "result_count": len(family_results),
                "price_continuity_pass_rate": str(
                    Decimal(
                        sum(1 for result in family_results if result.evaluation.price_continuity.get("all_within_tolerance") is True)
                    )
                    / Decimal(len(family_results))
                ),
                "slippage_pass_rate": str(
                    Decimal(
                        sum(1 for result in family_results if result.evaluation.slippage_improvement.get("all_buy_quotes_improved") is True)
                    )
                    / Decimal(len(family_results))
                ),
                "solvency_pass_rate": str(
                    Decimal(sum(1 for result in family_results if result.evaluation.solvency.get("passed") is True))
                    / Decimal(len(family_results))
                ),
                "mean_max_price_change": str(_mean(family_price_changes)),
                "max_max_price_change": str(max(family_price_changes, default=Decimal("0"))),
                "invariant_failures": family_failures,
            }
        )

    overview = {
        "result_count": total_results,
        "run_families": sorted(by_family.keys()),
        "price_continuity_pass_rate": str(Decimal(price_passes) / Decimal(total_results) if total_results else Decimal("0")),
        "slippage_pass_rate": str(Decimal(slippage_passes) / Decimal(total_results) if total_results else Decimal("0")),
        "solvency_pass_rate": str(Decimal(solvency_passes) / Decimal(total_results) if total_results else Decimal("0")),
        "max_price_change": str(max_price_change),
        "mean_fairness_gap_nav_per_deposit": str(_mean(fairness_gaps)),
        "mean_abs_fairness_gap_nav_per_deposit": str(_mean([abs(gap) for gap in fairness_gaps])),
        "median_fairness_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.5"))),
        "p05_fairness_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.05"))),
        "p95_fairness_gap_nav_per_deposit": str(_quantile(fairness_gaps, Decimal("0.95"))),
        "max_abs_fairness_gap_nav_per_deposit": str(max((abs(gap) for gap in fairness_gaps), default=Decimal("0"))),
        "worst_positive_fairness_gap_nav_per_deposit": str(max(fairness_gaps, default=Decimal("0"))),
        "worst_negative_fairness_gap_nav_per_deposit": str(min(fairness_gaps, default=Decimal("0"))),
        "mean_divergence_max_quote_diff_vs_reference": str(_mean(divergence_quote_diffs)),
        "max_divergence_max_quote_diff_vs_reference": str(max(divergence_quote_diffs, default=Decimal("0"))),
        "mean_divergence_max_nav_per_deposit_diff_vs_reference": str(_mean(divergence_nav_per_deposit_diffs)),
        "max_divergence_max_nav_per_deposit_diff_vs_reference": str(
            max(divergence_nav_per_deposit_diffs, default=Decimal("0"))
        ),
        "invariant_failure_count": invariant_failure_count,
    }

    sorted_by_gap = sorted(
        scenario_rows,
        key=lambda row: abs(_to_decimal(row["fairness_gap_nav_per_deposit"])),
        reverse=True,
    )
    fairness_extreme_rows = []
    for direction, subset in (
        ("positive", sorted([row for row in scenario_rows if _to_decimal(row["fairness_gap_nav_per_deposit"]) > 0], key=lambda row: _to_decimal(row["fairness_gap_nav_per_deposit"]), reverse=True)[:5]),
        ("negative", sorted([row for row in scenario_rows if _to_decimal(row["fairness_gap_nav_per_deposit"]) < 0], key=lambda row: _to_decimal(row["fairness_gap_nav_per_deposit"]))[:5]),
        ("absolute", sorted_by_gap[:10]),
    ):
        for rank, row in enumerate(subset, start=1):
            fairness_extreme_rows.append(
                {
                    "direction": direction,
                    "rank": rank,
                    **row,
                }
            )

    markdown_lines = [
        "# Active LP Result Snapshot",
        "",
        f"- Results: {total_results}",
        f"- Run families: {', '.join(sorted(by_family.keys()))}",
        f"- Price continuity pass rate: {overview['price_continuity_pass_rate']}",
        f"- Slippage improvement pass rate: {overview['slippage_pass_rate']}",
        f"- Solvency pass rate: {overview['solvency_pass_rate']}",
        f"- Max price change at LP entry: {overview['max_price_change']}",
        f"- Mean fairness gap (late minus early NAV/deposit): {overview['mean_fairness_gap_nav_per_deposit']}",
        f"- Mean absolute fairness gap: {overview['mean_abs_fairness_gap_nav_per_deposit']}",
        f"- Mean max quote divergence vs reference: {overview['mean_divergence_max_quote_diff_vs_reference']}",
        f"- Mean max NAV/deposit divergence vs reference: {overview['mean_divergence_max_nav_per_deposit_diff_vs_reference']}",
        f"- Invariant failures: {overview['invariant_failure_count']}",
        "",
        "## Run Families",
        "",
    ]
    for row in run_family_rows:
        markdown_lines.append(
            f"- `{row['run_family']}`: results={row['result_count']}, price_pass={row['price_continuity_pass_rate']}, "
            f"slippage_pass={row['slippage_pass_rate']}, solvency_pass={row['solvency_pass_rate']}, "
            f"mean_max_price_change={row['mean_max_price_change']}, invariant_failures={row['invariant_failures']}"
        )
    markdown_lines.extend(["", "## Fairness Extremes", ""])
    for row in fairness_extreme_rows[:10]:
        markdown_lines.append(
            f"- `{row['direction']}` #{row['rank']}: `{row['scenario_name']}` ({row['run_family']}) fairness_gap={row['fairness_gap_nav_per_deposit']}"
        )

    return AggregatedReport(
        overview=overview,
        run_family_rows=run_family_rows,
        scenario_rows=scenario_rows,
        cohort_rows=cohort_rows,
        fairness_extreme_rows=fairness_extreme_rows,
        markdown="\n".join(markdown_lines) + "\n",
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


def write_aggregated_report(report: AggregatedReport, output_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    overview_path = out_dir / "aggregate.json"
    run_family_path = out_dir / "run_family_summary.csv"
    scenario_path = out_dir / "scenario_summary.csv"
    cohort_path = out_dir / "cohort_fairness.csv"
    fairness_extremes_path = out_dir / "fairness_extremes.csv"
    markdown_path = out_dir / "report.md"

    overview_path.write_text(json.dumps(report.overview, indent=2, sort_keys=True), encoding="utf-8")
    _write_csv(run_family_path, report.run_family_rows)
    _write_csv(scenario_path, report.scenario_rows)
    _write_csv(cohort_path, report.cohort_rows)
    _write_csv(fairness_extremes_path, report.fairness_extreme_rows)
    markdown_path.write_text(report.markdown, encoding="utf-8")

    return {
        "aggregate_json": overview_path,
        "run_family_summary_csv": run_family_path,
        "scenario_summary_csv": scenario_path,
        "cohort_fairness_csv": cohort_path,
        "fairness_extremes_csv": fairness_extremes_path,
        "report_md": markdown_path,
    }
