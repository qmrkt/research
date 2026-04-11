"""CLI entry point for the resolution trust simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.resolution_trust.metrics import print_summary, write_results_csv, write_results_json
from research.resolution_trust.scenarios import SCENARIO_FAMILIES, all_scenarios
from research.resolution_trust.simulation import run_parameter_sweep

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run resolution trust dispute simulations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run a single scenario family
    run = subparsers.add_parser("run", help="Run a scenario family")
    run.add_argument(
        "family",
        choices=list(SCENARIO_FAMILIES.keys()),
        help="Scenario family to run.",
    )
    run.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory.",
    )
    run.add_argument("--episodes", type=int, default=5000, help="Episodes per config.")

    # Run all scenario families
    run_all = subparsers.add_parser("run-all", help="Run all scenario families")
    run_all.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory.",
    )
    run_all.add_argument("--episodes", type=int, default=5000, help="Episodes per config.")

    # Generate paper artifacts
    artifacts = subparsers.add_parser("paper-artifacts", help="Run all and generate paper tables")
    artifacts.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory.",
    )
    artifacts.add_argument("--episodes", type=int, default=5000, help="Episodes per config.")

    # List available families
    subparsers.add_parser("list", help="List available scenario families")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        print("Available scenario families:")
        for name, fn in SCENARIO_FAMILIES.items():
            configs = fn()
            print(f"  {name}: {len(configs)} configurations")
        return

    if args.command == "run":
        configs = SCENARIO_FAMILIES[args.family]()
        # Override episodes
        from dataclasses import replace
        configs = [replace(c, num_episodes=args.episodes) for c in configs]

        print(f"Running {args.family}: {len(configs)} configurations, {args.episodes} episodes each")
        results = run_parameter_sweep(configs)
        print_summary(args.family, results)

        out_dir = args.output_dir / args.family
        write_results_csv(results, out_dir / f"{args.family}.csv")
        write_results_json(results, out_dir / f"{args.family}.json")
        print(f"Results written to {out_dir}")
        return

    if args.command in ("run-all", "paper-artifacts"):
        families = all_scenarios()
        all_results: dict[str, list] = {}

        for name, configs in families.items():
            from dataclasses import replace
            configs = [replace(c, num_episodes=args.episodes) for c in configs]
            print(f"Running {name}: {len(configs)} configurations...")
            results = run_parameter_sweep(configs)
            print_summary(name, results)
            all_results[name] = results

            out_dir = args.output_dir / name
            write_results_csv(results, out_dir / f"{name}.csv")

        if args.command == "paper-artifacts":
            from research.resolution_trust.figures import write_overview_json, write_paper_tables
            write_paper_tables(all_results)
            write_overview_json(all_results)

        total = sum(len(r) for r in all_results.values())
        print(f"\nComplete: {total} configurations across {len(all_results)} families.")
        return


if __name__ == "__main__":
    main()
