from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from research.active_lp.events import (
    BootstrapMarket,
    BuyOutcome,
    CancelMarket,
    ClaimLpFees,
    ClaimLpResidual,
    ClaimRefund,
    ClaimWinnings,
    LpEnterActive,
    ResolveMarket,
    SellOutcome,
    WithdrawLpFees,
)
from research.active_lp.figures import write_low_tail_failure_trace_figure
from research.active_lp.layer_c_analysis import build_layer_c_low_tail_config
from research.active_lp.layer_c_fixed_point import (
    LayerCFixedPointEngine,
    LayerCInvariantChecker,
    create_layer_c_initial_state,
)
from research.active_lp.monte_carlo import generate_monte_carlo_bundles
from research.active_lp.precision import DECIMAL_ZERO, to_decimal
from research.active_lp.reference_parallel_lmsr import (
    ReferenceInvariantChecker,
    ReferenceParallelLmsrEngine,
    _current_price_vector,
    _total_non_fee_assets,
    _winner_reserve_requirement,
    create_initial_state,
)

DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


@dataclass(slots=True)
class LowTailFailureSelection:
    scenario_name: str
    min_margin: Decimal
    failure_event_index: int


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


def _parse_decimal_tail(details: str, prefix: str) -> Decimal:
    if prefix not in details:
        return DECIMAL_ZERO
    tail = details.split(prefix, 1)[1]
    value = tail.split(",", 1)[0].strip()
    return Decimal(value)


def _select_representative_failure(results_path: Path) -> LowTailFailureSelection | None:
    if not results_path.exists():
        return None
    best: LowTailFailureSelection | None = None
    with results_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if str(record.get("mechanism")) != "reference_parallel_lmsr":
                continue
            failures = record.get("evaluation", {}).get("exact_vs_simplified_divergence", {}).get("invariant_failures", [])
            for failure in failures:
                if failure.get("name") != "sponsor_solvency":
                    continue
                min_margin = _parse_decimal_tail(str(failure.get("details", "")), "min_margin=")
                candidate = LowTailFailureSelection(
                    scenario_name=str(record["scenario_name"]),
                    min_margin=min_margin,
                    failure_event_index=int(failure["event_index"]),
                )
                if best is None or candidate.min_margin < best.min_margin:
                    best = candidate
    return best


def _event_label(event: object) -> str:
    if isinstance(event, BootstrapMarket):
        return "Bootstrap"
    if isinstance(event, BuyOutcome):
        return "Buy"
    if isinstance(event, SellOutcome):
        return "Sell"
    if isinstance(event, LpEnterActive):
        return "LP Enter"
    if isinstance(event, ResolveMarket):
        return "Resolve"
    if isinstance(event, CancelMarket):
        return "Cancel"
    if isinstance(event, ClaimWinnings):
        return "Claim Win"
    if isinstance(event, ClaimRefund):
        return "Claim Refund"
    if isinstance(event, ClaimLpFees):
        return "Claim Fees"
    if isinstance(event, WithdrawLpFees):
        return "Withdraw Fees"
    if isinstance(event, ClaimLpResidual):
        return "Claim LP"
    return type(event).__name__


def _price_bounds(state) -> tuple[Decimal, Decimal]:
    prices = tuple(map(to_decimal, _current_price_vector(state)))
    if not prices:
        return (DECIMAL_ZERO, DECIMAL_ZERO)
    return (min(prices), max(prices))


def _reserve_margin(state) -> Decimal:
    return _total_non_fee_assets(state) - _winner_reserve_requirement(state)


def _replay_reference_trace(bundle) -> list[dict[str, object]]:
    config = bundle.config
    engine = ReferenceParallelLmsrEngine(
        lp_fee_bps=config.fee_bps,
        protocol_fee_bps=config.protocol_fee_bps,
        residual_weight_scheme=config.residual_weight_scheme,
        residual_linear_lambda=config.residual_linear_lambda,
    )
    checker = ReferenceInvariantChecker()
    state = create_initial_state(
        config.num_outcomes,
        residual_weight_scheme=config.residual_weight_scheme,
        residual_linear_lambda=config.residual_linear_lambda,
    )
    rows: list[dict[str, object]] = []
    for event in bundle.primary_path.events:
        state = engine.apply_event(state, event)
        sponsor_check = checker.check_sponsor_solvency(state)
        p_min, p_max = _price_bounds(state)
        rows.append(
            {
                "event_index": state.event_index,
                "timestamp": state.pricing.timestamp,
                "event_label": _event_label(event),
                "event_kind": getattr(event, "kind", type(event).__name__),
                "depth_b": to_decimal(state.pricing.depth_b),
                "p_min": p_min,
                "p_max": p_max,
                "reserve_margin": _reserve_margin(state),
                "min_margin": _parse_decimal_tail(str(sponsor_check.details), "min_margin="),
            }
        )
    return rows


