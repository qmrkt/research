"""Exact finite-state source-composition experiments and trace attack vectors.

Run: python -m research.resolution_trust.blueprint_experiments --output-dir PATH
No behavioral detection probabilities, fitted parameters, or independent-sample
interpretation of reused counterfactual traces are involved.
"""
from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path

from .blueprint_protocol import (
    PROFILE, TRACE_VERSION, EVIDENCE_VERSION, REPORT_TYPES, PublicationLog, ResolutionSession,
    canonical_bytes, check_consistency, digest, evidence_root, execute, fixture_run,
    hard_timeout, make_blueprint, test_keys, trace_root, validate_blueprint, verify,
)


def fraction_text(x: Fraction) -> str:
    return f"{x.numerator}/{x.denominator}"


def serializable(obj):
    if isinstance(obj, Fraction):
        return {"fraction": fraction_text(obj), "decimal": float(obj)}
    if isinstance(obj, dict):
        return {k: serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serializable(x) for x in obj]
    return obj


def write_json(path, value):
    path.write_text(json.dumps(serializable(value), indent=2, sort_keys=True) + "\n")


def evidence_from(log):
    return {root: json.loads(raw) for root, (_, raw) in log.blobs.items()
            if json.loads(raw).get("body", {}).get("schema") == EVIDENCE_VERSION}


def export_log(log):
    return {"authority_keys": log.authority_keys,
            "publications": [{"root": root, "published_at": at, "object": json.loads(raw)}
                             for root, (at, raw) in sorted(log.blobs.items())],
            "source_slots": [{"market_id": m, "run_id": r, "node_id": n, "root": root}
                             for (m, r, n), root in sorted(log.slots.items())]}


def protocol_catalog():
    """Execute and independently verify every 1- and 3-report ternary state."""
    cache, table, vectors = {}, {}, []
    for n in (1, 3):
        bp = make_blueprint(n)
        for values in itertools.product((None, False, True), repeat=n):
            trace, log = fixture_run(bp, list(values), signed_cache=cache)
            verdict = verify(bp, trace_root(trace), "market-001", log, 115, 100)
            assert verdict["status"] in {"resolve", "cancel"}, verdict
            terminal = trace["terminal"]
            status = "cancel" if terminal["action"] == "cancel" else ("wrong" if terminal["outcome"] else "correct")
            result = {"classification": status, "decision": verdict["status"] == "resolve", "trace_root": trace_root(trace)}
            table[(n, values)] = result
            vectors.append({"source_count": n, "reports": values, "truth": False, "result": result,
                            "blueprint": bp, "trace": trace, "publication_log": export_log(log)})
    return table, vectors


def latent_states(n, error=Fraction(0), common_error=Fraction(0),
                  unavailable=Fraction(0), common_unavailable=Fraction(0)):
    """Exact mixture; common shocks and independent residual bits are explicit."""
    for common_wrong, common_down in itertools.product((False, True), repeat=2):
        shock_prob = (common_error if common_wrong else 1-common_error) * (
            common_unavailable if common_down else 1-common_unavailable)
        if not shock_prob:
            continue
        for error_bits in itertools.product((False, True), repeat=n):
            pe = Fraction(1)
            for bit in error_bits:
                pe *= error if bit else 1-error
            if not pe:
                continue
            for down_bits in itertools.product((False, True), repeat=n):
                pa = Fraction(1)
                for bit in down_bits:
                    pa *= unavailable if bit else 1-unavailable
                weight = shock_prob * pe * pa
                if not weight:
                    continue
                reports = tuple(None if common_down or down_bits[i] else bool(common_wrong or error_bits[i]) for i in range(n))
                yield {"common_wrong": common_wrong, "common_down": common_down,
                       "error_bits": error_bits, "down_bits": down_bits,
                       "reports": reports, "probability": weight}


def authority_actions(n, shared=False):
    actions = [{"id": f"source_{i}", "cost": 2*(i+1), "controls": [i]} for i in range(n)]
    if shared:
        actions.append({"id": "common_upstream", "cost": 3, "controls": list(range(n))})
    return actions


def action_sets(actions, budget):
    for selected in itertools.product((False, True), repeat=len(actions)):
        subset = [a for a, use in zip(actions, selected) if use]
        cost = sum(a["cost"] for a in subset)
        if cost <= budget:
            yield subset, cost


def alter(reports, actions, mode="corrupt"):
    result = list(reports)
    targets = {i for action in actions for i in action["controls"]}
    for i in targets:
        # Corruption changes report truth, not exogenous delivery availability.
        if mode == "withhold":
            result[i] = None
        elif result[i] is not None:
            result[i] = True
    return tuple(result)


