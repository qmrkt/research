"""Execute the paper's verification kernel against a private algod ledger.

Requires py-algorand-sdk==2.11.1 and PyNaCl==1.6.0. Credentials are read only
from an explicitly supplied private development node. No public-network access.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import statistics
import sys
import time
from pathlib import Path

from algosdk import encoding, kmd, transaction
from algosdk.v2client import algod, models
from nacl.signing import SigningKey


HERE = Path(__file__).resolve().parent
H = lambda b: hashlib.sha256(b).digest()
U = lambda n: n.to_bytes(8, "big")
LEAF = b"QM_EXEC_LEAF_V1\0"
NODE = b"QM_EXEC_NODE_V1\0"
ROOT = b"QM_EXEC_ROOT_V1\0"
RECEIPT = b"QM_EXEC_AVM_RECEIPT_V1\0"
SIMULATIONS = []


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fixture(count, target_size, index=None):
    """Exactly sized, deterministic ASCII canonical JSON diagnostic records."""
    context = H(b"avm context fixture v1")
    payloads = []
    for i in range(count):
        item = {"index": str(i), "input": str(i), "output": str(i + 1),
                "node": f"n{i}", "operation": "increment", "source_data": ""}
        item["source_data"] = "a" * (target_size - len(canonical(item)))
        payloads.append(canonical(item))
    levels = [[H(LEAF + context + U(count) + U(i) + H(p))
               for i, p in enumerate(payloads)]]
    while len(levels[-1]) > 1:
        current = levels[-1]
        levels.append([H(NODE + current[i] + current[i + 1])
                       for i in range(0, len(current), 2)])
    root = H(ROOT + context + U(count) + levels[-1][0])
    index = count - 1 if index is None else index
    proof = b"".join(level[(index >> depth) ^ 1]
                     for depth, level in enumerate(levels[:-1]))
    whole = b"[" + b",".join(payloads) + b"]"
    result = H(b"result fixture v1")
    # Public deterministic research fixture key. Not a production identity.
    key = SigningKey(H(b"question research public avm fixture key v1"))
    signature = key.sign(H(RECEIPT + context + U(count) + root + result)).signature
    return {"context": context, "count": count, "root": root, "result": result,
            "key": bytes(key.verify_key), "signature": signature, "index": index,
            "payload": payloads[index], "proof": proof, "whole": whole,
            "payloads": payloads}


def connect(node):
    genesis = json.loads((node / "genesis.json").read_text())
    if genesis.get("network") != "verified-execution-bench" or not genesis.get("devmode"):
        raise ValueError("refusing anything except the named private dev-mode benchmark network")
    endpoint = (node / "algod.net").read_text().strip()
    if not endpoint.startswith("127.0.0.1:"):
        raise ValueError("benchmark node must listen on loopback")
    client = algod.AlgodClient((node / "algod.token").read_text().strip(), "http://" + endpoint)
    kp = node / "kmd-v0.5"
    km = kmd.KMDClient((kp / "kmd.token").read_text().strip(),
                      "http://" + (kp / "kmd.net").read_text().strip())
    wallets = km.list_wallets()
    handle = km.init_wallet_handle(wallets[0]["id"], "")
    try:
        address = km.list_keys(handle)[0]
        secret = km.export_key(handle, "", address)
    finally:
        km.release_wallet_handle(handle)
    return client, address, secret


def simulate(client, signed):
    start = time.perf_counter_ns()
    evidence = {"simulation_id": len(SIMULATIONS),
                "signed_transactions_msgpack_base64": [encoding.msgpack_encode(tx) for tx in signed]}
    try:
        response = client.simulate_transactions(models.SimulateRequest(
            txn_groups=[models.SimulateRequestTransactionGroup(txns=signed)]))
        group = response["txn-groups"][0]
        elapsed = (time.perf_counter_ns() - start) / 1e6
        evidence.update(response=response, rpc_ms=elapsed)
        SIMULATIONS.append(evidence)
        return {"simulation_id": evidence["simulation_id"],
                "accepted": not bool(group.get("failure-message")),
                "failure": group.get("failure-message", ""),
                "group_opcode_cost": group.get("app-budget-consumed", 0),
                "group_opcode_budget": group.get("app-budget-added", 0),
                "txn_opcode_costs": [x.get("app-budget-consumed", 0)
                                      for x in group.get("txn-results", [])],
                "rpc_ms": elapsed}
    except Exception as error:
        elapsed = (time.perf_counter_ns() - start) / 1e6
        evidence.update(error=str(error), rpc_ms=elapsed)
        SIMULATIONS.append(evidence)
        return {"simulation_id": evidence["simulation_id"], "accepted": False,
                "failure": str(error), "rpc_ms": elapsed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=HERE.parent / "output" / "avm")
    args = ap.parse_args()
    SIMULATIONS.clear()
    args.output.mkdir(parents=True, exist_ok=True)
    client, address, secret = connect(args.node)
    approval = (HERE / "compiled" / "ExecutionVerifier.approval.bin").read_bytes()
    clear = (HERE / "compiled" / "ExecutionVerifier.clear.bin").read_bytes()
    counter = 0

    def params():
        sp = client.suggested_params()
        sp.fee = 1000
        sp.flat_fee = True
        return sp

    def create(f):
        before = client.account_info(address)["min-balance"]
        tx = transaction.ApplicationCreateTxn(
            address, params(), transaction.OnComplete.NoOpOC, approval, clear,
            transaction.StateSchema(1, 5), transaction.StateSchema(0, 0),
            app_args=[f["context"], U(f["count"]), f["root"], f["result"], f["key"], H(f["whole"])])
        signed = tx.sign(secret)
        info = simulate(client, [signed])
        if not info["accepted"]:
            raise RuntimeError(info)
        txid = client.send_transaction(signed)
        result = transaction.wait_for_confirmation(client, txid, 4)
        info["creator_min_balance_delta_microalgo"] = client.account_info(address)["min-balance"] - before
        return result["application-index"], info

    def group(app, appargs, app_calls, payments=0, fee=None):
        nonlocal counter
        counter += 1
        txs = []
        for i in range(payments):
            txs.append(transaction.PaymentTxn(address, params(), address, 0,
                       note=f"benchmark-{counter}-pay-{i}".encode()))
        for i in range(app_calls - 1):
            txs.append(transaction.ApplicationNoOpTxn(address, params(), app,
                       app_args=[b"budget"], note=f"benchmark-{counter}-budget-{i}".encode()))
        sp = params()
        # Consensus v42: 0.1 microAlgo for each argument byte above 2048,
        # rounded up at the final group fee. Extra fees buy bytes, not opcodes.
        sp.fee = fee if fee is not None else 1000 + (max(0, sum(map(len, appargs)) - 2048) + 9) // 10
        txs.append(transaction.ApplicationNoOpTxn(address, sp, app, app_args=appargs,
                   note=f"benchmark-{counter}-verify".encode()))
        transaction.assign_group_id(txs)
        return [tx.sign(secret) for tx in txs]

    cases, negative, baseline, index_sweep = [], [], [], []
    for count in (4, 16, 64):
        for size in (256, 1024, 2048, 4096):
            f = fixture(count, size)
            app, creation = create(f)
            common = [f["context"], U(count), U(f["index"]), f["payload"], f["proof"]]
            for method in (b"member", b"signed"):
                appargs = [method] + common + ([f["signature"]] if method == b"signed" else [])
                attempts = []
                chosen = None
                for calls in range(1, 5):
                    signed = group(app, appargs, calls, payments=1)
                    measured = simulate(client, signed)
                    attempts.append({"application_calls": calls, **measured})
                    if measured["accepted"]:
                        chosen = (calls, signed, measured)
                        break
                row = {"count": count, "payload_bytes": size,
                       "method": method.decode(), "proof_bytes": len(f["proof"]),
                       "argument_bytes": sum(map(len, appargs)), "whole_trace_bytes": len(f["whole"]),
                       "creation_opcode_cost": creation["group_opcode_cost"], "attempts": attempts}
                if chosen:
                    calls, signed, measured = chosen
                    repeats = [simulate(client, signed) for _ in range(7)]
                    assert all(r["accepted"] and r["group_opcode_cost"] == measured["group_opcode_cost"] for r in repeats)
                    txid = client.send_transactions(signed)
                    confirmed = transaction.wait_for_confirmation(client, txid, 4)
                    row.update({"accepted": True, "application_calls": calls, "payment_transactions": 1,
                                "simulation_id": measured["simulation_id"],
                                "group_fee_microalgo": sum(s.transaction.fee for s in signed),
                                "group_signed_bytes": sum(len(base64.b64decode(encoding.msgpack_encode(s))) for s in signed),
                                "group_opcode_cost": measured["group_opcode_cost"],
                                "group_opcode_budget": measured["group_opcode_budget"],
                                "txn_opcode_costs": measured["txn_opcode_costs"],
                                "rpc_median_ms": statistics.median(r["rpc_ms"] for r in repeats),
                                "confirmed_round": confirmed["confirmed-round"]})
                else:
                    row["accepted"] = False
                cases.append(row)
            whole_args = [b"whole", f["whole"]]
            baseline.append({"count": count, "payload_bytes": size,
                             "argument_bytes": sum(map(len, whole_args)),
                             **simulate(client, group(app, whole_args, 1))})
            if size == 256:
                for index in range(count):
                    each = fixture(count, size, index)
                    for method in (b"member", b"signed"):
                        aa = [method, each["context"], U(count), U(index), each["payload"], each["proof"]]
                        if method == b"signed":
                            aa.append(each["signature"])
                        measured = simulate(client, group(app, aa, 4, payments=1))
                        assert measured["accepted"]
                        index_sweep.append({"count": count, "index": index, "method": method.decode(), **measured})
                mutations = {
                    "wrong_context": [b"member", H(b"other"), *common[1:]],
                    "wrong_count": [b"member", common[0], U(count // 2), *common[2:]],
                    "index_out_of_bounds": [b"member", *common[:2], U(count), *common[3:]],
                    "wrong_index": [b"member", *common[:2], U(0), *common[3:]],
                    "modified_payload": [b"member", *common[:3], common[3] + b"x", common[4]],
                    "truncated_proof": [b"member", *common[:4], common[4][:-32]],
                    "extended_proof": [b"member", *common[:4], common[4] + bytes(32)],
                    "modified_sibling": [b"member", *common[:4], bytes(32) + common[4][32:]],
                    "bad_signature": [b"signed", *common, bytes(64)],
                    "truncated_signature": [b"signed", *common, f["signature"][:-1]],
                    "count_noncanonical_width": [b"member", common[0], bytes([count]), *common[2:]],
                    "index_noncanonical_width": [b"member", *common[:2], bytes([count - 1]), *common[3:]],
                }
                for name, altered in mutations.items():
                    negative.append({"count": count, "mutation": name,
                                     **simulate(client, group(app, altered, 4, payments=1))})
                negative.append({"count": count, "mutation": "payment_cannot_buy_signature_budget",
                                 **simulate(client, group(app, [b"signed", *common, f["signature"]], 1, payments=15))})
            if size == 2048:
                negative.append({"count": count, "mutation": "large_arguments_without_surcharge",
                                 **simulate(client, group(app, [b"member", *common], 4, payments=1, fee=1000))})
    # Cross-check real protocol payloads and roots, not only size-controlled data.
    spec = importlib.util.spec_from_file_location("execution_protocol_avm_bench", HERE.parent / "simulation" / "protocol.py")
    protocol = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = protocol
    spec.loader.exec_module(protocol)
    protocol_cases, protocol_baseline = [], []
    for count in (4, 16, 64):
        example = protocol.make_example(count)
        payloads = [protocol.canonical(record) for record in example["trace"]["records"]]
        f = fixture(count, 256)
        f.update(context=bytes.fromhex(protocol.context_digest(example["trace"]["context"])),
                 root=bytes.fromhex(example["trace_root"]),
                 result=bytes.fromhex(example["result_digest"]),
                 whole=protocol.canonical(example["trace"]))
        key = SigningKey(H(b"question research public avm fixture key v1"))
        f["signature"] = key.sign(H(RECEIPT + f["context"] + U(count) + f["root"] + f["result"])).signature
        app, creation = create(f)
        whole_args = [b"whole", f["whole"]]
        whole_group = group(app, whole_args, 1)
        protocol_baseline.append({"count": count, "trace_bytes": len(f["whole"]),
                                  "group_fee_microalgo": sum(s.transaction.fee for s in whole_group),
                                  **simulate(client, whole_group)})
        for index in (0, count // 2, count - 1):
            proof = b"".join(bytes.fromhex(x) for x in protocol.inclusion_proof(f["context"].hex(), payloads, index))
            for method in (b"member", b"signed"):
                appargs = [method, f["context"], U(count), U(index), payloads[index], proof]
                if method == b"signed":
                    appargs.append(f["signature"])
                for calls in range(1, 5):
                    signed = group(app, appargs, calls, payments=1)
                    measured = simulate(client, signed)
                    if measured["accepted"]:
                        break
                assert measured["accepted"], measured
                txid = client.send_transactions(signed)
                confirmed = transaction.wait_for_confirmation(client, txid, 4)
                protocol_cases.append({"count": count, "index": index, "method": method.decode(),
                    "payload_bytes": len(payloads[index]), "proof_bytes": len(proof),
                    "argument_bytes": sum(map(len, appargs)), "whole_trace_bytes": len(f["whole"]),
                    "application_calls": calls, "payment_transactions": 1,
                    "group_fee_microalgo": sum(s.transaction.fee for s in signed),
                    "group_signed_bytes": sum(len(base64.b64decode(encoding.msgpack_encode(s))) for s in signed),
                    "confirmed_round": confirmed["confirmed-round"],
                    "creator_min_balance_delta_microalgo": creation["creator_min_balance_delta_microalgo"],
                    **measured})
    for unsupported in (0, 3, 65):
        f = fixture(4, 256)
        tx = transaction.ApplicationCreateTxn(
            address, params(), transaction.OnComplete.NoOpOC, approval, clear,
            transaction.StateSchema(1, 5), transaction.StateSchema(0, 0),
            app_args=[f["context"], U(unsupported), f["root"], f["result"], f["key"], H(f["whole"])])
        negative.append({"count": unsupported, "mutation": "unsupported_creation_count",
                         **simulate(client, [tx.sign(secret)])})
    assert not any(x["accepted"] for x in negative)
    raw_path = args.output / "simulate_observations.jsonl.gz"
    with raw_path.open("wb") as raw_file:
        with gzip.GzipFile(fileobj=raw_file, mode="wb", filename="", mtime=0) as stream:
            for observation in SIMULATIONS:
                stream.write(canonical(observation) + b"\n")
    result = {"schema": "question-verified-execution-avm-v1", "node_version": client.versions(),
              "protocol": client.status()["last-version"], "avm_target": 11,
              "compiler": "puyapy 5.7.1 -O2 --target-avm-version 11", "host": platform.platform(),
              "dependencies": {name: importlib.metadata.version(name) for name in ("py-algorand-sdk", "PyNaCl", "puyapy")},
              "approval_bytes": len(approval), "clear_bytes": len(clear),
              "global_state": {"uint_slots": 1, "byte_slots": 5},
              "simulation_overrides": {}, "positive_cases": cases,
              "raw_observations": {"file": raw_path.name, "count": len(SIMULATIONS),
                                   "sha256": H(raw_path.read_bytes()).hex()},
              "negative_cases": negative, "whole_trace_baseline": baseline, "all_index_sweep": index_sweep,
              "real_protocol_cases": protocol_cases, "real_whole_trace_baseline": protocol_baseline,
              "source_sha256": {str(p.relative_to(HERE.parent)): H(p.read_bytes()).hex() for p in
                                (HERE / "contract.py", HERE / "benchmark.py", HERE.parent / "simulation" / "protocol.py",
                                 HERE / "compiled" / "ExecutionVerifier.approval.bin", HERE / "compiled" / "ExecutionVerifier.clear.bin")}}
    (args.output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"positive_accepted": sum(x["accepted"] for x in cases),
                      "positive_total": len(cases), "negative_rejected": len(negative),
                      "output": str(args.output / "results.json")}))


if __name__ == "__main__":
    main()
