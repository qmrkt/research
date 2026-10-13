"""Audit benchmark evidence; this is not a substitute for rerunning algod."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def audit(path):
    result = json.loads(path.read_text())
    assert result["avm_target"] == 11
    assert result["simulation_overrides"] == {}
    for relative, expected in result["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / relative).read_bytes()).hexdigest() == expected, relative
    raw_path = path.parent / result["raw_observations"]["file"]
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == result["raw_observations"]["sha256"]
    with gzip.open(raw_path, "rt") as stream:
        observations = [json.loads(line) for line in stream]
    assert len(observations) == result["raw_observations"]["count"]
    assert [row["simulation_id"] for row in observations] == list(range(len(observations)))
    for observation in observations:
        if "response" in observation:
            group = observation["response"]["txn-groups"][0]
            assert sum(row.get("app-budget-consumed", 0) for row in group.get("txn-results", [])) == group.get("app-budget-consumed", 0)
    positives = result["positive_cases"] + result["real_protocol_cases"]
    assert len(positives) == 42
    for row in positives:
        assert row["accepted"] and row["confirmed_round"] > 0
        assert row["group_opcode_cost"] == sum(row["txn_opcode_costs"])
        assert row["group_opcode_cost"] <= row["group_opcode_budget"] == row["application_calls"] * 700
        assert row["payment_transactions"] == 1 and row["txn_opcode_costs"][0] == 0
        surcharge = (max(0, row["argument_bytes"] - 2048) + 9) // 10
        assert row["group_fee_microalgo"] == (row["application_calls"] + 1) * 1000 + surcharge
        original = observations[row["simulation_id"]]["response"]["txn-groups"][0]
        assert not original.get("failure-message")
        assert row["group_opcode_cost"] == original["app-budget-consumed"]
        assert row["group_opcode_budget"] == original["app-budget-added"]
    assert len(result["negative_cases"]) == 45
    assert all(not row["accepted"] and row["failure"] for row in result["negative_cases"])
    for row in result["negative_cases"]:
        original = observations[row["simulation_id"]]
        assert original.get("error") or original["response"]["txn-groups"][0].get("failure-message")
    summaries = (result["all_index_sweep"] + result["whole_trace_baseline"]
                 + result["real_whole_trace_baseline"]
                 + [attempt for row in result["positive_cases"] for attempt in row["attempts"]])
    for row in summaries:
        original = observations[row["simulation_id"]]["response"]["txn-groups"][0]
        assert row["accepted"] == (not bool(original.get("failure-message")))
        assert row["group_opcode_cost"] == original.get("app-budget-consumed", 0)
    costs = []
    for count in (4, 16, 64):
        for method in ("member", "signed"):
            rows = [r for r in result["all_index_sweep"] if r["count"] == count and r["method"] == method]
            assert len(rows) == count and {r["index"] for r in rows} == set(range(count))
            assert all(row["accepted"] for row in rows)
            values = [row["txn_opcode_costs"][-1] for row in rows]
            costs.append({"count": count, "method": method, "minimum": min(values), "maximum": max(values)})
    return {"source_hashes_verified": len(result["source_sha256"]),
            "raw_responses_verified": len(observations),
            "confirmed_groups": len(positives), "negative_cases_rejected": 45,
            "all_index_checks": len(result["all_index_sweep"]), "cost_ranges": costs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=HERE.parent / "output" / "avm" / "results.json")
    args = parser.parse_args()
    print(json.dumps(audit(args.results), indent=2, sort_keys=True))
