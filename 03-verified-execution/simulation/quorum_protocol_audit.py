"""Independent boundary audit added after primary experiments; not a held-out run."""
import argparse
import hashlib
import json
from pathlib import Path

from . import protocol as p


def run(output_path):
    counts = (4, 5, 7, 16, 64)
    values = (-p.MAX_INTEGER, -1, 0, 3, 4, 7, p.MAX_INTEGER - p.MAX_NODES)
    rows = []
    for count in counts:
        for value in values:
            example = p.make_example(count, value)
            trace = example["trace"]
            payloads = [p.canonical(record) for record in trace["records"]]
            context, root = p.context_digest(trace["context"]), example["trace_root"]
            assert p.verify_trace(example["blueprint"], example["request"], trace)
            for index in range(count):
                proof = p.inclusion_proof(context, payloads, index)
                membership = p.verify_inclusion(context, count, index, payloads[index], proof, root)
                parent = example["blueprint"]["nodes"][index]["parent"]
                parent_payload = None if parent is None else payloads[parent]
                parent_proof = None if parent is None else p.inclusion_proof(context, payloads, parent)
                false_fault = p.verify_local_fault(example["blueprint"], example["request"], trace["context"],
                    root, index, payloads[index], proof, parent_payload, parent_proof)
                assert membership and not false_fault, (count, value, index)
                rows.append({"count": count, "source_value": value, "index": index,
                             "membership": membership, "false_local_fault": false_fault})
    report = {"kind": "post-primary independent boundary audit; recorded after first execution and rerun verbatim",
              "config": {"counts": counts, "source_values": values},
              "traces": len(counts) * len(values), "memberships": len(rows), "false_local_faults": 0,
              "source_sha256": {Path(name).name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                for name in (__file__, p.__file__)}, "rows": rows}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return {k: report[k] for k in ("traces", "memberships", "false_local_faults")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_path), indent=2))


if __name__ == "__main__":
    main()
