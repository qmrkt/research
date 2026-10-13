"""Replay the original low-tail diagnostic and cancellation reserve failure.

Run ``python -m research.active_lp.safety_validation`` to regenerate the complete
bundle. These are designed regression traces, not an estimate of attack frequency.
The exact and compressed Decimal engines are exercised without changing them.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import hashlib
from itertools import permutations
from pathlib import Path
import platform
import sys

from research.active_lp import publication_validation as pv
from research.active_lp import reference_parallel_lmsr as ref
from research.active_lp.candidate_global_state import CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state
from research.active_lp.events import BootstrapMarket, BuyOutcome, SellOutcome, LpEnterActive, ResolveMarket, CancelMarket, ClaimWinnings, ClaimRefund, ClaimLpResidual
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector

D, ZERO = Decimal, Decimal(0)
TOL = D("1e-16")
DEFAULT_OUTPUT = pv.REPO / "01-active-lp" / "output" / "safety_validation"
MODELS = {
    "reference": (ref.ReferenceParallelLmsrEngine, ref.ReferenceInvariantChecker, ref.create_initial_state),
    "compressed": (CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state),
}
PLAN = {
    "schema": "safety_validation_v1",
    "purpose": "designed regression traces and payout-order conservation; not randomized inference",
    "models": list(MODELS), "decimal_digits": 80, "tolerance": str(TOL),
    "funding": "100*ln(N)+20", "lp_fee_bps": 0, "protocol_fee_bps": 0,
    "settlement_policy": "reserve_pool; strict_all_claimed replay also preserves original low-tail diagnostic",
    "residual_weight": "linear_lambda_normalized", "lambda": ".15",
    "low_tail": "N64,b100; buy250outcome0; buy500outcome1; LPdepth20; resolve1; winner500claim. Also all6 orders of winner/creator/late payout under pooled policy.",
    "refund_failure": "N3,b100; a buys100outcome0,b buys500outcome0,a sells100outcome0,a buys100outcome1,c buys1000outcome1,a requests sell100outcome1; retain rejected request, cancel, all24 orders of3refunds+creator residual.",
    "cash_check": "independently quote each event before applying it; compare expected external cash with treasury change and cumulative ledger; assert failed request leaves state exactly unchanged",
}

AUDIT = """# Certified integer quote audit

The finite interval proof is valid on the module's declared domain. No empirically fitted safety margin enters a quote.

1. For exp(z), 0<=z<=1/2, each retained positive Taylor term is enclosed by directed integer division. The first omitted term has all subsequent term ratios at most 1/2, so twice its upper bound covers the tail. Reciprocal endpoints reverse order; positive squaring preserves order. At x=0 the helper returns exactly1.
2. For log(m), 1<=m<=2, z=(m−1)/(m+1)<=1/3. After 64 odd terms the tail is <=2*z^129/(129*(1−z²))<=9*z^129/(4*129). The implementation has advanced the stored power to z^129 at that point. Exact power-of-two reduction and the separately enclosed log2 preserve the bounds. The max inventory contributes an exact exp(0)=1, so each sum passed to log is at least 1.
3. For cost differences, subtracting the former upper endpoint from the latter lower endpoint gives a lower bound; the opposite subtraction gives an upper bound. A change in which inventory is the maximum is harmless because the max shifts are exact integers. Intersecting with[0,shares] is valid because every exact LMSR marginal price lies in[0,1].
4. Buy ceil(upper) never undercharges the exact increment; sell floor(lower) never overpays the decrement. Quote error is less than 1+certificate_width raw units, not necessarily strictly less than 1: an interval around an exactly integral value can produce an extra unit of conservative rounding.
5. The closed-cycle argument requires fixed b, no depth-changing LP operation, and a return to the same inventory vector. Under those conditions exact cost changes telescope to zero, so conservative rounding cannot produce trader profit. It is not a theorem about changing-depth cycles, favorable external flow, private information, or strategic LP transfers.
6. Public entry points check 2..64 outcomes, positive uint64 depth, uint64 inventories and requested shares, uint64 post-trade inventory, and before/after inventory spread and trade-size ratios no greater than 64. Unsupported inputs fail explicitly. A quote is returned only if its certificate width is below one raw unit. This is an accepted-quote guarantee; AVM compilation, intermediate-word limits and opcode cost are separate work.