def exact_experiment(name, n, table, params=None, actions=None, budget=0,
                     adaptive=False, mode="corrupt", forced_ids=None):
    params, actions = params or {}, actions or []
    states = list(latent_states(n, **params))
    assert sum(s["probability"] for s in states) == 1
    options = list(action_sets(actions, budget))
    if forced_ids is not None:
        options = [(a, c) for a, c in options if {x["id"] for x in a} == set(forced_ids)]
        assert len(options) == 1
    target = "cancel" if mode == "withhold" else "wrong"

    def expectation(option):
        selected, _ = option
        return sum(s["probability"] for s in states
                   if table[n, alter(s["reports"], selected, mode)]["classification"] == target)

    def option_key(option, reports=None):
        selected, cost = option
        score = expectation(option) if reports is None else int(
            table[n, alter(reports, selected, mode)]["classification"] == target)
        return (-score, cost, tuple(a["id"] for a in selected))

    static = min(options, key=option_key)
    totals = {key: Fraction(0) for key in ("wrong", "correct", "cancel", "blocked", "defer")}
    rows, attempt_rate, expected_cost = [], Fraction(0), Fraction(0)
    for index, state in enumerate(states):
        chosen, cost = min(options, key=lambda o: option_key(o, state["reports"])) if adaptive else static
        reports = alter(state["reports"], chosen, mode)
        outcome = table[n, reports]
        totals[outcome["classification"]] += state["probability"]
        attempt_rate += state["probability"] * bool(chosen)
        expected_cost += state["probability"] * cost
        rows.append({"experiment": name, "state_id": index, **state, "selected_actions": [a["id"] for a in chosen],
                     "cost": cost, "reports_after_attack": reports, **outcome})
    decision = totals["wrong"] + totals["correct"]
    summary = {"experiment": name, "source_count": n, "latent_parameters": params, "actions": actions,
               "budget": budget, "adaptive_observation": "all realized error and availability states" if adaptive else "none; ex ante choice",
               "objective": f"maximize {target} probability subject to budget; break ties by lower cost then action IDs",
               "attack_mode": mode, "latent_state_count": len(states), "rates_per_offer": totals,
               "decision_rate": decision, "wrong_given_decision": totals["wrong"]/decision if decision else None,
               "attempt_rate": attempt_rate, "expected_attack_cost": expected_cost,
               "static_choice": None if adaptive else [a["id"] for a in static[0]],
               "static_cost": None if adaptive else static[1]}
    return summary, rows


def minimum_authority_cover(actions, required):
    feasible = [(cost, [a["id"] for a in selected]) for selected, cost in action_sets(actions, sum(a["cost"] for a in actions))
                if len({i for a in selected for i in a["controls"]}) >= required]
    return min(feasible)


def attack_vectors():
    """Mutations include rehashed fraud, not merely stale-hash mismatch tests."""
    bp = make_blueprint()
    original, original_log = fixture_run(bp, [False, False, True])
    results = []

    def record(name, trace, log, market="market-001", previous=None):
        root = log.publish(TRACE_VERSION, trace, 111)
        consistency = check_consistency(bp, trace, evidence_from(log), market, previous)
        verdict = verify(bp, root, market, log, 115, 100)
        results.append({"name": name, "consistency_pass": not consistency, "consistency_errors": consistency,
                        "gate": verdict, "trace": trace, "publication_log": export_log(log)})

    record("honest_trace", copy.deepcopy(original), copy.deepcopy(original_log))
    for name, mutation in [
        ("wrong_terminal_rehashed", lambda t: t["terminal"].update(outcome=True)),
        ("missing_step_rehashed", lambda t: t["steps"].pop(0)),
        ("reordered_steps_rehashed", lambda t: t["steps"].reverse()),
        ("changed_source_output_rehashed", lambda t: t["steps"][0]["output"].update(value=True)),
        ("wrong_run_rehashed", lambda t: t.update(run_id=2)),
        ("wrong_blueprint_rehashed", lambda t: t.update(blueprint_root="0"*64)),
        ("wrong_node_type_rehashed", lambda t: t["steps"][0].update(node_type="human_judge")),
    ]:
        trace = copy.deepcopy(original)
        mutation(trace)
        record(name, trace, copy.deepcopy(original_log))
    record("market_replay", copy.deepcopy(original), copy.deepcopy(original_log), market="other-market")

    # Fabricator chooses coherent wrong values and a fresh canonical root, with
    # invented signatures. No hash collision is needed to pass consistency.
    fake_log = PublicationLog()
    executor_view = PublicationLog()
    for obj in evidence_from(original_log).values():
        forged = copy.deepcopy(obj)
        forged["body"]["value"] = True
        forged["signature"] = "00"*256
        root = fake_log.publish(EVIDENCE_VERSION, forged, 102)
        executor_view.publish(EVIDENCE_VERSION, forged, 102)
        # This is the malicious executor's invented source view, not the
        # authenticated publication admission interface used by the verifier.
        executor_view.slots[("market-001", 1, forged["body"]["node_id"])] = root
    fabricated = execute(bp, "market-001", 1, 100, executor_view)
    record("canonical_fabrication", fabricated, fake_log)

    withheld = copy.deepcopy(original_log)
    root = trace_root(original)
    del withheld.blobs[root]
    verdict = verify(bp, root, "market-001", withheld, 115, 100)
    results.append({"name": "trace_withheld", "gate": verdict,
                    "after_market_deadline": hard_timeout(verdict["status"], 200, 200)})
    late = copy.deepcopy(original_log)
    _, raw = late.blobs[root]
    late.blobs[root] = (116, raw)
    results.append({"name": "trace_published_after_deadline", "gate": verify(bp, root, "market-001", late, 116, 100)})
    missing_evidence = copy.deepcopy(original_log)
    ref = original["steps"][0]["evidence_refs"][0]
    del missing_evidence.blobs[ref]
    results.append({"name": "referenced_evidence_withheld", "gate": verify(bp, root, "market-001", missing_evidence, 115, 100)})
    signed_wrong, signed_log = fixture_run(bp, [True, True, True])
    record("authentic_common_error", signed_wrong, signed_log)
    return results


