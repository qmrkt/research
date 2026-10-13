"""Causal synthetic study of LP information and optional participation.

The outcome/flow/signal population is finitely enumerable.  No policy threshold
is estimated from realized profits: enter iff the Bayesian conditional expected
net profit is positive.  A separate independent RNG replication checks the exact
expectations.  This is a model experiment, not evidence about real LP behavior.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from random import Random
import statistics

from research.active_lp.events import (
    BootstrapMarket, BuyOutcome, ClaimWinnings, LpEnterActive, ResolveMarket,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, lmsr_prices, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    RESERVE_POOL, STRICT_ALL_CLAIMED, ReferenceParallelLmsrEngine,
    ReferenceInvariantChecker, create_initial_state,
)

D = Decimal
YEAR_SECONDS = 365 * 86400
RULES = ("flat", "normalized", "isolated_cohort")
POLICIES = ("early_committed", "early_optional", "late_committed", "late_public_optional", "late_private_optional")
MC_SEEDS = (724901, 824903, 924907)


@dataclass(frozen=True)
class TimingRegime:
    name: str
    pre_shares: int = 40
    future_shares: int = 80
    flow_accuracy: float = 0.8
    signal_accuracy: float = 0.8
    lp_fee_bps: int = 100
    bootstrap_extra: int = 0
    duration_days: int = 30
    annual_opportunity_cost: float = 0.05


def causal_regimes() -> tuple[TimingRegime, ...]:
    base = TimingRegime("canonical")
    return (base,) + tuple(replace(base, name=name, **changes) for name, changes in (
        ("uninformative_signal", {"signal_accuracy": 1 / 3}),
        ("weak_private_signal", {"signal_accuracy": 0.6}),
        ("strong_private_signal", {"signal_accuracy": 0.95}),
        ("perfect_private_signal", {"signal_accuracy": 1.0}),
        ("no_future_flow", {"future_shares": 0}),
        ("uninformed_future_flow", {"flow_accuracy": 1 / 3}),
        ("perfectly_informed_future_flow", {"flow_accuracy": 1.0}),
        ("small_future_flow", {"future_shares": 20}),
        ("large_future_flow", {"future_shares": 240}),
        ("zero_fees", {"lp_fee_bps": 0}),
        ("five_percent_fees", {"lp_fee_bps": 500}),
        ("bootstrap_plus_20", {"bootstrap_extra": 20}),
        ("long_expensive_lockup", {"duration_days": 180, "annual_opportunity_cost": 0.10}),
        ("zero_opportunity_cost", {"annual_opportunity_cost": 0.0}),
        ("high_noise_demand", {"pre_shares": 10, "future_shares": 240, "flow_accuracy": 1 / 3}),
    ))


def population_regimes(split: str) -> tuple[TimingRegime, ...]:
    if split == "train":
        grid = ((10, 40, 100), (20, 80, 240), (1 / 3, 0.5, 0.8), (100,), (0.8,))
    elif split == "holdout":
        grid = ((25, 70), (50, 160), (0.4, 0.65), (50, 200), (0.7, 0.9))
    else:
        raise ValueError(split)
    from itertools import product
    return tuple(
        TimingRegime(f"{split}_{i:03d}", pre, future, flow, signal, fee)
        for i, (pre, future, flow, fee, signal) in enumerate(product(*grid))
    )


def study_design(draws: int) -> dict:
    return {
        "design_version": 1,
        "registration_status": "Local design written before this study's outcomes; not externally preregistered.",
        "primary_estimand": "Expected private-optional minus public-optional profit / offered collateral at the same delayed time and public price; declined offers contribute zero.",
        "public_process": "A public branch U is uniform over 3 rotations. Before delayed entry, a fixed buy in U moves the baseline b=100 market. P(W|U) equals that baseline market price. By permutation symmetry all expectations are computed conditional on U=0; these are 9 economic worlds, not 27 independent observations.",
        "private_process": "P(S=W)=signal_accuracy; each other signal has probability (1-accuracy)/2. Conditional on W, the signal and future order direction are independent. Accuracy 1/3 is the null.",
        "flow_process": "One future buy has P(F=W)=flow_accuracy; each other direction has probability (1-accuracy)/2. Its quantity is exogenous and identical across potential LP policies. At decision time future order direction is not observed.",
        "policies": list(POLICIES),
        "policy_rule": "Enter iff exact conditional expected net profit is strictly positive. Public optional sees U and price only; private optional also sees S. No estimated thresholds or hindsight decisions.",
        "early_comparison": "Early committed enters before U; late committed enters after U. Early/late differences include changed curve depth, collateral pricing, fees, and lockup. They are not labeled a pure private-information effect.",
        "financial_terms": {"outcomes": 3, "bootstrap_depth": 100, "entrant_depth": 20, "protocol_fee_bps": 25, "cost_convention": "Simple annual capital opportunity cost for actual deployed collateral; declined offers have zero incremental profit relative to retaining outside capital."},
        "rules": list(RULES), "reference_normalized_lambda": 0.15,
        "causal_regimes": [asdict(r) for r in causal_regimes()],
        "train_population": [asdict(r) for r in population_regimes("train")],
        "holdout_population": [asdict(r) for r in population_regimes("holdout")],
        "lambda_search": {"initial_grid": [0, .025, .05, .1, .15, .25, .5, 1, 2, 4], "boundary_rule": "If selected lambda is the tested maximum, double it up to 64 until the optimum is interior or the next value is infeasible; report any remaining boundary.", "objective": "Minimize equal-regime mean private-information advantage on train only.", "participation_constraints": "For every train regime where flat public entry has strictly positive expected net profit, preserve strictly positive public entry profit. Preserve at least half of flat private entry rate averaged across train regimes. These are explicit normative safeguards, not a welfare theorem."},
        "mc_replication": {"seeds": list(MC_SEEDS), "draws_per_seed": draws, "pairing": "Identical world draws for every policy and residual rule in a regime.", "purpose": "Independent Monte Carlo check against exactly enumerated synthetic expectations, not additional real-world validation."},
    }


@lru_cache(maxsize=None)
def _cash_payoff(pre: int, future: int, fee: int, extra: int, days: int,
                 rule: str, lam: float, early: bool, winner: int, flow: int) -> dict:
    policy = STRICT_ALL_CLAIMED if rule == "isolated_cohort" else RESERVE_POOL
    scheme = "linear_lambda_normalized" if rule == "normalized" else "flat"
    engine = ReferenceParallelLmsrEngine(
        lp_fee_bps=fee, protocol_fee_bps=25, residual_policy=policy,
        residual_weight_scheme=scheme, residual_linear_lambda=D(str(lam)),
    )
    checker = ReferenceInvariantChecker(residual_policy=policy)
    state = create_initial_state(3, residual_weight_scheme=scheme, residual_linear_lambda=D(str(lam)))
    end = days * 86400
    with high_precision():
        funding = collateral_required(D(100), uniform_price_vector(3)) + D(extra)
    state = engine.apply_event(state, BootstrapMarket(0, "creator", funding, D(100)))

    def entry(current, timestamp):
        return engine.apply_event(current, LpEnterActive(timestamp, "entrant", D(20), D("1e50"), current.pricing.price_vector, D("1e-18")))

    if early:
        state = entry(state, 1)
    if pre:
        state = engine.apply_event(state, BuyOutcome(end // 3, "public_trader", 0, D(pre), D("1e50")))
    if not early:
        state = entry(state, end // 2)
    entry_state = state
    if future:
        state = engine.apply_event(state, BuyOutcome(2 * end // 3, "future_trader", flow, D(future), D("1e50")))
    state = engine.apply_event(state, ResolveMarket(end, winner))
    for trader, holdings in list(state.traders.positions_by_trader.items()):
        if holdings[winner] > 0:
            state = engine.apply_event(state, ClaimWinnings(end + 1, trader, winner, holdings[winner]))
    failures = [asdict(check) for check in checker.check_all(state) if not check.passed]
    if failures:
        raise AssertionError(failures)
    cohort_key = next(key for key, sponsor in state.sponsors.items() if sponsor.sponsor_id == "entrant")
    sponsor = state.sponsors[cohort_key]
    nav = engine.mark_to_market_nav(state)[cohort_key]
    deposit = D(sponsor.collateral_posted)
    return {
        "deposit": float(deposit), "terminal_nav": float(nav),
        "cash_profit": float(nav - deposit), "fee_income": float(sponsor.claimable_fees),
        "locked_seconds": end - sponsor.entry_timestamp,
        "entry_prices": [float(x) for x in entry_state.sponsors[cohort_key].entry_price_vector],
    }


def potential(regime: TimingRegime, rule: str, lam: float, early: bool, winner: int, flow: int) -> dict:
    cash = dict(_cash_payoff(regime.pre_shares, regime.future_shares, regime.lp_fee_bps,
                             regime.bootstrap_extra, regime.duration_days, rule, lam, early, winner, flow))
    cost = cash["deposit"] * regime.annual_opportunity_cost * cash["locked_seconds"] / YEAR_SECONDS
    cash["opportunity_cost"] = cost
    cash["net_profit"] = cash["cash_profit"] - cost
    cash["return_on_offered_capital"] = cash["net_profit"] / cash["deposit"]
    return cash


def _channel(observed: int, truth: int, accuracy: float) -> float:
    return accuracy if observed == truth else (1 - accuracy) / 2


def _weighted_quantile(values: list[tuple[float, float]], q: float) -> float:
    total = 0.0
    for value, probability in sorted(values):
        total += probability
        if total >= q - 1e-14:
            return value
    return max(value for value, _ in values)


def evaluate_regime(regime: TimingRegime, rule: str, lam: float = .15,
                    signal_target: str = "outcome") -> tuple[list[dict], list[dict]]:
    if signal_target not in ("outcome", "flow_alignment"):
        raise ValueError(signal_target)
    signals = range(3) if signal_target == "outcome" else range(2)
    # Baseline public posterior is fixed across entrant policy arms. An early
    # entrant changes the curve response but cannot change the external truth law.
    prior = tuple(float(p) for p in lmsr_prices((D(regime.pre_shares), D(0), D(0)), D(100)))
    worlds = []
    for winner in range(3):
        for flow in range(3):
            early = potential(regime, rule, lam, True, winner, flow)
            late = potential(regime, rule, lam, False, winner, flow)
            for signal in signals:
                if signal_target == "outcome":
                    signal_likelihood = _channel(signal, winner, regime.signal_accuracy)
                else:
                    aligned = int(flow == winner)
                    signal_likelihood = regime.signal_accuracy if signal == aligned else 1 - regime.signal_accuracy
                probability = prior[winner] * _channel(flow, winner, regime.flow_accuracy) * signal_likelihood
                worlds.append({"winner": winner, "flow": flow, "signal": signal,
                               "probability": probability, "early": early, "late": late})
    early_mean = sum(w["probability"] * w["early"]["net_profit"] for w in worlds)
    late_mean = sum(w["probability"] * w["late"]["net_profit"] for w in worlds)
    signal_probability = {s: sum(w["probability"] for w in worlds if w["signal"] == s) for s in signals}
    signal_mean = {
        s: (sum(w["probability"] * w["late"]["net_profit"] for w in worlds if w["signal"] == s) / signal_probability[s]
            if signal_probability[s] > 0 else 0.0)
        for s in signals
    }
    # Exact expected decisions use a tiny numerical threshold solely to avoid
    # a floating-point tie generating spurious entry in the null controls.
    threshold = 1e-12
    raw = []
    for w in worlds:
        entered = {"early_committed": True, "early_optional": early_mean > threshold,
                   "late_committed": True, "late_public_optional": late_mean > threshold,
                   "late_private_optional": signal_mean[w["signal"]] > threshold}
        row = {"regime": regime.name, "rule": rule, "lambda": lam, "signal_target": signal_target,
               "winner": w["winner"], "future_flow_direction": w["flow"], "private_signal": w["signal"],
               "probability": w["probability"], "public_price_0": prior[0], "public_price_1": prior[1], "public_price_2": prior[2],
               "signal_conditional_expected_net_profit": signal_mean[w["signal"]]}
        for time in ("early", "late"):
            for key, value in w[time].items():
                row[f"{time}_{key}"] = json.dumps(value) if isinstance(value, list) else value
        for policy in POLICIES:
            time = "early" if policy.startswith("early") else "late"
            row[f"{policy}_enter"] = entered[policy]
            row[f"{policy}_net_profit"] = w[time]["net_profit"] if entered[policy] else 0.0
            row[f"{policy}_offered_return"] = w[time]["return_on_offered_capital"] if entered[policy] else 0.0
        raw.append(row)
    summaries = []
    for policy in POLICIES:
        time = "early" if policy.startswith("early") else "late"
        entry_rate = sum(r["probability"] * r[f"{policy}_enter"] for r in raw)
        mean_profit = sum(r["probability"] * r[f"{policy}_net_profit"] for r in raw)
        mean_return = sum(r["probability"] * r[f"{policy}_offered_return"] for r in raw)
        variance = sum(r["probability"] * (r[f"{policy}_offered_return"] - mean_return) ** 2 for r in raw)
        mean_deployed = sum(r["probability"] * r[f"{time}_deposit"] * r[f"{policy}_enter"] for r in raw)
        support = [(r[f"{policy}_offered_return"], r["probability"]) for r in raw if r["probability"] > 0]
        summaries.append({
            **asdict(regime), "regime": regime.name, "rule": rule, "lambda": lam, "signal_target": signal_target, "policy": policy,
            "entry_rate": entry_rate, "mean_net_profit": mean_profit, "mean_return_per_offered_capital": mean_return,
            "mean_return_on_deployed_capital": mean_profit / mean_deployed if mean_deployed else "",
            "mean_deployed_collateral": mean_deployed, "return_std": math.sqrt(max(0.0, variance)),
            "worst_offered_return": min(v for v, _ in support), "p05_offered_return": _weighted_quantile(support, .05),
            "loss_probability": sum(r["probability"] for r in raw if r[f"{policy}_net_profit"] < -threshold),
            "expected_capital_days": sum(r["probability"] * r[f"{time}_deposit"] * r[f"{time}_locked_seconds"] / 86400 * r[f"{policy}_enter"] for r in raw),
            "public_price_0": prior[0], "public_price_1": prior[1], "public_price_2": prior[2],
        })
    return summaries, raw


def effect_row(summaries: list[dict]) -> dict:
    by = {r["policy"]: r for r in summaries}
    pub, private = by["late_public_optional"], by["late_private_optional"]
    return {"regime": pub["regime"], "rule": pub["rule"], "lambda": pub["lambda"], "signal_target": pub["signal_target"],
            "private_information_value": private["mean_return_per_offered_capital"] - pub["mean_return_per_offered_capital"],
            "public_entry_rate": pub["entry_rate"], "private_entry_rate": private["entry_rate"],
            "public_offered_return": pub["mean_return_per_offered_capital"], "private_offered_return": private["mean_return_per_offered_capital"],
            "late_committed_return": by["late_committed"]["mean_return_per_offered_capital"],
            "early_committed_return": by["early_committed"]["mean_return_per_offered_capital"],
            "committed_delay_effect": by["late_committed"]["mean_return_per_offered_capital"] - by["early_committed"]["mean_return_per_offered_capital"],
            "private_option_value_over_late_commitment": private["mean_return_per_offered_capital"] - by["late_committed"]["mean_return_per_offered_capital"]}


def monte_carlo_check(raw: list[dict], draws: int) -> list[dict]:
    exact = sum(r["probability"] * (r["late_private_optional_offered_return"] - r["late_public_optional_offered_return"]) for r in raw)
    output = []
    for seed in MC_SEEDS:
        rng = Random(seed)
        sampled = rng.choices(raw, weights=[r["probability"] for r in raw], k=draws)
        values = [r["late_private_optional_offered_return"] - r["late_public_optional_offered_return"] for r in sampled]
        mean = statistics.mean(values)
        se = statistics.stdev(values) / math.sqrt(draws) if draws > 1 else 0.0
        output.append({"regime": raw[0]["regime"], "rule": raw[0]["rule"], "lambda": raw[0]["lambda"],
                       "seed": seed, "draws": draws, "exact_information_value": exact,
                       "mc_information_value": mean, "mc_standard_error": se,
                       "ci95_lower": mean - 1.96 * se, "ci95_upper": mean + 1.96 * se,
                       "error": mean - exact})
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_causal_study(output_dir: Path, draws: int = 20000) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    design = study_design(draws)
    design_text = json.dumps(design, indent=2, sort_keys=True) + "\n"
    design_path = output_dir / "design.json"
    if design_path.exists() and design_path.read_text() != design_text:
        raise ValueError("Existing design differs; use a fresh output directory for a changed study.")
    design_path.write_text(design_text)
    summary, raw, effects, mc = [], [], [], []
    for regime in causal_regimes():
        for rule in RULES:
            rows, worlds = evaluate_regime(regime, rule, .15 if rule == "normalized" else 0.0)
            summary.extend(rows); raw.extend(worlds); effects.append(effect_row(rows))
            mc.extend(monte_carlo_check(worlds, draws))
    write_csv(output_dir / "policy_summary.csv", summary)
    write_csv(output_dir / "worlds.csv", raw)
    write_csv(output_dir / "causal_effects.csv", effects)
    write_csv(output_dir / "monte_carlo_replication.csv", mc)
    provenance = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_sha256": hashlib.sha256(design_text.encode()).hexdigest(),
        "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference_engine_sha256": hashlib.sha256(Path(__file__).with_name("reference_parallel_lmsr.py").read_bytes()).hexdigest(),
        "causal_regime_count": len(causal_regimes()), "policy_summary_rows": len(summary),
        "exact_world_rows": len(raw), "monte_carlo_draws_per_rule_regime": draws * len(MC_SEEDS),
    }
    (output_dir / "manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return {"effects": effects, "summary": summary, "provenance": provenance}


def run_population_study(output_dir: Path, signal_target: str = "outcome") -> dict:
    """Train-only lambda selection, retaining all worlds and separate holdouts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    train, holdout = population_regimes("train"), population_regimes("holdout")
    grid = [0, .025, .05, .1, .15, .25, .5, 1, 2, 4]
    if signal_target == "flow_alignment":
        grid = [0, .01, .025, .05, .075, .1, .15, .25, .5, 1, 2, 4]
    design = {
        "signal_target": signal_target,
        "status": "Plan frozen before executing this population/extension. Flow-alignment extension follows an outcome-signal study with many null effects, and is explicitly a subsequent hypothesis.",
        "signal_definition": ("Private categorical outcome signal; null accuracy1/3." if signal_target == "outcome" else "Private binary signal of A=1{future flow direction equals true winner}. P(S=A)=accuracy; null accuracy.5. Signal observes no public price change and no future cashflow; it is a noisy predictive signal, conditionally independent of other randomness given A."),
        "information_cost": "Signal is free; all policies are risk-neutral with simple collateral opportunity cost. No claim of robustness to signal acquisition costs or risk aversion.",
        "train": [asdict(r) for r in train], "holdout": [asdict(r) for r in holdout],
        "lambda_grid": grid,
        "selection": study_design(20000)["lambda_search"],
        "replication_seeds": list(MC_SEEDS), "replication_draws_per_seed": 20000,
        "negative_controls": "For each holdout regime, repeat with uninformative channel (1/3 outcome or.5 alignment). No-future-flow isolated cohort has no information benefit.",
    }
    design_text = json.dumps(design, sort_keys=True, indent=2) + "\n"
    design_path = output_dir / "design.json"
    if design_path.exists() and design_path.read_text() != design_text:
        raise ValueError("Population design changed; use a fresh output directory.")
    design_path.write_text(design_text)
    all_policy, all_worlds, effects = [], [], []

    def evaluate(regimes, rule, lam, split):
        selected = []
        for regime in regimes:
            summaries, raw = evaluate_regime(regime, rule, lam, signal_target)
            effect = effect_row(summaries)
            all_policy.extend({"split": split, **r} for r in summaries)
            all_worlds.extend({"split": split, **r} for r in raw)
            effects.append({"split": split, **effect})
            selected.append(effect)
        return selected

    base = evaluate(train, "flat", 0.0, "train")
    eligible = {r["regime"] for r in base if r["late_committed_return"] > 1e-12}
    baseline_private_entry = statistics.mean(r["private_entry_rate"] for r in base)
    candidates = []
    tested = set()

    def candidate(lam):
        rows = evaluate(train, "normalized", lam, "train")
        preserved = all(r["late_committed_return"] > 1e-12 for r in rows if r["regime"] in eligible)
        private_entry = statistics.mean(r["private_entry_rate"] for r in rows)
        feasible = bool(eligible) and preserved and private_entry >= baseline_private_entry * .5 - 1e-12
        record = {"lambda": lam, "feasible": feasible,
                  "mean_information_value": statistics.mean(r["private_information_value"] for r in rows),
                  "public_entry_rate": statistics.mean(r["public_entry_rate"] for r in rows),
                  "private_entry_rate": private_entry,
                  "public_profitable_baseline_regimes": len(eligible),
                  "public_profitable_baseline_regimes_preserved": sum(r["late_committed_return"] > 1e-12 for r in rows if r["regime"] in eligible),
                  "mean_public_offered_return": statistics.mean(r["public_offered_return"] for r in rows),
                  "mean_private_offered_return": statistics.mean(r["private_offered_return"] for r in rows)}
        candidates.append(record); tested.add(lam)

    for lam in grid:
        candidate(lam)
    while True:
        feasible = [r for r in candidates if r["feasible"]]
        selected = min(feasible, key=lambda r: (r["mean_information_value"], r["lambda"])) if feasible else None
        if selected is None or selected["lambda"] < max(tested) or max(tested) >= 64:
            break
        candidate(max(tested) * 2)
    # Only now is the holdout population evaluated. No lambda is selected on it.
    holdout_sets = {}
    for rule, lam in (("flat", 0.0), ("normalized", .15), ("isolated_cohort", 0.0)):
        holdout_sets[f"{rule}_{lam}"] = evaluate(holdout, rule, lam, "holdout")
    if selected is not None and selected["lambda"] != .15:
        holdout_sets[f"selected_{selected['lambda']}"] = evaluate(holdout, "normalized", selected["lambda"], "holdout_selected")
    elif selected is not None:
        holdout_sets[f"selected_{selected['lambda']}"] = holdout_sets["normalized_0.15"]
    # Negative controls use the same worlds/payoffs, with only the information
    # channel replaced by independent noise; never used to choose lambda.
    controls = []
    for regime in holdout:
        null = replace(regime, signal_accuracy=(1 / 3 if signal_target == "outcome" else .5))
        control = effect_row(evaluate_regime(null, "flat", 0.0, signal_target)[0])
        controls.append(control)
        if abs(control["private_information_value"]) > 1e-10:
            raise AssertionError("Uninformative-signal control failed")
    no_flow = TimingRegime("no_future_flow_isolated_control", future_shares=0, signal_accuracy=.9)
    controls.append(effect_row(evaluate_regime(no_flow, "isolated_cohort", 0.0, signal_target)[0]))
    if abs(controls[-1]["private_information_value"]) > 1e-10:
        raise AssertionError("No-flow isolated-cohort control failed")
    aggregates = []
    for name, rows in holdout_sets.items():
        aggregates.append({"arm": name, "regime_count": len(rows),
                           "mean_information_value": statistics.mean(r["private_information_value"] for r in rows),
                           "mean_public_offered_return": statistics.mean(r["public_offered_return"] for r in rows),
                           "mean_private_offered_return": statistics.mean(r["private_offered_return"] for r in rows),
                           "public_entry_rate": statistics.mean(r["public_entry_rate"] for r in rows),
                           "private_entry_rate": statistics.mean(r["private_entry_rate"] for r in rows),
                           "strict_information_value_regimes": sum(r["private_information_value"] > 1e-10 for r in rows)})
    # Paired independent-seed MC checks all reported held-out policy arms.
    grouped = {}
    for row in all_worlds:
        if row["split"].startswith("holdout"):
            grouped.setdefault((row["split"], row["regime"], row["rule"], row["lambda"]), []).append(row)
    mc = [result for rows in grouped.values() for result in monte_carlo_check(rows, 20000)]
    write_csv(output_dir / "policy_summary.csv", all_policy)
    write_csv(output_dir / "worlds.csv", all_worlds)
    write_csv(output_dir / "causal_effects.csv", effects)
    write_csv(output_dir / "lambda_train_selection.csv", candidates)
    write_csv(output_dir / "holdout_summary.csv", aggregates)
    write_csv(output_dir / "negative_controls.csv", controls)
    write_csv(output_dir / "monte_carlo_replication.csv", mc)
    result = {"signal_target": signal_target, "selected": selected,
              "selection_at_upper_boundary": selected is not None and selected["lambda"] == max(tested),
              "holdout": aggregates, "exact_world_rows": len(all_worlds),
              "design_sha256": hashlib.sha256(design_text.encode()).hexdigest(),
              "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "reference_engine_sha256": hashlib.sha256(Path(__file__).with_name("reference_parallel_lmsr.py").read_bytes()).hexdigest()}
    (output_dir / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mc-draws", type=int, default=20000)
    parser.add_argument("--population", choices=("outcome", "flow_alignment"))
    args = parser.parse_args()
    if args.mc_draws < 2:
        parser.error("--mc-draws must be at least 2")
    if args.population:
        result = run_population_study(args.output_dir, args.population)
        print(json.dumps(result, indent=2))
    else:
        result = run_causal_study(args.output_dir, args.mc_draws)
        print(json.dumps({"provenance": result["provenance"], "canonical": [r for r in result["effects"] if r["regime"] == "canonical"]}, indent=2))


if __name__ == "__main__":
    main()
