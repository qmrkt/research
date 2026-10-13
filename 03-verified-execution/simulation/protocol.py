"""Bounded execution/commitment reference profile; see ../PROTOCOL.md.

This is an executable research protocol, not a TEE or production interpreter.
RSA keys in fixtures are PUBLIC TEST KEYS; no production secrets are present.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_INTEGER = 2**53 - 1
MAX_NODES = 64
MAX_LEAF_BYTES = 4096
MAX_OBJECT_BYTES = MAX_NODES * MAX_LEAF_BYTES + 16384
LEAF_DOMAIN = b"QM_EXEC_LEAF_V1\0"
NODE_DOMAIN = b"QM_EXEC_NODE_V1\0"
PAD_DOMAIN = b"QM_EXEC_PAD_V1\0"
ROOT_DOMAIN = b"QM_EXEC_ROOT_V1\0"
PROFILE = "question.execution.branch-chain.v1"
AGREEMENT_POLICY = {"version": 1, "equivalence": "complete-deterministic-semantics"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_DER = bytes.fromhex("3031300d060960864801650304020105000420")


class ProtocolError(ValueError):
    """Malformed or semantically invalid protocol object."""


def canonical(value: Any) -> bytes:
    """Strict ASCII JSON profile: exact integer types, no floats, sorted keys."""
    def check(x, depth=0):
        if depth > 32:
            raise ProtocolError("nesting exceeds profile")
        if x is None or type(x) is bool:
            return
        if type(x) is int:
            if abs(x) > MAX_INTEGER:
                raise ProtocolError("integer outside exact profile")
        elif type(x) is str:
            if not x.isascii():
                raise ProtocolError("non-ASCII string")
        elif type(x) is list:
            for item in x:
                check(item, depth + 1)
        elif type(x) is dict:
            for key, item in x.items():
                if type(key) is not str:
                    raise ProtocolError("non-string key")
                check(key, depth + 1)
                check(item, depth + 1)
        else:
            raise ProtocolError("unsupported canonical type")
    check(value)
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(raw) > MAX_OBJECT_BYTES:
        raise ProtocolError("canonical byte budget exceeded")
    return raw


def parse_canonical(raw: bytes) -> Any:
    if type(raw) is not bytes or len(raw) > MAX_OBJECT_BYTES:
        raise ProtocolError("canonical bytes required within budget")
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ProtocolError("duplicate JSON key")
            out[k] = v
        return out
    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=pairs)
        if canonical(value) != raw:
            raise ProtocolError("noncanonical JSON bytes")
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("invalid canonical JSON") from exc


def object_digest(domain: str, value: Any) -> str:
    if not domain.isascii() or "\0" in domain:
        raise ProtocolError("invalid domain")
    return hashlib.sha256(domain.encode("ascii") + b"\0" + canonical(value)).hexdigest()


def _keys(obj, keys):
    if type(obj) is not dict or set(obj) != set(keys):
        raise ProtocolError("unexpected object fields")


def _integer(value, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError("invalid integer")
    return value


def _hex(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ProtocolError("32-byte lowercase hex digest required")
    return bytes.fromhex(value)


def _name(value):
    if type(value) is not str or not value.isascii() or not 1 <= len(value) <= 128:
        raise ProtocolError("nonempty bounded ASCII identifier required")
    return value


def request_digest(request):
    _keys(request, ("version", "chain_id", "market_id", "request_id", "blueprint_digest", "snapshot_digest", "agreement_policy_digest"))
    if type(request["version"]) is not int or request["version"] != 1:
        raise ProtocolError("request version")
    for key in ("chain_id", "market_id", "request_id"):
        _name(request[key])
    for key in ("blueprint_digest", "snapshot_digest", "agreement_policy_digest"):
        _hex(request[key])
    return object_digest("QM_EXEC_REQUEST_V1", request)


def result_digest(result):
    _keys(result, ("version", "request_digest", "snapshot_digest", "terminal_action", "outcome", "semantic_projection_digest"))
    if type(result["version"]) is not int or result["version"] != 1 or result["terminal_action"] != "resolve" or type(result["outcome"]) is not bool:
        raise ProtocolError("invalid result schema")
    for key in ("request_digest", "snapshot_digest", "semantic_projection_digest"):
        _hex(result[key])
    return object_digest("QM_EXEC_RESULT_V1", result)


def agreement_policy_digest(policy=None):
    policy = AGREEMENT_POLICY if policy is None else policy
    if type(policy) is not dict or set(policy) not in (set(AGREEMENT_POLICY), set(AGREEMENT_POLICY) | {"quorum_policy_digest", "attempt_policy_digest"}):
        raise ProtocolError("unknown deterministic agreement policy schema")
    if type(policy["version"]) is not int or policy["version"] != 1 or policy["equivalence"] != AGREEMENT_POLICY["equivalence"]:
        raise ProtocolError("unsupported semantic equivalence policy")
    if "quorum_policy_digest" in policy:
        _hex(policy["quorum_policy_digest"])
        _hex(policy["attempt_policy_digest"])
    return object_digest("QM_EXEC_POLICY_V1", policy)


def context_digest(context):
    _keys(context, ("request_digest", "snapshot_digest", "run_id", "runner_id", "measurement"))
    for key in ("request_digest", "snapshot_digest", "measurement"):
        _hex(context[key])
    for key in ("run_id", "runner_id"):
        _name(context[key])
    return object_digest("QM_EXEC_CONTEXT_V1", context)


def _u64(n):
    return _integer(n, 0, 2**64 - 1).to_bytes(8, "big")


def _shape(context, count, index=None):
    _hex(context)
    _integer(count, 1, MAX_NODES)
    if index is not None:
        _integer(index, 0, count - 1)


def leaf_hash(context: str, count: int, index: int, payload: bytes) -> bytes:
    _shape(context, count, index)
    if type(payload) is not bytes or len(payload) > MAX_LEAF_BYTES:
        raise ProtocolError("leaf byte budget exceeded")
    return hashlib.sha256(LEAF_DOMAIN + bytes.fromhex(context) + _u64(count) + _u64(index) + hashlib.sha256(payload).digest()).digest()


def _pad(context, count, index):
    return hashlib.sha256(PAD_DOMAIN + bytes.fromhex(context) + _u64(count) + _u64(index)).digest()


def _parent(left, right):
    return hashlib.sha256(NODE_DOMAIN + left + right).digest()


def _wrap(context, count, inner):
    return hashlib.sha256(ROOT_DOMAIN + bytes.fromhex(context) + _u64(count) + inner).hexdigest()


def merkle_root(context: str, payloads: list[bytes]) -> str:
    count = len(payloads)
    _shape(context, count)
    width = 1 << (count - 1).bit_length()
    row = [leaf_hash(context, count, i, p) for i, p in enumerate(payloads)]
    row.extend(_pad(context, count, i) for i in range(count, width))
    while len(row) > 1:
        row = [_parent(row[i], row[i+1]) for i in range(0, len(row), 2)]
    return _wrap(context, count, row[0])


def inclusion_proof(context: str, payloads: list[bytes], index: int) -> list[str]:
    count = len(payloads)
    _shape(context, count, index)
    width = 1 << (count - 1).bit_length()
    row = [leaf_hash(context, count, i, p) for i, p in enumerate(payloads)]
    row.extend(_pad(context, count, i) for i in range(count, width))
    proof = []
    while len(row) > 1:
        proof.append(row[index ^ 1].hex())
        row = [_parent(row[i], row[i+1]) for i in range(0, len(row), 2)]
        index //= 2
    return proof


def verify_inclusion(context: str, count: int, index: int, payload: bytes, proof: list[str], root: str) -> bool:
    """Authenticate bytes only; malformed challenger evidence never proves fraud."""
    try:
        _shape(context, count, index)
        _hex(root)
        if type(proof) is not list or len(proof) != (count - 1).bit_length():
            return False
        current = leaf_hash(context, count, index, payload)
        cursor = index
        for level, sibling_hex in enumerate(proof):
            sibling = _hex(sibling_hex)
            start = (cursor ^ 1) << level
            if start >= count:
                # A wholly padded sibling subtree has one uniquely prescribed hash.
                pads = [_pad(context, count, i) for i in range(start, start + (1 << level))]
                while len(pads) > 1:
                    pads = [_parent(pads[i], pads[i+1]) for i in range(0, len(pads), 2)]
                if sibling != pads[0]:
                    return False
            current = _parent(current, sibling) if cursor % 2 == 0 else _parent(sibling, current)
            cursor //= 2
        return _wrap(context, count, current) == root
    except (ProtocolError, TypeError, ValueError, OverflowError):
        return False


def test_keys():
    return json.loads((Path(__file__).parent / "fixtures" / "TEST_ONLY_RSA_KEYS.json").read_text())["keys"]


def public_key(key):
    return {"n": key["n"], "e": key["e"]}


def _public_key(key):
    _keys(key, ("n", "e"))
    if type(key["n"]) is not str or re.fullmatch(r"[0-9a-f]{512}", key["n"]) is None or int(key["n"], 16).bit_length() != 2048 or type(key["e"]) is not int or key["e"] != 65537:
        raise ProtocolError("canonical 2048-bit RSA key required")


def _emsa(message):
    data = _DER + hashlib.sha256(message).digest()
    return b"\x00\x01" + b"\xff" * (256 - len(data) - 3) + b"\x00" + data


def sign_test_source(body, key):
    """Public fixture keys only: this is not reviewed constant-time crypto."""
    encoded = _emsa(b"QM_EXEC_SOURCE_V1\0" + canonical(body))
    sig = pow(int.from_bytes(encoded, "big"), int(key["d"], 16), int(key["n"], 16))
    return {"body": copy.deepcopy(body), "signature": sig.to_bytes(256, "big").hex()}


def authentic_source(report, key):
    try:
        _keys(report, ("body", "signature"))
        _public_key(key)
        if type(report["signature"]) is not str or re.fullmatch(r"[0-9a-f]{512}", report["signature"]) is None:
            return False
        sig = int(report["signature"], 16)
        n = int(key["n"], 16)
        if sig >= n:
            return False
        actual = pow(sig, key["e"], n).to_bytes(256, "big")
        return actual == _emsa(b"QM_EXEC_SOURCE_V1\0" + canonical(report["body"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _nodes(count):
    _integer(count, 4, MAX_NODES)
    nodes = []
    for i in range(count):
        kind = "source" if i == 0 else "add" if i < count-3 else "ge" if i == count-3 else "terminal"
        parent = None if i == 0 else i-1 if i <= count-3 else count-3
        params = {} if kind == "source" else {"amount": 1} if kind == "add" else {"threshold": count} if kind == "ge" else {"when": i == count-2}
        nodes.append({"index": i, "node_id": f"n{i:03}", "kind": kind, "parent": parent, "params": params})
    return nodes


def make_blueprint(count=4):
    return {"version": 1, "profile": PROFILE, "source_authority": "source_a", "source_key": public_key(test_keys()["source_a"]), "min_observed_at": 100, "max_observed_at": 110, "nodes": _nodes(count)}


def validate_blueprint(bp):
    _keys(bp, ("version", "profile", "source_authority", "source_key", "min_observed_at", "max_observed_at", "nodes"))
    if type(bp["version"]) is not int or bp["version"] != 1 or bp["profile"] != PROFILE:
        raise ProtocolError("unknown blueprint profile")
    _name(bp["source_authority"])
    _public_key(bp["source_key"])
    _integer(bp["min_observed_at"])
    _integer(bp["max_observed_at"], bp["min_observed_at"])
    if type(bp["nodes"]) is not list:
        raise ProtocolError("nodes array required")
    n = len(bp["nodes"])
    _integer(n, 4, MAX_NODES)
    # The profile is deliberately total and small: one authenticated source,
    # zero or more integer additions, one comparison, two exclusive terminals.
    expected = _nodes(n)
    if canonical(bp["nodes"]) != canonical(expected):
        raise ProtocolError("invalid index/order/parent/branch grammar")
    return bp["nodes"]


def _source_value(bp, request, snapshot, authenticate=True):
    _keys(snapshot, ("version", "reports"))
    if type(snapshot["version"]) is not int or snapshot["version"] != 1 or type(snapshot["reports"]) is not list or len(snapshot["reports"]) != 1:
        raise ProtocolError("snapshot schema")
    if object_digest("QM_EXEC_SNAPSHOT_V1", snapshot) != request["snapshot_digest"]:
        raise ProtocolError("snapshot commitment mismatch")
    report = snapshot["reports"][0]
    _keys(report, ("body", "signature"))
    body = report["body"]
    _keys(body, ("version", "chain_id", "market_id", "request_id", "blueprint_digest", "authority", "observed_at", "value", "data"))
    if type(body["version"]) is not int or body["version"] != 1:
        raise ProtocolError("source version")
    for k in ("chain_id", "market_id", "request_id", "blueprint_digest"):
        if body[k] != request[k]:
            raise ProtocolError("source request binding mismatch")
    if body["authority"] != bp["source_authority"]:
        raise ProtocolError("source authority mismatch")
    _integer(body["observed_at"], bp["min_observed_at"], bp["max_observed_at"])
    _integer(body["value"], -MAX_INTEGER, MAX_INTEGER - MAX_NODES)
    if type(body["data"]) is not str or not body["data"].isascii() or len(body["data"]) > 1024:
        raise ProtocolError("source payload bounds")
    if authenticate and not authentic_source(report, bp["source_key"]):
        raise ProtocolError("source authentication failed")
    return body["value"]


def run(bp, request, snapshot, run_id="run-a", runner_id="runner-a", measurement="00"*32, agreement_policy=None):
    nodes = validate_blueprint(bp)
    rd = request_digest(request)
    if request["agreement_policy_digest"] != agreement_policy_digest(agreement_policy):
        raise ProtocolError("unsupported agreement policy for this grammar")
    if object_digest("QM_EXEC_BLUEPRINT_V1", bp) != request["blueprint_digest"]:
        raise ProtocolError("blueprint mismatch")
    value = _source_value(bp, request, snapshot)
    records = []
    gate = None
    for node in nodes:
        i, kind = node["index"], node["kind"]
        if kind == "source":
            inp, out, status, edge = copy.deepcopy(snapshot), value, "ok", nodes[i+1]["node_id"]
        elif kind == "add":
            inp, out, status, edge = value, value + 1, "ok", nodes[i+1]["node_id"]
            value = out
        elif kind == "ge":
            inp, out, status = value, value >= node["params"]["threshold"], "ok"
            gate = out
            edge = nodes[-2 if gate else -1]["node_id"]
        else:
            inp, status, edge = gate, "ok" if gate == node["params"]["when"] else "skipped", None
            out = gate if status == "ok" else None
        records.append({"index": i, "node_id": node["node_id"], "kind": kind, "status": status, "input": inp, "output": out, "edge_taken": edge})
    context = {"request_digest": rd, "snapshot_digest": request["snapshot_digest"], "run_id": run_id, "runner_id": runner_id, "measurement": measurement}
    context_digest(context)
    result = {"version": 1, "request_digest": rd, "snapshot_digest": request["snapshot_digest"], "terminal_action": "resolve", "outcome": gate, "semantic_projection_digest": object_digest("QM_EXEC_SEMANTICS_V1", records)}
    trace = {"version": 1, "context": context, "records": records, "result": result}
    return trace


def verify_trace(bp, request, trace, authenticate=True, agreement_policy=None):
    """Independent rule checker, not an invocation of the trace producer."""
    nodes = validate_blueprint(bp)
    rd = request_digest(request)
    if request["agreement_policy_digest"] != agreement_policy_digest(agreement_policy):
        raise ProtocolError("unsupported agreement policy for this grammar")
    if object_digest("QM_EXEC_BLUEPRINT_V1", bp) != request["blueprint_digest"]:
        raise ProtocolError("blueprint commitment")
    _keys(trace, ("version", "context", "records", "result"))
    if type(trace["version"]) is not int or trace["version"] != 1:
        raise ProtocolError("trace version")
    context_digest(trace["context"])
    if trace["context"]["request_digest"] != rd or trace["context"]["snapshot_digest"] != request["snapshot_digest"]:
        raise ProtocolError("trace request context")
    records = trace["records"]
    if type(records) is not list or len(records) != len(nodes):
        raise ProtocolError("trace cardinality")
    gate = None
    terminals = []
    for i, (node, rec) in enumerate(zip(nodes, records)):
        _keys(rec, ("index", "node_id", "kind", "status", "input", "output", "edge_taken"))
        if type(rec["index"]) is not int or rec["index"] != i or rec["node_id"] != node["node_id"] or rec["kind"] != node["kind"]:
            raise ProtocolError("trace position/identity/kind")
        if len(canonical(rec)) > MAX_LEAF_BYTES:
            raise ProtocolError("trace leaf budget")
        kind = node["kind"]
        if kind == "source":
            output = _source_value(bp, request, rec["input"], authenticate)
            expected = ("ok", output, nodes[i+1]["node_id"])
        else:
            parent_output = records[node["parent"]]["output"]
            if canonical(rec["input"]) != canonical(parent_output):
                raise ProtocolError("parent input/output link")
            if kind == "add":
                _integer(rec["input"], -MAX_INTEGER, MAX_INTEGER - 1)
                expected = ("ok", rec["input"] + node["params"]["amount"], nodes[i+1]["node_id"])
            elif kind == "ge":
                _integer(rec["input"], -MAX_INTEGER, MAX_INTEGER)
                gate = rec["input"] >= node["params"]["threshold"]
                expected = ("ok", gate, nodes[-2 if gate else -1]["node_id"])
            else:
                if type(rec["input"]) is not bool:
                    raise ProtocolError("terminal Boolean input")
                selected = rec["input"] == node["params"]["when"]
                expected = ("ok" if selected else "skipped", rec["input"] if selected else None, None)
                if selected:
                    terminals.append(rec["input"])
        if canonical([rec["status"], rec["output"], rec["edge_taken"]]) != canonical(list(expected)):
            raise ProtocolError("transition or typed node semantics")
    if len(terminals) != 1 or type(gate) is not bool:
        raise ProtocolError("unique terminal")
    result_digest(trace["result"])
    expected_result = {"version": 1, "request_digest": rd, "snapshot_digest": request["snapshot_digest"], "terminal_action": "resolve", "outcome": terminals[0], "semantic_projection_digest": object_digest("QM_EXEC_SEMANTICS_V1", records)}
    if canonical(trace["result"]) != canonical(expected_result):
        raise ProtocolError("terminal/result link")
    return True


def trace_commitment(trace):
    context = context_digest(trace["context"])
    return merkle_root(context, [canonical(r) for r in trace["records"]])


def whole_trace_digest(trace):
    return object_digest("QM_EXEC_WHOLE_TRACE_V1", trace)


def make_example(count=4, value=7, run_id="run-a", runner_id="runner-a", measurement="00"*32):
    bp = make_blueprint(count)
    bpd = object_digest("QM_EXEC_BLUEPRINT_V1", bp)
    body = {"version": 1, "chain_id": "algorand-research", "market_id": "market-001", "request_id": "authorized-slot-001", "blueprint_digest": bpd, "authority": "source_a", "observed_at": 105, "value": value, "data": "archived-source-payload:" + "x"*256}
    snapshot = {"version": 1, "reports": [sign_test_source(body, test_keys()["source_a"])]}
    request = {"version": 1, "chain_id": body["chain_id"], "market_id": body["market_id"], "request_id": body["request_id"], "blueprint_digest": bpd, "snapshot_digest": object_digest("QM_EXEC_SNAPSHOT_V1", snapshot), "agreement_policy_digest": object_digest("QM_EXEC_POLICY_V1", AGREEMENT_POLICY)}
    trace = run(bp, request, snapshot, run_id, runner_id, measurement)
    return {"blueprint": bp, "request": request, "snapshot": snapshot, "trace": trace, "result": trace["result"], "trace_root": trace_commitment(trace), "result_digest": result_digest(trace["result"])}


def verify_snapshot_disclosure(snapshot, expected_digest):
    """Require every pinned source preimage, without inferring source truth.

    This is an availability/schema gate, not signature or transition validation.
    A wrong or forged but fully disclosed report is a semantic challenge case.
    """
    _keys(snapshot, ("version", "reports"))
    if type(snapshot["version"]) is not int or snapshot["version"] != 1 or type(snapshot["reports"]) is not list or len(snapshot["reports"]) != 1:
        raise ProtocolError("complete source snapshot disclosure required")
    report = snapshot["reports"][0]
    _keys(report, ("body", "signature"))
    _keys(report["body"], ("version", "chain_id", "market_id", "request_id", "blueprint_digest", "authority", "observed_at", "value", "data"))
    if type(report["signature"]) is not str or re.fullmatch(r"[0-9a-f]{512}", report["signature"]) is None:
        raise ProtocolError("complete source signature bytes required")
    if object_digest("QM_EXEC_SNAPSHOT_V1", snapshot) != expected_digest:
        raise ProtocolError("disclosed snapshot does not match request")
    return True


@dataclass
class RevealSession:
    """Bounded on-chain-data state machine, simulated with an ordered clock.

    Every committed leaf (including all source preimages) must be posted before
    reveal_deadline. The challenge window starts only after complete reveal.
    Clock progress and data persistence are ledger assumptions. No gateway is
    queried or presumed honest. Economic settlement is deliberately separate.
    """
    blueprint: dict
    request: dict
    context: dict
    root: str
    result: dict
    proposed_at: int = 0
    reveal_window: int = 10
    challenge_window: int = 10
    agreement_policy: dict | None = None
    records: dict[int, dict] = field(default_factory=dict, init=False)
    status: str = field(default="revealing", init=False)
    challenge_deadline: int | None = field(default=None, init=False)
    last_time: int = field(default=0, init=False)

    def __post_init__(self):
        validate_blueprint(self.blueprint)
        rd = request_digest(self.request)
        context_digest(self.context)
        result_digest(self.result)
        _hex(self.root)
        _integer(self.proposed_at)
        _integer(self.reveal_window, 1, 10000)
        _integer(self.challenge_window, 1, 10000)
        if self.proposed_at + self.reveal_window + self.challenge_window > MAX_INTEGER:
            raise ProtocolError("lifecycle deadlines exceed exact clock profile")
        self.agreement_policy = copy.deepcopy(AGREEMENT_POLICY if self.agreement_policy is None else self.agreement_policy)
        if self.request["agreement_policy_digest"] != agreement_policy_digest(self.agreement_policy):
            raise ProtocolError("proposal agreement policy mismatch")
        if self.context["request_digest"] != rd or self.context["snapshot_digest"] != self.request["snapshot_digest"] or self.result["request_digest"] != rd or self.result["snapshot_digest"] != self.request["snapshot_digest"] or self.request["blueprint_digest"] != object_digest("QM_EXEC_BLUEPRINT_V1", self.blueprint):
            raise ProtocolError("proposal context does not match immutable request")
        self.last_time = self.proposed_at
        self.blueprint, self.request, self.context, self.result = map(copy.deepcopy, (self.blueprint, self.request, self.context, self.result))

    @property
    def count(self):
        return len(self.blueprint["nodes"])

    @property
    def reveal_deadline(self):
        return self.proposed_at + self.reveal_window

    def _advance(self, now):
        _integer(now, self.last_time)
        self.last_time = now
        if self.status == "revealing" and now >= self.reveal_deadline:
            self.status = "unavailable"

    def reveal(self, index, payload, proof, now):
        self._advance(now)
        if self.status != "revealing" or index in self.records:
            raise ProtocolError("reveal not open or duplicate position")
        if not verify_inclusion(context_digest(self.context), self.count, index, payload, proof, self.root):
            raise ProtocolError("invalid reveal inclusion")
        rec = parse_canonical(payload)
        # Source preimages must be available before opening any challenge
        # window; a fabricated placeholder cannot satisfy this positive gate.
        if index == 0:
            if type(rec) is not dict or "input" not in rec:
                raise ProtocolError("source snapshot preimage omitted")
            verify_snapshot_disclosure(rec["input"], self.request["snapshot_digest"])
        # Other schema and all source/transition semantics remain challenge
        # checks. Complete bytes need not constitute a correct execution.
        self.records[index] = rec
        if len(self.records) == self.count:
            self.status = "challenging"
            self.challenge_deadline = now + self.challenge_window
        return self.status

    def revealed_trace(self):
        if len(self.records) != self.count:
            raise ProtocolError("incomplete reveal")
        return {"version": 1, "context": copy.deepcopy(self.context), "records": [copy.deepcopy(self.records[i]) for i in range(self.count)], "result": copy.deepcopy(self.result)}

    def challenge(self, bp, request, now):
        self._advance(now)
        if self.status != "challenging" or now >= self.challenge_deadline:
            raise ProtocolError("challenge window not open")
        if canonical(bp) != canonical(self.blueprint) or canonical(request) != canonical(self.request):
            raise ProtocolError("challenger supplied wrong immutable context")
        try:
            verify_trace(bp, request, self.revealed_trace(), agreement_policy=self.agreement_policy)
        except ProtocolError:
            self.status = "rejected"
            return True
        return False

    def challenge_inclusion(self, index, payload, proof, now):
        """Invalid challenger Merkle evidence is rejected, never a slashing fact."""
        self._advance(now)
        if self.status != "challenging" or now >= self.challenge_deadline:
            raise ProtocolError("challenge window not open")
        if not verify_inclusion(context_digest(self.context), self.count, index, payload, proof, self.root):
            return False
        # Membership alone says nothing about fraud; full semantics remain needed.
        return self.challenge(self.blueprint, self.request, now)

    def finalize(self, now):
        self._advance(now)
        if self.status == "challenging" and now >= self.challenge_deadline:
            self.status = "finalized"
        return self.status


def verify_local_fault(bp, request, context, root, index, payload, proof, parent_payload=None, parent_proof=None):
    """Two-membership deterministic fraud predicate, independent of full trace.

    Return False for invalid challenger evidence. Return True only for an
    authenticated local contradiction. Parent evidence is required for nonroot
    slots; the committed blueprint fixes which parent index to authenticate.
    Final result linkage / full semantic-projection hashing are separate checks.
    """
    try:
        nodes = validate_blueprint(bp)
        rd = request_digest(request)
        c = context_digest(context)
        if context['request_digest'] != rd or context['snapshot_digest'] != request['snapshot_digest'] or request['blueprint_digest'] != object_digest('QM_EXEC_BLUEPRINT_V1', bp):
            return False
        if not verify_inclusion(c,len(nodes),index,payload,proof,root):
            return False
        node=nodes[index]
        if node['parent'] is not None:
            parent=node['parent']
            if not verify_inclusion(c,len(nodes),parent,parent_payload,parent_proof,root):
                return False
        try:
            rec=parse_canonical(payload)
            _keys(rec, ('index','node_id','kind','status','input','output','edge_taken'))
            if type(rec['index']) is not int or rec['index'] != index or rec['node_id'] != node['node_id'] or rec['kind'] != node['kind']:
                return True
            kind=node['kind']
            if kind=='source':
                expected=['ok',_source_value(bp,request,rec['input']),nodes[1]['node_id']]
            else:
                par=parse_canonical(parent_payload)
                _keys(par, ('index','node_id','kind','status','input','output','edge_taken'))
                if canonical(rec['input']) != canonical(par['output']):
                    return True
                if kind=='add':
                    _integer(rec['input'],-MAX_INTEGER,MAX_INTEGER-1)
                    expected=['ok',rec['input']+node['params']['amount'],nodes[index+1]['node_id']]
                elif kind=='ge':
                    _integer(rec['input'],-MAX_INTEGER,MAX_INTEGER)
                    value=rec['input']>=node['params']['threshold']
                    expected=['ok',value,nodes[-2 if value else -1]['node_id']]
                else:
                    if type(rec['input']) is not bool:
                        return True
                    selected=rec['input']==node['params']['when']
                    expected=['ok' if selected else 'skipped',rec['input'] if selected else None,None]
            return canonical([rec['status'],rec['output'],rec['edge_taken']]) != canonical(expected)
        except (ProtocolError,KeyError,TypeError,IndexError):
            return True
    except (ProtocolError,KeyError,TypeError,IndexError):
        return False
