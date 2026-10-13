"""Adversarial threshold, registration, and attempt-state conformance tests."""
import copy
from dataclasses import replace
from fractions import Fraction
import hashlib
import hmac
import itertools
import unittest

from research.verified_execution import quorum as q
from research.verified_execution import quorum_experiments as e
from research.verified_execution import protocol as p
from research.verified_execution import quorum_integration as integration


class QuorumTests(unittest.TestCase):
    def test_real_wire_trace_to_receipt_certificate_and_reveal(self):
        vectors = {row["name"]: row for row in integration.cases()}
        honest = vectors["same_snapshot_independent_runs"]
        self.assertTrue(honest["certificate_accepted"])
        self.assertEqual(len(set(honest["trace_roots"])), 3)
        self.assertTrue(honest["truth_correct"])
        self.assertFalse(vectors["authentic_common_source_error"]["truth_correct"])
        self.assertFalse(vectors["fabricated_source_preimage"]["receipt_issued"])
        self.assertFalse(vectors["wrong_registered_measurement"]["receipt_issued"])
        self.assertFalse(vectors["one_trace_withheld"]["all_required_trace_gate_passed"])

    def test_distinct_receipts_share_only_result_digest(self):
        policy = e.committee()
        request = q.make_request(policy)
        result, receipts, auth = e.certificate(policy, request, True)
        self.assertEqual(q.request_digest(request), p.request_digest(request))
        self.assertEqual(q.result_digest(result), p.result_digest(result))
        self.assertEqual(len({q.digest("RECEIPT", x) for x in receipts}), 3)
        self.assertEqual(len({x["receipt"]["result_digest"] for x in receipts}), 1)
        self.assertTrue(q.verify_certificate(policy, request, result, receipts, auth))

    def test_adversarial_receipt_vectors(self):
        vectors = e.adversarial_vectors()
        self.assertGreaterEqual(len(vectors), 17)
        self.assertEqual(sum(x["accepted"] for x in vectors), 3)

    def test_malformed_authentic_receipts_do_not_bypass_schema(self):
        policy = e.committee()
        request = q.make_request(policy)
        result, receipts, auth = e.certificate(policy, request, True)
        for field, value in (("version", True), ("registration_epoch", True),
                             ("measurement", "x" * 64), ("trace_root", "A" * 64),
                             ("runner_id", ""), ("run_id", 1)):
            bad = copy.deepcopy(receipts)
            bad[0]["receipt"][field] = value
            bad[0]["test_mac"] = hmac.new(auth.keys["r0"], p.canonical(bad[0]["receipt"]), hashlib.sha256).hexdigest()
            self.assertFalse(q.verify_certificate(policy, request, result, bad, auth), field)
        for field, value in (("version", True), ("snapshot_digest", "x"), ("extra", 1)):
            self.assertFalse(q.verify_certificate(policy, {**request, field: value}, result, receipts, auth))
        self.assertFalse(q.verify_certificate(policy, request, {**result, "version": True}, receipts, auth))
        for bad in (None, {}, [{"receipt": None}], [None]):
            self.assertFalse(q.verify_certificate(policy, request, result, bad, auth))

    def test_honest_signer_refuses_equivocation(self):
        policy = e.committee()
        request, auth = q.make_request(policy), q.ReceiptHarness(policy)
        e.certificate(policy, request, True, auth=auth)
        with self.assertRaises(q.QuorumError):
            e.certificate(policy, request, False, auth=auth)

    def test_general_intersection_authenticity_liveness(self):
        # Enumerate independent set oracle, not implementation internals.
        for n in range(1, 7):
            for k in range(1, n + 1):
                policy = e.committee(n, k)
                ids = set(range(n))
                minimal = [set(c) for c in itertools.combinations(ids, k)]
                self.assertEqual(policy.min_intersection(), min(len(a & b) for a in minimal for b in minimal))
                for f in range(n + 1):
                    for bad in itertools.combinations(ids, f):
                        self.assertEqual(any(s <= set(bad) for s in minimal), f >= k)
                        self.assertEqual(any(s.isdisjoint(bad) for s in minimal), n - f >= k)

    def test_k_greater_than_faults_does_not_ensure_conflict_resistance(self):
        policy, auth = e.committee(), q.ReceiptHarness(e.committee())
        request = q.make_request(policy)
        yes, yr, _ = e.certificate(policy, request, True, ["r0", "r1", "r2"], auth, ("r0",))
        no, nr, _ = e.certificate(policy, request, False, ["r0", "r3", "r4"], auth, ("r0",))
        self.assertTrue(q.verify_certificate(policy, request, yes, yr, auth))
        self.assertTrue(q.verify_certificate(policy, request, no, nr, auth))
        self.assertEqual(policy.min_intersection(), 1)
        self.assertGreater(e.committee(5, 4).min_intersection(), 1)

    def test_domain_constraint_and_shared_dependency_cover(self):
        rows = e.dependency_covers()
        self.assertEqual([r["minimum_attack"]["cost"] for r in rows], [10, 1, 20, 1])
        self.assertEqual([r["minimum_intersection"] for r in rows], [1, 1, 1, 1])

    def test_key_aliases_cannot_expand_fixed_voting_set(self):
        policy = e.committee()
        aliases = (replace(policy.runners[0], voting_identity="operator-key"),
                   replace(policy.runners[1], voting_identity="operator-key")) + policy.runners[2:]
        with self.assertRaises(q.QuorumError):
            replace(policy, runners=aliases)
        # Multiple real identities of one operator must satisfy the independently
        # declared operator quorum requirement; counting keys is insufficient.
        same_operator = tuple(replace(r, operator="one-operator") for r in policy.runners)
        with self.assertRaises(q.QuorumError):
            q.QuorumPolicy(same_operator, 3, min_operators=2)

    def test_same_label_different_semantic_projection_diverges(self):
        policy = e.committee()
        request = q.make_request(policy)
        result, receipts, auth = e.certificate(policy, request, True)
        alternate, ar, _ = e.certificate(policy, request, True, ["r3"], auth, projection="77" * 32)
        self.assertNotEqual(q.result_digest(result), q.result_digest(alternate))
        self.assertFalse(q.verify_certificate(policy, request, result, receipts[:2] + ar, auth))


