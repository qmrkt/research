"""Reproduce final-policy A/B/C numerical and settlement comparisons.

python -m research.active_lp.fixed_point_validation --output <directory>

The request generator and holdout seeds match publication_validation. This is a
bounded empirical Python experiment, not compiled AVM verification or a uniform
error bound for the historical transcendental approximation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from decimal import Decimal as D, ROUND_CEILING
from pathlib import Path
from typing import Any

from research.active_lp import candidate_global_state as cand
from research.active_lp import layer_c_fixed_point as fp
from research.active_lp import publication_validation as pub
from research.active_lp import reference_parallel_lmsr as ref
from research.active_lp.events import (
    BootstrapMarket, CancelMarket, ClaimLpFees, ClaimLpResidual, ClaimRefund,
    ClaimWinnings, ResolveMarket, WithdrawLpFees,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import lmsr_cost_delta, lmsr_sell_return


MICRO = D("0.000001")
ZERO = D(0)
MODELS = {
    "A": (ref.ReferenceParallelLmsrEngine, ref.create_initial_state, ref.ReferenceInvariantChecker),
    "B": (cand.CandidateGlobalStateEngine, cand.create_candidate_initial_state, cand.CandidateInvariantChecker),
    "C": (fp.LayerCFixedPointEngine, fp.create_layer_c_initial_state, fp.LayerCInvariantChecker),
}
PLAN = {
    "schema": "fixed_point_validation_v1",
    "seed_start": 41000,
    "histories": 96,
    "request_generator": "publication_validation.generate_history; same fresh holdout IDs",
    "funding": list(pub.FUNDING),
    "bootstrap_quantization": "common to A/B/C: max(ceil(exact funding*1e6)/1e6, C initial funding requirement) + one micro-unit; C requirement includes quantized uniform prices and its one-micro entry margin; actual deposit recorded",
    "policy": "reserve_pool",
    "weight_scheme": "linear_lambda_normalized",
    "lambda": "0.15",
    "terminal_branches": "all N resolved outcomes plus cancellation for each accepted active history",
    "claim_order": "all LP residuals first, then all senior claims, then all LP fees; permutation coverage is in test_layer_c_final_policy.py",
    "stress": "all seven publication_validation.stress_histories, separately summarized",
    "state_evolution": "identical requested actions; quotes and LP price expectations use each model's own current state; execution disagreements retained",
    "fixed_point_quantization": "certified integer interval quotes: buy ceil upper, sell floor lower; each fee floor; removed partial basis floor; last partial claim gets remaining basis; once-only rational-weight residual snapshot, each entitlement floor; dust retained",
    "fixed_point_reserve_margin_micro": 0,
    "pricing_source": "certified_math for trade quotes; unchanged April12 helper for quantized prices and liquidity scaling; all source SHA retained",
    "pricing_domain": "2..64 outcomes, uint64 q/b/shares, normalized spread and trade size <=64; explicit rejection outside certified domain",
    "quote_validation": "every C trade quote compared with independent 80-digit Decimal LMSR at C's exact integer q,b; mathematical enclosure proof is separate from sampled cross-model error",
    "scope": "Certified conservative integer quote intervals plus empirical cross-model fidelity and guarded settlement accounting. No compiled AVM behavior, opcode budget, or production safety claim.",
}


def difference(left: Any, right: Any) -> D:
    return max((abs(D(a) - D(b)) for a, b in zip(left, right)), default=ZERO)


def assert_safe(checker: Any, state: Any, label: str) -> None:
    failed = [asdict(check) for check in checker.check_all(state) if not check.passed]
    if failed:
        raise AssertionError(f"{label}: invariant failures {failed}")


def initial_models(history: pub.History, funding: str) -> dict[str, tuple[Any, Any, Any]]:
    common_funding = pub.funded_amount(history.outcomes, history.initial_b, funding).quantize(MICRO, rounding=ROUND_CEILING) + MICRO
    c_floor = fp._fp_to_amount(fp._collateral_required_fp(fp._amount_to_fp(history.initial_b), fp._decimal_prices_to_fp(pub.uniform_price_vector(history.outcomes))))
    common_funding = max(common_funding, c_floor + MICRO)
    models = {}
    for name, (engine_type, state_factory, checker_type) in MODELS.items():
        engine = engine_type(
            lp_fee_bps=history.fee_bps, protocol_fee_bps=history.protocol_fee_bps,
            residual_policy=ref.RESERVE_POOL, residual_weight_scheme="linear_lambda_normalized",
            residual_linear_lambda=D(".15"),
        )
        state = state_factory(history.outcomes, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=D(".15"))
        state = engine.apply_event(state, BootstrapMarket(1, "creator", common_funding, history.initial_b))
        checker = checker_type(residual_policy=ref.RESERVE_POOL)
        assert_safe(checker, state, f"{name} bootstrap")
        models[name] = engine, state, checker
    return models


def settle(history: pub.History, model: str, engine: Any, active: Any, checker: Any, outcome: int | None) -> tuple[dict, dict[str, dict]]:
    terminal = CancelMarket(history.settlement_time, "validation branch") if outcome is None else ResolveMarket(history.settlement_time, outcome)
    state = engine.apply_event(active, terminal)
    assert_safe(checker, state, f"{model} terminal {outcome}")
    nav = engine.mark_to_market_nav(state)
    cohorts = {
        key: {
            "model": model, "cohort_id": key, "sponsor": sponsor.sponsor_id,
            "deposit": D(sponsor.collateral_posted), "nav": nav[key],
            "nav_per_deposit": nav[key] / D(sponsor.collateral_posted),
            "fees": D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus),
        }
        for key, sponsor in state.sponsors.items()
    }
    lp_paid = ZERO
    actors = sorted({s.sponsor_id for s in state.sponsors.values()}, reverse=True)
    for actor in actors:
        funds = D(state.treasury.contract_funds)
        state = engine.apply_event(state, ClaimLpResidual(history.settlement_time + 1, actor))
        lp_paid += funds - D(state.treasury.contract_funds)
        assert_safe(checker, state, f"{model} residual before senior")
    senior_paid = ZERO
    for actor, vector in list(state.traders.positions_by_trader.items()):
        for index, shares in enumerate(vector):
            if shares > 0 and (outcome is None or outcome == index):
                funds = D(state.treasury.contract_funds)
                event = ClaimRefund(history.settlement_time + 2, actor, index, shares) if outcome is None else ClaimWinnings(history.settlement_time + 2, actor, index, shares)
                state = engine.apply_event(state, event)
                senior_paid += funds - D(state.treasury.contract_funds)
                assert_safe(checker, state, f"{model} senior after residual")
    for actor in actors:
        state = engine.apply_event(state, ClaimLpFees(history.settlement_time + 3, actor))
    for actor in actors:
        amount = sum((D(s.withdrawable_fee_surplus) for s in state.sponsors.values() if s.sponsor_id == actor), ZERO)
        if amount > 0:
            state = engine.apply_event(state, WithdrawLpFees(history.settlement_time + 4, actor, amount))
            lp_paid += amount
            assert_safe(checker, state, f"{model} fee withdrawal")
    expected = sum(nav.values(), ZERO)
    if abs(lp_paid - expected) > D("1e-18"):
        raise AssertionError(f"{model}: settled NAV and actual paid cash disagree")
    nonfee_left = ref._total_non_fee_assets(state)
    dust = D(state.treasury.rounding_dust)
    if abs(nonfee_left - dust) > D("1e-18"):
        raise AssertionError(f"{model}: unexplained assets after all claims: {nonfee_left} dust={dust}")
    return {
        "model": model, "lp_paid": lp_paid, "senior_paid": senior_paid,
        "protocol_fees_retained": state.treasury.protocol_fee_balance,
        "rounding_dust": dust, "nonfee_assets_after_all_claims": nonfee_left,
        "cohorts": len(cohorts), "all_claims_paid": True,
    }, cohorts


def run_path(history: pub.History, funding: str) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    models = initial_models(history, funding)
    base = {"path_id": history.path_id, "pack": history.pack, "funding": funding, "outcomes": history.outcomes}
    requests, rejections, terminals, cohort_rows = [], [], [], []
    max_quote_ab = max_quote_ac = max_price_ab = max_price_ac = max_entry_jump = ZERO
    min_refund = min_outcome = D("Infinity")
    acceptance_disagreements = 0
    identical_prefix = True
    for index, step in enumerate(history.steps):
        row = {**base, "request_index": index, **step, "identical_execution_prefix": identical_prefix}
        accepted = {}
        quotes = {}
        for name, (engine, state, checker) in models.items():
            quote = None
            error = None
            try:
                if step["kind"] == "buy":
                    quote = engine.buy_cost(state.pricing, step["outcome"], step["amount"])
                elif step["kind"] == "sell":
                    quote = engine.sell_return(state.pricing, step["outcome"], step["amount"])
                before_prices = tuple(state.pricing.price_vector)
                next_state = engine.apply_event(state, pub.step_event(step, state))
            except ValueError as exc:
                error = {"category": "refund_reserve" if isinstance(exc, ref.RefundReserveViolation) else "other_rejection", "reason": str(exc), "shortfall": getattr(exc, "shortfall", None)}
                next_state = state
            accepted[name] = error is None
            row[f"{name}_accepted"] = accepted[name]
            row[f"{name}_quote"] = quote
            quotes[name] = quote
            if name == "C" and quote is not None:
                q = tuple(D(value) / fp.AVM_AMOUNT_SCALE for value in state.pricing.pricing_q)
                b = D(state.pricing.depth_b) / fp.AVM_AMOUNT_SCALE
                quantity = fp._fp_to_amount(fp._amount_to_fp(step["amount"]))
                oracle_function = lmsr_cost_delta if step["kind"] == "buy" else lmsr_sell_return
                oracle = oracle_function(q, b, step["outcome"], quantity)
                signed_error = quote - oracle
                valid = signed_error >= -D("1e-60") if step["kind"] == "buy" else signed_error <= D("1e-60")
                row["C_same_state_oracle_quote"] = oracle
                row["C_signed_error_against_same_state_oracle"] = signed_error
                row["C_conservative_direction"] = valid
                if not valid:
                    raise AssertionError(f"C quote lacks conservative direction: {history.path_id}/{funding}/{index}: {signed_error}")
            if error is not None:
                rejections.append({**base, "request_index": index, "model": name, **step, **error, "quoted_gross": quote})
            elif step["kind"] == "lp":
                jump = difference(before_prices, next_state.pricing.price_vector)
                row[f"{name}_entry_price_jump"] = jump
                if name == "C":
                    max_entry_jump = max(max_entry_jump, jump)
            assert_safe(checker, next_state, f"{history.path_id}/{funding}/{name}/{index}")
            models[name] = engine, next_state, checker
            if name == "C":
                assets = ref._total_non_fee_assets(next_state)
                min_refund = min(min_refund, assets - ref._refund_reserve_requirement(next_state))
                min_outcome = min(min_outcome, assets - max(next_state.traders.aggregate_outstanding_claims))
        mismatch = len(set(accepted.values())) > 1
        acceptance_disagreements += mismatch
        row["acceptance_disagreement"] = mismatch
        identical_prefix = identical_prefix and not mismatch
        if all(quote is not None for quote in quotes.values()):
            row["quote_abs_A_B"] = abs(quotes["A"] - quotes["B"])
            row["quote_abs_A_C"] = abs(quotes["A"] - quotes["C"])
            max_quote_ab = max(max_quote_ab, row["quote_abs_A_B"])
            max_quote_ac = max(max_quote_ac, row["quote_abs_A_C"])
        max_price_ab = max(max_price_ab, difference(models["A"][1].pricing.price_vector, models["B"][1].pricing.price_vector))
        max_price_ac = max(max_price_ac, difference(models["A"][1].pricing.price_vector, models["C"][1].pricing.price_vector))
        requests.append(row)
    max_nav_ab = max_nav_ac = max_ratio_ac = max_dust = ZERO
    for outcome in [*range(history.outcomes), None]:
        model_cohorts = {}
        branch_rows = {}
        for model, (engine, active, checker) in models.items():
            result, cohorts = settle(history, model, engine, active, checker, outcome)
            branch_rows[model] = {**base, "outcome": outcome, **result}
            model_cohorts[model] = cohorts
            cohort_rows.extend({**base, "outcome": outcome, **row} for row in cohorts.values())
        common = set(model_cohorts["A"]) & set(model_cohorts["B"]) & set(model_cohorts["C"])
        if any(set(rows) != common for rows in model_cohorts.values()):
            raise AssertionError("models accepted different cohort sets; cannot silently pair NAVs")
        branch_nav_ab = max((abs(model_cohorts["A"][key]["nav"] - model_cohorts["B"][key]["nav"]) for key in common), default=ZERO)
        branch_nav_ac = max((abs(model_cohorts["A"][key]["nav"] - model_cohorts["C"][key]["nav"]) for key in common), default=ZERO)
        ratio_ac = max((abs(model_cohorts["A"][key]["nav_per_deposit"] - model_cohorts["C"][key]["nav_per_deposit"]) for key in common), default=ZERO)
        for result in branch_rows.values():
            result.update(max_nav_abs_A_B=branch_nav_ab, max_nav_abs_A_C=branch_nav_ac, max_nav_per_deposit_abs_A_C=ratio_ac)
            terminals.append(result)
        max_nav_ab = max(max_nav_ab, branch_nav_ab)
        max_nav_ac = max(max_nav_ac, branch_nav_ac)
        max_ratio_ac = max(max_ratio_ac, ratio_ac)
        max_dust = max(max_dust, branch_rows["C"]["rounding_dust"])
    return {
        **base, "seed": history.seed, "requests": len(history.steps),
        "trade_requests": sum(step["kind"] != "lp" for step in history.steps),
        "lp_entries": sum(step["kind"] == "lp" for step in history.steps),
        "common_initial_collateral": next(iter(models["A"][1].sponsors.values())).collateral_posted,
        "request_hash": pub.digest(history.steps), "acceptance_disagreements": acceptance_disagreements,
        "max_trade_quote_abs_A_B": max_quote_ab, "max_trade_quote_abs_A_C": max_quote_ac,
        "max_price_abs_A_B": max_price_ab, "max_price_abs_A_C": max_price_ac,
        "max_C_entry_price_jump": max_entry_jump,
        "max_terminal_nav_abs_A_B": max_nav_ab, "max_terminal_nav_abs_A_C": max_nav_ac,
        "max_terminal_nav_per_deposit_abs_A_C": max_ratio_ac,
        "min_C_refund_margin": min_refund, "min_C_outcome_margin": min_outcome,
        "max_C_settlement_dust": max_dust, "terminal_branches_per_model": history.outcomes + 1,
        "C_rejected_requests": sum(row["model"] == "C" for row in rejections),
        "all_terminal_claims_paid": True,
    }, requests, rejections, terminals, cohort_rows


def summarize(rows: list[dict], requests: list[dict], rejections: list[dict], terminals: list[dict]) -> dict:
    result = {}
    for pack in sorted({row["pack"] for row in rows}):
        selected = [row for row in rows if row["pack"] == pack]
        rejected = [row for row in rejections if row["pack"] == pack]
        values = {
            "histories": len({row["path_id"] for row in selected}), "path_funding_runs": len(selected),
            "requested_actions": sum(row["requests"] for row in selected),
            "trade_requests": sum(row["trade_requests"] for row in selected),
            "lp_entries": sum(row["lp_entries"] for row in selected),
            "terminal_branches_per_model": sum(row["terminal_branches_per_model"] for row in selected),
            "terminal_model_runs": sum(row["pack"] == pack for row in terminals),
            "acceptance_disagreements": sum(row["acceptance_disagreements"] for row in selected),
            "rejections_by_model": {model: sum(row["model"] == model for row in rejected) for model in MODELS},
            "other_rejections": sum(row["category"] != "refund_reserve" for row in rejected),
            "C_one_sided_quote_checks": sum(row["pack"] == pack and "C_conservative_direction" in row for row in requests),
            "C_one_sided_quote_failures": sum(row["pack"] == pack and row.get("C_conservative_direction") is False for row in requests),
            "all_terminal_claims_paid": all(row["all_terminal_claims_paid"] for row in selected),
            "min_C_refund_margin": min(row["min_C_refund_margin"] for row in selected),
            "min_C_outcome_margin": min(row["min_C_outcome_margin"] for row in selected),
        }
        for metric in (key for key in selected[0] if key.startswith("max_")):
            worst = max(selected, key=lambda row: row[metric])
            values[metric] = worst[metric]
            values[metric + "_path"] = {"path_id": worst["path_id"], "funding": worst["funding"]}
        result[pack] = values
    return result


def run(output: Path, *, smoke: bool = False) -> dict:
    config = dict(PLAN)
    if smoke:
        config.update(seed_start=31000, histories=3, scope="development smoke only; no publication inference")
    output.mkdir(parents=True, exist_ok=True)
    pub.write_json(output / "config.json", config)
    source_dir = Path(__file__).resolve().parent
    source_names = ["fixed_point_validation.py", "certified_math.py", "publication_validation.py", "reference_parallel_lmsr.py", "candidate_global_state.py", "reference_math.py", "layer_c_fixed_point.py", "events.py", "state.py", "precision.py", "_vendor/lmsr_math.py", "_vendor/provenance.json"]
    hashes = {name: hashlib.sha256((source_dir / name).read_bytes()).hexdigest() for name in source_names}
    provenance = {"config_sha256": pub.digest(config), "python": sys.version, "platform": platform.platform(), "sources": hashes, "generator_plan_sha256": pub.digest(pub.PLAN)}
    try:
        provenance["git_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_dir, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        provenance["git_head"] = None
    pub.write_json(output / "provenance.json", provenance)
    rows, requests, rejections, terminals, cohorts = [], [], [], [], []
    with high_precision():
        histories = [pub.generate_history(config["seed_start"] + index) for index in range(config["histories"])] + pub.stress_histories()
        pub.write_jsonl(output / "paths.jsonl", (asdict(history) for history in histories))
        for index, history in enumerate(histories):
            for funding in pub.FUNDING:
                row, requested, rejected, terminal, cohort = run_path(history, funding)
                rows.append(row)
                requests.extend(requested)
                rejections.extend(rejected)
                terminals.extend(terminal)
                cohorts.extend(cohort)
            if (index + 1) % 12 == 0 or index + 1 == len(histories):
                print(f"validated {index + 1}/{len(histories)} histories", flush=True)
    summary = summarize(rows, requests, rejections, terminals)
    pub.write_csv(output / "rows.csv", rows)
    pub.write_jsonl(output / "requests.jsonl", requests)
    pub.write_jsonl(output / "rejections.jsonl", rejections)
    pub.write_csv(output / "terminal_rows.csv", terminals)
    pub.write_jsonl(output / "cohort_rows.jsonl", cohorts)
    pub.write_json(output / "summary.json", summary)
    (output / "report.md").write_text("# Final-policy fixed-point validation\n\n" + config["scope"] + "\n\n```json\n" + json.dumps(summary, default=pub.json_default, indent=2) + "\n```\n")
    for name, expected_hash in hashes.items():
        if hashlib.sha256((source_dir / name).read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError(f"source changed during run: {name}")
    pub.write_json(output / "manifest.json", {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size} for path in sorted(output.iterdir()) if path.is_file() and path.name != "manifest.json"})
    print(f"wrote {len(rows)} path/funding rows and {len(terminals)} terminal model runs to {output}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("01-active-lp/output/fixed_point_validation"))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.output, smoke=args.smoke)


if __name__ == "__main__":
    main()
