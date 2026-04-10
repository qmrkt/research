from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from research.active_lp.figures import (
    write_layer_c_regime_comparison_figure,
    write_residual_rule_comparison_figure,
    write_residual_weight_calibration_figure,
)
from research.active_lp.low_tail_trace import build_low_tail_failure_trace_artifacts
from research.active_lp.paper_tables import build_paper_tables

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


@dataclass(slots=True)
class ResidualWeightSweepSource:
    name: str
    summary_path: Path


def default_residual_weight_sources(output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> list[ResidualWeightSweepSource]:
    root = Path(output_root)
    return [
        ResidualWeightSweepSource("core", root / "residual_weight_sweep_core" / "parameter_summary.csv"),
        ResidualWeightSweepSource("fine", root / "residual_weight_sweep_fine" / "parameter_summary.csv"),
        ResidualWeightSweepSource("tune", root / "residual_weight_sweep_tune" / "parameter_summary.csv"),
        ResidualWeightSweepSource("paper_candidates", root / "residual_weight_paper_candidates" / "parameter_summary.csv"),
        ResidualWeightSweepSource("paper_tight", root / "residual_weight_paper_tight" / "parameter_summary.csv"),
        ResidualWeightSweepSource("paper_midpoint", root / "residual_weight_paper_midpoint" / "parameter_summary.csv"),
    ]


def load_residual_weight_rows(
    sources: list[ResidualWeightSweepSource] | None = None,
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in sources or default_residual_weight_sources(output_root):
        if not source.summary_path.exists():
            continue
        with source.summary_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                enriched = dict(row)
                enriched["source"] = source.name
                enriched["summary_path"] = str(source.summary_path)
                rows.append(enriched)
    return rows


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
    return Decimal(str(value))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_paper_artifacts(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    artifact_dir: str | Path | None = None,
    highlight_name: str = "linear_lambda_003250",
) -> dict[str, Path]:
    root = Path(output_root)
    out_dir = Path(artifact_dir) if artifact_dir is not None else root / "paper_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = load_residual_weight_rows(output_root=root)
    calibration_rows = [
        row
        for row in all_rows
        if row.get("scheme") == "linear_lambda" and _to_decimal(row["linear_lambda"]) <= Decimal("0.05")
    ]
    calibration_rows.sort(key=lambda row: (_to_decimal(row["linear_lambda"]), str(row["source"]), str(row["name"])))

    csv_path = out_dir / "residual_weight_calibration_points.csv"
    _write_csv(csv_path, calibration_rows)

    svg_path = write_residual_weight_calibration_figure(
        calibration_rows,
        out_dir / "residual_weight_calibration.svg",
        highlight_name=highlight_name,
    )

    candidate_row = next((row for row in calibration_rows if row["name"] == highlight_name), None)
    overview = {
        "figure_scope": "first_stage_event_step_calibration",
        "highlight_name": highlight_name,
        "highlight_mean_fairness_gap_nav_per_deposit": candidate_row["mean_fairness_gap_nav_per_deposit"]
        if candidate_row is not None
        else None,
        "highlight_linear_lambda": candidate_row["linear_lambda"] if candidate_row is not None else None,
        "source_count": len({row["source"] for row in calibration_rows}),
        "point_count": len(calibration_rows),
    }
    selection_summary_path = root / "lambda_selection_summary.json"
    if selection_summary_path.exists():
        selection_summary = json.loads(selection_summary_path.read_text(encoding="utf-8"))
        normalized_selection = dict(selection_summary.get("normalized", {}).get("parameter", {}))
        if normalized_selection:
            overview["current_protocol_default_name"] = normalized_selection.get("name")
            overview["current_protocol_default_scheme"] = normalized_selection.get("scheme")
            overview["current_protocol_default_linear_lambda"] = normalized_selection.get("linear_lambda")
    json_path = out_dir / "paper_artifacts_overview.json"
    json_path.write_text(json.dumps(overview, indent=2, sort_keys=True), encoding="utf-8")

    layer_c_target = json.loads((root / "layer_c_compare_target" / "aggregate.json").read_text(encoding="utf-8"))
    layer_c_low_tail = json.loads((root / "layer_c_low_tail_compare" / "aggregate.json").read_text(encoding="utf-8"))

    layer_c_regime_figure = write_layer_c_regime_comparison_figure(
        [
            {
                "label": "mean quote diff delta",
                "value": _to_decimal(layer_c_low_tail["mean_divergence_max_quote_diff_vs_reference"])
                - _to_decimal(layer_c_target["mean_divergence_max_quote_diff_vs_reference"]),
            },
            {
                "label": "max quote diff delta",
                "value": _to_decimal(layer_c_low_tail["max_divergence_max_quote_diff_vs_reference"])
                - _to_decimal(layer_c_target["max_divergence_max_quote_diff_vs_reference"]),
            },
            {
                "label": "mean nav diff delta",
                "value": _to_decimal(layer_c_low_tail["mean_divergence_max_nav_per_deposit_diff_vs_reference"])
                - _to_decimal(layer_c_target["mean_divergence_max_nav_per_deposit_diff_vs_reference"]),
            },
            {
                "label": "invariant failures delta",
                "value": _to_decimal(layer_c_low_tail["invariant_failure_count"])
                - _to_decimal(layer_c_target["invariant_failure_count"]),
            },
        ],
        out_dir / "layer_c_regime_comparison.svg",
    )

    low_tail_trace_outputs = build_low_tail_failure_trace_artifacts(output_root=root, artifact_dir=out_dir)
    table_outputs = build_paper_tables(output_root=root, table_dir=out_dir)
    residual_rule_rows = _read_csv_rows(table_outputs["residual_rule_comparison_csv"])
    residual_rule_labels = {
        "flat_reserve": "flat",
        "linear_time_weighted": "linear",
        "affine_calibrated_0.03250": "affine 0.03250",
    }
    residual_rule_figure = write_residual_rule_comparison_figure(
        [
            {
                "label": residual_rule_labels.get(row["rule"], row["rule"].replace("affine_normalized_", "affine norm ")),
                "value": row["mean_fairness_gap_nav_per_deposit"],
            }
            for row in residual_rule_rows
        ],
        out_dir / "residual_rule_comparison.svg",
    )

    return {
        "calibration_points_csv": csv_path,
        "calibration_svg": svg_path,
        "overview_json": json_path,
        "residual_rule_comparison_svg": residual_rule_figure,
        "layer_c_regime_comparison_svg": layer_c_regime_figure,
        **low_tail_trace_outputs,
        **table_outputs,
    }
