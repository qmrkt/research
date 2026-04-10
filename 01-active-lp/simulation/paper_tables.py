from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
ORDINARY_RUN_FAMILIES = frozenset({"monte_carlo", "adversarial"})


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _markdown_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _first_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _selected_parameter_metadata(root: Path) -> dict[str, object]:
    path = root / "lambda_selection_summary.json"
    if not path.exists():
        return {}
    return _read_json(path)


def _max_abs_gap_from_selection_row(row: dict[str, object]) -> Decimal:
    return max(
        abs(_to_decimal(row.get("worst_positive_gap_nav_per_deposit", "0"))),
        abs(_to_decimal(row.get("worst_negative_gap_nav_per_deposit", "0"))),
    )


def _reference_entry_rows(
    results_path: Path,
    *,
    allowed_run_families: frozenset[str] | None = None,
) -> list[dict[str, Decimal]]:
    if not results_path.exists():
        return []
    rows: list[dict[str, Decimal]] = []
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            run_family = str(record.get("run_family", ""))
            if allowed_run_families is not None and run_family not in allowed_run_families:
                continue
            mechanism = str(record.get("mechanism", ""))
            if not mechanism.startswith("reference_parallel_lmsr"):
                continue
            entries = record.get("evaluation", {}).get("price_continuity", {}).get("entries", [])
            fairness_rows = record.get("evaluation", {}).get("lp_fairness_by_entry_time", {}).get("rows", [])
            if not entries or len(fairness_rows) < 2:
                continue
            max_entry_probability = max(
                max(_to_decimal(price) for price in entry.get("before", []))
                for entry in entries
            )
            fairness_gap = _to_decimal(fairness_rows[-1]["nav_per_deposit"]) - _to_decimal(
                fairness_rows[0]["nav_per_deposit"]
            )
            rows.append(
                {
                    "max_entry_probability": max_entry_probability,
                    "fairness_gap_nav_per_deposit": fairness_gap,
                }
            )
    return rows