def worked_examples():
    bp = make_blueprint(max_runs=2)
    session = ResolutionSession(bp, "market-001", 100)
    first, log = fixture_run(bp, [False, True, None])
    first_gate = session.advance(trace_root(first), 115, log)
    second, log = fixture_run(bp, [False, False, True], run_id=2, start=120, log=log, previous_trace=first)
    second_gate = session.advance(trace_root(second), 135, log)
    external = []
    for kind in ("market_evidence", "llm_judge", "human_judge"):
        typed_bp = make_blueprint(1, report_type=kind)
        trace, typed_log = fixture_run(typed_bp, [True])
        external.append({"declared_type": kind, "truth": False, "blueprint": typed_bp,
                         "trace": trace, "publication_log": export_log(typed_log),
                         "gate": verify(typed_bp, trace_root(trace), "market-001", typed_log, 115, 100),
                         "interpretation": "Authenticated reported output; correctness of external judgment not established."})
    return {"market": {"market_id": "market-001", "initial_start": 100, "hard_deadline": session.market_deadline,
                       "final_state": session.terminal},
            "blueprint": bp, "blueprint_root": digest(PROFILE, bp),
            "runs": [first, second], "gates": [first_gate, second_gate], "publication_log": export_log(log),
            "external_judgment_fixtures": external}


