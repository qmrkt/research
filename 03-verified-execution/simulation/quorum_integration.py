"""Post-primary integrated trace -> honest receipt -> quorum -> reveal checks."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from . import protocol as p
from . import quorum as q
from . import quorum_experiments as e


DESIGN = {
    "version": 1,
    "relationship_to_primary": "Follow-up integration designed after primary selection simulations; not held-out empirical validation.",
    "cases": ["same_snapshot_independent_runs", "authentic_common_source_error",
              "fabricated_source_preimage", "wrong_registered_measurement", "one_trace_withheld"],
    "committee": {"n": 5, "k": 3},
    "trace_nodes": 4,
    "authentication": "RSA test-source signature plus HMAC test-runner authentication; no actual TEE",
}


def fixture(value=7):
    example = p.make_example(count=4, value=value)
    committee = e.committee()
    policy = q.agreement_policy(committee, "33" * 32)
    request = {**example["request"], "agreement_policy_digest": p.agreement_policy_digest(policy)}
    traces = [p.run(example["blueprint"], request, example["snapshot"], "independent-" + runner.runner_id,
                    runner.runner_id, runner.expected_measurement, agreement_policy=policy)
              for runner in committee.runners[:3]]
    return example["blueprint"], request, traces, committee, policy


def reveal(blueprint, request, trace, policy, withhold=False):
    root = p.trace_commitment(trace)
    payloads = [p.canonical(record) for record in trace["records"]]
    context = p.context_digest(trace["context"])
    session = p.RevealSession(blueprint, request, trace["context"], root, trace["result"],
                              agreement_policy=policy)
    for i, payload in enumerate(payloads[:-1] if withhold else payloads):
        session.reveal(i, payload, p.inclusion_proof(context, payloads, i), 1)
    return session.finalize(11)


def cases():
    rows = []
    for value, name, true_world_outcome in ((7, "same_snapshot_independent_runs", True),
                                           (0, "authentic_common_source_error", True)):
        bp, request, traces, committee, policy = fixture(value)
        auth = q.ReceiptHarness(committee)
        receipts = [auth.issue_verified_trace(bp, request, trace) for trace in traces]
        roots = [p.trace_commitment(t) for t in traces]
        result = traces[0]["result"]
        accepted = q.verify_certificate(committee, request, result, receipts, auth)
        statuses = [reveal(bp, request, trace, policy) for trace in traces]
        assert len(set(roots)) == 3
        assert len({p.result_digest(t["result"]) for t in traces}) == 1
        assert accepted and statuses == ["finalized"] * 3
        rows.append({"name": name, "trace_roots": roots, "shared_result_digest": p.result_digest(result),
                     "certificate_accepted": accepted, "reveal_statuses": statuses,
                     "result_outcome": result["outcome"], "synthetic_true_world_outcome": true_world_outcome,
                     "truth_correct": result["outcome"] == true_world_outcome})

    bp, request, traces, committee, policy = fixture()
    auth = q.ReceiptHarness(committee)
    bad = copy.deepcopy(traces[0])
    snapshot = bad["records"][0]["input"]
    snapshot["reports"][0]["body"]["data"] = "host-fabricated-source-body"
    changed_request = {**request, "snapshot_digest": p.object_digest("QM_EXEC_SNAPSHOT_V1", snapshot)}
    bad["context"].update(request_digest=p.request_digest(changed_request), snapshot_digest=changed_request["snapshot_digest"])
    bad["result"].update(request_digest=p.request_digest(changed_request), snapshot_digest=changed_request["snapshot_digest"],
                           semantic_projection_digest=p.object_digest("QM_EXEC_SEMANTICS_V1", bad["records"]))
    assert p.verify_trace(bp, changed_request, bad, authenticate=False, agreement_policy=policy)
    try:
        auth.issue_verified_trace(bp, changed_request, bad)
        raise AssertionError("fabrication accepted")
    except p.ProtocolError as exc:
        rows.append({"name": "fabricated_source_preimage", "internal_consistency": True,
                     "receipt_issued": False, "reason": str(exc)})

    bad = copy.deepcopy(traces[0])
    bad["context"]["measurement"] = "ff" * 32
    assert p.verify_trace(bp, request, bad, agreement_policy=policy)
    try:
        auth.issue_verified_trace(bp, request, bad)
        raise AssertionError("wrong measurement accepted")
    except q.QuorumError as exc:
        rows.append({"name": "wrong_registered_measurement", "internal_consistency": True,
                     "receipt_issued": False, "reason": str(exc)})

    receipts = [auth.issue_verified_trace(bp, request, trace) for trace in traces]
    accepted = q.verify_certificate(committee, request, traces[0]["result"], receipts, auth)
    statuses = [reveal(bp, request, trace, policy, withhold=i == 0) for i, trace in enumerate(traces)]
    assert accepted and statuses == ["unavailable", "finalized", "finalized"]
    rows.append({"name": "one_trace_withheld", "certificate_accepted": accepted,
                 "reveal_statuses": statuses, "all_required_trace_gate_passed": False})
    return rows


def run(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen = output_dir / "integration_design.json"
    if frozen.exists() and json.loads(frozen.read_text()) != DESIGN:
        raise RuntimeError("different frozen integration design")
    e.write_json(frozen, DESIGN)
    results = cases()
    e.write_json(output_dir / "integration_vectors.json", results)
    files = [Path(__file__), Path(q.__file__), Path(p.__file__), frozen,
             output_dir / "integration_vectors.json"]
    e.write_json(output_dir / "integration_manifest.json", {
        "files": {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in files},
        "cases": len(results), "all_expected_results": True})
    return {"cases": len(results), "all_expected_results": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
