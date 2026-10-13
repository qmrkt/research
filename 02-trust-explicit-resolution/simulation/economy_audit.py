"""Independently audit published raw episodes without rerunning agent decisions."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path


def audit(output: Path) -> dict:
    manifest = json.loads((output/"manifest.json").read_text())
    for name, record in manifest.items():
        blob = (output/name).read_bytes()
        assert len(blob) == record["bytes"], name
        assert hashlib.sha256(blob).hexdigest() == record["sha256"], name
    provenance = json.loads((output/"provenance.json").read_text())
    for name, digest in provenance["sources"].items():
        assert hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() == digest, name
    plan = json.loads((output/"plan.json").read_text())
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == provenance["plan_sha256"]
    configs = {row["key"]: row["config"] for row in plan["cases"]}
    counts, seen = defaultdict(Counter), defaultdict(int)
    max_error = 0.
    with gzip.open(output/"episodes.jsonl.gz", "rt") as handle:
        for line in handle:
            e = json.loads(line)
            c = configs[e["case"]]
            assert e["seed"] in plan["seeds"] and 0 <= e["episode"] < plan["episodes_per_seed"]
            key, bit = (e["case"], e["seed"]), 1 << e["episode"]
            assert not seen[key] & bit, "Duplicate raw episode"
            seen[key] |= bit
            count = counts[e["case"]]
            count["episodes"] += 1
            count["wrong"] += e["final_wrong"]
            count["submitted"] += e["status"] != "deferred"
            assert e["status"] in ("correct", "incorrect", "deferred")
            assert e["final_wrong"] == (e["status"] == "incorrect")
            assert e["attack_attempted"] == e["proposal_false"]
            error = (sum(e["actor_cash_changes"]) + e["protocol_receipt"] + e["resource_cost"]
                     + e["reserve_final"] - e["reserve_initial"])
            max_error = max(max_error, abs(error))
            assert abs(error) < 1e-8
            assert e["reserve_initial"] == c["proposer_fee"] and e["reserve_final"] >= 0
            assert abs(e["reserve_final"] + e["proposer_fee_paid"] - c["proposer_fee"]) < 1e-8
            if e["status"] == "deferred":
                assert e["proposer"] is None and not e["challenged"] and not e["attack_attempted"]
                continue
            bp = c["bond_floor"] if c["bond_rule"] == "flat" else max(c["bond_floor"], c["bond_rate"]*c["pool"])
            if c["bond_rule"] == "capped":
                bp = min(bp, c["bond_cap"])
            bc, ch = bp*c["challenger_ratio"], e["challenged"]
            overturned = ch and e["final_wrong"] != e["proposal_false"]
            resource = c["proposer_work"] + e["checks"]*c["verification_work"] + ch*c["challenge_work"]
            assert abs(e["resource_cost"]-resource) < 1e-8
            reward = c["reward_fraction"]*bp if overturned else 0.
            protocol = (bp-reward if overturned else bc) if ch else 0.
            assert abs(e["challenger_reward"]-reward) < 1e-8
            assert abs(e["protocol_receipt"]-protocol) < 1e-8
            assert abs(e["proposer_fee_paid"]-(0 if overturned else c["proposer_fee"])) < 1e-8
            assert abs(e["bond_locked"]-bp-ch*bc) < 1e-8
            q = e["expected_challenge"]
            expectation = 1-q*c["accuracy"] if e["proposal_false"] else q*(1-c["accuracy"])
            assert abs(e["expected_wrong"]-expectation) < 1e-12
            net = (e["actor_cash_changes"][e["proposer"]] + e["signed_gain"]*e["final_wrong"]
                   - c["capital_apy"]*bp*(c["window"]+c["adjudication_delay"])/8760)
            assert abs(net-e["proposer_net"]) < 1e-8
            assert e["false_challenge"] == (ch and not e["proposal_false"])
            assert e["wrongful_proposer_slash"] == (ch and not e["proposal_false"] and e["final_wrong"])
    mask = (1 << plan["episodes_per_seed"]) - 1
    assert len(seen) == len(configs)*len(plan["seeds"])
    assert all(value == mask for value in seen.values())
    for row in json.loads((output/"summary.json").read_text()):
        for key in ("episodes", "wrong", "submitted"):
            assert row[key] == counts[row["case"]][key], (row["case"], key)
    return {"audited_episodes": sum(row["episodes"] for row in counts.values()), "configurations": len(counts),
            "artifact_hashes": len(manifest), "source_hashes": len(provenance["sources"]),
            "max_cash_residual": max_error, "complete_unique_seed_episode_grid": True,
            "branch_accounting_and_raw_reaggregation": "passed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
