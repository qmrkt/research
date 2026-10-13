"""Meaningful adversarial and metamorphic checks for the research protocol."""
import copy
from fractions import Fraction
import itertools
import json
import unittest

from research.resolution_trust import blueprint_protocol as p
from research.resolution_trust import blueprint_experiments as e


class BlueprintProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bp = p.make_blueprint()
        cls.cache = {}
        cls.trace, cls.log = p.fixture_run(cls.bp, [False, False, True], signed_cache=cls.cache)

    def test_all_report_vectors_match_independent_quorum_oracle(self):
        for n in (1, 3):
            bp = p.make_blueprint(n)
            for values in itertools.product((None, False, True), repeat=n):
                trace, log = p.fixture_run(bp, list(values), signed_cache=self.cache)
                verdict = p.verify(bp, p.trace_root(trace), "market-001", log, 115, 100)
                matching = [v for v in (False, True) if sum(x is v for x in values) > n/2]
                if matching:
                    self.assertEqual(verdict["terminal"], {"action": "resolve", "outcome": matching[0]})
                else:
                    self.assertEqual(verdict["status"], "cancel")

    def test_rehashed_tampering_and_fabrication(self):
        vectors = {v["name"]: v for v in e.attack_vectors()}
        valid = {"honest_trace", "authentic_common_error"}
        for name, vector in vectors.items():
            self.assertEqual(vector["gate"]["status"], "resolve" if name in valid else "blocked", name)
        forged = vectors["canonical_fabrication"]
        self.assertTrue(forged["consistency_pass"])
        self.assertEqual(forged["gate"]["reason"], "source signature invalid")
        self.assertTrue(vectors["authentic_common_error"]["consistency_pass"])
        self.assertTrue(vectors["authentic_common_error"]["gate"]["terminal"]["outcome"])

    def test_retry_binds_prior_verified_run_and_budget(self):
        bp = p.make_blueprint(max_runs=2)
        first, log = p.fixture_run(bp, [None, False, True])
        self.assertEqual(first["terminal"], {"action": "defer", "next_start": 120})
        second, log = p.fixture_run(bp, [False, False, True], run_id=2, start=120, log=log, previous_trace=first)
        result = p.verify(bp, p.trace_root(second), "market-001", log, 135, 120, [first])
        self.assertEqual(result["status"], "resolve")
        self.assertEqual(p.verify(bp, p.trace_root(second), "market-001", log, 135, 120)["status"], "blocked")
        with self.assertRaises(p.ProtocolError):
            p.execute(bp, "market-001", 2, 119, log, first)
        with self.assertRaises(p.ProtocolError):
            p.execute(bp, "market-001", 3, 140, log, second)
        bad_first = copy.deepcopy(first)
        bad_first["terminal"]["next_start"] = 121
        self.assertEqual(p.verify(bp, p.trace_root(second), "market-001", log, 135, 120, [bad_first])["status"], "blocked")
        # A valid final retry with no quorum cancels; it does not retry forever.
        empty, empty_log = p.fixture_run(bp, [None, None, None])
        final, empty_log = p.fixture_run(bp, [None, None, None], run_id=2, start=120,
                                         log=empty_log, previous_trace=empty)
        self.assertEqual(p.verify(bp, p.trace_root(final), "market-001", empty_log, 135, 120, [empty])["status"], "cancel")

    def test_dag_schema_and_authority_sybil_rejection(self):
        mutations = [lambda b: b["nodes"][0]["parents"].append("submit"),
                     lambda b: b["nodes"][1].update(id=b["nodes"][0]["id"]),
                     lambda b: b["nodes"][1]["params"].update(public_key=b["nodes"][0]["params"]["public_key"]),
                     lambda b: b["nodes"][-1]["params"].update(threshold=1),
                     lambda b: b["nodes"][-1].update(parents=["source_a"]),
                     lambda b: b.update(max_nodes=5),
                     lambda b: b.update(retry_delay=1),
                     lambda b: b["nodes"][0].update(type="arbitrary_python")]
        for mutate in mutations:
            bad = copy.deepcopy(self.bp)
            mutate(bad)
            with self.assertRaises(p.ProtocolError):
                p.validate_blueprint(bad)
        # Node serialization order does not alter the deterministic topological
        # order, though the immutable bytes deliberately have a different root.
        reordered = copy.deepcopy(self.bp)
        reordered["nodes"].reverse()
        self.assertEqual([x["id"] for x in p.validate_blueprint(self.bp)],
                         [x["id"] for x in p.validate_blueprint(reordered)])

    def test_canonical_encoding_and_complete_commitment(self):
        obj = {"z": [True, None, "x"], "a": 12}
        self.assertEqual(p.canonical_bytes(obj), b'{"a":12,"z":[true,null,"x"]}')
        self.assertEqual(p.parse_canonical(p.canonical_bytes(obj)), obj)
        for raw in (b'{"a":1,"a":2}', b'{ "a":1}', b'{"a":1.0}'):
            with self.assertRaises(p.ProtocolError):
                p.parse_canonical(raw)
        for value in (1.0, float("nan"), "é", 2**53):
            with self.assertRaises(p.ProtocolError):
                p.canonical_bytes(value)
        original = p.trace_root(self.trace)
        for mutate in (lambda t: t.update(market_id="other"),
                       lambda t: t.update(run_id=2),
                       lambda t: t["steps"][0].update(status="unavailable"),
                       lambda t: t["steps"][0]["input"].update(source_deadline=999),
                       lambda t: t["steps"][0].update(evidence_refs=[])):
            changed = copy.deepcopy(self.trace)
            mutate(changed)
            self.assertNotEqual(original, p.trace_root(changed))
        for mutate in (lambda t: t["steps"][0]["output"].update(value=0),
                       lambda t: t["terminal"].update(outcome=0),
                       lambda t: t["steps"][0].update(step_index=False)):
            changed = copy.deepcopy(self.trace)
            mutate(changed)
            self.assertTrue(p.check_consistency(self.bp, changed, e.evidence_from(self.log), "market-001"))

    def test_duplicate_key_identity_is_numeric_not_hex_spelling(self):
        for spelling in (str.upper, lambda n: "00" + n, lambda n: "+0x" + n):
            bp = copy.deepcopy(self.bp)
            first = bp["nodes"][0]["params"]["public_key"]
            second = copy.deepcopy(first)
            second["n"] = spelling(first["n"])
            self.assertNotEqual(p.canonical_bytes(first), p.canonical_bytes(second))
            self.assertEqual(int(first["n"], 16), int(second["n"], 16))
            bp["nodes"][1]["params"]["public_key"] = second
            with self.assertRaisesRegex(p.ProtocolError, "duplicate source authority/key"):
                p.validate_blueprint(bp)

    def test_authentication_cannot_be_replaced_by_content_hash_or_slot_squatting(self):
        node = p.validate_blueprint(self.bp)[0]
        evidence = next(iter(e.evidence_from(self.log).values()))
        key = p.test_keys()[evidence["body"]["authority"]]
        self.assertTrue(p.authentic(evidence, p.public_key(key)))
        fresh = p.PublicationLog(authority_keys=copy.deepcopy(self.log.authority_keys))
        fake = copy.deepcopy(evidence)
        fake["body"]["value"] = not fake["body"]["value"]
        self.assertNotEqual(p.evidence_root(evidence), p.evidence_root(fake))
        self.assertFalse(p.authentic(fake, p.public_key(key)))
        with self.assertRaises(p.ProtocolError):
            fresh.publish_evidence(fake, 101)
        self.assertEqual(fresh.slots, {})
        fresh.publish_evidence(evidence, 102)
        self.assertEqual(len(fresh.slots), 1)
        for field, value in (("market_id", "replay"), ("run_id", 2), ("request_root", "0"*64),
                             ("authority", "source_c")):
            fake = copy.deepcopy(evidence)
            fake["body"][field] = value
            self.assertFalse(p.authentic(fake, p.public_key(key)))
        fake = copy.deepcopy(evidence)
        fake["signature"] += "00"
        self.assertFalse(p.authentic(fake, p.public_key(key)))

    def test_deadline_and_hard_timeout_are_explicit(self):
        root = p.trace_root(self.trace)
        self.assertEqual(p.verify(self.bp, root, "market-001", self.log, 114, 100)["status"], "pending")
        self.assertEqual(p.verify(self.bp, root, "market-001", self.log, 115, 100)["status"], "resolve")
        self.assertEqual(p.hard_timeout("blocked", 199, 200), "blocked")
        self.assertEqual(p.hard_timeout("blocked", 200, 200), "cancel_timeout")
        self.assertEqual(p.hard_timeout("resolve", 200, 200), "resolve")
        # An executor cannot omit an already published honest source and recast
        # the trace as an unavailable input, even if its local replay is coherent.
        hidden = copy.deepcopy(self.log)
        hidden.slots.pop(("market-001", 1, "source_a"))
        omitted = p.execute(self.bp, "market-001", 1, 100, hidden)
        real = copy.deepcopy(self.log)
        root = real.publish(p.TRACE_VERSION, omitted, 111)
        self.assertEqual(p.verify(self.bp, root, "market-001", real, 115, 100)["status"], "blocked")

    def test_market_session_retries_and_irreversible_terminal(self):
        bp = p.make_blueprint(max_runs=2)
        session = p.ResolutionSession(bp, "market-001", 100)
        self.assertEqual(session.market_deadline, 136)
        first, log = p.fixture_run(bp, [None, False, True])
        second, log = p.fixture_run(bp, [False, False, True], run_id=2, start=120, log=log, previous_trace=first)
        self.assertEqual(session.advance(p.trace_root(second), 115, log)["status"], "blocked")
        self.assertEqual(session.advance(p.trace_root(first), 115, log)["status"], "defer")
        self.assertEqual(session.advance(p.trace_root(second), 135, log)["status"], "resolve")
        with self.assertRaises(p.ProtocolError):
            session.advance(p.trace_root(first), 136, log)
        self.assertEqual(session.expire(136), {"action": "resolve", "outcome": False})
        withheld = p.ResolutionSession(bp, "market-001", 100)
        with self.assertRaises(p.ProtocolError):
            withheld.expire(135)
        self.assertEqual(withheld.expire(136), {"action": "cancel_timeout"})

    def test_exact_composition_and_authority_cover(self):
        table, _ = e.protocol_catalog()
        summary, rows = e.exact_experiment("iid", 3, table, params={"error": Fraction(1,20)})
        expected = 3*Fraction(1,20)**2 - 2*Fraction(1,20)**3
        self.assertEqual(summary["rates_per_offer"]["wrong"], expected)
        self.assertEqual(sum(x["probability"] for x in rows), 1)
        common, _ = e.exact_experiment("common", 3, table, params={"error": Fraction(1,20), "common_error": Fraction(1,10)})
        self.assertEqual(common["rates_per_offer"]["wrong"], Fraction(1,10)+Fraction(9,10)*expected)
        self.assertEqual(e.minimum_authority_cover(e.authority_actions(3), 2)[0], 6)
        self.assertEqual(e.minimum_authority_cover(e.authority_actions(3, True), 2)[0], 3)
        static, _ = e.exact_experiment("s", 3, table, params={"error": Fraction(1,20)}, actions=e.authority_actions(3), budget=2)
        adaptive, _ = e.exact_experiment("a", 3, table, params={"error": Fraction(1,20)}, actions=e.authority_actions(3), budget=2, adaptive=True)
        self.assertGreaterEqual(adaptive["rates_per_offer"]["wrong"], static["rates_per_offer"]["wrong"])
        self.assertLessEqual(adaptive["expected_attack_cost"], 2)

    def test_external_judgment_fixtures_do_not_prove_truth(self):
        for kind in ("market_evidence", "llm_judge", "human_judge"):
            bp = p.make_blueprint(1, report_type=kind)
            trace, log = p.fixture_run(bp, [True])
            result = p.verify(bp, p.trace_root(trace), "market-001", log, 115, 100)
            self.assertEqual(result["status"], "resolve")
            self.assertTrue(result["terminal"]["outcome"])
            # Ground truth is False in this fixture: authentic judgment can err.


if __name__ == "__main__":
    unittest.main()