def build_paper_tables(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    table_dir: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    out_dir = Path(table_dir) if table_dir is not None else root / "paper_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    layer_b = _read_json(root / "layer_b_compare_core" / "aggregate.json")
    reserve_flat = _read_json(root / "reserve_residual_quick" / "combined" / "aggregate.json")
    reserve_linear = _read_json(root / "time_weighted_reserve_quick" / "combined" / "aggregate.json")
    reserve_calibrated = _read_json(root / "residual_weight_paper_midpoint" / "linear_lambda_003250" / "aggregate.json")
    layer_c_target = _read_json(root / "layer_c_compare_target" / "aggregate.json")
    layer_c_low_tail = _read_json(root / "layer_c_low_tail_compare" / "aggregate.json")
    selection_summary = _selected_parameter_metadata(root)
    normalized_selection = dict(selection_summary.get("normalized", {}).get("test", {}))
    normalized_name = str(normalized_selection.get("name", "")).strip()

    midpoint_reference_rows = _reference_entry_rows(
        root / "residual_weight_paper_midpoint" / "linear_lambda_003250" / "results.jsonl",
        allowed_run_families=ORDINARY_RUN_FAMILIES,
    )
    normalized_reference_path = (
        root / "residual_weight_test_normalized" / normalized_name / "results.jsonl"
        if normalized_name
        else Path()
    )
    normalized_reference_rows = (
        _reference_entry_rows(
            normalized_reference_path,
            allowed_run_families=ORDINARY_RUN_FAMILIES,
        )
        if normalized_name
        else []
    )
    ordinary_reference_rows = normalized_reference_rows or midpoint_reference_rows

    high_skew_summary_rows = _read_csv_rows(
        root / "residual_weight_boundary_validation" / "high_skew" / normalized_name / "high_skew_threshold_summary.csv"
    ) if normalized_name else []
    high_skew_reference_rows = _reference_entry_rows(root / "high_skew_boundary_calibrated" / "results.jsonl")

    fpmm_paired_path = _first_existing_path(
        root / "fpmm_compare_normalized_core" / "paired_summary.csv",
        root / "fpmm_compare_core" / "paired_summary.csv",
    )
    fpmm_paired_rows = _read_csv_rows(fpmm_paired_path) if fpmm_paired_path is not None else []

    layer_b_rows = [
        {"metric": "result_count", "value": layer_b["result_count"]},
        {"metric": "price_continuity_pass_rate", "value": layer_b["price_continuity_pass_rate"]},
        {"metric": "slippage_pass_rate", "value": layer_b["slippage_pass_rate"]},
        {"metric": "solvency_pass_rate", "value": layer_b["solvency_pass_rate"]},
        {"metric": "mean_max_quote_diff_vs_reference", "value": layer_b["mean_divergence_max_quote_diff_vs_reference"]},
        {"metric": "max_max_quote_diff_vs_reference", "value": layer_b["max_divergence_max_quote_diff_vs_reference"]},
        {
            "metric": "mean_max_nav_per_deposit_diff_vs_reference",
            "value": layer_b["mean_divergence_max_nav_per_deposit_diff_vs_reference"],
        },
        {
            "metric": "max_max_nav_per_deposit_diff_vs_reference",
            "value": layer_b["max_divergence_max_nav_per_deposit_diff_vs_reference"],
        },
        {"metric": "invariant_failure_count", "value": layer_b["invariant_failure_count"]},
    ]

    residual_rule_rows = [
        {
            "rule": "flat_reserve",
            "mean_fairness_gap_nav_per_deposit": reserve_flat["mean_fairness_gap_nav_per_deposit"],
            "max_abs_fairness_gap_nav_per_deposit": reserve_flat["max_abs_fairness_gap_nav_per_deposit"],
            "invariant_failure_count": reserve_flat["invariant_failure_count"],
            "interpretation": "late-LP favoring baseline",
        },
        {
            "rule": "linear_time_weighted",
            "mean_fairness_gap_nav_per_deposit": reserve_linear["mean_fairness_gap_nav_per_deposit"],
            "max_abs_fairness_gap_nav_per_deposit": reserve_linear["max_abs_fairness_gap_nav_per_deposit"],
            "invariant_failure_count": reserve_linear["invariant_failure_count"],
            "interpretation": "overcorrects toward early LPs",
        },
        {
            "rule": "affine_calibrated_0.03250",
            "mean_fairness_gap_nav_per_deposit": reserve_calibrated["mean_fairness_gap_nav_per_deposit"],
            "max_abs_fairness_gap_nav_per_deposit": reserve_calibrated["max_abs_fairness_gap_nav_per_deposit"],
            "invariant_failure_count": reserve_calibrated["invariant_failure_count"],
            "interpretation": "useful in-sample crossover, but too clock-sensitive to keep as the default",
        },
    ]
    if normalized_selection:
        residual_rule_rows.append(
            {
                "rule": f"affine_normalized_{normalized_selection['linear_lambda']}",
                "mean_fairness_gap_nav_per_deposit": normalized_selection["mean_gap_nav_per_deposit"],
                "max_abs_fairness_gap_nav_per_deposit": str(_max_abs_gap_from_selection_row(normalized_selection)),
                "invariant_failure_count": normalized_selection["invariant_failure_count"],
                "interpretation": "current paper and protocol default",
            }
        )

    layer_c_rows = [
        {
            "metric": "result_count",
            "ordinary_target_regime": layer_c_target["result_count"],
            "low_tail_regime": layer_c_low_tail["result_count"],
        },
        {
            "metric": "price_continuity_pass_rate",
            "ordinary_target_regime": layer_c_target["price_continuity_pass_rate"],
            "low_tail_regime": layer_c_low_tail["price_continuity_pass_rate"],
        },
        {
            "metric": "slippage_pass_rate",
            "ordinary_target_regime": layer_c_target["slippage_pass_rate"],
            "low_tail_regime": layer_c_low_tail["slippage_pass_rate"],
        },
        {
            "metric": "solvency_pass_rate",
            "ordinary_target_regime": layer_c_target["solvency_pass_rate"],
            "low_tail_regime": layer_c_low_tail["solvency_pass_rate"],
        },
        {
            "metric": "invariant_failure_count",
            "ordinary_target_regime": layer_c_target["invariant_failure_count"],
            "low_tail_regime": layer_c_low_tail["invariant_failure_count"],
        },
        {
            "metric": "mean_max_quote_diff_vs_reference",
            "ordinary_target_regime": layer_c_target["mean_divergence_max_quote_diff_vs_reference"],
            "low_tail_regime": layer_c_low_tail["mean_divergence_max_quote_diff_vs_reference"],
        },
        {
            "metric": "max_max_quote_diff_vs_reference",
            "ordinary_target_regime": layer_c_target["max_divergence_max_quote_diff_vs_reference"],
            "low_tail_regime": layer_c_low_tail["max_divergence_max_quote_diff_vs_reference"],
        },
        {
            "metric": "mean_max_nav_per_deposit_diff_vs_reference",
            "ordinary_target_regime": layer_c_target["mean_divergence_max_nav_per_deposit_diff_vs_reference"],
            "low_tail_regime": layer_c_low_tail["mean_divergence_max_nav_per_deposit_diff_vs_reference"],
        },
        {
            "metric": "max_max_nav_per_deposit_diff_vs_reference",
            "ordinary_target_regime": layer_c_target["max_divergence_max_nav_per_deposit_diff_vs_reference"],
            "low_tail_regime": layer_c_low_tail["max_divergence_max_nav_per_deposit_diff_vs_reference"],
        },
    ]

    high_skew_rows: list[dict[str, object]] = []
    if ordinary_reference_rows:
        high_skew_rows.append(
            {
                "slice": "ordinary_reference_all",
                "scenario_count": len(ordinary_reference_rows),
                "max_entry_probability": max(row["max_entry_probability"] for row in ordinary_reference_rows),
                "mean_fairness_gap_nav_per_deposit": sum(
                    row["fairness_gap_nav_per_deposit"] for row in ordinary_reference_rows
                )
                / len(ordinary_reference_rows),
                "min_fairness_gap_nav_per_deposit": min(
                    row["fairness_gap_nav_per_deposit"] for row in ordinary_reference_rows
                ),
                "max_fairness_gap_nav_per_deposit": max(
                    row["fairness_gap_nav_per_deposit"] for row in ordinary_reference_rows
                ),
                "interpretation": "ordinary calibration workload never reaches near-resolved LP entry",
            }
        )
    if high_skew_summary_rows:
        for row in high_skew_summary_rows:
            threshold = str(row["threshold"])
            high_skew_rows.append(
                {
                    "slice": f"high_skew_normalized_reference_max_p_ge_{threshold.replace('.', '_')}",
                    "scenario_count": int(row["scenario_count"]),
                    "max_entry_probability": row["max_entry_probability"],
                    "mean_fairness_gap_nav_per_deposit": row["mean_fairness_gap_nav_per_deposit"],
                    "min_fairness_gap_nav_per_deposit": row["min_fairness_gap_nav_per_deposit"],
                    "max_fairness_gap_nav_per_deposit": row["max_fairness_gap_nav_per_deposit"],
                    "interpretation": "normalized default still treats near-resolved late entry as a boundary regime",
                }
            )
    else:
        for threshold in (Decimal("0.8"), Decimal("0.9")):
            threshold_rows = [
                row for row in high_skew_reference_rows if row["max_entry_probability"] >= threshold
            ]
            if not threshold_rows:
                continue
            high_skew_rows.append(
                {
                    "slice": f"high_skew_calibrated_reference_max_p_ge_{str(threshold).replace('.', '_')}",
                    "scenario_count": len(threshold_rows),
                    "max_entry_probability": max(row["max_entry_probability"] for row in threshold_rows),
                    "mean_fairness_gap_nav_per_deposit": sum(
                        row["fairness_gap_nav_per_deposit"] for row in threshold_rows
                    )
                    / len(threshold_rows),
                    "min_fairness_gap_nav_per_deposit": min(
                        row["fairness_gap_nav_per_deposit"] for row in threshold_rows
                    ),
                    "max_fairness_gap_nav_per_deposit": max(
                        row["fairness_gap_nav_per_deposit"] for row in threshold_rows
                    ),
                    "interpretation": "calibrated affine rule still treats near-resolved late entry as a boundary regime",
                }
            )

    fpmm_rows: list[dict[str, object]] = []
    if fpmm_paired_rows:
        families = sorted({row["run_family"] for row in fpmm_paired_rows})
        for run_family in [*families, "overall"]:
            subset = fpmm_paired_rows if run_family == "overall" else [
                row for row in fpmm_paired_rows if row["run_family"] == run_family
            ]
            if not subset:
                continue
            active_abs_wins = 0
            fpmm_abs_wins = 0
            active_sum = Decimal("0")
            fpmm_sum = Decimal("0")
            diff_sum = Decimal("0")
            for row in subset:
                active_gap = _to_decimal(row["active_lp_fairness_gap_nav_per_deposit"])
                fpmm_gap = _to_decimal(row["fpmm_fairness_gap_nav_per_deposit"])
                diff = _to_decimal(row["fpmm_minus_active_lp_gap"])
                active_sum += active_gap
                fpmm_sum += fpmm_gap
                diff_sum += diff
                if abs(active_gap) < abs(fpmm_gap):
                    active_abs_wins += 1
                elif abs(fpmm_gap) < abs(active_gap):
                    fpmm_abs_wins += 1
            count = Decimal(len(subset))
            fpmm_rows.append(
                {
                    "slice": run_family,
                    "scenario_count": len(subset),
                    "active_lp_mean_fairness_gap_nav_per_deposit": active_sum / count,
                    "fpmm_mean_fairness_gap_nav_per_deposit": fpmm_sum / count,
                    "mean_fpmm_minus_active_lp_gap": diff_sum / count,
                    "active_lp_abs_gap_wins": active_abs_wins,
                    "fpmm_abs_gap_wins": fpmm_abs_wins,
                }
            )

    layer_b_csv = out_dir / "table_layer_b_equivalence.csv"
    residual_rule_csv = out_dir / "table_residual_rule_comparison.csv"
    layer_c_csv = out_dir / "table_layer_c_regime_comparison.csv"
    high_skew_csv = out_dir / "table_high_skew_entry_boundary.csv"
    fpmm_csv = out_dir / "table_fpmm_comparison.csv"
    low_tail_trace_csv = out_dir / "table_low_tail_failure_trace.csv"
    markdown_path = out_dir / "paper_tables.md"

    _write_csv(layer_b_csv, layer_b_rows)
    _write_csv(residual_rule_csv, residual_rule_rows)
    _write_csv(layer_c_csv, layer_c_rows)
    _write_csv(high_skew_csv, high_skew_rows)
    _write_csv(fpmm_csv, fpmm_rows)
    low_tail_trace_rows = _read_csv_rows(low_tail_trace_csv)

    markdown = "\n\n".join(
        [
            "# Paper Tables",
            "## Layer B Equivalence Summary",
            _markdown_table(layer_b_rows, ["metric", "value"]),
            "## Residual Rule Comparison",
            _markdown_table(
                residual_rule_rows,
                ["rule", "mean_fairness_gap_nav_per_deposit", "max_abs_fairness_gap_nav_per_deposit", "invariant_failure_count", "interpretation"],
            ),
            "## Layer C Regime Comparison",
            _markdown_table(layer_c_rows, ["metric", "ordinary_target_regime", "low_tail_regime"]),
            "## High-Skew Late-Entry Boundary",
            _markdown_table(
                high_skew_rows,
                [
                    "slice",
                    "scenario_count",
                    "max_entry_probability",
                    "mean_fairness_gap_nav_per_deposit",
                    "min_fairness_gap_nav_per_deposit",
                    "max_fairness_gap_nav_per_deposit",
                    "interpretation",
                ],
            ),
            "## Active LP vs FPMM",
            _markdown_table(
                fpmm_rows,
                [
                    "slice",
                    "scenario_count",
                    "active_lp_mean_fairness_gap_nav_per_deposit",
                    "fpmm_mean_fairness_gap_nav_per_deposit",
                    "mean_fpmm_minus_active_lp_gap",
                    "active_lp_abs_gap_wins",
                    "fpmm_abs_gap_wins",
                ],
            ),
            "## Representative Low-Tail Failure Trace",
            _markdown_table(
                low_tail_trace_rows,
                [
                    "event_index",
                    "event_label",
                    "depth_b",
                    "p_min",
                    "p_max",
                    "reserve_margin",
                    "min_cohort_margin",
                ],
            )
            if low_tail_trace_rows
            else "Representative low-tail failure trace not available.",
        ]
    )
    markdown_path.write_text(markdown + "\n", encoding="utf-8")

    return {
        "layer_b_equivalence_csv": layer_b_csv,
        "residual_rule_comparison_csv": residual_rule_csv,
        "layer_c_regime_comparison_csv": layer_c_csv,
        "high_skew_entry_boundary_csv": high_skew_csv,
        "fpmm_comparison_csv": fpmm_csv,
        **({"low_tail_failure_trace_csv": low_tail_trace_csv} if low_tail_trace_rows else {}),
        "paper_tables_md": markdown_path,
    }
