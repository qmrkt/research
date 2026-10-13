"""Executable, deliberately small trust-explicit blueprint protocol.

This research profile executes authenticated Boolean reports followed by explicit
quorum-gated submit/cancel/defer terminals. It is not the product interpreter.
Only Python's standard library is required. See BLUEPRINT_PROTOCOL.md for the
normative profile, assumptions, proof boundaries, and reproduction commands.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROFILE = "question.blueprint.boolean.v1"
TRACE_VERSION = "question.trace.v1"
EVIDENCE_VERSION = "question.evidence.v1"
REPORT_TYPES = {"api_fetch", "market_evidence", "llm_judge", "human_judge"}
TERMINAL_TYPES = {"submit_result", "cancel_market", "defer_resolution"}
MAX_CANONICAL_BYTES = 262144
MAX_SAFE_INTEGER = 2**53 - 1
_SHA256_DER = bytes.fromhex("3031300d060960864801650304020105000420")


class ProtocolError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    """ASCII-only JSON, sorted object keys, no whitespace/floats/duplicate keys.

    Restricting the data model avoids cross-language number and Unicode
    normalization ambiguity; this is a specified profile, not a claim to JCS.
    """
    def check(x: Any) -> None:
        if x is None or isinstance(x, bool):
            return
        if isinstance(x, int):
            if abs(x) > MAX_SAFE_INTEGER:
                raise ProtocolError("integer outside canonical profile")
        elif isinstance(x, str):
            if not x.isascii():
                raise ProtocolError("non-ASCII string outside canonical profile")
        elif isinstance(x, list):
            for item in x:
                check(item)
        elif isinstance(x, dict):
            for key, item in x.items():
                if not isinstance(key, str):
                    raise ProtocolError("non-string object key")
                check(key)
                check(item)
        else:
            raise ProtocolError("unsupported canonical value")
    check(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(raw) > MAX_CANONICAL_BYTES:
        raise ProtocolError("canonical byte budget exceeded")
    return raw


def parse_canonical(raw: bytes) -> Any:
    if len(raw) > MAX_CANONICAL_BYTES:
        raise ProtocolError("canonical byte budget exceeded")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ProtocolError("duplicate JSON key")
            result[k] = v
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid JSON") from exc
    if canonical_bytes(value) != raw:
        raise ProtocolError("noncanonical encoding")
    return value


def digest(domain: str, value: Any) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\x00" + canonical_bytes(value)).hexdigest()


def same_json(left: Any, right: Any) -> bool:
    """JSON type-aware equality: Python otherwise considers False equal to 0."""
    return canonical_bytes(left) == canonical_bytes(right)


def evidence_root(evidence: dict) -> str:
    return digest(EVIDENCE_VERSION, evidence)


def trace_root(trace: dict) -> str:
    return digest(TRACE_VERSION, trace)


def test_keys() -> dict:
    return json.loads((Path(__file__).parent / "fixtures" / "TEST_ONLY_RSA_KEYS.json").read_text())["keys"]


def public_key(key: dict) -> dict:
    return {"n": key["n"], "e": key["e"]}


def _emsa(message: bytes, length: int) -> bytes:
    data = _SHA256_DER + hashlib.sha256(message).digest()
    if length < len(data) + 11:
        raise ProtocolError("RSA modulus too short")
    return b"\x00\x01" + b"\xff" * (length - len(data) - 3) + b"\x00" + data


def sign_test_evidence(body: dict, key: dict) -> dict:
    """Fixture signer only: public private keys; no production/side-channel claim."""
    n, d = int(key["n"], 16), int(key["d"], 16)
    length = (n.bit_length() + 7) // 8
    message = EVIDENCE_VERSION.encode() + b"\x00" + canonical_bytes(body)
    encoded = int.from_bytes(_emsa(message, length), "big")
    signature = pow(encoded, d, n).to_bytes(length, "big").hex()
    return {"body": copy.deepcopy(body), "signature": signature}


def authentic(evidence: dict, key: dict) -> bool:
    """Strict RSASSA-PKCS1-v1_5/SHA-256 verification (RFC 8017 sections 8.2/9.2)."""
    try:
        if set(evidence) != {"body", "signature"} or set(key) != {"n", "e"}:
            return False
        n, e = int(key["n"], 16), key["e"]
        if n.bit_length() != 2048 or e != 65537:
            return False
        length = (n.bit_length() + 7) // 8
        sig = bytes.fromhex(evidence["signature"])
        if len(sig) != length or int.from_bytes(sig, "big") >= n:
            return False
        actual = pow(int.from_bytes(sig, "big"), e, n).to_bytes(length, "big")
        message = EVIDENCE_VERSION.encode() + b"\x00" + canonical_bytes(evidence["body"])
        return actual == _emsa(message, length)
    except (ValueError, KeyError, TypeError, OverflowError):
        return False


def make_blueprint(n: int = 3, max_runs: int = 1, report_type: str = "api_fetch") -> dict:
    if n not in (1, 3):
        raise ProtocolError("worked constructors support one or three sources")
    keys = test_keys()
    names = list(sorted(keys))[:n]
    request = {"event": "binary-event-at-fixed-time", "extraction": "Boolean value"}
    if report_type == "llm_judge":
        request.update(model="fixture-model-v1", prompt="Return the Boolean judgment.", temperature_milli=0)
    if report_type == "human_judge":
        request.update(panel="fixture-panel", rule="Signed Boolean judgment")
    nodes = [{"id": name, "type": report_type, "parents": [], "params": {
        "authority": name, "public_key": public_key(keys[name]), "request": request,
    }} for name in names]
    for ident, kind, when in (("submit", "submit_result", "has_quorum"),
                              ("cancel", "cancel_market", "no_quorum_final"),
                              ("defer", "defer_resolution", "no_quorum_retry")):
        nodes.append({"id": ident, "type": kind, "parents": names,
                      "params": {"when": when, "threshold": n // 2 + 1}})
    return {"profile": PROFILE, "blueprint_version": 1, "event_id": "event-001",
            "source_window": 10, "availability_window": 5, "retry_delay": 20,
            "max_runs": max_runs, "max_nodes": 16, "nodes": nodes}


def validate_blueprint(bp: dict) -> list[dict]:
    canonical_bytes(bp)
    required = {"profile", "blueprint_version", "event_id", "source_window", "availability_window",
                "retry_delay", "max_runs", "max_nodes", "nodes"}
    if set(bp) != required or bp["profile"] != PROFILE or type(bp["blueprint_version"]) is not int or bp["blueprint_version"] != 1:
        raise ProtocolError("unknown blueprint schema/version")
    for k in ("source_window", "availability_window", "retry_delay", "max_runs", "max_nodes"):
        if type(bp[k]) is not int or bp[k] <= 0:
            raise ProtocolError("positive integer budget required")
    if bp["retry_delay"] < bp["source_window"] + bp["availability_window"]:
        raise ProtocolError("retry starts before availability deadline")
    if bp["max_runs"] > 8 or bp["max_nodes"] > 16 or not 4 <= len(bp["nodes"]) <= bp["max_nodes"]:
        raise ProtocolError("profile run/node budget exceeded")
    ids = [n["id"] for n in bp["nodes"]]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise ProtocolError("duplicate/empty node identifier")
    reports, terminals = [], []
    for node in bp["nodes"]:
        if set(node) != {"id", "type", "parents", "params"}:
            raise ProtocolError("unknown node fields")
        if len(set(node["parents"])) != len(node["parents"]) or not set(node["parents"]) <= set(ids):
            raise ProtocolError("invalid parent references")
        if node["type"] in REPORT_TYPES:
            if node["parents"] or set(node["params"]) != {"authority", "public_key", "request"}:
                raise ProtocolError("report nodes must be parameterized roots")
            if node["params"]["authority"] != node["id"]:
                raise ProtocolError("this profile binds one node to each authority identifier")
            key = node["params"]["public_key"]
            if set(key) != {"n", "e"} or int(key["n"], 16).bit_length() != 2048 or key["e"] != 65537:
                raise ProtocolError("unsupported authority key")
            reports.append(node)
        elif node["type"] in TERMINAL_TYPES:
            if set(node["params"]) != {"when", "threshold"}:
                raise ProtocolError("unknown terminal parameters")
            terminals.append(node)
        else:
            raise ProtocolError("node type outside executable profile")
    names = {n["id"] for n in reports}
    authorities = [n["params"]["authority"] for n in reports]
    # Identity is the mathematical public key, not its textual hex spelling.
    # Case, leading zeros or another accepted integer encoding cannot create
    # another independently controlled vote from the same signing authority.
    keys = [(int(n["params"]["public_key"]["n"], 16), n["params"]["public_key"]["e"])
            for n in reports]
    if len(set(authorities)) != len(reports) or len(set(keys)) != len(reports):
        raise ProtocolError("duplicate source authority/key cannot count twice")
    if len(terminals) != 3 or {n["type"] for n in terminals} != TERMINAL_TYPES:
        raise ProtocolError("exactly one of each terminal declaration required")
    thresholds = {n["params"]["threshold"] for n in terminals}
    if len(thresholds) != 1 or type(next(iter(thresholds))) is not int:
        raise ProtocolError("inconsistent quorum threshold")
    threshold = next(iter(thresholds))
    if not len(reports) // 2 < threshold <= len(reports):
        raise ProtocolError("strict-majority threshold required")
    conditions = {"submit_result": "has_quorum", "cancel_market": "no_quorum_final",
                  "defer_resolution": "no_quorum_retry"}
    for node in terminals:
        if set(node["parents"]) != names or node["parents"] != sorted(names):
            raise ProtocolError("terminal join must include every distinct source")
        if node["params"]["when"] != conditions[node["type"]]:
            raise ProtocolError("terminal condition/type mismatch")
    # This profile's edges are report -> terminal only. No internal retry edges.
    return sorted(reports, key=lambda n: n["id"]) + sorted(terminals, key=lambda n: n["id"])


@dataclass
class PublicationLog:
    """Ideal append-only, publicly available publication layer with trusted time.

    A real deployment needs a data-availability implementation or an explicitly
    trusted checker for this abstraction. A content hash by itself is insufficient.
    The first published source slot is binding; later records cannot replace it.
    """
    blobs: dict[str, tuple[int, bytes]] = field(default_factory=dict)
    slots: dict[tuple[str, int, str], str] = field(default_factory=dict)
    authority_keys: dict[str, dict] = field(default_factory=dict)

    def publish(self, domain: str, value: dict, at: int) -> str:
        if type(at) is not int or at < 0:
            raise ProtocolError("publication time must be a nonnegative ledger integer")
        root = digest(domain, value)
        if root not in self.blobs:
            self.blobs[root] = (at, canonical_bytes(value))
        return root

    def publish_evidence(self, evidence: dict, at: int) -> str:
        body = evidence["body"]
        # Arbitrary uploaded bytes cannot reserve somebody else's source slot.
        key = self.authority_keys.get(body["authority"])
        if key is None or not authentic(evidence, key):
            raise ProtocolError("unauthenticated source cannot occupy a report slot")
        if body["node_id"] != body["authority"]:
            raise ProtocolError("authority/node slot mismatch")
        if type(body["observed_at"]) is not int or body["observed_at"] > at:
            raise ProtocolError("report claims an observation after its publication")
        root = self.publish(EVIDENCE_VERSION, evidence, at)
        slot = (body["market_id"], body["run_id"], body["node_id"])
        self.slots.setdefault(slot, root)
        return root

    def get(self, root: str, deadline: int) -> dict:
        if root not in self.blobs or self.blobs[root][0] > deadline:
            raise ProtocolError("blob unavailable by deadline")
        return parse_canonical(self.blobs[root][1])

    def source_ref(self, market_id: str, run_id: int, node_id: str, deadline: int) -> str | None:
        root = self.slots.get((market_id, run_id, node_id))
        if root is None or root not in self.blobs or self.blobs[root][0] > deadline:
            return None
        return root


def report_body(bp: dict, node: dict, market_id: str, run_id: int, start: int, value: bool) -> dict:
    return {"schema": EVIDENCE_VERSION, "blueprint_root": digest(PROFILE, bp),
            "market_id": market_id, "event_id": bp["event_id"], "run_id": run_id,
            "node_id": node["id"], "report_type": node["type"],
            "authority": node["params"]["authority"],
            "request_root": digest("question.request.v1", node["params"]["request"]),
            "observed_at": start + 1, "value": value}


def quorum_value(values: list[bool | None], threshold: int) -> bool | None:
    # Identity checks deliberately distinguish False from None and integer zero.
    for outcome in (False, True):
        if sum(x is outcome for x in values) >= threshold:
            return outcome
    return None


def execute(bp: dict, market_id: str, run_id: int, start: int, log: PublicationLog,
            previous_trace: dict | None = None) -> dict:
    """Runner. Authenticity and publication are enforced separately by verify()."""
    ordered = validate_blueprint(bp)
    if type(run_id) is not int or not 1 <= run_id <= bp["max_runs"]:
        raise ProtocolError("run budget exceeded")
    if (run_id == 1) != (previous_trace is None):
        raise ProtocolError("retry requires its prior run")
    if previous_trace is not None:
        if previous_trace["terminal"]["action"] != "defer" or previous_trace["run_id"] + 1 != run_id:
            raise ProtocolError("only deferred runs may restart")
        if start != previous_trace["terminal"]["next_start"]:
            raise ProtocolError("retry must use fixed not-before anchor")
    steps, outputs = [], {}
    for index, node in enumerate(ordered):
        if node["type"] in REPORT_TYPES:
            inp = {"request": node["params"]["request"], "source_deadline": start + bp["source_window"]}
            ref = log.source_ref(market_id, run_id, node["id"], inp["source_deadline"])
            if ref is None:
                output, status, refs = {"value": None}, "unavailable", []
            else:
                evidence = log.get(ref, inp["source_deadline"])
                output, status, refs = {"value": evidence["body"]["value"]}, "reported", [ref]
        else:
            inp = {name: outputs[name] for name in node["parents"]}
            winner = quorum_value([x["value"] for x in inp.values()], node["params"]["threshold"])
            action = "submit_result" if winner is not None else (
                "defer_resolution" if run_id < bp["max_runs"] else "cancel_market")
            status, refs = ("success" if node["type"] == action else "skipped"), []
            output = {}
            if status == "success":
                output = {"action": {"submit_result": "resolve", "defer_resolution": "defer",
                                      "cancel_market": "cancel"}[action]}
                if action == "submit_result":
                    output["outcome"] = winner
                elif action == "defer_resolution":
                    output["next_start"] = start + bp["retry_delay"]
        outputs[node["id"]] = output
        steps.append({"step_index": index, "node_id": node["id"], "node_type": node["type"],
                      "input": inp, "output": output, "status": status, "evidence_refs": refs})
    terminal = next(x["output"] for x in steps if x["status"] == "success")
    return {"trace_version": TRACE_VERSION, "blueprint_root": digest(PROFILE, bp),
            "blueprint_version": bp["blueprint_version"], "market_id": market_id,
            "event_id": bp["event_id"], "run_id": run_id, "started_at": start,
            "source_deadline": start + bp["source_window"],
            "availability_deadline": start + bp["source_window"] + bp["availability_window"],
            "previous_trace_root": None if previous_trace is None else trace_root(previous_trace),
            "steps": steps, "terminal": terminal}


def check_consistency(bp: dict, trace: dict, evidence: dict[str, dict],
                      expected_market: str, previous_trace: dict | None = None) -> list[str]:
    """Independent verifier; never invokes execute and deliberately ignores signatures.

    It checks graph, bindings, input/output snapshots, type semantics, joins,
    terminal selection, budgets and run chaining. Fabricated but coherent inputs
    can satisfy this function, which is why authenticity is a separate gate.
    """
    errors = []
    try:
        ordered = validate_blueprint(bp)
        if set(trace) != {"trace_version", "blueprint_root", "blueprint_version", "market_id", "event_id",
                          "run_id", "started_at", "source_deadline", "availability_deadline",
                          "previous_trace_root", "steps", "terminal"}:
            raise ProtocolError("unknown trace fields")
        if trace["trace_version"] != TRACE_VERSION or trace["blueprint_root"] != digest(PROFILE, bp):
            raise ProtocolError("blueprint/trace commitment mismatch")
        if trace["market_id"] != expected_market or trace["event_id"] != bp["event_id"]:
            raise ProtocolError("market/event replay")
        if type(trace["blueprint_version"]) is not int or trace["blueprint_version"] != bp["blueprint_version"]:
            raise ProtocolError("blueprint version mismatch")
        run, start = trace["run_id"], trace["started_at"]
        if type(run) is not int or type(start) is not int or start < 0 or not 1 <= run <= bp["max_runs"]:
            raise ProtocolError("invalid run/time budget")
        if trace["source_deadline"] != start + bp["source_window"] or trace["availability_deadline"] != start + bp["source_window"] + bp["availability_window"]:
            raise ProtocolError("deadline mismatch")
        if run == 1:
            if previous_trace is not None or trace["previous_trace_root"] is not None:
                raise ProtocolError("unexpected parent run")
        elif previous_trace is None or previous_trace["run_id"] != run - 1 or previous_trace["market_id"] != expected_market or previous_trace["blueprint_root"] != trace["blueprint_root"] or previous_trace["terminal"] != {"action": "defer", "next_start": start} or trace["previous_trace_root"] != trace_root(previous_trace):
            raise ProtocolError("invalid cross-run retry")
        if len(trace["steps"]) != len(ordered):
            raise ProtocolError("incomplete/extra trace steps")
        values, terminals = {}, []
        for index, (node, step) in enumerate(zip(ordered, trace["steps"])):
            if set(step) != {"step_index", "node_id", "node_type", "input", "output", "status", "evidence_refs"}:
                raise ProtocolError("unknown step fields")
            if type(step["step_index"]) is not int or step["step_index"] != index or step["node_id"] != node["id"] or step["node_type"] != node["type"]:
                raise ProtocolError("step order/type/identity mismatch")
            if node["type"] in REPORT_TYPES:
                expected_in = {"request": node["params"]["request"], "source_deadline": trace["source_deadline"]}
                if not same_json(step["input"], expected_in):
                    raise ProtocolError("source input mismatch")
                if step["status"] == "unavailable":
                    if step["output"] != {"value": None} or step["evidence_refs"]:
                        raise ProtocolError("unavailable source carries a vote")
                    value = None
                elif step["status"] == "reported":
                    if len(step["evidence_refs"]) != 1:
                        raise ProtocolError("one report reference required")
                    root = step["evidence_refs"][0]
                    obj = evidence[root]
                    if evidence_root(obj) != root:
                        raise ProtocolError("evidence content hash mismatch")
                    body = obj["body"]
                    if type(body["value"]) is not bool or type(body["observed_at"]) is not int:
                        raise ProtocolError("invalid report type")
                    expected_body = report_body(bp, node, expected_market, run, start, body["value"])
                    expected_body["observed_at"] = body["observed_at"]
                    if not same_json(body, expected_body) or not start <= body["observed_at"] <= trace["source_deadline"]:
                        raise ProtocolError("report binding/time mismatch")
                    if not same_json(step["output"], {"value": body["value"]}):
                        raise ProtocolError("source output differs from evidence")
                    value = body["value"]
                else:
                    raise ProtocolError("invalid source status")
                values[node["id"]] = {"value": value}
            else:
                inputs = {parent: values[parent] for parent in node["parents"]}
                if not same_json(step["input"], inputs) or step["evidence_refs"]:
                    raise ProtocolError("join inputs/references mismatch")
                counts = {False: 0, True: 0}
                for parent in node["parents"]:
                    value = values[parent]["value"]
                    if value is not None:
                        counts[value] += 1
                qualifying = [v for v in (False, True) if counts[v] >= node["params"]["threshold"]]
                expected_type = "submit_result" if qualifying else ("defer_resolution" if run < bp["max_runs"] else "cancel_market")
                active = node["type"] == expected_type
                if not active:
                    if step["status"] != "skipped" or step["output"] != {}:
                        raise ProtocolError("inactive terminal executed")
                else:
                    output = ({"action": "resolve", "outcome": qualifying[0]} if qualifying else
                              {"action": "defer", "next_start": start + bp["retry_delay"]} if run < bp["max_runs"] else
                              {"action": "cancel"})
                    if step["status"] != "success" or not same_json(step["output"], output):
                        raise ProtocolError("wrong terminal decision")
                    terminals.append(output)
        if len(terminals) != 1 or not same_json(trace["terminal"], terminals[0]):
            raise ProtocolError("conflicting/missing terminal")
        canonical_bytes(trace)
    except (ProtocolError, KeyError, TypeError, ValueError, IndexError) as exc:
        errors.append(str(exc))
    return errors


def verify(bp: dict, proposal_root: str, expected_market: str, log: PublicationLog,
           at: int, expected_start: int, previous_traces: list[dict] | None = None) -> dict:
    """Deadline gate. Missing data => blocked proposal, never a guessed outcome.

    expected_start and at are ledger time, not proposer-supplied clocks. A caller
    must subsequently apply the market's declared hard-timeout cancellation.
    """
    previous_traces = previous_traces or []
    if type(at) is not int or type(expected_start) is not int or expected_start < 0:
        return {"status": "blocked", "reason": "invalid authoritative clock input"}
    deadline = expected_start + bp["source_window"] + bp["availability_window"]
    if at < deadline:
        return {"status": "pending", "reason": "availability deadline not reached"}
    try:
        trace = log.get(proposal_root, deadline)
        if trace_root(trace) != proposal_root or trace["started_at"] != expected_start:
            raise ProtocolError("trace root/start mismatch")
        if trace["run_id"] != len(previous_traces) + 1:
            raise ProtocolError("complete prior-run chain required")
        for i, prior in enumerate(previous_traces):
            prior_verdict = verify(bp, trace_root(prior), expected_market, log,
                                   prior["availability_deadline"], prior["started_at"], previous_traces[:i])
            if prior_verdict.get("status") != "defer":
                raise ProtocolError("prior run not verified deferred")
        evidence = {}
        for node, step in zip(validate_blueprint(bp), trace["steps"]):
            if node["type"] not in REPORT_TYPES:
                continue
            for ref in step["evidence_refs"]:
                obj = log.get(ref, trace["source_deadline"])
                if not authentic(obj, node["params"]["public_key"]):
                    raise ProtocolError("source signature invalid")
                evidence[ref] = obj
            expected_ref = log.source_ref(expected_market, trace["run_id"], node["id"], trace["source_deadline"])
            if step["evidence_refs"] != ([] if expected_ref is None else [expected_ref]):
                raise ProtocolError("report omission/substitution relative to public slot")
        problems = check_consistency(bp, trace, evidence, expected_market,
                                     previous_traces[-1] if previous_traces else None)
        if problems:
            raise ProtocolError("; ".join(problems))
        return {"status": trace["terminal"]["action"], "terminal": trace["terminal"],
                "trace_root": proposal_root, "verified_at": deadline}
    except (ProtocolError, KeyError, TypeError, ValueError, IndexError) as exc:
        return {"status": "blocked", "reason": str(exc)}


def hard_timeout(status: str, at: int, market_deadline: int) -> str:
    if status in {"resolve", "cancel"}:
        return status
    return "cancel_timeout" if at >= market_deadline else status


@dataclass
class ResolutionSession:
    """Market envelope: fixed clock anchors, verified retries, terminal finality.

    The hard deadline is one clock unit after the last possible availability
    deadline. Thus a valid last-run decision has a nonambiguous finalization
    point before timeout takes precedence. No caller may restart a settled market.
    """
    blueprint: dict
    market_id: str
    initial_start: int
    accepted_deferred_traces: list[dict] = field(default_factory=list)
    terminal: dict | None = None

    def __post_init__(self):
        validate_blueprint(self.blueprint)
        self.blueprint = copy.deepcopy(self.blueprint)
        if type(self.initial_start) is not int or self.initial_start < 0:
            raise ProtocolError("invalid market start")

    @property
    def market_deadline(self):
        bp = self.blueprint
        return self.initial_start + (bp["max_runs"]-1)*bp["retry_delay"] + bp["source_window"] + bp["availability_window"] + 1

    def advance(self, proposal_root: str, at: int, log: PublicationLog) -> dict:
        if self.terminal is not None:
            raise ProtocolError("market is already terminal")
        if at >= self.market_deadline:
            self.terminal = {"action": "cancel_timeout"}
            return {"status": "cancel_timeout", "terminal": self.terminal}
        start = self.initial_start + len(self.accepted_deferred_traces)*self.blueprint["retry_delay"]
        result = verify(self.blueprint, proposal_root, self.market_id, log, at, start, self.accepted_deferred_traces)
        if result["status"] == "defer":
            self.accepted_deferred_traces.append(log.get(proposal_root, at))
        elif result["status"] in {"resolve", "cancel"}:
            self.terminal = copy.deepcopy(result["terminal"])
        return result

    def expire(self, at: int) -> dict:
        if self.terminal is not None:
            return copy.deepcopy(self.terminal)
        if at < self.market_deadline:
            raise ProtocolError("market deadline not reached")
        self.terminal = {"action": "cancel_timeout"}
        return copy.deepcopy(self.terminal)


def fixture_run(bp: dict, values: list[bool | None], market_id: str = "market-001",
                run_id: int = 1, start: int = 100, log: PublicationLog | None = None,
                previous_trace: dict | None = None, signed_cache: dict | None = None) -> tuple[dict, PublicationLog]:
    keys = test_keys()
    log = log or PublicationLog(authority_keys={name: public_key(key) for name, key in keys.items()})
    reports = [n for n in validate_blueprint(bp) if n["type"] in REPORT_TYPES]
    if len(values) != len(reports):
        raise ProtocolError("one supplied value per source")
    for node, value in zip(reports, values):
        if value is None:
            continue
        body = report_body(bp, node, market_id, run_id, start, value)
        cache_key = canonical_bytes(body)
        obj = signed_cache.get(cache_key) if signed_cache is not None else None
        if obj is None:
            obj = sign_test_evidence(body, keys[node["params"]["authority"]])
            if signed_cache is not None:
                signed_cache[cache_key] = obj
        log.publish_evidence(obj, start + 2)
    trace = execute(bp, market_id, run_id, start, log, previous_trace)
    log.publish(TRACE_VERSION, trace, trace["source_deadline"] + 1)
    return trace, log