def _replay_layer_c_trace(bundle) -> list[dict[str, object]]:
    config = bundle.config
    engine = LayerCFixedPointEngine(
        lp_fee_bps=config.fee_bps,
        protocol_fee_bps=config.protocol_fee_bps,
    )
    checker = LayerCInvariantChecker()
    state = create_layer_c_initial_state(config.num_outcomes)
    rows: list[dict[str, object]] = []
    for event in bundle.primary_path.events:
        state = engine.apply_event(state, event)
        sponsor_check = checker.check_sponsor_solvency(state)
        p_min, p_max = _price_bounds(state)
        rows.append(
            {
                "event_index": state.event_index,
                "timestamp": state.pricing.timestamp,
                "event_label": _event_label(event),
                "event_kind": getattr(event, "kind", type(event).__name__),
                "depth_b": to_decimal(state.pricing.depth_b),
                "p_min": p_min,
                "p_max": p_max,
                "reserve_margin": _reserve_margin(state),
                "min_margin": _parse_decimal_tail(str(sponsor_check.details), "min_margin="),
            }
        )
    return rows


def build_low_tail_failure_trace_artifacts(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    artifact_dir: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    selection = _select_representative_failure(root / "layer_c_low_tail_compare" / "results.jsonl")
    if selection is None:
        return {}

    config = build_layer_c_low_tail_config()
    bundles = {bundle.config.name: bundle for bundle in generate_monte_carlo_bundles(config.monte_carlo)}
    bundle = bundles.get(selection.scenario_name)
    if bundle is None:
        return {}

    trace_dir = root / "low_tail_failure_trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    paper_dir = Path(artifact_dir) if artifact_dir is not None else root / "paper_artifacts"
    paper_dir.mkdir(parents=True, exist_ok=True)

    reference_rows = _replay_reference_trace(bundle)
    layer_c_rows = _replay_layer_c_trace(bundle)
    merged_rows: list[dict[str, object]] = []
    compact_rows: list[dict[str, object]] = []
    for reference_row, layer_c_row in zip(reference_rows, layer_c_rows):
        merged_rows.append(
            {
                "scenario_name": selection.scenario_name,
                "event_index": reference_row["event_index"],
                "timestamp": reference_row["timestamp"],
                "event_label": reference_row["event_label"],
                "event_kind": reference_row["event_kind"],
                "reference_depth_b": reference_row["depth_b"],
                "reference_p_min": reference_row["p_min"],
                "reference_p_max": reference_row["p_max"],
                "reference_reserve_margin": reference_row["reserve_margin"],
                "reference_min_margin": reference_row["min_margin"],
                "layer_c_depth_b": layer_c_row["depth_b"],
                "layer_c_p_min": layer_c_row["p_min"],
                "layer_c_p_max": layer_c_row["p_max"],
                "layer_c_reserve_margin": layer_c_row["reserve_margin"],
                "layer_c_min_margin": layer_c_row["min_margin"],
            }
        )
        compact_rows.append(
            {
                "event_index": reference_row["event_index"],
                "event_label": reference_row["event_label"],
                "depth_b": reference_row["depth_b"],
                "p_min": reference_row["p_min"],
                "p_max": reference_row["p_max"],
                "reserve_margin": reference_row["reserve_margin"],
                "min_cohort_margin": reference_row["min_margin"],
            }
        )

    trace_csv = trace_dir / "trace.csv"
    table_csv = paper_dir / "table_low_tail_failure_trace.csv"
    summary_json = trace_dir / "summary.json"
    figure_svg = paper_dir / "low_tail_failure_trace.svg"

    _write_csv(trace_csv, merged_rows)
    _write_csv(table_csv, compact_rows)
    write_low_tail_failure_trace_figure(merged_rows, figure_svg)

    summary = {
        "scenario_name": selection.scenario_name,
        "num_outcomes": bundle.config.num_outcomes,
        "failure_event_index": selection.failure_event_index,
        "reference_min_margin": str(min(Decimal(str(row["reference_min_margin"])) for row in merged_rows)),
        "layer_c_min_margin": str(min(Decimal(str(row["layer_c_min_margin"])) for row in merged_rows)),
        "reference_reserve_margin_min": str(min(Decimal(str(row["reference_reserve_margin"])) for row in merged_rows)),
        "layer_c_reserve_margin_min": str(min(Decimal(str(row["layer_c_reserve_margin"])) for row in merged_rows)),
    }
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "low_tail_failure_trace_csv": trace_csv,
        "low_tail_failure_trace_table_csv": table_csv,
        "low_tail_failure_trace_svg": figure_svg,
        "low_tail_failure_trace_summary_json": summary_json,
    }