class AttemptTests(unittest.TestCase):
    def ledger(self, slots=1):
        return q.AttemptLedger("market-request", q.AttemptPolicy(slots, "first_slot" if slots == 1 else "all_majority"),
                               e.committee())

    def complete(self, ledger, slot, outcome, *, available=True):
        request = ledger.requests[slot]
        result, receipts, auth = e.certificate(ledger.quorum_policy, request, outcome)
        ledger.complete(slot, 20, result, receipts, auth, availability_gate=available)
        return auth

    def test_no_cherry_pick_among_preauthorized_attempts(self):
        ledger = self.ledger(3)
        for i, outcome in enumerate((False, False, True)):
            ledger.start(i, 20)
            self.complete(ledger, i, outcome)
        self.assertEqual(ledger.finalize(30), {"status": "resolve", "outcome": False})
        with self.assertRaises(q.QuorumError):
            ledger.finalize(31)

    def test_missing_required_attempt_cancels_even_with_favorable_majority(self):
        ledger = self.ledger(3)
        for i in (0, 1):
            ledger.start(i, 20)
            self.complete(ledger, i, True)
        with self.assertRaises(q.QuorumError):
            ledger.finalize(99)
        self.assertEqual(ledger.finalize(100)["status"], "cancel")

    def test_unauthorized_retry_restart_and_late_completion_blocked(self):
        ledger = self.ledger()
        with self.assertRaises(q.QuorumError):
            ledger.start(1, 10)
        ledger.start(0, 10)
        with self.assertRaises(q.QuorumError):
            ledger.start(0, 11)
        self.complete(ledger, 0, False)
        with self.assertRaises(q.QuorumError):
            self.complete(ledger, 0, True)
        with self.assertRaises(q.QuorumError):
            ledger.start(0, 100)
        self.assertFalse(ledger.finalize(100)["outcome"])

    def test_availability_and_selection_are_separate_gates(self):
        ledger = self.ledger()
        ledger.start(0, 10)
        with self.assertRaises(q.QuorumError):
            self.complete(ledger, 0, True, available=False)
        self.assertEqual(ledger.finalize(100)["status"], "cancel")

    def test_snapshot_and_slot_assignment_cannot_be_replayed(self):
        ledger = self.ledger(3)
        ledger.start(1, 10)
        result, receipts, auth = e.certificate(ledger.quorum_policy, ledger.requests[0], True)
        with self.assertRaises(q.QuorumError):
            ledger.complete(1, 20, result, receipts, auth, availability_gate=True)

    def test_revocation_after_publication_cancels_pending_result(self):
        ledger = self.ledger()
        ledger.start(0, 10)
        auth = self.complete(ledger, 0, True)
        auth.revoked_at["r0"] = 25
        self.assertEqual(ledger.finalize(30)["status"], "cancel")

    def test_abort_and_timeout_remain_visible_denominator(self):
        outputs = []
        for favorable in (True, False, False, False, False, False, False, False, False, False):
            ledger = self.ledger()
            ledger.start(0, 10)
            if favorable:
                self.complete(ledger, 0, favorable)
            else:
                ledger.abort(0, 20)
            outputs.append(ledger.finalize(30))
        accepted = [x for x in outputs if x["status"] == "resolve"]
        self.assertEqual(len(accepted) / len(outputs), 0.1)
        self.assertTrue(all(x["outcome"] for x in accepted))
        self.assertEqual(q.finalized_bounds(Fraction(1, 10), Fraction(1, 10))[1], 1)

    def test_hidden_nondeterministic_restarts_are_not_detected_by_ledger(self):
        # Deliberate accepted counterexample, preserved as a boundary test.
        hidden_outputs = [False] * 29 + [True]
        ledger = self.ledger()
        ledger.start(0, 10)
        self.complete(ledger, 0, next(x for x in hidden_outputs if x))
        self.assertTrue(ledger.finalize(30)["outcome"])
        self.assertEqual([e["event"] for e in ledger.events], ["authorize", "start", "complete", "finalize"])

    def test_exact_selection_formula_and_sharp_abort_bounds(self):
        self.assertAlmostEqual(float(q.selection_probability(Fraction(1, 10), 30)), 0.9576088417247838)
        for n in range(1, 8):
            for event in range(1 << n):
                for selected in range(1, 1 << n):
                    lower, upper = q.finalized_bounds(Fraction(event.bit_count(), n),
                                                      Fraction(selected.bit_count(), n))
                    conditional = Fraction((event & selected).bit_count(), selected.bit_count())
                    self.assertLessEqual(lower, conditional)
                    self.assertLessEqual(conditional, upper)

    def test_fixed_seed_reexecution_is_identical_but_abort_still_possible(self):
        request = q.make_request(e.committee())
        for seed in (b"beacon-1", b"beacon-2", b"beacon-3"):
            self.assertEqual(len({q.seeded_bit(request, seed) for _ in range(30)}), 1)
        ledger = self.ledger()
        ledger.start(0, 10)
        ledger.abort(0, 20)
        self.assertEqual(ledger.finalize(30)["status"], "cancel")

    def test_monotone_clock_and_authorization_snapshots(self):
        ledger = self.ledger()
        original = q.request_digest(ledger.requests[0])
        request_alias = ledger.requests
        request_alias[0]["snapshot_digest"] = "ff" * 32
        self.assertEqual(q.request_digest(ledger.requests[0]), original)
        ledger.start(0, 10)
        self.complete(ledger, 0, False)
        ledger.results[0] = True
        with self.assertRaises(q.QuorumError):
            ledger.finalize(19)
        self.assertFalse(ledger.finalize(30)["outcome"])


if __name__ == "__main__":
    unittest.main()