def run(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    config = {"version": 1, "truth": False, "method": "exact finite-state enumeration using rational probabilities",
              "random_seed": None, "parameter_tuning": "none", "sampling_intervals": "not applicable: exact specified model expectations",
              "security_assumptions": ["signature unforgeability and pinned authority keys (public test keys only in fixture runs)",
                                       "binding SHA-256 domain-separated canonical roots", "honest append-only publication layer and clock"],
              "protocol_states": "all 3^1+3^3 = 30 possible Boolean/absent source vectors",
              "dependency_models": ["distinct sources", "common error shock", "shared corruptible upstream", "independent and common availability"],
              "attack_cost_units": "illustrative units, independent keys cost 2/4/6; common upstream costs 3",
              "adversary": "cost-constrained maximizer; not an equilibrium proposer/challenger model"}
    write_json(output_dir / "config.json", config)  # freeze before evaluation
    table, catalog = protocol_catalog()
    summaries, rows = [], []

    def add(*args, **kwargs):
        summary, raw = exact_experiment(*args, table=table, **kwargs)
        summaries.append(summary)
        rows.extend(raw)

    for n in (1, 3):
        add(f"perfect_{n}", n)
        add(f"independent_error_005_{n}", n, params={"error": Fraction(1, 20)})
        add(f"independent_error_0145_{n}", n, params={"error": Fraction(29, 200)})
        add(f"common_error_matched_0145_{n}", n, params={"error": Fraction(1, 20), "common_error": Fraction(1, 10)})
        add(f"independent_error_and_outage_{n}", n, params={"error": Fraction(1, 20), "unavailable": Fraction(1, 5)})
        add(f"common_outage_{n}", n, params={"error": Fraction(1, 20), "common_unavailable": Fraction(1, 5)})
    actions = authority_actions(3)
    for ids, budget in [(["source_0"], 2), (["source_0", "source_1"], 6)]:
        add(f"forced_{len(ids)}_corrupt", 3, actions=actions, budget=budget, forced_ids=ids)
        add(f"forced_{len(ids)}_withheld", 3, actions=actions, budget=budget, forced_ids=ids, mode="withhold")
    for shared, budget, adaptive in itertools.product((False, True), (0, 2, 3, 4, 6, 12), (False, True)):
        add(f"choice_shared{int(shared)}_budget{budget}_{'adaptive' if adaptive else 'static'}", 3,
            params={"error": Fraction(1, 20), "unavailable": Fraction(1, 10)},
            actions=authority_actions(3, shared), budget=budget, adaptive=adaptive)
    cuts = {"independent": {"integrity": minimum_authority_cover(actions, 2),
                             "availability": minimum_authority_cover(actions, 2)},
            "shared": {"integrity": minimum_authority_cover(authority_actions(3, True), 2),
                       "availability": minimum_authority_cover(authority_actions(3, True), 2)}}
    attacks = attack_vectors()
    assert next(a for a in attacks if a["name"] == "canonical_fabrication")["consistency_pass"]
    assert next(a for a in attacks if a["name"] == "canonical_fabrication")["gate"]["status"] == "blocked"
    assert next(a for a in attacks if a["name"] == "authentic_common_error")["gate"]["terminal"]["outcome"] is True
    write_json(output_dir / "protocol_test_vectors.json", catalog)
    write_json(output_dir / "worked_example.json", worked_examples())
    write_json(output_dir / "tampering_vectors.json", attacks)
    write_json(output_dir / "summary.json", {"experiments": summaries, "minimum_authority_covers": cuts,
                                              "counterfactual_protocol_vectors": len(catalog), "exact_weighted_rows": len(rows)})
    with (output_dir / "weighted_states.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(serializable(row), sort_keys=True) + "\n")
    source_files = [Path(__file__), Path(__file__).with_name("blueprint_protocol.py"),
                    Path(__file__).parent / "fixtures" / "TEST_ONLY_RSA_KEYS.json"]
    provenance = {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    write_json(output_dir / "source_hashes.json", provenance)
    lookup = {s["experiment"]: s for s in summaries}
    lines = ["# Executed blueprint and source-composition validation", "",
             "All rates below are exact expectations under stated synthetic probabilities. They are not field estimates or Monte Carlo confidence intervals.", "",
             "The suite executes and independently verifies every one-source and three-source Boolean/absent state (30 canonical protocol vectors). Exact weighted states reference those full traces.", "",
             "| Experiment | Wrong per offer | Correct per offer | Cancel | Wrong given decision |", "|---|---:|---:|---:|---:|"]
    for name in ["independent_error_005_1", "independent_error_005_3", "independent_error_0145_3",
                 "common_error_matched_0145_3", "independent_error_and_outage_3", "common_outage_3",
                 "forced_1_corrupt", "forced_2_corrupt", "forced_1_withheld", "forced_2_withheld",
                 "choice_shared0_budget2_static", "choice_shared0_budget2_adaptive",
                 "choice_shared0_budget4_static", "choice_shared0_budget4_adaptive", "choice_shared1_budget3_static"]:
        s = lookup[name]
        r = s["rates_per_offer"]
        conditional = "undefined" if s["wrong_given_decision"] is None else f"{float(s['wrong_given_decision']):.6f}"
        lines.append(f"| {name} | {float(r['wrong']):.6f} | {float(r['correct']):.6f} | {float(r['cancel']):.6f} | {conditional} |")
    lines += ["", "A one-corrupt deterministic 2-of-3 majority cannot resolve wrongly when all other reports are true; two corrupted reporters can. With natural source errors, a single attacker can combine with an honest source error, so the zero-error threshold is not a population error bound.", "",
              "The independent authority minimum cost for two controlled reports is 6 units (2+4); a common upstream controlling all reports reduces it to 3. These are stipulated authority costs, not measured hacking costs. Adaptive attackers observe the realized errors and availability before selecting a cost-constrained action.", "",
              "Canonical fabricated traces pass the consistency checker and fail authenticated verification. Authentically signed common errors pass both and can finalize wrongly. Authentication proves origin under a key assumption, not factual correctness. Missing/late trace data blocks the proposal and leads to the explicit hard-timeout cancellation; it is never counted as a correct answer.", "",
              "The publication abstraction is an append-only available byte log with a trusted clock. This demonstrates the gate and failure transition; it does not measure real network retrieval, prove IPFS availability, or implement consensus. LLM/human fixtures validate only authenticated reported I/O, not model or human accuracy.", ""]
    (output_dir / "report.md").write_text("\n".join(lines))
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output_dir.iterdir())
                if p.is_file() and p.name != "manifest.json"}
    write_json(output_dir / "manifest.json", manifest)
    return {"experiment_count": len(summaries), "exact_weighted_rows": len(rows), "protocol_vectors": len(catalog),
            "tampering_vectors": len(attacks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
