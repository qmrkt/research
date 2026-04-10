from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from research.active_lp.adversarial_search import AdversarialSearchConfig, run_adversarial_search
from research.active_lp.calibration_upgrade import CalibrationUpgradeConfig, run_calibration_upgrade
from research.active_lp.experiments import ExperimentRunner, write_experiment_results
from research.active_lp.fpmm_comparison import FpmmComparisonConfig, run_fpmm_head_to_head
from research.active_lp.figures import write_figure_pack
from research.active_lp.layer_c_analysis import (
    LayerCParameterSet,
    build_layer_c_low_tail_config,
    build_layer_c_sell_heavy_config,
    build_layer_c_target_config,
    run_layer_c_parameter_sweep,
    run_layer_c_target_analysis,
    write_layer_c_analysis_pack,
)
from research.active_lp.layer_c_fixed_point import FP_ENTRY_SAFETY_MARGIN, FP_PRICE_FLOOR
from research.active_lp.monte_carlo import MonteCarloSweepConfig, run_monte_carlo_sweep
from research.active_lp.paper_artifacts import build_paper_artifacts
from research.active_lp.reporting import aggregate_results, write_aggregated_report
from research.active_lp.residual_weight_analysis import run_residual_weight_sweep
from research.active_lp.scenarios import deterministic_scenario_names
from research.active_lp.sweep_presets import build_sweep_preset, sweep_preset_names

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run active-LP research simulations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    deterministic = subparsers.add_parser("deterministic", help="Run named deterministic scenarios")
    deterministic.add_argument(
        "--scenario",
        action="append",
        choices=deterministic_scenario_names(),
        help="Scenario name to run; omit to run the full deterministic suite.",
    )
    deterministic.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "deterministic",
        help="Directory for JSONL/CSV outputs.",
    )

    monte_carlo = subparsers.add_parser("monte-carlo", help="Run a Monte Carlo sweep")
    monte_carlo.add_argument("--num-trials", type=int, default=25, help="Number of randomized trials to generate.")
    monte_carlo.add_argument("--seed", type=int, default=1, help="Base RNG seed.")
    monte_carlo.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "monte_carlo",
        help="Directory for JSONL/CSV outputs.",
    )
    monte_carlo.add_argument("--name", default="active_lp_monte_carlo", help="Sweep name prefix.")
    monte_carlo.add_argument("--fee-bps", type=Decimal, action="append", help="Optional LP fee choices in basis points.")
    monte_carlo.add_argument(
        "--protocol-fee-bps",
        type=Decimal,
        action="append",
        help="Optional protocol fee choices in basis points.",
    )

    adversarial = subparsers.add_parser("adversarial", help="Run targeted adversarial fairness search")
    adversarial.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "adversarial",
        help="Directory for adversarial outputs.",
    )
    adversarial.add_argument("--name", default="active_lp_adversarial", help="Search name prefix.")

    preset = subparsers.add_parser("preset", help="Run a named combined sweep preset")
    preset.add_argument("--preset", choices=sweep_preset_names(), default="paper_quick", help="Preset to run.")
    preset.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "preset",
        help="Directory for preset outputs.",
    )

    layer_c_target = subparsers.add_parser("layer-c-target", help="Run the focused Layer C compare pack")
    layer_c_target.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "layer_c_target",
        help="Directory for Layer C target outputs.",
    )
    layer_c_target.add_argument("--price-floor-fp", type=int, default=FP_PRICE_FLOOR, help="Fixed-point price floor.")
    layer_c_target.add_argument(
        "--entry-safety-margin",
        type=int,
        default=FP_ENTRY_SAFETY_MARGIN,
        help="Extra fixed-point entry collateral margin.",
    )
    layer_c_target.add_argument(
        "--monte-carlo-trials",
        type=int,
        help="Optional override for Monte Carlo trial count.",
    )
    layer_c_target.add_argument(
        "--adversarial-limit",
        type=int,
        help="Optional cap on adversarial bundles.",
    )
    layer_c_target.add_argument(
        "--scenario",
        action="append",
        choices=deterministic_scenario_names(),
        help="Optional deterministic scenarios to include.",
    )

    layer_c_sell_heavy = subparsers.add_parser("layer-c-sell-heavy", help="Run the sell-heavy Layer C compare pack")
    layer_c_sell_heavy.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "layer_c_sell_heavy",
        help="Directory for Layer C sell-heavy outputs.",
    )
    layer_c_sell_heavy.add_argument("--price-floor-fp", type=int, default=FP_PRICE_FLOOR, help="Fixed-point price floor.")
    layer_c_sell_heavy.add_argument(
        "--entry-safety-margin",
        type=int,
        default=FP_ENTRY_SAFETY_MARGIN,
        help="Extra fixed-point entry collateral margin.",
    )
    layer_c_sell_heavy.add_argument(
        "--monte-carlo-trials",
        type=int,
        help="Optional override for Monte Carlo trial count.",
    )
    layer_c_sell_heavy.add_argument(
        "--adversarial-limit",
        type=int,
        help="Optional cap on adversarial bundles.",
    )
    layer_c_sell_heavy.add_argument(
        "--scenario",
        action="append",
        choices=deterministic_scenario_names(),
        help="Optional deterministic scenarios to include.",
    )

    layer_c_low_tail = subparsers.add_parser("layer-c-low-tail", help="Run the low-probability Layer C stress pack")
    layer_c_low_tail.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "layer_c_low_tail",
        help="Directory for Layer C low-tail outputs.",
    )
    layer_c_low_tail.add_argument("--price-floor-fp", type=int, default=FP_PRICE_FLOOR, help="Fixed-point price floor.")
    layer_c_low_tail.add_argument(
        "--entry-safety-margin",
        type=int,
        default=FP_ENTRY_SAFETY_MARGIN,
        help="Extra fixed-point entry collateral margin.",
    )
    layer_c_low_tail.add_argument(
        "--monte-carlo-trials",
        type=int,
        help="Optional override for Monte Carlo trial count.",
    )
    layer_c_low_tail.add_argument(
        "--adversarial-limit",
        type=int,
        help="Optional cap on adversarial bundles.",
    )

    layer_c_sweep = subparsers.add_parser("layer-c-sweep", help="Run a Layer C parameter sweep")
    layer_c_sweep.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "layer_c_sweep",
        help="Directory for Layer C sweep outputs.",
    )
    layer_c_sweep.add_argument(
        "--price-floor-fp",
        type=int,
        action="append",
        help="Fixed-point price floor choices; omit for 1, 10, 100.",
    )
    layer_c_sweep.add_argument(
        "--entry-safety-margin",
        type=int,
        action="append",
        help="Entry safety margin choices; omit for 1, 10, 100.",
    )
    layer_c_sweep.add_argument(
        "--monte-carlo-trials",
        type=int,
        default=8,
        help="Monte Carlo trials per parameter set.",
    )
    layer_c_sweep.add_argument(
        "--adversarial-limit",
        type=int,
        default=16,
        help="Adversarial bundles per parameter set.",
    )

    residual_weight = subparsers.add_parser("residual-weight-sweep", help="Run the reserve residual weighting sweep")
    residual_weight.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "residual_weight_sweep",
        help="Directory for residual-weight sweep outputs.",
    )
    residual_weight.add_argument(
        "--monte-carlo-trials",
        type=int,
        default=16,
        help="Monte Carlo trials per weighting function.",
    )
    residual_weight.add_argument(
        "--adversarial-limit",
        type=int,
        help="Optional cap on adversarial bundles per weighting function.",
    )

    paper_artifacts = subparsers.add_parser("paper-artifacts", help="Build paper-facing calibration artifacts from traced outputs")
    paper_artifacts.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Root directory containing traced simulation outputs.",
    )
    paper_artifacts.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "paper_artifacts",
        help="Directory for derived paper-facing artifacts.",
    )
    paper_artifacts.add_argument(
        "--highlight-name",
        default="linear_lambda_003250",
        help="Residual-weight parameter name to highlight in the calibration figure.",
    )

    fpmm_compare = subparsers.add_parser("fpmm-compare", help="Run the matched resolved-only Active-LP vs FPMM comparison pack")
    fpmm_compare.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "fpmm_compare_normalized_core",
        help="Directory for FPMM comparator outputs.",
    )
    fpmm_compare.add_argument(
        "--adversarial-limit",
        type=int,
        default=24,
        help="Maximum adversarial bundles to include.",
    )
    fpmm_compare.add_argument(
        "--high-skew-limit",
        type=int,
        default=12,
        help="Maximum high-skew bundles to include.",
    )

    calibration_upgrade = subparsers.add_parser(
        "calibration-upgrade",
        help="Run held-out event-clock vs normalized residual-weight calibration packs",
    )
    calibration_upgrade.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Root directory for calibration-upgrade outputs.",
    )
    calibration_upgrade.add_argument(
        "--train-monte-carlo-trials",
        type=int,
        default=64,
        help="Ordinary-regime train Monte Carlo bundle count before duration stamping.",
    )
    calibration_upgrade.add_argument(
        "--test-monte-carlo-trials",
        type=int,
        default=64,
        help="Ordinary-regime held-out test Monte Carlo bundle count before duration stamping.",
    )
    calibration_upgrade.add_argument(
        "--adversarial-limit",
        type=int,
        help="Optional cap on ordinary adversarial bundles per split.",
    )
    calibration_upgrade.add_argument(
        "--high-skew-monte-carlo-trials",
        type=int,
        default=16,
        help="High-skew boundary Monte Carlo bundle count.",
    )
    calibration_upgrade.add_argument(
        "--high-skew-adversarial-limit",
        type=int,
        default=24,
        help="High-skew boundary adversarial bundle cap.",
    )
    calibration_upgrade.add_argument(
        "--low-tail-monte-carlo-trials",
        type=int,
        default=16,
        help="Low-tail boundary Monte Carlo bundle count.",
    )
    calibration_upgrade.add_argument(
        "--low-tail-adversarial-limit",
        type=int,
        default=24,
        help="Low-tail boundary adversarial bundle cap.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    runner = ExperimentRunner()
    default_sweep = MonteCarloSweepConfig()

    def _write_analysis_outputs(results, output_dir: Path, manifest_label: str) -> None:
        write_experiment_results(results, output_dir, manifest_label=manifest_label)
        report = aggregate_results(results)
        write_aggregated_report(report, output_dir)
        write_figure_pack(report, output_dir)

    if args.command == "deterministic":
        scenario_names = tuple(args.scenario) if args.scenario else None
        results = runner.run_deterministic_suite(scenario_names)
        _write_analysis_outputs(results, args.output_dir, "deterministic")
        print(f"wrote {len(results)} deterministic results to {args.output_dir / 'summary.csv'}")
        return 0

    if args.command == "monte-carlo":
        sweep_config = MonteCarloSweepConfig(
            name=args.name,
            seed=args.seed,
            num_trials=args.num_trials,
            fee_bps_choices=tuple(args.fee_bps) if args.fee_bps else default_sweep.fee_bps_choices,
            protocol_fee_bps_choices=tuple(args.protocol_fee_bps)
            if args.protocol_fee_bps
            else default_sweep.protocol_fee_bps_choices,
        )
        results = run_monte_carlo_sweep(sweep_config, runner=runner)
        _write_analysis_outputs(results, args.output_dir, "monte_carlo")
        print(f"wrote {len(results)} Monte Carlo results to {args.output_dir / 'summary.csv'}")
        return 0

    if args.command == "adversarial":
        results = run_adversarial_search(AdversarialSearchConfig(name=args.name), runner=runner)
        _write_analysis_outputs(results, args.output_dir, "adversarial")
        print(f"wrote {len(results)} adversarial-search results to {args.output_dir / 'summary.csv'}")
        return 0

    if args.command == "preset":
        preset = build_sweep_preset(args.preset)
        deterministic_results = runner.run_deterministic_suite(preset.deterministic_names)
        monte_carlo_results = run_monte_carlo_sweep(preset.monte_carlo, runner=runner)
        adversarial_results = run_adversarial_search(preset.adversarial, runner=runner) if preset.adversarial else []
        combined_results = deterministic_results + monte_carlo_results + adversarial_results

        deterministic_dir = args.output_dir / "deterministic"
        monte_carlo_dir = args.output_dir / "monte_carlo"
        adversarial_dir = args.output_dir / "adversarial"
        combined_dir = args.output_dir / "combined"

        _write_analysis_outputs(deterministic_results, deterministic_dir, f"{preset.name}_deterministic")
        _write_analysis_outputs(monte_carlo_results, monte_carlo_dir, f"{preset.name}_monte_carlo")
        if adversarial_results:
            _write_analysis_outputs(adversarial_results, adversarial_dir, f"{preset.name}_adversarial")
        _write_analysis_outputs(combined_results, combined_dir, preset.name)

        print(
            f"wrote {len(combined_results)} preset results "
            f"({len(deterministic_results)} deterministic, {len(monte_carlo_results)} monte carlo, {len(adversarial_results)} adversarial) "
            f"to {combined_dir / 'summary.csv'}"
        )
        return 0

    if args.command in {"layer-c-target", "layer-c-sell-heavy", "layer-c-low-tail"}:
        parameter_set = LayerCParameterSet(
            name="custom",
            price_floor_fp=args.price_floor_fp,
            entry_safety_margin=args.entry_safety_margin,
        )
        scenario_arg = getattr(args, "scenario", None)
        deterministic_names = tuple(scenario_arg) if scenario_arg else None
        if args.command == "layer-c-target":
            config = build_layer_c_target_config(
                parameter_set=parameter_set,
                deterministic_names=deterministic_names,
                adversarial_limit=args.adversarial_limit,
            )
        elif args.command == "layer-c-sell-heavy":
            config = build_layer_c_sell_heavy_config(
                parameter_set=parameter_set,
                deterministic_names=deterministic_names,
                adversarial_limit=args.adversarial_limit,
            )
        else:
            config = build_layer_c_low_tail_config(
                parameter_set=parameter_set,
                adversarial_limit=args.adversarial_limit,
            )
        if args.monte_carlo_trials is not None:
            config.monte_carlo.num_trials = args.monte_carlo_trials
        results = run_layer_c_target_analysis(config, runner=runner)
        write_layer_c_analysis_pack(results, args.output_dir, manifest_label=args.command.replace("-", "_"))
        print(f"wrote {len(results)} Layer C comparison results to {args.output_dir / 'report.md'}")
        return 0

    if args.command == "layer-c-sweep":
        floor_values = args.price_floor_fp if args.price_floor_fp else [1, 10, 100]
        margin_values = args.entry_safety_margin if args.entry_safety_margin else [1, 10, 100]
        parameter_sets = [
            LayerCParameterSet(
                name=f"floor_{floor}_margin_{margin}",
                price_floor_fp=floor,
                entry_safety_margin=margin,
            )
            for floor in floor_values
            for margin in margin_values
        ]
        rows = run_layer_c_parameter_sweep(
            parameter_sets,
            monte_carlo_trials=args.monte_carlo_trials,
            adversarial_limit=args.adversarial_limit,
            output_dir=args.output_dir,
            runner=runner,
        )
        print(f"wrote {len(rows)} Layer C parameter rows to {args.output_dir / 'parameter_summary.csv'}")
        return 0

    if args.command == "residual-weight-sweep":
        rows = run_residual_weight_sweep(
            monte_carlo_trials=args.monte_carlo_trials,
            adversarial_limit=args.adversarial_limit,
            output_dir=args.output_dir,
            runner=runner,
        )
        print(f"wrote {len(rows)} residual-weight rows to {args.output_dir / 'parameter_summary.csv'}")
        return 0

    if args.command == "paper-artifacts":
        outputs = build_paper_artifacts(
            output_root=args.output_root,
            artifact_dir=args.output_dir,
            highlight_name=args.highlight_name,
        )
        print(f"wrote paper artifacts to {outputs['calibration_svg']}")
        return 0

    if args.command == "fpmm-compare":
        outputs = run_fpmm_head_to_head(
            config=FpmmComparisonConfig(
                adversarial_limit=args.adversarial_limit,
                high_skew_limit=args.high_skew_limit,
            ),
            output_dir=args.output_dir,
            runner=runner,
        )
        print(f"wrote FPMM comparison outputs to {outputs['paired_report_md']}")
        return 0

    if args.command == "calibration-upgrade":
        outputs = run_calibration_upgrade(
            config=CalibrationUpgradeConfig(
                train_monte_carlo_trials=args.train_monte_carlo_trials,
                test_monte_carlo_trials=args.test_monte_carlo_trials,
                adversarial_limit=args.adversarial_limit,
                high_skew_monte_carlo_trials=args.high_skew_monte_carlo_trials,
                high_skew_adversarial_limit=args.high_skew_adversarial_limit,
                low_tail_monte_carlo_trials=args.low_tail_monte_carlo_trials,
                low_tail_adversarial_limit=args.low_tail_adversarial_limit,
            ),
            output_root=args.output_dir,
            runner=runner,
        )
        print(f"wrote calibration-upgrade outputs to {outputs['report_md']}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