Coverage includes independent Decimal80 cost oracles across N2/3/8/64, near-uint64 scales, spread64, one-micro trades, zero routing, gauge shifts and exact integer rescaling; closed fixed-depth inventory cycles; the original high-skew100micro-for1micro sell bug; exact-rational exponential enclosures; log reduction boundaries; and exact integer-cost ties. Source hashes identify the audited helper and tests. Tests are regression evidence supporting the mathematical argument, not a replacement for it.
"""


def snapshot(state, checker):
    checks = [asdict(check) for check in checker.check_all(state)]
    failures = [check for check in checks if not check["passed"]]
    if failures:
        raise AssertionError(failures)
    assets = ref._total_non_fee_assets(state)
    reserve = ref._winner_reserve_requirement(state)
    if assets - reserve < -TOL:
        raise AssertionError("senior reserve underfunded")
    return {
        "status": state.pricing.status.value, "treasury": state.treasury.contract_funds,
        "lp_fees": state.treasury.lp_fee_balance, "protocol_fees": state.treasury.protocol_fee_balance,
        "assets": assets, "reserve": reserve, "margin": assets - reserve,
        "refund_basis": ref._refund_reserve_requirement(state),
        "outstanding_claims": state.traders.aggregate_outstanding_claims,
        "cohorts": {key: list(sponsor.residual_basis_by_outcome[:2]) for key, sponsor in state.sponsors.items()},
        "checks": checks,
    }


def expected_cash(engine, state, event):
    quote = {}
    if isinstance(event, BootstrapMarket):
        return D(event.initial_collateral), quote
    if isinstance(event, BuyOutcome):
        cost = engine.buy_cost(state.pricing, event.outcome_index, event.shares)
        quote = {"gross_cost": cost}
        return cost * (1 + (engine.lp_fee_bps + engine.protocol_fee_bps) / 10000), quote
    if isinstance(event, SellOutcome):
        quote = engine.sell_execution_quote(state, event.trader_id, event.outcome_index, event.shares)
        return -D(quote["gross_return"]) * (1 - (engine.lp_fee_bps + engine.protocol_fee_bps) / 10000), quote
    if isinstance(event, LpEnterActive):
        cost = collateral_required(D(event.target_delta_b), tuple(map(D, state.pricing.price_vector)))
        return cost, {"required_deposit": cost}
    if isinstance(event, ClaimWinnings):
        return -D(event.shares), quote
    if isinstance(event, ClaimRefund):
        held = D(state.traders.positions_by_trader[event.trader_id][event.outcome_index])
        basis = D(state.traders.cost_basis_by_trader[event.trader_id][event.outcome_index])
        return -basis * D(event.shares) / held, {"remaining_basis": basis, "remaining_shares": held}
    if isinstance(event, ClaimLpResidual):
        amount = sum((ref._claimable_residual_for_cohort(state, sponsor) for sponsor in state.sponsors.values() if sponsor.sponsor_id == event.sponsor_id), ZERO)
        return -amount, {"residual_entitlement": amount}
    return ZERO, quote


def apply_checked(engine, checker, state, event, *, label, ledger, metadata):
    expected, quote = expected_cash(engine, state, event)
    before = deepcopy(state)
    rejected = None
    try:
        after = engine.apply_event(state, event)
    except ref.RefundReserveViolation as exc:
        if state != before:
            raise AssertionError("guard rejection mutated state")
        after = state
        rejected = {"reason": str(exc), "available_assets": exc.available_assets, "required_refunds": exc.required_refunds, "shortfall": exc.shortfall}
        expected = ZERO
    actual = D(after.treasury.contract_funds) - D(before.treasury.contract_funds)
    ledger += expected
    if abs(actual - expected) > TOL or abs(D(after.treasury.contract_funds) - ledger) > TOL:
        raise AssertionError("quote/cash conservation mismatch")
    row = {**metadata, "label": label, "event": asdict(event), "quote": quote, "rejection": rejected,
           "expected_cash_change": expected, "actual_cash_change": actual,
           "quote_cash_error": actual - expected, "external_cash_ledger": ledger,
           "cash_ledger_error": D(after.treasury.contract_funds) - ledger, **snapshot(after, checker)}
    return after, ledger, row


def replay_prefix(model, path, *, policy=ref.RESERVE_POOL):
    engine_type, checker_type, initial = MODELS[model]
    engine = engine_type(residual_policy=policy, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=D(".15"))
    checker = checker_type(residual_policy=policy)
    n = 64 if path == "low_tail" else 3
    state = initial(n, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=D(".15"))
    metadata = {"model": model, "path": path, "policy": policy, "phase": "prefix", "order_id": None}
    rows, ledger = [], ZERO
    def execute(event, label):
        nonlocal state, ledger
        state, ledger, row = apply_checked(engine, checker, state, event, label=label, ledger=ledger, metadata=metadata)
        rows.append(row)
    execute(BootstrapMarket(1, "creator", collateral_required(D(100), uniform_price_vector(n)) + D(20), D(100)), "Bootstrap")
    if path == "low_tail":
        execute(BuyOutcome(2, "loser", 0, D(250), D("1e50")), "Buy0")
        execute(BuyOutcome(3, "winner", 1, D(500), D("1e50")), "Buy1")
        execute(LpEnterActive(4, "late", D(20), D("1e50"), state.pricing.price_vector, TOL), "LP entry")
        execute(ResolveMarket(5, 1), "Resolve")
        if policy == ref.STRICT_ALL_CLAIMED:
            execute(ClaimWinnings(6, "winner", 1, D(500)), "Winner claim")
    else:
        events = (BuyOutcome(2, "a", 0, D(100), D("1e50")), BuyOutcome(3, "b", 0, D(500), D("1e50")), SellOutcome(4, "a", 0, D(100), ZERO), BuyOutcome(5, "a", 1, D(100), D("1e50")), BuyOutcome(6, "c", 1, D(1000), D("1e50")), SellOutcome(7, "a", 1, D(100), ZERO))
        for index, event in enumerate(events):
            execute(event, f"request_{index + 1}")
        if sum(row["rejection"] is not None for row in rows) != 1 or rows[-1]["rejection"] is None:
            raise AssertionError("original refund-underfunding sell was not the unique rejected request")
        execute(CancelMarket(8, "original refund failure regression"), "Cancel")
    return engine, checker, state, ledger, rows


def payout_orders(model, path, engine, checker, settled):
    if path == "low_tail":
        actions = (ClaimWinnings(9, "winner", 1, D(500)), ClaimLpResidual(9, "creator"), ClaimLpResidual(9, "late"))
    else:
        actions = tuple(ClaimRefund(9, actor, outcome, shares) for actor, vector in sorted(settled.traders.positions_by_trader.items()) for outcome, shares in enumerate(vector) if shares > 0) + (ClaimLpResidual(9, "creator"),)
    all_rows, summaries, reference_payments = [], [], None
    for order_id, order in enumerate(permutations(actions)):
        state = deepcopy(settled)
        ledger = D(state.treasury.contract_funds)
        payments = {}
        metadata = {"model": model, "path": path, "policy": ref.RESERVE_POOL, "phase": "payout_order", "order_id": order_id}
        for event in order:
            label = type(event).__name__ + ":" + getattr(event, "trader_id", getattr(event, "sponsor_id", ""))
            state, ledger, row = apply_checked(engine, checker, state, event, label=label, ledger=ledger, metadata=metadata)
            payments[label] = -row["actual_cash_change"]
            all_rows.append(row)
        if reference_payments is None:
            reference_payments = payments
        if any(abs(payments[key] - reference_payments[key]) > TOL for key in payments):
            raise AssertionError("claim order changed a recipient's payout")
        if abs(ref._total_non_fee_assets(state)) > TOL or ref._winner_reserve_requirement(state) != 0:
            raise AssertionError("payout sequence left unexplained assets or senior obligations")
        summaries.append({**metadata, "payments": payments, "final_treasury": state.treasury.contract_funds, "final_reserve": ref._winner_reserve_requirement(state), "all_checks_passed": True})
    return all_rows, summaries


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    pv.write_json(output / "config.json", PLAN)
    names = ("safety_validation.py", "reference_parallel_lmsr.py", "candidate_global_state.py", "reference_math.py", "precision.py", "events.py", "state.py", "certified_math.py")
    paths = [Path(__file__).with_name(name) for name in names]
    test_paths = [pv.REPO / "tests" / name for name in ("test_certified_math.py", "test_certified_math_audit.py", "test_safety_validation.py")]
    paths.extend(path for path in test_paths if path.is_file())
    hashes = {str(path.relative_to(pv.REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    pv.write_json(output / "provenance.json", {"config_sha256": pv.digest(PLAN), "python": sys.version, "platform": platform.platform(), "sources": hashes, "test_source_files_present": [str(path.relative_to(pv.REPO)) for path in test_paths if path.is_file()]})
    records, orders, comparisons = [], [], {}
    with high_precision():
        for model in MODELS:
            _, _, _, _, original = replay_prefix(model, "low_tail", policy=ref.STRICT_ALL_CLAIMED)
            records.extend(original)
            if model == "reference":
                pv.write_json(output / "low_tail.json", [{"event": row["label"], **{key: row[key] for key in ("assets", "reserve", "margin", "cohorts", "checks")}} for row in original])
            for path in ("low_tail", "refund_failure"):
                engine, checker, settled, _, prefix = replay_prefix(model, path)
                records.extend(prefix)
                claim_rows, claim_summary = payout_orders(model, path, engine, checker, settled)
                records.extend(claim_rows)
                orders.extend(claim_summary)
                comparisons[f"{model}/{path}"] = {"prefix_events": len(prefix), "rejected_requests": sum(row["rejection"] is not None for row in prefix), "terminal_assets": ref._total_non_fee_assets(settled), "terminal_senior_reserve": ref._winner_reserve_requirement(settled), "terminal_residual": ref._total_non_fee_assets(settled) - ref._winner_reserve_requirement(settled), "claim_orders": len(claim_summary)}
        for path in ("low_tail", "refund_failure"):
            for key in ("terminal_assets", "terminal_senior_reserve", "terminal_residual"):
                if abs(comparisons[f"reference/{path}"][key] - comparisons[f"compressed/{path}"][key]) > TOL:
                    raise AssertionError("exact and compressed cash ledgers disagree")
    pv.write_jsonl(output / "events.jsonl", records)
    pv.write_jsonl(output / "claim_orders.jsonl", orders)
    summary = {"runs": comparisons, "event_rows": len(records), "claim_orders": len(orders), "all_checks_passed": True, "maximum_quote_cash_error": str(max(abs(row["quote_cash_error"]) for row in records)), "maximum_cash_ledger_error": str(max(abs(row["cash_ledger_error"]) for row in records))}
    pv.write_json(output / "summary.json", summary)
    (output / "certified_math_audit.md").write_text(AUDIT)
    lines = ["# Historical safety regressions", "", "These exact event sequences reproduce the old 64-outcome low-tail diagnostic and the cancellation-refund failure. Both reference and compressed Decimal models now pass their state-aware checks. This is a designed regression bundle, not a population safety estimate.", "", "| Model / path | Terminal assets | Senior reserve | Free residual | Rejected requests | Claim orders |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for key, values in comparisons.items():
        lines.append(f"| {key} | {float(values['terminal_assets']):.9f} | {float(values['terminal_senior_reserve']):.9f} | {float(values['terminal_residual']):.9f} | {values['rejected_requests']} | {values['claim_orders']} |")
    lines += ["", "After the low-tail winner claim, the creator's obsolete losing-outcome component entry is approximately −189.464309 while its realized winning-outcome residual is +60.535691. No losing outcome can become payable after resolution; the actual aggregate reserve and cash ledger remain funded.", "", "In the cancellation trace, the final sell would leave refundable cost basis underfunded by 22.448755. It is rejected atomically; the prior profitable sell remains executed. Every still-open position receives its full remaining cost basis after cancellation. The rejected immediate sell quote is retained in events.jsonl.", "", f"All {len(orders)} payout orders conserve recipient entitlements and finish with no senior liabilities or unexplained non-fee assets. Each event's cash flow is independently quoted before application; maximum quote-versus-cash error is {summary['maximum_quote_cash_error']} and cumulative-ledger error is {summary['maximum_cash_ledger_error']}.", "", "Run `python -m research.active_lp.safety_validation` to reproduce. config.json freezes the sequences; provenance.json and manifest.json identify sources and output hashes; events.jsonl includes all requests, rejected quotes, reserves and checks; claim_orders.jsonl records each complete payout order. low_tail.json reproduces the original compact trace. certified_math_audit.md records the separate numerical proof audit and its scope.", ""]
    (output / "report.md").write_text("\n".join(lines))
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path.relative_to(pv.REPO))]:
            raise RuntimeError(f"source changed during safety run: {path}")
    pv.write_json(output / "manifest.json", {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size} for path in sorted(output.iterdir()) if path.is_file() and path.name != "manifest.json"})
    print(f"Wrote {len(records)} event rows and {len(orders)} payout orders to {output}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
