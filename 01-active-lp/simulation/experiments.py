from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from research.active_lp.candidate_global_state import (
    CandidateGlobalStateEngine,
    CandidateMetricCollector,
    CandidateScenarioRunner,
    create_candidate_initial_state,
)
from research.active_lp.fpmm_baseline import (
    FpmmBaselineEngine,
    FpmmMetricCollector,
    FpmmScenarioRunner,
    create_fpmm_initial_state,
)
from research.active_lp.layer_c_fixed_point import (
    LayerCFixedPointEngine,
    LayerCMetricCollector,
    LayerCScenarioRunner,
    create_layer_c_initial_state,
)
from research.active_lp.metrics import CanonicalEvaluation
from research.active_lp.reference_parallel_lmsr import (
    ReferenceMetricCollector,
    ReferenceParallelLmsrEngine,
    ReferenceScenarioRunner,
    RESERVE_POOL,
    STRICT_ALL_CLAIMED,
    create_initial_state,
)
from research.active_lp.scenarios import ScenarioBundle, ScenarioConfig, build_deterministic_scenarios
from research.active_lp.state import SimulationState
from research.active_lp.types import MechanismVariant


@dataclass(slots=True)
class ExperimentResult:
    run_family: str
    scenario_name: str
    description: str
    mechanism: MechanismVariant
    config: ScenarioConfig
    primary_path_label: str
    path_labels: tuple[str, ...]
    event_count: int
    evaluation: CanonicalEvaluation


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _first_reference_trade_size(config: ScenarioConfig) -> Decimal:
    if not config.reference_trades:
        return Decimal("1")
    return Decimal(config.reference_trades[0].shares)


def _run_reference_state(config: ScenarioConfig, events: tuple[object, ...] | list[object]) -> SimulationState:
    engine = ReferenceParallelLmsrEngine(lp_fee_bps=config.fee_bps, protocol_fee_bps=config.protocol_fee_bps)
    state = create_initial_state(config.num_outcomes)
    for event in events:
        state = engine.apply_event(state, event)
    return state


