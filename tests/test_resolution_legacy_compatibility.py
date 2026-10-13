from dataclasses import replace
import random
import unittest

from research.resolution_trust.agents import challenger_decides, composition_detection_probability, estimate_proposer_mev, generate_participants, proposer_action
from research.resolution_trust.metrics import aggregate
from research.resolution_trust.scenarios import all_scenarios
from research.resolution_trust.simulation import run_simulation
from research.resolution_trust.types import BondStructure, ChallengerMix, CompositionScenario, Participant, ProposerType, SimConfig


class LegacyCompatibilityTests(unittest.TestCase):
    def test_review_regressions_are_fixed(self):
        cfg = SimConfig(pool_size=5000, num_participants=2)
        true_winner = Participant(0, 2500, True, False, capital_budget=10000)
        other = Participant(1, 2500, False, True, capital_budget=10000)
        self.assertEqual(estimate_proposer_mev(cfg, true_winner), -2500)
        self.assertEqual(proposer_action(cfg, true_winner, [true_winner, other], 2500), "truthful")
        self.assertFalse(challenger_decides(replace(true_winner, capital_budget=0), cfg))
        self.assertEqual(composition_detection_probability(cfg), 1.)

    def test_legacy_generation_now_funds_each_outcome(self):
        cfg = SimConfig(pool_size=5000, num_participants=3)
        actors = generate_participants(cfg, random.Random(42))
        self.assertAlmostEqual(sum(p.payout_true for p in actors), 5000)
        self.assertAlmostEqual(sum(p.payout_false for p in actors), 5000)

    def test_honest_proposals_pay_for_checks_and_deferral_is_distinct(self):
        cfg = SimConfig(pool_size=5000, num_participants=10, proposer_type=ProposerType.HONEST,
                        challenger_mix=ChallengerMix.ALL_ATTENTIVE, num_episodes=20)
        result = run_simulation(cfg)
        self.assertGreater(sum(e.num_verifiers for e in result.episodes), 0)
        self.assertGreater(aggregate(result).mean_resource_cost, 0)
        deferred = run_simulation(replace(cfg, proposer_work_cost=10, proposer_fee=0))
        self.assertTrue(all(e.terminal_status == "deferred" and e.resolution_correct is None for e in deferred.episodes))

    def test_every_listed_legacy_case_is_valid_and_no_pseudo_escalation(self):
        self.assertEqual(sum(len(v) for v in all_scenarios().values()), 177)
        for rows in all_scenarios().values():
            for cfg in rows:
                run_simulation(replace(cfg, num_episodes=1))
        cfg = SimConfig(pool_size=5000, num_participants=10)
        for changed in (replace(cfg, composition_scenario=CompositionScenario.THREE_SOURCE_ONE_CORRUPT),
                        replace(cfg, bond_structure=BondStructure.EXPONENTIAL_ESCALATION)):
            with self.assertRaises(ValueError):
                run_simulation(changed)


if __name__ == "__main__":
    unittest.main()
