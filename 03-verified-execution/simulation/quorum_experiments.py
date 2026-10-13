"""Reproducible exact enumeration, adversarial vectors, and seeded selection runs.

Run: python -m research.verified_execution.quorum_experiments --output-dir ...
The design is frozen on disk before any experiment output is generated.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
from dataclasses import replace
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys

from . import quorum as q


DESIGN = {
    "version": 1,
    "purpose": "mechanism conformance and model counterexamples, not deployed TEE validation",
    "frozen_before_run": True,
    "probabilities": [[1, 100], [1, 10], [3, 10], [1, 2]],
    "attempt_counts": [1, 3, 10, 30],
    "seeds": list(range(73000, 73020)),
    "episodes_per_seed_cell": 1000,
    "quorum_committee_sizes": list(range(1, 9)),
    "abort_enumeration_population": 8,
    "toy_seeded_requests": 10000,
    "analysis": "exact probabilities primary; paired seeded Bernoulli Monte Carlo as implementation check",
    "raw_schema": ["p_numerator", "p_denominator", "attempts", "seed", "episode", "outcome_bitmask"],
    "authentication": "public test-secret HMAC; no claim of public-key or hardware attestation",
    "excluded": ["real LLM accuracy", "real TEE compromise rates", "network latency", "economic attacker costs"],
}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def committee(n: int = 5, k: int = 3, **kwargs) -> q.QuorumPolicy:
    runners = tuple(q.Runner(f"r{i}", "vendor-a" if i < 3 else "vendor-b",
                            f"operator-{i}", "registrar-common", "build-common") for i in range(n))
    return q.QuorumPolicy(runners, k, **kwargs)


def certificate(policy: q.QuorumPolicy, request: dict, outcome: bool,
                ids: list[str] | None = None, auth: q.ReceiptHarness | None = None,
                faulty_ids: tuple[str, ...] = (), projection: str = "44" * 32):
    auth = auth or q.ReceiptHarness(policy)
    result = q.make_result(request, outcome, projection)
    selected = ids or [r.runner_id for r in policy.runners[:policy.threshold]]
    receipts = [auth.issue(i, request, result, "run-" + i,
                            hashlib.sha256(("trace:" + i).encode()).hexdigest(),
                            hashlib.sha256(("binary:" + i).encode()).hexdigest(),
                            faulty=i in faulty_ids) for i in selected]
    return result, receipts, auth


def adversarial_vectors() -> list[dict]:
    policy = committee()
    request = q.make_request(policy)
    result, receipts, auth = certificate(policy, request, True)
    vectors = []

    def check(name, req, res, rec, expected, pol=policy, authentication=auth, **kwargs):
        accepted = q.verify_certificate(pol, req, res, rec, authentication, **kwargs)
        if accepted != expected:
            raise AssertionError(name)
        vectors.append({"name": name, "accepted": accepted, "expected": expected})

    check("distinct_run_trace_binary_same_shared_result", request, result, receipts, True)
    if len({q.digest("FULL_RECEIPT", r["receipt"]) for r in receipts}) != 3:
        raise AssertionError("per-run receipts unexpectedly equal")
    check("duplicate_signer", request, result, [receipts[0]] * 3, False)
    check("insufficient_signers", request, result, receipts[:2], False)
    bad = copy.deepcopy(receipts)
    bad[0]["receipt"]["trace_root"] = "ff" * 32
    check("tampered_receipt", request, result, bad, False)
    check("cross_request_replay", {**request, "request_id": "other"}, result, receipts, False)
    check("changed_snapshot", {**request, "snapshot_digest": "ff" * 32}, result, receipts, False)
    check("changed_terminal", request, {**result, "outcome": False}, receipts, False)
    check("changed_semantic_projection", request, {**result, "semantic_projection_digest": "ff" * 32}, receipts, False)
    outsider = q.ReceiptHarness(committee(6, 3))
    outsider_receipt = outsider.issue("r5", request, result, "outside", "55" * 32, "66" * 32)
    check("unassigned_runner", request, result, receipts[:2] + [outsider_receipt], False)
    constrained = committee(min_vendors=2)
    constrained_request = q.make_request(constrained)
    cres, crec, cauth = certificate(constrained, constrained_request, True)
    check("three_of_five_one_vendor_rejected_by_domain_policy", constrained_request, cres, crec,
          False, constrained, cauth)
    cres, crec, cauth = certificate(constrained, constrained_request, True, ["r0", "r1", "r3"])
    check("cross_vendor_certificate", constrained_request, cres, crec, True, constrained, cauth)
    check("policy_swap", request, result, receipts, False, constrained)
    check("expires_before_finalization_deadline", request, result, receipts, False, final_deadline=1001)
    check("receipt_before_registration", request, result, receipts, False, now=-1)
    epoch_policy = replace(policy, runners=tuple(replace(r, registration_epoch=2) for r in policy.runners))
    check("epoch_replay", request, result, receipts, False, epoch_policy)
    auth.revoked_at["r0"] = 20
    check("valid_before_revocation", request, result, receipts, True, now=19)
    check("revoked_before_finalization", request, result, receipts, False, now=20)
    return vectors


def exact_quorums() -> dict:
    rows, fault_sets = [], 0
    for n in DESIGN["quorum_committee_sizes"]:
        for k in range(1, n + 1):
            policy = committee(n, k)
            actual_intersection = policy.min_intersection()
            assert actual_intersection == max(0, 2 * k - n)
            for f in range(n + 1):
                unsafe_auth, live = False, True
                ids = {r.runner_id for r in policy.runners}
                for faults in itertools.combinations(sorted(ids), f):
                    fault_sets += 1
                    unsafe_auth |= policy.accepts(faults)
                    live &= policy.accepts(ids - set(faults))
                assert (not unsafe_auth) == (k > f)
                assert live == (k <= n - f)
                rows.append({"n": n, "k": k, "f": f,
                             "authenticity": not unsafe_auth, "honest_quorum_available": live,
                             "conflict_resistance": actual_intersection > f,
                             "minimum_intersection": actual_intersection})
    # Actual conflicting certificates: one Byzantine double-voter; each honest
    # signer votes once. No cryptography is broken in this witness.
    policy = committee(5, 3)
    request, auth = q.make_request(policy), q.ReceiptHarness(policy)
    yes, yr, _ = certificate(policy, request, True, ["r0", "r1", "r2"], auth, ("r0",))
    no, nr, _ = certificate(policy, request, False, ["r0", "r3", "r4"], auth, ("r0",))
    assert q.verify_certificate(policy, request, yes, yr, auth)
    assert q.verify_certificate(policy, request, no, nr, auth)
    return {"configurations": len(rows), "fault_sets_enumerated": fault_sets, "rows": rows,
            "conflicting_certificates_witness": {"n": 5, "k": 3, "f": 1,
                "yes_signers": ["r0", "r1", "r2"], "no_signers": ["r0", "r3", "r4"],
                "byzantine": ["r0"], "both_verify": True}}


def dependency_covers() -> list[dict]:
    rows = []
    for constrained in (False, True):
        pol = committee(min_vendors=2 if constrained else 1)
        vendors = tuple(q.DependencyAttack(v, frozenset(r.runner_id for r in pol.runners if r.vendor == v), 10)
                        for v in sorted({r.vendor for r in pol.runners}))
        for shared in (False, True):
            attacks = vendors + ((q.DependencyAttack("shared-registrar", frozenset(r.runner_id for r in pol.runners), 1),)
                                 if shared else ())
            rows.append({"domain_requirement": pol.min_vendors, "shared_registrar_attack": shared,
                         "accepted_sets": len(pol.quorums()), "minimum_intersection": pol.min_intersection(),
                         "minimum_attack": q.minimum_attack(pol, attacks),
                         "cost_interpretation": "illustrative units, not measured compromise costs"})
    return rows


def abort_enumeration() -> dict:
    n = DESIGN["abort_enumeration_population"]
    checked, equal_lower, equal_upper = 0, 0, 0
    for event in range(1 << n):
        p = Fraction(event.bit_count(), n)
        for final in range(1, 1 << n):
            alpha = Fraction(final.bit_count(), n)
            lower, upper = q.finalized_bounds(p, alpha)
            conditional = Fraction((event & final).bit_count(), final.bit_count())
            assert lower <= conditional <= upper
            assert Fraction((event & final).bit_count(), n) <= p
            checked += 1
            equal_lower += conditional == lower
            equal_upper += conditional == upper
    return {"population": n, "event_selection_pairs": checked, "lower_bound_equalities": equal_lower,
            "upper_bound_equalities": equal_upper, "violations": 0,
            "counterexample": {"p": 0.1, "completion": 0.1,
                               "favorable_given_finalized": 1.0, "favorable_per_authorization": 0.1}}


def wilson(successes: int, total: int) -> list[float]:
    if not total:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = successes / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0.0, center - radius), min(1.0, center + radius)]


def simulate(output_dir: Path) -> list[dict]:
    rows = []
    with (output_dir / "selection_observations.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            for numerator, denominator in DESIGN["probabilities"]:
                p = Fraction(numerator, denominator)
                for attempts in DESIGN["attempt_counts"]:
                    firsts, bests, total, majority = 0, 0, 0, 0
                    per_seed = []
                    for seed in DESIGN["seeds"]:
                        # Reuse the same seed within a cell for paired policy arms.
                        rng = random.Random(f"qm-quorum-v1:{seed}:{numerator}/{denominator}:{attempts}")
                        seed_first, seed_best = 0, 0
                        for episode in range(DESIGN["episodes_per_seed_cell"]):
                            bits = [rng.random() < float(p) for _ in range(attempts)]
                            mask = sum(int(bit) << i for i, bit in enumerate(bits))
                            obs = [numerator, denominator, attempts, seed, episode, mask]
                            zipped.write((json.dumps(obs, separators=(",", ":")) + "\n").encode())
                            firsts += bits[0]
                            bests += any(bits)
                            majority += sum(bits) > attempts / 2
                            seed_first += bits[0]
                            seed_best += any(bits)
                            total += 1
                        per_seed.append({"seed": seed, "first": seed_first, "best": seed_best})
                    rows.append({"p": float(p), "attempts": attempts, "episodes": total,
                                 "unrestricted_best_of_m": bests / total,
                                 "best_of_m_exact": float(q.selection_probability(p, attempts)),
                                 "best_of_m_wilson95": wilson(bests, total),
                                 "fixed_first_slot": firsts / total,
                                 "first_slot_wilson95": wilson(firsts, total),
                                 "fixed_all_majority": majority / total,
                                 "all_majority_exact": sum(math.comb(attempts, i) * float(p)**i * (1-float(p))**(attempts-i)
                                                           for i in range(attempts // 2 + 1, attempts + 1)),
                                 "selective_abort_completion": firsts / total,
                                 "selective_abort_favorable_given_finalized": 1.0 if firsts else None,
                                 "selective_abort_favorable_per_authorization": firsts / total,
                                 "per_seed": per_seed})
    return rows


def audit_raw(output_dir: Path, expected: list[dict]) -> dict:
    aggregate = defaultdict(lambda: [0, 0, 0, 0])
    seen = set()
    with gzip.open(output_dir / "selection_observations.jsonl.gz", "rt") as src:
        for line in src:
            a, b, m, seed, episode, mask = json.loads(line)
            key = (a, b, m, seed, episode)
            if key in seen or not 0 <= mask < 1 << m:
                raise AssertionError("invalid or duplicate raw observation")
            if ([a, b] not in DESIGN["probabilities"] or m not in DESIGN["attempt_counts"]
                    or seed not in DESIGN["seeds"] or not 0 <= episode < DESIGN["episodes_per_seed_cell"]):
                raise AssertionError("observation outside frozen design")
            seen.add(key)
            counts = aggregate[(a / b, m)]
            counts[0] += 1
            counts[1] += mask & 1
            counts[2] += mask != 0
            counts[3] += mask.bit_count() > m / 2
    for row in expected:
        n, first, best, majority = aggregate[(row["p"], row["attempts"])]
        assert n == row["episodes"] == len(DESIGN["seeds"]) * DESIGN["episodes_per_seed_cell"]
        assert first / n == row["fixed_first_slot"]
        assert best / n == row["unrestricted_best_of_m"]
        assert majority / n == row["fixed_all_majority"]
    return {"raw_observations": len(seen), "cells": len(aggregate), "duplicate_rows": 0,
            "reaggregation": "passed", "complete_frozen_grid": True}


def seeded_restarts() -> dict:
    policy = committee()
    favorable, checked = 0, 0
    for i in range(DESIGN["toy_seeded_requests"]):
        request = q.make_request(policy, f"seeded-request-{i}")
        seed = hashlib.sha256(f"public-toy-beacon-{i}".encode()).digest()
        first = q.seeded_bit(request, seed)
        favorable += first
        for _ in range(30):
            assert q.seeded_bit(request, seed) == first
            checked += 1
    return {"requests": DESIGN["toy_seeded_requests"], "reexecutions": checked,
            "changed_results": 0, "favorable_requests": favorable,
            "warning": "deterministic toy inference only; no real LLM determinism or unbiased beacon claim"}


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    design_path = output_dir / "design.json"
    if design_path.exists() and json.loads(design_path.read_text()) != DESIGN:
        raise RuntimeError("refusing to replace a different frozen design")
    write_json(design_path, DESIGN)
    vectors = adversarial_vectors()
    write_json(output_dir / "certificate_vectors.json", vectors)
    exact = exact_quorums()
    write_json(output_dir / "exact_quorums.json", exact)
    dependencies = dependency_covers()
    write_json(output_dir / "dependency_covers.json", dependencies)
    aborts = abort_enumeration()
    write_json(output_dir / "selective_abort_exact.json", aborts)
    selection = simulate(output_dir)
    write_json(output_dir / "selection_summary.json", selection)
    audit = audit_raw(output_dir, selection)
    write_json(output_dir / "raw_audit.json", audit)
    seeded = seeded_restarts()
    write_json(output_dir / "seeded_restarts.json", seeded)
    source = Path(__file__).parent
    manifest = {"python": sys.version, "design_sha256": hashlib.sha256(design_path.read_bytes()).hexdigest(),
                "source_sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                   for name in ("quorum.py", "quorum_experiments.py", "protocol.py")},
                "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(output_dir.iterdir()) if p.name != "manifest.json"
                              and not p.name.startswith("integration_") and p.is_file()},
                "summary": {"raw_observations": audit["raw_observations"],
                            "quorum_configurations": exact["configurations"],
                            "fault_sets_enumerated": exact["fault_sets_enumerated"],
                            "abort_event_selection_pairs": aborts["event_selection_pairs"],
                            "certificate_vectors": len(vectors)}}
    write_json(output_dir / "manifest.json", manifest)
    return manifest["summary"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