def _state_for_mechanism(
    config: ScenarioConfig,
    mechanism: MechanismVariant,
    events: tuple[object, ...] | list[object],
) -> SimulationState:
    if mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR:
        engine = ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        state = create_initial_state(
            config.num_outcomes,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
    elif mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL:
        engine = ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_policy=RESERVE_POOL,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        state = create_initial_state(
            config.num_outcomes,
            mechanism=mechanism,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
    elif mechanism is MechanismVariant.FPMM_POOL_SHARE:
        engine = FpmmBaselineEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
        )
        state = create_fpmm_initial_state(config.num_outcomes)
    elif mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL:
        engine = CandidateGlobalStateEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        state = create_candidate_initial_state(
            config.num_outcomes,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
    elif mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL:
        engine = CandidateGlobalStateEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_policy=RESERVE_POOL,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        state = create_candidate_initial_state(
            config.num_outcomes,
            mechanism=mechanism,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
    elif mechanism is MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT:
        engine = LayerCFixedPointEngine(lp_fee_bps=config.fee_bps, protocol_fee_bps=config.protocol_fee_bps)
        state = create_layer_c_initial_state(config.num_outcomes)
    else:
        raise NotImplementedError(f"mechanism not implemented yet: {mechanism.value}")
    for event in events:
        state = engine.apply_event(state, event)
    return state


def _collector_for_mechanism(
    mechanism: MechanismVariant,
) -> ReferenceMetricCollector | CandidateMetricCollector | FpmmMetricCollector:
    if mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR:
        return ReferenceMetricCollector()
    if mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL:
        return ReferenceMetricCollector(residual_policy=RESERVE_POOL)
    if mechanism is MechanismVariant.FPMM_POOL_SHARE:
        return FpmmMetricCollector()
    if mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL:
        return CandidateMetricCollector()
    if mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL:
        return CandidateMetricCollector(residual_policy=RESERVE_POOL)
    if mechanism is MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT:
        return LayerCMetricCollector()
    raise NotImplementedError(f"mechanism not implemented yet: {mechanism.value}")


def _runner_for_mechanism(
    config: ScenarioConfig,
    mechanism: MechanismVariant,
) -> ReferenceScenarioRunner | CandidateScenarioRunner | FpmmScenarioRunner:
    if mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR:
        engine = ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        return ReferenceScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            collector=ReferenceMetricCollector(residual_policy=STRICT_ALL_CLAIMED),
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    if mechanism is MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL:
        engine = ReferenceParallelLmsrEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_policy=RESERVE_POOL,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        return ReferenceScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            collector=ReferenceMetricCollector(residual_policy=RESERVE_POOL),
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    if mechanism is MechanismVariant.FPMM_POOL_SHARE:
        engine = FpmmBaselineEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
        )
        return FpmmScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            collector=FpmmMetricCollector(
                lp_fee_bps=config.fee_bps,
                protocol_fee_bps=config.protocol_fee_bps,
            ),
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    if mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_COHORT_RESIDUAL:
        engine = CandidateGlobalStateEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        return CandidateScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            collector=CandidateMetricCollector(residual_policy=STRICT_ALL_CLAIMED),
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    if mechanism is MechanismVariant.GLOBAL_STATE_FUNGIBLE_FEES_RESERVE_RESIDUAL:
        engine = CandidateGlobalStateEngine(
            lp_fee_bps=config.fee_bps,
            protocol_fee_bps=config.protocol_fee_bps,
            residual_policy=RESERVE_POOL,
            residual_weight_scheme=config.residual_weight_scheme,
            residual_linear_lambda=config.residual_linear_lambda,
        )
        return CandidateScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            collector=CandidateMetricCollector(residual_policy=RESERVE_POOL),
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    if mechanism is MechanismVariant.GLOBAL_STATE_AVM_FIXED_POINT:
        engine = LayerCFixedPointEngine(lp_fee_bps=config.fee_bps, protocol_fee_bps=config.protocol_fee_bps)
        return LayerCScenarioRunner(
            num_outcomes=config.num_outcomes,
            engine=engine,
            reference_trade_size=_first_reference_trade_size(config),
            reference_trades=config.reference_trades,
        )
    raise NotImplementedError(f"mechanism not implemented yet: {mechanism.value}")


def _summary_record(result: ExperimentResult) -> dict[str, str]:
    evaluation = result.evaluation
    fairness_rows = evaluation.lp_fairness_by_entry_time.get("rows", [])
    invariant_failures = evaluation.exact_vs_simplified_divergence.get("invariant_failures", [])
    divergence = evaluation.exact_vs_simplified_divergence
    return {
        "run_family": result.run_family,
        "scenario_name": result.scenario_name,
        "description": result.description,
        "mechanism": result.mechanism.value,
        "num_outcomes": str(result.config.num_outcomes),
        "duration_steps": str(result.config.duration_steps or ""),
        "duration_bucket": str(result.config.duration_bucket or ""),
        "clock_mode": str(result.config.clock_mode),
        "split": str(result.config.split or ""),
        "fee_bps": str(result.config.fee_bps),
        "protocol_fee_bps": str(result.config.protocol_fee_bps),
        "event_count": str(result.event_count),
        "path_labels": "|".join(result.path_labels),
        "max_price_change": str(result.evaluation.price_continuity.get("max_abs_change", "")),
        "all_prices_within_tolerance": str(result.evaluation.price_continuity.get("all_within_tolerance", "")),
        "all_buy_quotes_improved": str(result.evaluation.slippage_improvement.get("all_buy_quotes_improved", "")),
        "lp_fairness_rows": str(len(fairness_rows)),
        "solvency_passed": str(result.evaluation.solvency.get("passed", "")),
        "path_terminal_states": str(result.evaluation.path_dependence.get("terminal_states", "")),
        "path_max_price_diff": str(result.evaluation.path_dependence.get("max_price_diff", "")),
        "path_max_funds_diff": str(result.evaluation.path_dependence.get("max_funds_diff", "")),
        "path_max_residual_claimed_diff": str(result.evaluation.path_dependence.get("max_residual_claimed_diff", "")),
        "reserve_required": str(result.evaluation.residual_release.get("reserve_required", "")),
        "releasable_pool": str(result.evaluation.residual_release.get("releasable_pool", "")),
        "total_residual_claimed": str(result.evaluation.residual_release.get("total_residual_claimed", "")),
        "divergence_implemented": str(divergence.get("implemented", "")),
        "divergence_max_price_entry_diff": str(divergence.get("max_price_entry_diff_vs_reference", "")),
        "divergence_max_quote_diff": str(divergence.get("max_quote_diff_vs_reference", "")),
        "divergence_max_nav_diff": str(divergence.get("max_nav_diff_vs_reference", "")),
        "divergence_max_nav_per_deposit_diff": str(divergence.get("max_nav_per_deposit_diff_vs_reference", "")),
        "divergence_solvency_match": str(divergence.get("solvency_match", "")),
        "invariant_failures": str(len(invariant_failures)),
    }


class ExperimentRunner:
    def __init__(self) -> None:
        self.collector = ReferenceMetricCollector()

    def run_bundle(self, bundle: ScenarioBundle, *, run_family: str = "bundle") -> list[ExperimentResult]:
        results: list[ExperimentResult] = []
        all_paths = (bundle.primary_path,) + bundle.alternate_paths
        evaluations: dict[MechanismVariant, CanonicalEvaluation] = {}

        for mechanism in bundle.config.mechanisms:
            runner = _runner_for_mechanism(bundle.config, mechanism)
            collector = _collector_for_mechanism(mechanism)
            evaluation = runner.run(list(bundle.primary_path.events), mechanism)
            if len(all_paths) > 1:
                final_states = [_state_for_mechanism(bundle.config, mechanism, path.events) for path in all_paths]
                evaluation.path_dependence = {
                    **collector.path_dependence(final_states),
                    "labels": [path.label for path in all_paths],
                }
            evaluations[mechanism] = evaluation

        reference_evaluation = (
            evaluations.get(MechanismVariant.REFERENCE_PARALLEL_LMSR)
            or evaluations.get(MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL)
        )
        if reference_evaluation is not None:
            for mechanism, evaluation in evaluations.items():
                if mechanism in (
                    MechanismVariant.REFERENCE_PARALLEL_LMSR,
                    MechanismVariant.REFERENCE_PARALLEL_LMSR_RESERVE_RESIDUAL,
                ):
                    continue
                collector = _collector_for_mechanism(mechanism)
                divergence = collector.divergence(reference_evaluation, evaluation)
                evaluation.exact_vs_simplified_divergence = {
                    **divergence,
                    "invariant_failures": list(evaluation.exact_vs_simplified_divergence.get("invariant_failures", [])),
                }

        for mechanism in bundle.config.mechanisms:
            results.append(
                ExperimentResult(
                    run_family=run_family,
                    scenario_name=bundle.config.name,
                    description=bundle.description,
                    mechanism=mechanism,
                    config=bundle.config,
                    primary_path_label=bundle.primary_path.label,
                    path_labels=tuple(path.label for path in all_paths),
                    event_count=len(bundle.primary_path.events),
                    evaluation=evaluations[mechanism],
                )
            )
        return results

    def run_bundles(self, bundles: list[ScenarioBundle], *, run_family: str = "bundle") -> list[ExperimentResult]:
        results: list[ExperimentResult] = []
        for bundle in bundles:
            results.extend(self.run_bundle(bundle, run_family=run_family))
        return results

    def run_deterministic_suite(self, names: tuple[str, ...] | list[str] | None = None) -> list[ExperimentResult]:
        return self.run_bundles(build_deterministic_scenarios(names), run_family="deterministic")


def write_experiment_results(
    results: list[ExperimentResult],
    output_dir: str | Path,
    *,
    manifest_label: str,
) -> dict[str, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_dir / "results.jsonl"
    summary_path = out_dir / "summary.csv"
    manifest_path = out_dir / "manifest.json"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for result in results:
            record = _json_safe(asdict(result))
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

    summary_rows = [_summary_record(result) for result in results]
    fieldnames: list[str] = []
    for row in summary_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    manifest = {
        "label": manifest_label,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "result_count": len(results),
        "run_families": sorted({result.run_family for result in results}),
        "scenario_names": sorted({result.scenario_name for result in results}),
        "mechanisms": sorted({result.mechanism.value for result in results}),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "results_jsonl": jsonl_path,
        "summary_csv": summary_path,
        "manifest_json": manifest_path,
    }
