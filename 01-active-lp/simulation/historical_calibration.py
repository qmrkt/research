"""Retrospective repair of the original residual-weight calibration comparison.

Both functional forms minimize absolute training mean late-minus-founder NAV /
initial deposit on the original training pack. Test rows are never used to
select lambda. This is a historical reanalysis, not a new independent holdout;
the fresh publication_validation suite remains fixed and separate.
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import statistics
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from research.active_lp import calibration_upgrade as original
from research.active_lp import publication_validation as pv
from research.active_lp.events import BootstrapMarket, BuyOutcome, CancelMarket, LpEnterActive, ResolveMarket, SellOutcome
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import uniform_price_vector

D, ZERO, ONE = Decimal, Decimal(0), Decimal(1)
DEFAULT_OUTPUT = pv.REPO / "01-active-lp" / "output" / "historical_calibration"
PLAN = {
    "schema": "historical_calibration_v1",
    "status": "retrospective repair of parameter-grid comparison; not fresh validation",
    "train_mc_seed": 1100, "test_mc_seed": 2100, "mc_trials_each": 64,
    "duration_buckets": [["short", 12], ["medium", 48], ["long", 168]],
    "adversarial_split": "original even-index training / odd-index test; terminal policies, not independent strategy histories",
    "selection_funding": "fixed_20: initial b*ln(N)+20; entrants always meet their own component funding floor",
    "selection_objective": "absolute row-weighted TRAIN mean late-minus-founder terminal NAV/deposit gap; primary objective used by original study",
    "selection_method": "nonnegative lambda; verify every training-row gap is nonincreasing, bracket mean zero by doubling, then 60 bisections; lambda=0 if mean already nonpositive",
    "bracket_starts": {"event": "0.005", "normalized": "0.25"},
    "maximum_bracket_doublings": 30, "bisection_iterations": 60,
    "floor_diagnostic": "reuse selected +20-trained parameters on b*ln(N) paths; no floor retuning",
    "diagnostic_parameters": {"event": ["0", "0.0025", "0.025"], "normalized": ["0", "0.15"]},
    "reporting": "original row weighting; mean, mean absolute gap, quantiles, duration means; no new population inference",
    "cache": "replay each unique untimed economic history/funding once; store scalar cohort accounting and exact requested timestamps for each restamp",
    "scope": "allocation comparison only; does not identify information timing, establish risk-adjusted fairness, or alter the fresh 96-history diagnostic",
}


def historical_pack(split: str, trials: int = 64, adversarial_limit: int | None = None) -> list[tuple[pv.History, dict]]:
    seed = 1100 if split == "train" else 2100
    duration = tuple((str(label), int(length)) for label, length in PLAN["duration_buckets"])
    mc = original._prepare_monte_carlo_bundles(split=split, seed=seed, num_trials=trials, duration_buckets=duration)
    adversarial = original._prepare_adversarial_bundles(split=split, adversarial_limit=adversarial_limit)
    result = []
    for index, bundle in enumerate(mc + adversarial):
        config = bundle.config
        family = "monte_carlo" if index < len(mc) else "adversarial"
        cluster = f"mc_{config.seed}" if family == "monte_carlo" else f"adversarial_{index - len(mc)}"
        steps, winner, terminal = [], None, None
        for event in bundle.primary_path.events:
            if isinstance(event, BootstrapMarket):
                continue
            if isinstance(event, (ResolveMarket, CancelMarket)):
                winner = event.winning_outcome if isinstance(event, ResolveMarket) else None
                terminal = event.timestamp
                break
            if isinstance(event, LpEnterActive):
                steps.append({"kind": "lp", "timestamp": event.timestamp, "actor": event.sponsor_id, "amount": D(event.target_delta_b)})
            elif isinstance(event, (BuyOutcome, SellOutcome)):
                steps.append({"kind": "buy" if isinstance(event, BuyOutcome) else "sell", "timestamp": event.timestamp, "actor": event.trader_id, "outcome": event.outcome_index, "amount": D(event.shares)})
        if terminal is None:
            raise ValueError("historical path has no terminal event")
        history = pv.History(config.name, cluster, "historical_calibration", config.seed, config.num_outcomes, D(config.initial_depth_b), D(config.fee_bps), D(config.protocol_fee_bps), uniform_price_vector(config.num_outcomes), steps, winner, terminal, bundle.description)
        result.append((history, {"split": split, "family": family, "duration_bucket": config.duration_bucket or "unscaled_adversarial"}))
    return result


def economic_key(history: pv.History, funding: str) -> str:
    return pv.digest({"n": history.outcomes, "b": history.initial_b, "fee": history.fee_bps, "protocol": history.protocol_fee_bps, "funding": funding, "requests": [{k: v for k, v in step.items() if k != "timestamp"} for step in history.steps]})


def snapshot(history: pv.History, funding: str, state: Any, audit: dict, metadata: dict) -> dict:
    ordered = sorted(state.sponsors.items(), key=lambda pair: (pair[1].entry_timestamp, pair[0]))
    entry_times = [1] + [step["timestamp"] for step in history.steps if step["kind"] == "lp"]
    if len(ordered) != len(entry_times):
        raise AssertionError("cohort count differs from requested entries")
    cohorts = []
    for (key, sponsor), entry_time in zip(ordered, entry_times):
        cohorts.append({"cohort_id": key, "depth": D(sponsor.share_units), "deposit": D(sponsor.collateral_posted), "fees": D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus), "entry_timestamp": entry_time})
    reserve = pv.refund_requirement(state) if history.winner is None else D(state.traders.aggregate_outstanding_claims[history.winner])
    free = pv.nonfee_assets(state) - reserve
    if free < D("-1e-12"):
        raise AssertionError("terminal free residual below zero")
    return {"path_id": history.path_id, "cluster_id": history.cluster_id, "seed": history.seed, "funding": funding, "winner": history.winner, "outcomes": history.outcomes, "duration": history.settlement_time - 1, "settlement_time": history.settlement_time, "free_residual": max(free, ZERO), "cohorts": cohorts, "rejected_sells": audit["rejected_sells"], "economic_key": economic_key(history, funding), "request_hash": pv.digest(history.steps), **metadata}


def coefficients(row: dict, scheme: str) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """gap(lambda) = free*(a+b*lambda)/(c+d*lambda) + fee_gap."""
    cohorts = row["cohorts"]
    span = max(1, row["settlement_time"] - min(c["entry_timestamp"] for c in cohorts))
    premium = [D(max(0, row["settlement_time"] - cohort["entry_timestamp"] - 1)) for cohort in cohorts]
    if scheme == "normalized":
        premium = [value / D(span - 1) if span > 1 else ZERO for value in premium]
    elif scheme != "event":
        raise ValueError(scheme)
    first, last = cohorts[0], cohorts[-1]
    a = last["depth"] / last["deposit"] - first["depth"] / first["deposit"]
    b = last["depth"] * premium[-1] / last["deposit"] - first["depth"] * premium[0] / first["deposit"]
    c = sum((cohort["depth"] for cohort in cohorts), ZERO)
    d = sum((cohort["depth"] * p for cohort, p in zip(cohorts, premium)), ZERO)
    fee_gap = last["fees"] / last["deposit"] - first["fees"] / first["deposit"]
    return row["free_residual"] * a, row["free_residual"] * b, c, d, fee_gap


def gap_from_coefficients(parts: tuple[Decimal, ...], value: Decimal) -> Decimal:
    a, b, c, d, fee_gap = parts
    return (a + b * value) / (c + d * value) + fee_gap


def select_lambda(rows: list[dict], scheme: str) -> tuple[Decimal, list[dict]]:
    if any(row["split"] != "train" or row["funding"] != "fixed_20" for row in rows):
        raise ValueError("selection accepts +20 training snapshots only")
    parts = [coefficients(row, scheme) for row in rows]
    if any(b * c - a * d > D("1e-30") for a, b, c, d, _ in parts):
        raise AssertionError("training gap is not rowwise nonincreasing; bisection is invalid")
    history = []
    def mean(value: Decimal, phase: str) -> Decimal:
        gaps = [gap_from_coefficients(part, value) for part in parts]
        average = sum(gaps, ZERO) / len(gaps)
        history.append({"scheme": scheme, "phase": phase, "lambda": value, "training_mean_gap": average, "training_mean_absolute_gap": sum(map(abs, gaps), ZERO) / len(gaps), "training_rows": len(gaps)})
        return average
    if mean(ZERO, "zero") <= 0:
        return ZERO, history
    low, high = ZERO, D(PLAN["bracket_starts"][scheme])
    for _ in range(PLAN["maximum_bracket_doublings"]):
        if mean(high, "bracket") <= 0:
            break
        low, high = high, high * 2
    else:
        raise ValueError("training zero not bracketed; no finite optimum selected")
    for _ in range(PLAN["bisection_iterations"]):
        middle = (low + high) / 2
        if mean(middle, "bisection") > 0:
            low = middle
        else:
            high = middle
    chosen = (low + high) / 2
    mean(chosen, "selected")
    return chosen, history


def evaluate(row: dict, scheme: str, value: Decimal, label: str) -> dict:
    gap = gap_from_coefficients(coefficients(row, scheme), value)
    return {key: row[key] for key in ("path_id", "cluster_id", "split", "family", "duration_bucket", "funding", "seed", "winner", "outcomes", "duration", "rejected_sells", "request_hash", "economic_key")} | {"label": label, "scheme": scheme, "lambda": value, "gap": gap, "absolute_gap": abs(gap)}


def summarize(rows: list[dict]) -> dict:
    gaps = [D(row["gap"]) for row in rows]
    return {"rows": len(rows), "base_path_ids": len({row["cluster_id"] for row in rows}), "mean_gap": sum(gaps, ZERO) / len(gaps), "mean_absolute_gap": sum(map(abs, gaps), ZERO) / len(gaps), "min_gap": min(gaps), "max_gap": max(gaps), "p05": pv.quantile(list(map(float, gaps)), .05), "p95": pv.quantile(list(map(float, gaps)), .95), "rejected_sells": sum(row["rejected_sells"] for row in rows)}


def report_text(selected: dict, summaries: dict, slices: list[dict]) -> str:
    lines = ["# Expanded historical calibration comparison", "", "This retrospective repair gives both formulas a continuous nonnegative parameter range and selects only on the original +20-funded training data. It does not change the fresh 96-path publication suite or identify an information-timing effect.", "", "The original ordinary training and test packs each contain 192 MC duration variants (64 base histories, durations 12/48/168) plus 96 designed adversarial rows. The adversarial parity split separates terminal policies of related strategy histories and is not independent held-out behavior. Row weighting is preserved for comparability; no population confidence intervals are attached.", "", "## Train-only selection", "", "The primary objective is absolute mean late-minus-founder terminal NAV/deposit gap, as in the original calibration. Every training row's gap is checked to be nonincreasing in lambda. A nonnegative root is bracketed, then solved by 60 bisections. Mean absolute gap and duration heterogeneity are reported, not silently substituted as selection objectives.", "", "| Formula | Selected lambda |", "| --- | ---: |"]
    for scheme, value in selected.items():
        lines.append(f"| {scheme} | {float(value):.12f} |")
    lines += ["", "## Original test pack and funding ablation", "", "The floor diagnostic reuses the +20-trained parameter; no parameter is refit to the floor-funded paths.", "", "| Split | Funding | Rule | Rows | Mean gap | Mean absolute gap | Min | Max |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for key, values in summaries.items():
        split, funding, label = key.split("/")
        lines.append(f"| {split} | {funding} | {label} | {values['rows']} | {float(values['mean_gap']):.9f} | {float(values['mean_absolute_gap']):.9f} | {float(values['min_gap']):.9f} | {float(values['max_gap']):.9f} |")
    lines += ["", "## Duration slices", "", "The unscaled adversarial rows are a separate family, not a duration treatment. MC restamps preserve economic requests and only alter the clock. Dividing by the total active span reduces dependence on clock units, but the one-unit offsets in the numerator and denominator and integer restamp rounding prevent exact affine clock invariance. Reduced duration sensitivity in these slices is a portability result, not evidence that the calibrated allocation is economically fair.", "", "| Funding | Rule | Duration/family | Rows | Mean gap | Mean absolute gap |", "| --- | --- | --- | ---: | ---: | ---: |"]
    for row in slices:
        if row["split"] == "test" and row["label"] in ("flat", "event_selected", "normalized_selected", "event_0.025", "normalized_0.15"):
            lines.append(f"| {row['funding']} | {row['label']} | {row['duration_bucket']} | {row['rows']} | {float(row['mean_gap']):.9f} | {float(row['mean_absolute_gap']):.9f} |")
    lines += ["", "## Reproduction and limits", "", "snapshots.jsonl retains terminal free residuals, cohort deposits/depth/fees and entry clocks, enough to recompute every allocation without replaying trades. paths.jsonl retains the exact requests. selection_trace.csv contains every training objective evaluated during bracketing/bisection; raw_rows.csv retains each path for every reported parameter/funding; config.json and provenance.json record the design and source hashes. The cache is keyed on all economic requests, funding and fee parameters; time-only variants reuse accounting, while each path retains its own clocks.", "", "The +20 founding endowment affects the measured gap. These retrospective results repair the restricted-grid comparison; they do not establish a universal optimal coefficient, risk-adjusted fairness, causal timing advantage, or deployment safety. The original test pack has already been examined and is explicitly historical.", ""]
    return "\n".join(lines)


def run(output: Path, *, smoke: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    config = dict(PLAN, smoke=smoke)
    if smoke:
        config.update(mc_trials_each=2, adversarial_limit=4, status="smoke only, not publication results")
    pv.write_json(output / "config.json", config)
    source_names = ("historical_calibration.py", "publication_validation.py", "calibration_upgrade.py", "reference_parallel_lmsr.py", "reference_math.py", "precision.py", "events.py", "state.py", "scenarios.py", "monte_carlo.py", "adversarial_search.py", "sweep_presets.py")
    source_paths = [Path(__file__).with_name(name) for name in source_names]
    hashes = {str(path.relative_to(pv.REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    pv.write_json(output / "provenance.json", {"python": sys.version, "platform": platform.platform(), "config_sha256": pv.digest(config), "sources": hashes})
    cached, snapshots, paths, selection_trace, raw = {}, [], [], [], []
    with high_precision():
        for split in ("train", "test"):
            pack = historical_pack(split, config["mc_trials_each"], config.get("adversarial_limit"))
            for history, metadata in pack:
                paths.append(asdict(history) | metadata)
                for funding in ("fixed_20", "floor"):
                    key = economic_key(history, funding)
                    if key not in cached:
                        cached[key] = pv.run_history(history, funding)[:2]
                    state, audit = cached[key]
                    snapshots.append(snapshot(history, funding, state, audit, metadata))
            print(f"{split}: {len(pack)} rows, {len(cached)} cumulative accounting replays", flush=True)
        train = [row for row in snapshots if row["split"] == "train" and row["funding"] == "fixed_20"]
        selected = {}
        for scheme in ("event", "normalized"):
            selected[scheme], trace = select_lambda(train, scheme)
            selection_trace.extend(trace)
        rules = [("flat", "event", ZERO), ("event_selected", "event", selected["event"]), ("normalized_selected", "normalized", selected["normalized"]), ("event_0.0025", "event", D(".0025")), ("event_0.025", "event", D(".025")), ("normalized_0.15", "normalized", D(".15"))]
        for row in snapshots:
            for label, scheme, value in rules:
                raw.append(evaluate(row, scheme, value, label))
        summaries, slices = {}, []
        for split in ("train", "test"):
            for funding in ("fixed_20", "floor"):
                for label, _, _ in rules:
                    chosen = [row for row in raw if row["split"] == split and row["funding"] == funding and row["label"] == label]
                    summaries[f"{split}/{funding}/{label}"] = summarize(chosen)
                    for bucket in ("short", "medium", "long", "unscaled_adversarial"):
                        sliced = [row for row in chosen if row["duration_bucket"] == bucket]
                        if sliced:
                            slices.append({"split": split, "funding": funding, "label": label, "duration_bucket": bucket, **summarize(sliced)})
        pv.write_json(output / "summary.json", {"selected_lambdas": selected, "summaries": summaries, "duration_slices": slices, "cached_accounting_replays": len(cached)})
        pv.write_jsonl(output / "snapshots.jsonl", snapshots)
        pv.write_jsonl(output / "paths.jsonl", paths)
        pv.write_csv(output / "selection_trace.csv", selection_trace)
        pv.write_csv(output / "raw_rows.csv", raw)
        pv.write_csv(output / "duration_slices.csv", slices)
        (output / "report.md").write_text(report_text(selected, summaries, slices))
    for path in source_paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path.relative_to(pv.REPO))]:
            raise RuntimeError(f"source changed during historical run: {path}")
    pv.write_json(output / "manifest.json", {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(output.iterdir()) if path.is_file() and path.name != "manifest.json"})
    print(f"Wrote {len(snapshots)} snapshots, {len(raw)} allocation rows to {output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.output, smoke=args.smoke)


if __name__ == "__main__":
    main()
