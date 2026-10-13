"""Executable quorum and attempt-policy model; not a TEE implementation.

The receipt authenticator is HMAC with public test secrets held by the harness.
It tests authentication and state-machine boundaries, not public signatures or
hardware attestation. Request/result encodings come from the wire prototype.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
import copy
import hashlib
import hmac
import itertools
from typing import Iterable

from .protocol import (canonical, object_digest, request_digest as wire_request_digest,
                       result_digest as wire_result_digest, context_digest, ProtocolError)
from . import protocol as wire


class QuorumError(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return canonical(value)


def digest(domain: str, value: object) -> str:
    return object_digest(domain, value)


@dataclass(frozen=True)
class Runner:
    runner_id: str
    vendor: str
    operator: str
    registrar: str
    build: str
    voting_identity: str = ""
    registration_epoch: int = 1
    valid_from: int = 0
    valid_until: int = 1000
    measurement: str = ""

    @property
    def expected_measurement(self) -> str:
        return self.measurement or hashlib.sha256(("binary:" + self.runner_id).encode()).hexdigest()


@dataclass(frozen=True)
class QuorumPolicy:
    runners: tuple[Runner, ...]
    threshold: int
    min_vendors: int = 1
    min_operators: int = 1
    min_registrars: int = 1

    def __post_init__(self) -> None:
        ids = [r.runner_id for r in self.runners]
        identities = [r.voting_identity or r.runner_id for r in self.runners]
        if type(self.threshold) is not int or len(set(ids)) != len(ids) or not 1 <= self.threshold <= len(ids):
            raise QuorumError("invalid fixed committee or threshold")
        if len(set(identities)) != len(identities):
            raise QuorumError("key aliases do not create voting identities")
        if any(not r.runner_id for r in self.runners):
            raise QuorumError("empty runner identity")
        for r in self.runners:
            if (type(r.registration_epoch) is not int or r.registration_epoch < 1
                    or type(r.valid_from) is not int or type(r.valid_until) is not int
                    or not 0 <= r.valid_from < r.valid_until):
                raise QuorumError("invalid registration interval or epoch")
        if any(type(x) is not int or x < 1 for x in (self.min_vendors, self.min_operators, self.min_registrars)):
            raise QuorumError("invalid domain constraint")
        if not self.accepts(ids):
            raise QuorumError("unsatisfiable domain policy")

    @property
    def policy_digest(self) -> str:
        return digest("QM_QUORUM_MODEL_POLICY_V1", {
            "runners": [asdict(r) for r in self.runners], "threshold": self.threshold,
            "min_vendors": self.min_vendors, "min_operators": self.min_operators,
            "min_registrars": self.min_registrars})

    def accepts(self, signer_ids: Iterable[str]) -> bool:
        ids = tuple(signer_ids)
        selected = [r for r in self.runners if r.runner_id in ids]
        return (len(ids) == len(set(ids)) == len(selected)
                and len(ids) >= self.threshold
                and len({r.vendor for r in selected}) >= self.min_vendors
                and len({r.operator for r in selected}) >= self.min_operators
                and len({r.registrar for r in selected}) >= self.min_registrars)

    def quorums(self) -> tuple[frozenset[str], ...]:
        """All accepted sets, including those larger than k (n <= 12 here)."""
        if len(self.runners) > 12:
            raise QuorumError("exhaustive research model supports at most 12 runners")
        ids = tuple(r.runner_id for r in self.runners)
        return tuple(frozenset(q) for size in range(self.threshold, len(ids) + 1)
                     for q in itertools.combinations(ids, size) if self.accepts(q))

    def min_intersection(self) -> int:
        qs = self.quorums()
        return min(len(a & b) for a in qs for b in qs)


def make_request(policy: QuorumPolicy, request_id: str = "request-1",
                 snapshot_digest: str = "22" * 32,
                 attempt_policy_digest: str = "33" * 32) -> dict:
    """Bind the fixed committee/selection policy through agreement_policy_digest."""
    agreement = agreement_digest(policy, attempt_policy_digest)
    return {"version": 1, "chain_id": "test-chain", "market_id": "test-market",
            "request_id": request_id, "blueprint_digest": "11" * 32,
            "snapshot_digest": snapshot_digest, "agreement_policy_digest": agreement}


def agreement_digest(policy: QuorumPolicy, attempt_policy_digest: str) -> str:
    return wire.agreement_policy_digest(agreement_policy(policy, attempt_policy_digest))


def agreement_policy(policy: QuorumPolicy, attempt_policy_digest: str) -> dict:
    return {**wire.AGREEMENT_POLICY,
        "quorum_policy_digest": policy.policy_digest,
        "attempt_policy_digest": attempt_policy_digest,
    }


def request_digest(request: dict) -> str:
    return wire_request_digest(request)


def make_result(request: dict, outcome: bool, projection: str = "44" * 32) -> dict:
    if type(outcome) is not bool:
        raise QuorumError("outcome must be Boolean")
    return {"version": 1, "request_digest": request_digest(request),
            "snapshot_digest": request["snapshot_digest"], "terminal_action": "resolve",
            "outcome": outcome, "semantic_projection_digest": projection}


def result_digest(result: dict) -> str:
    return wire_result_digest(result)


class ReceiptHarness:
    """Test authentication oracle with enforced honest one-vote-per-request state.

    A real adapter verifies asymmetric signatures and attested key registration.
    `faulty=True` models compromised signers and is never available to a verifier.
    """
    def __init__(self, policy: QuorumPolicy):
        self.policy = policy
        self.keys = {r.runner_id: hashlib.sha256(("PUBLIC TEST SECRET:" + r.runner_id).encode()).digest()
                     for r in policy.runners}
        self.votes: dict[tuple[str, str], str] = {}
        self.revoked_at: dict[str, int] = {}

    def issue(self, runner_id: str, request: dict, result: dict,
              run_id: str, trace_root: str, measurement: str,
              faulty: bool = False) -> dict:
        if runner_id not in self.keys:
            raise QuorumError("runner not assigned")
        if result["request_digest"] != request_digest(request):
            raise QuorumError("wrong request")
        rd = result_digest(result)
        key = runner_id, request_digest(request)
        if not faulty and key in self.votes and self.votes[key] != rd:
            raise QuorumError("honest runner refuses second result for request")
        if not faulty:
            self.votes[key] = rd
        body = {"version": 1, "request_digest": request_digest(request),
                "snapshot_digest": request["snapshot_digest"],
                "result_digest": rd, "runner_id": runner_id, "run_id": run_id,
                "trace_root": trace_root, "trace_cid": "sha256:" + trace_root,
                "measurement": measurement,
                "registration_epoch": next(r.registration_epoch for r in self.policy.runners
                                            if r.runner_id == runner_id)}
        mac = hmac.new(self.keys[runner_id], _canonical(body), hashlib.sha256).hexdigest()
        return {"receipt": body, "test_mac": mac}

    def verify(self, signed: dict) -> bool:
        try:
            body, mac = signed["receipt"], signed["test_mac"]
            runner_id = body["runner_id"]
            expected = hmac.new(self.keys[runner_id], _canonical(body), hashlib.sha256).hexdigest()
            return isinstance(mac, str) and hmac.compare_digest(expected, mac)
        except (KeyError, TypeError, ValueError):
            return False

    def issue_verified_trace(self, blueprint: dict, request: dict, trace: dict,
                             attempt_policy_digest: str = "33" * 32) -> dict:
        """Honest signer adapter: authenticate sources and verify complete semantics.

        The wire checker is independent of the trace producer. This adapter
        binds its passed result to a registered identity and per-run trace root.
        Availability remains the subsequent mandatory reveal gate.
        """
        policy = agreement_policy(self.policy, attempt_policy_digest)
        wire.verify_trace(blueprint, request, trace, agreement_policy=policy)
        context = trace["context"]
        runner = next((r for r in self.policy.runners if r.runner_id == context["runner_id"]), None)
        if runner is None or context["measurement"] != runner.expected_measurement:
            raise QuorumError("unassigned runner or measurement mismatch")
        return self.issue(context["runner_id"], request, trace["result"], context["run_id"],
                          wire.trace_commitment(trace), context["measurement"])


def verify_certificate(policy: QuorumPolicy, request: dict, result: dict,
                       receipts: list[dict], auth: ReceiptHarness,
                       now: int = 10, final_deadline: int = 100,
                       attempt_policy_digest: str = "33" * 32) -> bool:
    try:
        return _verify_certificate(policy, request, result, receipts, auth, now,
                                   final_deadline, attempt_policy_digest)
    except (ProtocolError, KeyError, TypeError, ValueError, AttributeError):
        return False


def _verify_certificate(policy: QuorumPolicy, request: dict, result: dict,
                        receipts: list[dict], auth: ReceiptHarness,
                        now: int, final_deadline: int, attempt_policy_digest: str) -> bool:
    """Check shared result and independent receipts; availability is a later gate."""
    request_digest(request)
    result_digest(result)
    if type(receipts) is not list or type(now) is not int or type(final_deadline) is not int:
        return False
    expected_fields = {"version", "request_digest", "snapshot_digest", "terminal_action",
                       "outcome", "semantic_projection_digest"}
    if (set(result) != expected_fields or result["version"] != 1
            or type(result["outcome"]) is not bool or result["terminal_action"] != "resolve"
            or result["request_digest"] != request_digest(request)
            or result["snapshot_digest"] != request["snapshot_digest"]
            or request["agreement_policy_digest"] != agreement_digest(policy, attempt_policy_digest)):
        return False
    ids = []
    for signed in receipts:
        if not auth.verify(signed):
            return False
        body = signed["receipt"]
        if set(signed) != {"receipt", "test_mac"}:
            return False
        context_digest({k: body[k] for k in ("request_digest", "snapshot_digest", "run_id",
                                            "runner_id", "measurement")})
        if (type(body["trace_root"]) is not str or len(body["trace_root"]) != 64
                or any(c not in "0123456789abcdef" for c in body["trace_root"])):
            return False
        fields = {"version", "request_digest", "snapshot_digest", "result_digest", "runner_id",
                  "run_id", "trace_root", "trace_cid", "measurement", "registration_epoch"}
        if (set(body) != fields or type(body["version"]) is not int or body["version"] != 1
                or type(body["registration_epoch"]) is not int or body["registration_epoch"] < 1
                or not body["run_id"]
                or body["request_digest"] != request_digest(request)
                or body["snapshot_digest"] != request["snapshot_digest"]
                or body["result_digest"] != result_digest(result)
                or body["trace_cid"] != "sha256:" + body["trace_root"]):
            return False
        runner = next((r for r in policy.runners if r.runner_id == body["runner_id"]), None)
        if (runner is None or body["registration_epoch"] != runner.registration_epoch
                or body["measurement"] != runner.expected_measurement
                or not runner.valid_from <= now < runner.valid_until
                or runner.valid_until < final_deadline
                or auth.revoked_at.get(runner.runner_id, runner.valid_until) <= now):
            return False
        ids.append(body["runner_id"])
    return policy.accepts(ids)


@dataclass(frozen=True)
class DependencyAttack:
    name: str
    compromises: frozenset[str]
    cost: int


def minimum_attack(policy: QuorumPolicy, attacks: tuple[DependencyAttack, ...]) -> dict:
    """Exact weighted dependency cover; costs are scenario units, not estimates."""
    found = []
    assigned = {r.runner_id for r in policy.runners}
    if any(type(a.cost) is not int or a.cost < 0 for a in attacks):
        raise QuorumError("attack costs must be nonnegative integer scenario units")
    for size in range(len(attacks) + 1):
        for choice in itertools.combinations(attacks, size):
            compromised = frozenset().union(*(x.compromises for x in choice)) & assigned
            if policy.accepts(compromised):
                found.append((sum(x.cost for x in choice), tuple(x.name for x in choice),
                              sorted(compromised)))
    if not found:
        return {"possible": False}
    cost, names, runners = min(found)
    return {"possible": True, "cost": cost, "attacks": list(names), "compromised": runners}


@dataclass(frozen=True)
class AttemptPolicy:
    slots: int = 1
    aggregation: str = "first_slot"
    deadline: int = 100
    deterministic_under_seed: bool = False

    def __post_init__(self) -> None:
        if type(self.slots) is not int or type(self.deadline) is not int or self.slots < 1 or self.deadline < 1:
            raise QuorumError("invalid attempt policy")
        if self.aggregation == "first_slot" and self.slots != 1:
            raise QuorumError("first_slot authorizes exactly one slot")
        if self.aggregation == "all_majority" and self.slots % 2 != 1:
            raise QuorumError("majority requires an odd fixed slot count")
        if self.aggregation not in ("first_slot", "all_majority"):
            raise QuorumError("unknown aggregation")

    @property
    def policy_digest(self) -> str:
        return digest("QM_ATTEMPT_MODEL_POLICY_V1", asdict(self))


class AttemptLedger:
    """Authoritative preauthorization, single completion, and abort-as-cancel.

    A published slot cannot be replaced. This does not see hidden invocations:
    deterministic_under_seed is a measured execution requirement, not a ledger
    guarantee. `availability_gate` is the separate protocol verifier's verdict.
    """
    def __init__(self, parent_id: str, policy: AttemptPolicy,
                 quorum_policy: QuorumPolicy, snapshot_digest: str = "22" * 32):
        self.parent_id, self.policy, self.quorum_policy = parent_id, policy, quorum_policy
        self._requests = [make_request(quorum_policy, f"{parent_id}/slot/{i}", snapshot_digest,
                                      policy.policy_digest) for i in range(policy.slots)]
        self._states = ["authorized"] * policy.slots
        self._results: list[bool | None] = [None] * policy.slots
        self.certificates: dict[int, tuple[dict, list[dict], ReceiptHarness]] = {}
        self.events = [{"event": "authorize", "slot": i,
                        "request_digest": request_digest(r)} for i, r in enumerate(self.requests)]
        self.closed = False
        self.last_time = 0

    @property
    def requests(self) -> list[dict]:
        return copy.deepcopy(self._requests)

    @property
    def states(self) -> list[str]:
        return list(self._states)

    @property
    def results(self) -> list[bool | None]:
        return list(self._results)

    def _advance(self, now: int) -> None:
        if type(now) is not int or now < self.last_time:
            raise QuorumError("ledger clock must advance monotonically")
        self.last_time = now

    def _guard(self, slot: int, now: int) -> None:
        self._advance(now)
        if type(slot) is not int or not 0 <= slot < self.policy.slots:
            raise QuorumError("unauthorized slot")
        if self.closed or now < 0 or now >= self.policy.deadline:
            raise QuorumError("closed or outside completion window")

    def start(self, slot: int, now: int) -> None:
        self._guard(slot, now)
        if self.states[slot] != "authorized":
            raise QuorumError("slot already started")
        self._states[slot] = "started"
        self.events.append({"event": "start", "slot": slot})

    def complete(self, slot: int, now: int, result: dict, receipts: list[dict],
                 auth: ReceiptHarness, *, availability_gate: bool) -> None:
        self._guard(slot, now)
        if self.states[slot] != "started":
            raise QuorumError("slot not started or already terminal")
        if not availability_gate:
            raise QuorumError("evidence publication gate not passed")
        if not verify_certificate(self.quorum_policy, self.requests[slot], result, receipts, auth,
                                  now, self.policy.deadline, self.policy.policy_digest):
            raise QuorumError("invalid result certificate")
        self._states[slot], self._results[slot] = "completed", result["outcome"]
        self.certificates[slot] = copy.deepcopy(result), copy.deepcopy(receipts), auth
        self.events.append({"event": "complete", "slot": slot,
                            "result_digest": result_digest(result)})

    def abort(self, slot: int, now: int) -> None:
        self._guard(slot, now)
        if self.states[slot] not in ("authorized", "started"):
            raise QuorumError("slot already terminal")
        self._states[slot] = "aborted"
        self.events.append({"event": "abort", "slot": slot})

    def finalize(self, now: int) -> dict:
        self._advance(now)
        if self.closed:
            raise QuorumError("request already finalized")
        certificate_revoked = any(not verify_certificate(
            self.quorum_policy, self.requests[i], result, receipts, auth, now,
            self.policy.deadline, self.policy.policy_digest)
            for i, (result, receipts, auth) in self.certificates.items())
        if certificate_revoked or any(s == "aborted" for s in self.states):
            status, outcome = "cancel", None
        elif all(s == "completed" for s in self.states):
            status = "resolve"
            outcome = sum(x is True for x in self.results) > self.policy.slots // 2
        elif now >= self.policy.deadline:
            status, outcome = "cancel", None
            self._states = [s if s == "completed" else "timed_out" for s in self.states]
        else:
            raise QuorumError("waiting for all required slots")
        self.closed = True
        self.events.append({"event": "finalize", "status": status, "outcome": outcome})
        return {"status": status, "outcome": outcome}


def selection_probability(p: Fraction, attempts: int) -> Fraction:
    if not 0 <= p <= 1 or attempts < 1:
        raise QuorumError("invalid probability or attempt count")
    return 1 - (1 - p) ** attempts


def finalized_bounds(p: Fraction, completion: Fraction) -> tuple[Fraction, Fraction]:
    """Sharp distribution-free binary selective-abort bounds for alpha > 0."""
    if not 0 <= p <= 1 or not 0 < completion <= 1:
        raise QuorumError("invalid baseline or completion probability")
    return max(Fraction(0), (p + completion - 1) / completion), min(Fraction(1), p / completion)


def seeded_bit(request: dict, seed: bytes, probability_tenths: int = 1) -> bool:
    """Deterministic toy inference. A real model needs a fixed exact inference spec.

    Reduction modulo ten has negligible (< 10/2^256), explicitly nonzero bias;
    this is a reproducibility example, not a new randomness protocol.
    """
    if not 0 <= probability_tenths <= 10:
        raise QuorumError("invalid toy probability")
    raw = hashlib.sha256(b"QM_TOY_SEEDED_EXECUTION_V1\0" + seed + bytes.fromhex(request_digest(request))).digest()
    return int.from_bytes(raw, "big") % 10 < probability_tenths
