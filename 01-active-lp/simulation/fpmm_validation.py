"""Re-run the published 44-pair comparator with explicit founder funding.

These are designed workloads, not random observations or causal information
treatments. Neither market permits LP withdrawal in this comparison.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from research.active_lp.adversarial_search import generate_adversarial_bundles
from research.active_lp.events import BootstrapMarket
from research.active_lp.experiments import ExperimentRunner, _json_safe, write_experiment_results
from research.active_lp.fpmm_comparison import (
    FpmmComparisonConfig, _overview, _paired_rows, _with_comparator_mechanisms,
    build_fpmm_adversarial_config, build_fpmm_deterministic_bundles,
    build_fpmm_high_skew_bundles,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector
from research.active_lp.publication_validation import write_csv, write_json


def rebase(bundle, funding):
    def path_rebase(path):
        events = []
        for event in path.events:
            if isinstance(event, BootstrapMarket):
                floor = collateral_required(Decimal(event.initial_depth_b), uniform_price_vector(bundle.config.num_outcomes))
                amount = {"floor": floor, "fixed_20": floor + 20, "proportional_20pct": floor * Decimal("1.20")}[funding]
                event = replace(event, initial_collateral=amount)
            events.append(event)
        return replace(path, events=tuple(events))
    return replace(bundle, primary_path=path_rebase(bundle.primary_path), alternate_paths=tuple(path_rebase(path) for path in bundle.alternate_paths))


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    config = FpmmComparisonConfig()
    write_json(output / "config.json", {"comparison": asdict(config), "funding": ["floor", "fixed_20", "proportional_20pct"], "inference": "descriptive designed 44 pairs; no population confidence intervals", "entry_deposits": "same LMSR-derived deposit schedule for both mechanisms", "fixed": ["trader share requests", "fee rates", "LP entry dates", "resolved outcome", "LP hold-to-settlement"]})
    source_dir = Path(__file__).parent
    sources = {name: hashlib.sha256((source_dir / name).read_bytes()).hexdigest() for name in ("fpmm_validation.py", "fpmm_comparison.py", "fpmm_baseline.py", "reference_parallel_lmsr.py", "scenarios.py", "experiments.py")}
    write_json(output / "provenance.json", {"python": sys.version, "sources": sources})
    with high_precision():
        families = {
            "deterministic": build_fpmm_deterministic_bundles(),
            "adversarial": [_with_comparator_mechanisms(b, residual_weight_scheme=config.residual_weight_scheme, linear_lambda=config.linear_lambda) for b in generate_adversarial_bundles(build_fpmm_adversarial_config())[:24]],
            "high_skew": build_fpmm_high_skew_bundles(limit=12),
        }
        summaries = {}
        all_paired = []
        for funding in ("floor", "fixed_20", "proportional_20pct"):
            folder = output / funding
            folder.mkdir(exist_ok=True)
            results, requests = [], []
            runner = ExperimentRunner()
            for family, bundles in families.items():
                for bundle in bundles:
                    revised = rebase(bundle, funding)
                    requests.append({"family": family, "bundle": _json_safe(asdict(revised))})
                    results.extend(runner.run_bundle(revised, run_family=family))
            write_json(folder / "requests.json", requests)
            write_experiment_results(results, folder, manifest_label=f"revised_fpmm_{funding}")
            paired = _paired_rows(results)
            write_csv(folder / "paired_rows.csv", paired)
            overview = _overview(results, paired)
            overview["by_family"] = {family: _overview([r for r in results if r.run_family == family], [r for r in paired if r["run_family"] == family]) for family in families}
            overview["failed_checks"] = [{"scenario": r.scenario_name, "mechanism": r.mechanism.value, "checks": r.evaluation.solvency} for r in results if not r.evaluation.solvency.get("passed", False)]
            summaries[funding] = overview
            all_paired.extend({"funding": funding, **r} for r in paired)
            print(f"{funding}: {len(paired)} pairs", flush=True)
        write_json(output / "summary.json", summaries)
        write_csv(output / "paired_rows.csv", all_paired)
    lines = ["# Revalidated FPMM comparison", "", "Same 44 designed histories; normalized lambda .15, explicit matched founder funding. Results are distributional diagnostics, not an equilibrium or causal information-timing experiment.", "", "| Funding | Active-LP mean gap | FPMM mean gap | Smaller absolute gap: Active LP / FPMM |", "| --- | ---: | ---: | --- |"]
    for funding, summary in summaries.items():
        means = summary["mechanism_mean_fairness_gap"]
        lines.append(f"| {funding} | {float(means['reference_parallel_lmsr_reserve_residual']):.6f} | {float(means['fpmm_pool_share']):.6f} | {summary['active_lp_beats_fpmm_on_abs_gap_count']} / {summary['fpmm_beats_active_lp_on_abs_gap_count']} |")
    lines += ["", "The comparison fixes requested share quantities, not equal expenditure or equal realized prices. FPMM returned outcome tokens are included in LP wealth. The scheduled deposits use the LMSR reference price at entry for both mechanisms. Both hold capital to settlement. A common initial funding amount does not equalize liquidity functions, risk, or opportunity cost.", "", "Each funding directory contains complete requested bundles and per-mechanism result rows. summary.json separates designed families and records any failed checks."]
    (output / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("01-active-lp/output/fpmm_validation"))
    run(parser.parse_args().output)
