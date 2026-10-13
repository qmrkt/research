"""Frozen publication diagnostics for active LP residual accounting.

Run from the repository root after installing the research package::

    python -m research.active_lp.publication_validation

This suite does not tune parameters. It compares residual allocations on identical
requested histories, distinguishes stress cases from randomized inference, and
retains source hashes, requests, cohort rows, blocked trades and bootstrap configuration.
The capital-account comparator is resolved-only, separate from production policy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from research.active_lp import reference_parallel_lmsr as ref
from research.active_lp.events import (
    BootstrapMarket, BuyOutcome, CancelMarket, LpEnterActive, ResolveMarket, SellOutcome,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector

D = Decimal
ZERO = D(0)
ONE = D(1)
FUNDING = ("floor", "fixed_20", "proportional_20pct")
POLICIES = ("flat", "normalized_015", "capital_accounts")
REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO / "01-active-lp" / "output" / "publication_validation"
PLAN = {
    "schema": "publication_validation_v1",
    "status": "fixed diagnostic comparison; no parameter selection or retuning",
    "holdout_seed_start": 41000,
    "holdout_histories": 96,
    "development_seed_start": 31000,
    "adaptive_stress_seed_start": 42000,
    "adaptive_stress_histories": 4,
    "outcomes": [3, 5, 8],
    "depths": [80, 100, 160],
    "trade_count": [40, 100],
    "lp_entry_count": [1, 4],
    "lp_depth_fractions": [0.1, 0.2, 0.4],
    "trade_depth_fractions": [0.02, 0.05, 0.1, 0.2],
    "lp_fee_bps": [50, 200],
    "protocol_fee_bps": [0, 25],
    "sell_request_probability": 0.35,
    "traders": 8,
    "clock": "independent integer interarrival gaps uniform 1..6; no restamped holdout copies",
    "latent_process": "softmax of iid Normal(0,0.8) logits; fixed latent outcome probabilities per path",
    "buy_signal": "mixture of uniform and latent probabilities; latent weight 0.15+0.7*trade_index/trade_count",
    "outcome_draw": "independent categorical draw from latent probabilities after requests are constructed",
    "funding": {"floor": "b*ln(N)", "fixed_20": "floor+20", "proportional_20pct": "floor*1.20"},
    "residual_rules": {
        "flat": "pool allocated by depth shares",
        "normalized_015": "historical lambda=.15 normalized time premium; diagnostic, never retuned",
        "capital_accounts": "D_k+trade_cash_k-net_claim_k[winner]; resolved-only component bookkeeping; fees unchanged",
    },
    "primary_estimands": ["mean late-minus-founder terminal NAV/deposit gap", "mean absolute gap"],
    "secondary_metrics": ["LP profit/deposit", "founder and last LP returns", "5/50/95 percentiles", "min/max", "conditional 5% tails", "guard rejection counts and quoted blocked proceeds", "minimum refund and outcome coverage", "fee yield"],
    "inference": "95% percentile intervals, 2000 bootstrap resamples of independent history IDs; paired policy/funding contrasts; no CI for stress/adaptive packs",
    "bootstrap_seed": 51000,
    "bootstrap_resamples": 2000,
    "historical": "paper_quick MC seeds2100..2163 restamped12/48/168 and odd-parity adversarial holdout; descriptive replication, not fresh evidence",
    "adaptive": "greedy state-aware one-step expected terminal wealth improvement using fixed latent belief; observed current state, projected scheduled terminal time; wait/buy/sell/LP/joint buy+LP candidates; 4 decision epochs; not global optimality or equilibrium",
    "scope": "decimal reference accounting after cancellation reserve guard; synthetic workload, no AVM/production safety or universal fairness claim",
}


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value: Any) -> str:
    return json.dumps(value, default=json_default, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, default=json_default, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, values: Iterable[dict]) -> None:
    with path.open("w") as handle:
        for value in values:
            handle.write(canonical(value) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


@dataclass
class History:
    path_id: str
    cluster_id: str
    pack: str
    seed: int | None
    outcomes: int
    initial_b: Decimal
    fee_bps: Decimal
    protocol_fee_bps: Decimal
    true_probabilities: tuple[Decimal, ...]
    steps: list[dict]
    winner: int | None
    settlement_time: int
    description: str = ""


def sample_category(rng: random.Random, probabilities: Iterable[Decimal | float]) -> int:
    values = list(probabilities)
    value = rng.random()
    for index, probability in enumerate(values):
        value -= float(probability)
        if value <= 0:
            return index
    return len(values) - 1


def generate_history(seed: int, *, pack: str = "holdout") -> History:
    rng = random.Random(seed)
    n = rng.choice(PLAN["outcomes"])
    b = D(rng.choice(PLAN["depths"]))
    count = rng.randint(*PLAN["trade_count"])
    entries = rng.randint(*PLAN["lp_entry_count"])
    fee = D(rng.choice(PLAN["lp_fee_bps"]))
    protocol = D(rng.choice(PLAN["protocol_fee_bps"]))
    logits = [math.exp(rng.gauss(0, 0.8)) for _ in range(n)]
    probabilities = [D(str(value / sum(logits))) for value in logits]
    probabilities[-1] = ONE - sum(probabilities[:-1], ZERO)
    entry_slots = sorted(rng.randrange(1, count + 1) for _ in range(entries))
    positions: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    steps: list[dict] = []
    clock = 1
    entry_count = 0
    for slot in range(count + 1):
        for _ in range(entry_slots.count(slot)):
            clock += rng.randint(1, 6)
            steps.append({"kind": "lp", "timestamp": clock, "actor": f"lp_{entry_count}", "amount": b * D(str(rng.choice(PLAN["lp_depth_fractions"])))})
            entry_count += 1
        if slot == count:
            break
        clock += rng.randint(1, 6)
        available = [(key, size) for key, size in sorted(positions.items()) if size > 0]
        if available and rng.random() < PLAN["sell_request_probability"]:
            (actor, outcome), held = rng.choice(available)
            size = min(held, b * D(str(rng.choice(PLAN["trade_depth_fractions"]))))
            positions[(actor, outcome)] -= size
            kind = "sell"
        else:
            signal_weight = D(".15") + D(".7") * D(slot) / D(count)
            signal = [(ONE - signal_weight) / n + signal_weight * p for p in probabilities]
            outcome = sample_category(rng, signal)
            actor = f"trader_{rng.randrange(PLAN['traders'])}"
            size = b * D(str(rng.choice(PLAN["trade_depth_fractions"])))
            positions[(actor, outcome)] += size
            kind = "buy"
        steps.append({"kind": kind, "timestamp": clock, "actor": actor, "outcome": outcome, "amount": size})
    winner = sample_category(rng, probabilities)
    return History(f"{pack}_{seed}", f"{pack}_{seed}", pack, seed, n, b, fee, protocol, tuple(probabilities), steps, winner, clock + rng.randint(1, 6))


def funded_amount(n: int, b: Decimal, funding: str) -> Decimal:
    floor = collateral_required(b, uniform_price_vector(n))
    if funding == "floor":
        return floor
    if funding == "fixed_20":
        return floor + D(20)
    if funding == "proportional_20pct":
        return floor * D("1.2")
    raise ValueError(funding)


def nonfee_assets(state: Any) -> Decimal:
    return D(state.treasury.contract_funds) - D(state.treasury.lp_fee_balance) - D(state.treasury.protocol_fee_balance)


def refund_requirement(state: Any) -> Decimal:
    return sum((sum(map(D, basis), ZERO) for basis in state.traders.cost_basis_by_trader.values()), ZERO)


def engine_for(history: History) -> ref.ReferenceParallelLmsrEngine:
    return ref.ReferenceParallelLmsrEngine(lp_fee_bps=history.fee_bps, protocol_fee_bps=history.protocol_fee_bps, residual_policy=ref.RESERVE_POOL, residual_weight_scheme="flat")


def initial_state(history: History, funding: str, engine: Any) -> Any:
    state = ref.create_initial_state(history.outcomes, residual_weight_scheme="flat")
    return engine.apply_event(state, BootstrapMarket(1, "creator", funded_amount(history.outcomes, history.initial_b, funding), history.initial_b))


def step_event(step: dict, state: Any) -> Any:
    kind = step["kind"]
    t, actor, amount = step["timestamp"], step["actor"], D(step["amount"])
    if kind == "lp":
        return LpEnterActive(t, actor, amount, D("1e100"), tuple(state.pricing.price_vector), D("1e-18"))
    if kind == "buy":
        return BuyOutcome(t, actor, step["outcome"], amount, D("1e100"))
    if kind == "sell":
        return SellOutcome(t, actor, step["outcome"], amount, ZERO)
    raise ValueError(kind)


def apply_request(engine: Any, state: Any, step: dict) -> tuple[Any, Decimal, dict | None]:
    """Return updated state, actor cash outflow (negative for sells), rejection."""
    event = step_event(step, state)
    before = D(state.treasury.contract_funds)
    try:
        after = engine.apply_event(state, event)
    except ValueError as exc:
        if not isinstance(event, SellOutcome) or "underfund cancellation refunds" not in str(exc):
            raise
        gross = engine.sell_return(state.pricing, event.outcome_index, event.shares)
        net = gross * (ONE - (engine.lp_fee_bps + engine.protocol_fee_bps) / D(10000))
        rejection = {**step, "reason": str(exc), "quoted_gross_proceeds": gross, "quoted_net_proceeds": net, "shortfall": getattr(exc, "shortfall", None), "pre_refund_margin": nonfee_assets(state) - refund_requirement(state)}
        return state, ZERO, rejection
    return after, D(after.treasury.contract_funds) - before, None


def run_history(history: History, funding: str) -> tuple[Any, dict, list[dict]]:
    engine = engine_for(history)
    state = initial_state(history, funding, engine)
    min_refund = nonfee_assets(state) - refund_requirement(state)
    min_outcome = nonfee_assets(state) - max(map(D, state.traders.aggregate_outstanding_claims))
    minimum_component = min(map(D, next(iter(state.sponsors.values())).residual_basis_by_outcome))
    min_price = min(map(D, state.pricing.price_vector))
    rejected: list[dict] = []
    executed: list[dict] = []
    for index, step in enumerate(history.steps):
        state, _, failure = apply_request(engine, state, step)
        if failure is not None:
            rejected.append({"path_id": history.path_id, "cluster_id": history.cluster_id, "funding": funding, "request_index": index, **failure})
        else:
            executed.append(step)
        min_refund = min(min_refund, nonfee_assets(state) - refund_requirement(state))
        min_outcome = min(min_outcome, nonfee_assets(state) - max(map(D, state.traders.aggregate_outstanding_claims)))
        minimum_component = min(minimum_component, *(D(v) for sponsor in state.sponsors.values() for v in sponsor.residual_basis_by_outcome))
        min_price = min(min_price, *map(D, state.pricing.price_vector))
    audit = {
        "requested_trades": sum(s["kind"] in ("buy", "sell") for s in history.steps),
        "requested_sells": sum(s["kind"] == "sell" for s in history.steps),
        "rejected_sells": len(rejected),
        "blocked_net_proceeds": sum((r["quoted_net_proceeds"] for r in rejected), ZERO),
        "blocked_shares": sum((D(r["amount"]) for r in rejected), ZERO),
        "min_refund_margin": min_refund,
        "min_all_outcome_margin": min_outcome,
        "min_component_branch_margin": minimum_component,
        "min_price": min_price,
        "request_hash": digest(history.steps),
        "execution_hash": digest(executed),
    }
    return state, audit, rejected


def allocations(state: Any, policy: str, winner: int | None, settlement_time: int) -> dict[str, Decimal]:
    """Terminal pre-claim residuals, with no external valuation assumption.

    Capital accounts are only an accounting comparator for resolved outcomes;
    they have the exact component-wise D+cash-liability identity. Cancellation
    refund liabilities are not component attributable by the proposed protocol.
    """
    reserve = refund_requirement(state) if winner is None else D(state.traders.aggregate_outstanding_claims[winner])
    free = nonfee_assets(state) - reserve
    if free < D("-1e-12"):
        raise AssertionError(f"underfunded terminal reserve: {free}")
    free = max(free, ZERO)
    if policy == "capital_accounts":
        if winner is None:
            raise ValueError("capital accounts comparator is resolved-only")
        result = {key: D(sponsor.locked_collateral) + D(sponsor.trade_cash_balance) - (D(sponsor.current_q[winner]) - D(sponsor.baseline_q[winner])) for key, sponsor in state.sponsors.items()}
        if min(result.values()) < D("-1e-12"):
            raise AssertionError("negative resolved component capital account")
    else:
        start = min(s.entry_timestamp for s in state.sponsors.values())
        span = max(1, settlement_time - start)
        weights = {}
        for key, sponsor in state.sponsors.items():
            weight = D(sponsor.share_units)
            if policy == "normalized_015":
                elapsed = max(1, settlement_time - sponsor.entry_timestamp)
                exposure = D(max(0, elapsed - 1)) / D(span - 1) if span > 1 else ZERO
                weight *= ONE + D(".15") * exposure
            elif policy != "flat":
                raise ValueError(policy)
            weights[key] = weight
        total = sum(weights.values(), ZERO)
        result = {key: free * weight / total for key, weight in weights.items()}
    if abs(sum(result.values(), ZERO) - free) > D("1e-10"):
        raise AssertionError("residual allocation does not conserve aggregate pool")
    return result


def measure(history: History, funding: str, state: Any, audit: dict, *, winner: int | None = -1, policy: str = "flat") -> tuple[dict, list[dict]]:
    if winner == -1:
        winner = history.winner
    residual = allocations(state, policy, winner, history.settlement_time)
    cohorts = []
    for key, sponsor in sorted(state.sponsors.items(), key=lambda pair: (pair[1].entry_timestamp, pair[0])):
        deposited = D(sponsor.collateral_posted)
        fees = D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus)
        nav = residual[key] + fees
        cohorts.append({"path_id": history.path_id, "cluster_id": history.cluster_id, "pack": history.pack, "funding": funding, "policy": policy, "winner": winner, "cohort_id": key, "actor": sponsor.sponsor_id, "entry_timestamp": sponsor.entry_timestamp, "depth": sponsor.target_delta_b, "deposit": deposited, "residual": residual[key], "fees": fees, "nav": nav, "profit": nav - deposited, "nav_per_deposit": nav / deposited, "locked_capital_time": deposited * max(1, history.settlement_time - sponsor.entry_timestamp)})
    first, last = cohorts[0], cohorts[-1]
    gap = last["nav_per_deposit"] - first["nav_per_deposit"]
    total_deposit = sum((r["deposit"] for r in cohorts), ZERO)
    total_nav = sum((r["nav"] for r in cohorts), ZERO)
    total_fees = sum((r["fees"] for r in cohorts), ZERO)
    row = {"path_id": history.path_id, "cluster_id": history.cluster_id, "pack": history.pack, "seed": history.seed, "funding": funding, "policy": policy, "outcomes": history.outcomes, "winner": winner, "initial_b": history.initial_b, "duration": history.settlement_time - 1, "cohorts": len(cohorts), "gap": gap, "absolute_gap": abs(gap), "founder_nav_per_deposit": first["nav_per_deposit"], "late_nav_per_deposit": last["nav_per_deposit"], "total_lp_deposit": total_deposit, "total_lp_nav": total_nav, "total_lp_profit": total_nav - total_deposit, "total_lp_roi": total_nav / total_deposit - ONE, "fee_yield": total_fees / total_deposit, "min_cohort_roi": min(r["nav_per_deposit"] - ONE for r in cohorts), "total_locked_capital_time": sum((r["locked_capital_time"] for r in cohorts), ZERO), **audit}
    return row, cohorts


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty sample")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def clustered_summary(rows: list[dict], metric: str, *, resamples: int = 2000, seed: int = 51000) -> dict:
    """Equal-weight base histories; restamps/branches never increase sample size."""
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[row["cluster_id"]].append(float(row[metric]))
    values = [statistics.mean(groups[key]) for key in sorted(groups)]
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(resamples)]
    tail_size = max(1, math.ceil(0.05 * len(values)))
    ordered = sorted(values)
    return {"n_rows": len(rows), "n_independent_clusters": len(values), "mean": statistics.mean(values), "ci95": [quantile(means, 0.025), quantile(means, 0.975)], "p05": quantile(values, 0.05), "median": quantile(values, 0.5), "p95": quantile(values, 0.95), "min": min(values), "max": max(values), "mean_lower_5pct": statistics.mean(ordered[:tail_size]), "mean_upper_5pct": statistics.mean(ordered[-tail_size:]), "positive_fraction": sum(v > 1e-12 for v in values) / len(values)}


def summarize_holdout(rows: list[dict], resamples: int) -> dict:
    result: dict[str, Any] = {"groups": {}, "paired_contrasts": {}}
    metrics = ("gap", "absolute_gap", "total_lp_roi", "fee_yield", "rejected_sells", "blocked_net_proceeds")
    for funding in FUNDING:
        for policy in POLICIES:
            selected = [r for r in rows if r["funding"] == funding and r["policy"] == policy]
            result["groups"][f"{funding}/{policy}"] = {metric: clustered_summary(selected, metric, resamples=resamples) for metric in metrics}
        base = {r["path_id"]: r for r in rows if r["funding"] == funding and r["policy"] == "flat"}
        for policy in POLICIES[1:]:
            selected = [r for r in rows if r["funding"] == funding and r["policy"] == policy]
            for metric in ("gap", "absolute_gap"):
                paired = [{"cluster_id": r["cluster_id"], "difference": D(r[metric]) - D(base[r["path_id"]][metric])} for r in selected]
                result["paired_contrasts"][f"{funding}/{policy}-flat/{metric}"] = clustered_summary(paired, "difference", resamples=resamples)
    for policy in POLICIES:
        base = {r["path_id"]: r for r in rows if r["funding"] == "floor" and r["policy"] == policy}
        for funding in FUNDING[1:]:
            selected = [r for r in rows if r["funding"] == funding and r["policy"] == policy]
            paired = [{"cluster_id": r["cluster_id"], "difference": D(r["gap"]) - D(base[r["path_id"]]["gap"])} for r in selected]
            result["paired_contrasts"][f"{policy}/{funding}-floor/gap"] = clustered_summary(paired, "difference", resamples=resamples)
    result["guard"] = {"unique_path_funding_runs": len(rows) // len(POLICIES), "runs_with_rejected_sells": sum(r["rejected_sells"] > 0 for r in rows if r["policy"] == "flat"), "total_rejected_sells": sum(r["rejected_sells"] for r in rows if r["policy"] == "flat"), "minimum_refund_margin": str(min(D(r["min_refund_margin"]) for r in rows)), "minimum_outcome_margin": str(min(D(r["min_all_outcome_margin"]) for r in rows))}
    return result


def stress_histories() -> list[History]:
    result = []
    for n in (3, 8):
        name = f"stress_zero_flow_n{n}"
        result.append(History(name, name, "stress", None, n, D(100), ZERO, ZERO, uniform_price_vector(n), [{"kind": "lp", "timestamp": 2, "actor": "late", "amount": D(20)}], 0, 3, "zero information/flow: isolates bootstrap endowment transfer"))
        steps = []
        for index in range(60):
            steps.append({"kind": "buy", "timestamp": 2 * index + 2, "actor": f"trader_{index % 4}", "outcome": 0 if index < 45 else 1, "amount": D(20)})
            if index in (15, 30, 50):
                steps.append({"kind": "lp", "timestamp": 2 * index + 3, "actor": f"lp_{index}", "amount": D(20)})
        name = f"stress_concentrated_n{n}"
        result.append(History(name, name, "stress", None, n, D(100), D(200), D(25), uniform_price_vector(n), steps, 0, 124, "concentrated 60-trade path; every terminal outcome evaluated"))
    steps = [{"kind": "buy", "timestamp": 2, "actor": "alice", "outcome": 0, "amount": D(250)}, {"kind": "buy", "timestamp": 3, "actor": "bob", "outcome": 1, "amount": D(500)}, {"kind": "lp", "timestamp": 4, "actor": "late", "amount": D(20)}]
    result.append(History("stress_low_tail_n64", "stress_low_tail_n64", "stress", None, 64, D(100), ZERO, ZERO, uniform_price_vector(64), steps, 1, 5, "previous low-tail trace; all 64 resolved branches, preclaim accounting"))
    steps = []
    for index in range(40):
        steps.append({"kind": "buy", "timestamp": index * 2 + 2, "actor": f"trader_{index % 4}", "outcome": index % 3, "amount": D(5)})
        if index < 32:
            steps.append({"kind": "lp", "timestamp": index * 2 + 3, "actor": f"micro_lp_{index}", "amount": D(".1")})
    result.append(History("stress_many_cohorts", "stress_many_cohorts", "stress", None, 3, D(100), D(200), D(25), uniform_price_vector(3), steps, 0, 84, "32 small late cohorts; accounting only, not AVM resource validation"))
    steps = []
    for index, (kind, actor, outcome, amount) in enumerate((("buy", "a", 0, 100), ("buy", "b", 0, 500), ("sell", "a", 0, 100), ("buy", "a", 1, 100), ("buy", "c", 1, 1000), ("sell", "a", 1, 100))):
        steps.append({"kind": kind, "timestamp": index + 2, "actor": actor, "outcome": outcome, "amount": D(amount)})
    result.append(History("stress_cancel_profit_sells", "stress_cancel_profit_sells", "stress", None, 3, D(100), ZERO, ZERO, uniform_price_vector(3), steps, None, 8, "published cancellation counterexample; rejected request retained"))
    return result


def expected_attacker_wealth(state: Any, policy: str, history: History, outlay: Decimal) -> Decimal:
    expected = -outlay
    shares = state.traders.positions_by_trader.get("adaptive_attacker", (ZERO,) * history.outcomes)
    for outcome, probability in enumerate(history.true_probabilities):
        residual = allocations(state, policy, outcome, history.settlement_time)
        value = D(shares[outcome])
        for key, sponsor in state.sponsors.items():
            if sponsor.sponsor_id == "adaptive_attacker":
                value += residual[key] + D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus)
        expected += probability * value
    return expected


def adaptive_candidates(state: Any, timestamp: int, initial_b: Decimal) -> list[list[dict]]:
    def step(kind: str, amount: Decimal, outcome: int | None = None) -> dict:
        record = {"kind": kind, "timestamp": timestamp, "actor": "adaptive_attacker", "amount": amount}
        if outcome is not None:
            record["outcome"] = outcome
        return record
    candidates: list[list[dict]] = [[]]
    for fraction in (D(".1"), D(".25")):
        candidates.append([step("lp", initial_b * fraction)])
    holdings = state.traders.positions_by_trader.get("adaptive_attacker", (ZERO,) * state.pricing.num_outcomes)
    for outcome in range(state.pricing.num_outcomes):
        for fraction in (D(".05"), D(".2")):
            size = initial_b * fraction
            buy = step("buy", size, outcome)
            candidates.append([buy])
            candidates.append([buy, step("lp", initial_b * D(".1"))])
            if D(holdings[outcome]) > 0:
                candidates.append([step("sell", min(D(holdings[outcome]), size), outcome)])
    return candidates


def run_adaptive(history: History, funding: str, policy: str) -> tuple[list[dict], list[dict]]:
    engine = engine_for(history)
    state = initial_state(history, funding, engine)
    outlay = ZERO
    decisions = []
    epochs = {0, len(history.steps) // 3, 2 * len(history.steps) // 3, len(history.steps)}
    selected_count = 0
    rejected_external = 0
    for index in range(len(history.steps) + 1):
        if index in epochs:
            timestamp = history.steps[index]["timestamp"] if index < len(history.steps) else history.settlement_time - 1
            current = expected_attacker_wealth(state, policy, history, outlay)
            best, best_state, best_outlay, chosen = current, state, outlay, []
            candidates_log = []
            for actions in adaptive_candidates(state, timestamp, history.initial_b):
                candidate = state
                candidate_outlay = outlay
                valid = True
                for action in actions:
                    candidate, cash, rejected = apply_request(engine, candidate, action)
                    if rejected is not None:
                        valid = False
                        break
                    candidate_outlay += cash
                if not valid:
                    candidates_log.append({"actions": actions, "rejected_by_guard": True})
                    continue
                value = expected_attacker_wealth(candidate, policy, history, candidate_outlay)
                candidates_log.append({"actions": actions, "expected_profit": value})
                if value > best + D("1e-12"):
                    best, best_state, best_outlay, chosen = value, candidate, candidate_outlay, actions
            decisions.append({"path_id": history.path_id, "funding": funding, "policy": policy, "request_index": index, "observed_prices": list(state.pricing.price_vector), "belief": history.true_probabilities, "baseline_expected_profit": current, "chosen_expected_profit": best, "gain_over_wait": best - current, "chosen_actions": chosen, "candidates": candidates_log})
            state, outlay = best_state, best_outlay
            selected_count += len(chosen)
        if index < len(history.steps):
            state, _, rejection = apply_request(engine, state, history.steps[index])
            rejected_external += rejection is not None
    rows = []
    for outcome in range(history.outcomes):
        residual = allocations(state, policy, outcome, history.settlement_time)
        payoff = D(state.traders.positions_by_trader.get("adaptive_attacker", (ZERO,) * history.outcomes)[outcome])
        for key, sponsor in state.sponsors.items():
            if sponsor.sponsor_id == "adaptive_attacker":
                payoff += residual[key] + D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus)
        rows.append({"path_id": history.path_id, "cluster_id": history.cluster_id, "pack": "adaptive_stress", "funding": funding, "policy": policy, "winner": outcome, "belief_probability": history.true_probabilities[outcome], "attacker_cash_outlay": outlay, "attacker_terminal_payoff": payoff, "attacker_profit": payoff - outlay, "selected_actions": selected_count, "external_sells_rejected": rejected_external, "expected_profit": expected_attacker_wealth(state, policy, history, outlay)})
    return rows, decisions


def historical_histories() -> list[History]:
    from research.active_lp.monte_carlo import generate_monte_carlo_bundles
    from research.active_lp.adversarial_search import generate_adversarial_bundles
    from research.active_lp.scenarios import restamp_bundle_duration
    from research.active_lp.sweep_presets import build_sweep_preset
    preset = build_sweep_preset("paper_quick")
    base = generate_monte_carlo_bundles(replace(preset.monte_carlo, seed=2100, num_trials=64))
    bundles = [(restamp_bundle_duration(bundle, duration_steps=duration, duration_bucket=label, split="test", name_suffix=label), f"historical_mc_{bundle.config.seed}") for bundle in base for label, duration in (("short", 12), ("medium", 48), ("long", 168))]
    for index, bundle in enumerate(generate_adversarial_bundles(preset.adversarial)):
        if index % 2:
            bundles.append((bundle, f"historical_adv_{index // 2}"))
    histories = []
    for bundle, cluster in bundles:
        steps = []
        winner = None
        terminal = None
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
            raise ValueError("historical path lacks terminal event")
        config = bundle.config
        histories.append(History(f"historical_{config.name}", cluster, "historical", config.seed, config.num_outcomes, D(config.initial_depth_b), D(config.fee_bps), D(config.protocol_fee_bps), uniform_price_vector(config.num_outcomes), steps, winner, terminal, bundle.description))
    return histories


def historical_summary(rows: list[dict]) -> dict:
    result = {}
    for funding in FUNDING:
        for policy in POLICIES:
            selected = [r for r in rows if r["funding"] == funding and r["policy"] == policy]
            if not selected:
                continue
            result[f"{funding}/{policy}"] = {"rows": len(selected), "base_histories": len({r["cluster_id"] for r in selected}), "row_weighted_mean_gap": float(statistics.mean(D(r["gap"]) for r in selected)), "row_weighted_mean_absolute_gap": float(statistics.mean(D(r["absolute_gap"]) for r in selected)), "min_gap": float(min(D(r["gap"]) for r in selected)), "max_gap": float(max(D(r["gap"]) for r in selected)), "rejected_sells": sum(r["rejected_sells"] for r in selected), "warning": "historical row-weighted replication only; restamps are not independent; capital-account cancellation rows omitted"}
    return result


def report_text(summary: dict, historical: dict, rows: list[dict], stress: list[dict], adaptive: list[dict], config: dict) -> str:
    lines = ["# Active-LP publication validation", "", "Fixed diagnostic comparison; synthetic reference-engine results, not a fairness optimum or deployment validation.", "", f"Independent holdout histories: {config['holdout_histories']}; seeds {config['holdout_seed_start']}–{config['holdout_seed_start'] + config['holdout_histories'] - 1}; 40–100 requested trades each. Funding is paired by identical requests. Guard-rejected requests remain in the logs; actual execution can differ across funding regimes. Normalized lambda .15 is frozen, not fit to these data.", "", "## Fresh randomized holdout", "", "Intervals are percentile bootstrap 95% intervals on history-level means. No restamps are counted as independent observations. Tail statistics are empirical sample tails.", "", "| Funding | Residual allocation | Mean late−founder gap | 95% CI | Mean absolute gap | 95% CI | Mean LP ROI |", "| --- | --- | ---: | --- | ---: | --- | ---: |"]
    for key, values in summary["groups"].items():
        gap, absolute = values["gap"], values["absolute_gap"]
        funding, policy = key.split("/")
        lines.append(f"| {funding} | {policy} | {gap['mean']:.6f} | [{gap['ci95'][0]:.6f}, {gap['ci95'][1]:.6f}] | {absolute['mean']:.6f} | [{absolute['ci95'][0]:.6f}, {absolute['ci95'][1]:.6f}] | {values['total_lp_roi']['mean']:.6f} |")
    lines += ["", "The gap is a distributional diagnostic, not a risk-adjusted fairness criterion. Capital accounts use each component's contributed capital, routed trade cash and winning liability; they are resolved-only counterfactual bookkeeping, not NAV-priced entry or a production change. Fee rights are identical across comparisons.", "", "### Tails", "", "| Funding/rule | Gap p05 | Gap p95 | Gap min | Gap max | Mean worst 5% | Mean best 5% |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for key, values in summary["groups"].items():
        metric = values["gap"]
        lines.append(f"| {key} | {metric['p05']:.6f} | {metric['p95']:.6f} | {metric['min']:.6f} | {metric['max']:.6f} | {metric['mean_lower_5pct']:.6f} | {metric['mean_upper_5pct']:.6f} |")
    guard = summary["guard"]
    lines += ["", "### Cancellation reserve guard", "", f"{guard['total_rejected_sells']} sell requests were blocked in {guard['runs_with_rejected_sells']} of {guard['unique_path_funding_runs']} holdout path/funding runs. Minimum recorded refundable-basis margin: {guard['minimum_refund_margin']}. Minimum recorded all-outcome margin: {guard['minimum_outcome_margin']}.", "", "Blocked quoted proceeds are forgone immediate liquidation opportunity, not measured welfare loss. Each rejected request, share amount, quote and reserve shortfall is preserved in rejections.jsonl. The guard restricts sell availability; solvency is not costless.", "", "## Designed stress pack", "", f"{len(stress)} terminal outcome/funding/allocation rows, including all 64 low-tail branches, concentrated flow, zero-flow bootstrap dilution, 32 small LP cohorts and the cancellation counterexample. These are designed cases, not independent random observations and have no population confidence intervals.", "", "| History | Funding | Rejected sells | Blocked quoted net proceeds |", "| --- | --- | ---: | ---: |"]
    seen = set()
    for row in stress:
        key = (row["path_id"], row["funding"])
        if key not in seen:
            seen.add(key)
            lines.append(f"| {key[0]} | {key[1]} | {row['rejected_sells']} | {float(row['blocked_net_proceeds']):.6f} |")
    lines += ["", "## Adaptive LP/trader stress", "", "A greedy actor observes current state, evaluates explicit buy/sell/LP/joint buy+LP candidates against a fixed latent outcome belief and chooses the one-step expected-wealth improvement over waiting. This is an actual state-dependent action policy; it is not a globally optimal adversary, equilibrium, or an estimate of attack incidence. Candidate action sizes are bounded but there is no total attacker budget cap. Positive profit may reflect legitimate informed trading and is not by itself proof of extraction from LPs. All candidate objectives and selected actions are published.", "", "| Funding | Rule | Histories | Mean belief-weighted attacker profit | Worst realized branch | Best realized branch |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for funding in FUNDING:
        for policy in POLICIES:
            selected = [r for r in adaptive if r["funding"] == funding and r["policy"] == policy]
            if selected:
                grouped = {r["path_id"]: D(r["expected_profit"]) for r in selected}
                lines.append(f"| {funding} | {policy} | {len(grouped)} | {float(statistics.mean(grouped.values())):.6f} | {float(min(D(r['attacker_profit']) for r in selected)):.6f} | {float(max(D(r['attacker_profit']) for r in selected)):.6f} |")
    lines += ["", "## Historical ablation replication", "", "The original paper_quick held-out pack has 192 restamped MC rows from 64 histories plus 96 designed adversarial rows. Historical rows are reported with their original row weighting for comparison; this is not a new independent holdout. The original adversarial parity split separates terminal policies, not strategy histories. Capital-account summaries exclude cancellation rows and are therefore not directly comparable to pooled all-row summaries.", "", "| Funding/rule | Rows | Mean gap | Mean absolute gap |", "| --- | ---: | ---: | ---: |"]
    for key, values in historical.items():
        lines.append(f"| {key} | {values['rows']} | {values['row_weighted_mean_gap']:.9f} | {values['row_weighted_mean_absolute_gap']:.9f} |")
    lines += ["", "## Artifacts and limits", "", "- config.json records the predetermined design; provenance.json records interpreter, source hashes and configuration hash.", "- paths.jsonl contains every requested history; holdout_rows.csv and cohort_rows.jsonl retain outcomes, deposits, fees, returns, elapsed capital time and path/cluster IDs.", "- summary.json includes paired bootstrap contrasts, sample tails and secondary outcomes; no policy is selected from these results.", "- stress_rows.csv, adaptive_rows.csv, adaptive_decisions.jsonl and rejections.jsonl separate designed attacks from inference.", "- historical_rows.csv retains the complete selected historical holdout and its base-path IDs.", "", "The randomized distribution is synthetic and fixed for this study. It does not estimate real-world participation, information arrival, profitability or capital demand. All primary runs resolve; cancellation is checked in a separate explicit guarded stress path. Decimal-accounting checks do not validate fixed-point AVM budgets, rounding, deployed contracts, or proof of universal strategic safety. Small adaptive action grids can miss stronger attacks; capital accounts are a comparator rather than a newly validated mechanism.", ""]
    return "\n".join(lines)


def run(output: Path, *, smoke: bool = False, skip_historical: bool = False) -> dict:
    if not hasattr(ref, "refund_reserve_margin"):
        raise RuntimeError("Publication validation requires the corrected reference cancellation-reserve guard")
    config = dict(PLAN)
    if smoke:
        config.update(holdout_seed_start=31000, holdout_histories=3, adaptive_stress_histories=1, bootstrap_resamples=50, status="development smoke run; not publication evidence")
    config["historical_enabled"] = not skip_historical
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "config.json", config)  # freeze before any outcome is inspected
    source_files = [Path(__file__).with_name(name) for name in ("publication_validation.py", "reference_parallel_lmsr.py", "reference_math.py", "precision.py", "events.py", "state.py", "scenarios.py", "monte_carlo.py", "adversarial_search.py", "sweep_presets.py")]
    provenance = {"config_sha256": digest(config), "python": sys.version, "platform": platform.platform(), "sources": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}}
    try:
        provenance["git_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        provenance["git_head"] = None
    write_json(output / "provenance.json", provenance)
    rows, cohorts, rejections, paths = [], [], [], []
    with high_precision():
        histories = [generate_history(config["holdout_seed_start"] + i) for i in range(config["holdout_histories"])]
        for index, history in enumerate(histories):
            paths.append(asdict(history))
            for funding in FUNDING:
                state, audit, rejected = run_history(history, funding)
                rejections.extend(rejected)
                for policy in POLICIES:
                    row, cohort = measure(history, funding, state, audit, policy=policy)
                    rows.append(row)
                    cohorts.extend(cohort)
            if (index + 1) % 12 == 0:
                print(f"holdout {index + 1}/{len(histories)}", flush=True)
        stress_rows = []
        for history in stress_histories():
            paths.append(asdict(history))
            for funding in FUNDING:
                state, audit, rejected = run_history(history, funding)
                rejections.extend(rejected)
                winners = (None,) if history.winner is None else range(history.outcomes)
                for winner in winners:
                    for policy in POLICIES:
                        if winner is None and policy == "capital_accounts":
                            continue
                        row, cohort = measure(history, funding, state, audit, winner=winner, policy=policy)
                        stress_rows.append(row)
                        cohorts.extend(cohort)
        print("stress complete", flush=True)
        adaptive_rows, decisions = [], []
        for index in range(config["adaptive_stress_histories"]):
            history = generate_history(config["adaptive_stress_seed_start"] + index, pack="adaptive_stress")
            paths.append(asdict(history))
            for funding in FUNDING:
                for policy in POLICIES:
                    measured, chosen = run_adaptive(history, funding, policy)
                    adaptive_rows.extend(measured)
                    decisions.extend(chosen)
            print(f"adaptive {index + 1}/{config['adaptive_stress_histories']}", flush=True)
        historical_rows = []
        if not skip_historical:
            for history in historical_histories():
                paths.append(asdict(history))
                for funding in FUNDING:
                    state, audit, rejected = run_history(history, funding)
                    rejections.extend(rejected)
                    for policy in POLICIES:
                        if history.winner is None and policy == "capital_accounts":
                            continue
                        row, cohort = measure(history, funding, state, audit, policy=policy)
                        historical_rows.append(row)
                        cohorts.extend(cohort)
            print("historical complete", flush=True)
    summary = summarize_holdout(rows, config["bootstrap_resamples"])
    historical = historical_summary(historical_rows)
    write_jsonl(output / "paths.jsonl", paths)
    write_csv(output / "holdout_rows.csv", rows)
    write_jsonl(output / "cohort_rows.jsonl", cohorts)
    write_jsonl(output / "rejections.jsonl", rejections)
    write_csv(output / "stress_rows.csv", stress_rows)
    write_csv(output / "adaptive_rows.csv", adaptive_rows)
    write_jsonl(output / "adaptive_decisions.jsonl", decisions)
    write_csv(output / "historical_rows.csv", historical_rows)
    write_json(output / "summary.json", {"holdout": summary, "historical": historical})
    (output / "report.md").write_text(report_text(summary, historical, rows, stress_rows, adaptive_rows, config))
    for path in source_files:
        if hashlib.sha256(path.read_bytes()).hexdigest() != provenance["sources"][str(path.relative_to(REPO))]:
            raise RuntimeError(f"source changed during run: {path}")
    manifest = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}
    write_json(output / "manifest.json", manifest)
    print(f"Wrote {len(rows)} holdout, {len(stress_rows)} stress, {len(adaptive_rows)} adaptive and {len(historical_rows)} historical rows to {output}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--smoke", action="store_true", help="development seeds and smaller counts; not publication evidence")
    parser.add_argument("--skip-historical", action="store_true")
    args = parser.parse_args()
    run(args.output, smoke=args.smoke, skip_historical=args.skip_historical)


if __name__ == "__main__":
    main()
