"""Independent branch and conservation checks for the funded resolution game."""
from dataclasses import replace
import itertools
import math
import unittest
from unittest.mock import patch

from research.resolution_trust.economics import (
    Actor, GameConfig, Latents, all_proposer_values, can_challenge,
    challenge_value, choose_action, draw_latents, make_actors, play, proposer_values,
)


class ResolutionEconomicsTests(unittest.TestCase):
    def test_collateral_and_signed_positions(self):
        for n, dist in itertools.product((2, 3, 10, 30), ("uniform", "power_law", "whale")):
            cfg = GameConfig(participants=n, positions=dist)
            actors = make_actors(cfg, draw_latents(11, 4, n))
            self.assertAlmostEqual(sum(a.payout_true for a in actors), cfg.pool)
            self.assertAlmostEqual(sum(a.payout_false for a in actors), cfg.pool)
            self.assertAlmostEqual(sum(a.signed_gain for a in actors), 0)
            self.assertTrue(any(a.signed_gain < 0 for a in actors))
            self.assertTrue(any(a.signed_gain > 0 for a in actors))
            fast = all_proposer_values(cfg, actors)
            for actor, result in zip(actors, fast):
                for a, b in zip(result, proposer_values(cfg, actors, actor)):
                    self.assertAlmostEqual(a, b, places=10)
                if actor.signed_gain < 0 and result[2] == 0:
                    self.assertNotEqual(choose_action(cfg, actor, result), "false")

    def test_capital_and_negative_ev_are_separate_gates(self):
        cfg = GameConfig()
        actor = Actor(0, 1000, 0, 0, 1, 0)
        self.assertGreater(challenge_value(cfg, actor, 1), 0)
        self.assertFalse(can_challenge(cfg, actor, 1))
        rich = replace(actor, capital=1e6)
        self.assertTrue(can_challenge(cfg, rich, 1))
        self.assertFalse(can_challenge(replace(cfg, accuracy=0), rich, 1))

    def test_false_winner_can_correct_for_reward(self):
        cfg = GameConfig(bond_floor=1000, pool=1000, challenger_ratio=.1, accuracy=1,
                         challenge_work=0, verification_work=0, capital_apy=0)
        actor = Actor(0, 0, 10, 1e6, 1, 0)
        self.assertTrue(can_challenge(cfg, actor, 1))

    def test_false_challenge_is_not_forbidden(self):
        cfg = GameConfig(pool=1000, bond_rule="flat", bond_floor=10, challenger_ratio=.01,
                         accuracy=.8, capital_apy=0, challenge_work=0)
        actor = Actor(1, 0, 1000, 1e6, 1, 1)
        self.assertGreater(challenge_value(cfg, actor, 0), 0)
        self.assertTrue(can_challenge(cfg, actor, 0))

    def test_exact_branch_expectation_matches_executed_cash_on_truth_and_fraud(self):
        # Enumerate all inspection/adjudication branches independently: no
        # Monte Carlo tolerance and no use of the engine's expected result.
        q, a = .4, .8
        for honest in (False, True):
            cfg = GameConfig(pool=1000, participants=2, bond_rule="flat", bond_floor=10,
                             proposer_fee=200 if honest else 5, proposer_work=2,
                             verification_work=.5, challenge_work=.25,
                             challenger_ratio=.01, accuracy=a, capital_apy=0,
                             honest_proposer=honest)
            p = Actor(0, 1000 if honest else 0, 0 if honest else 1000, 10000, 0, 0)
            c = Actor(1, 0 if honest else 1000, 1000 if honest else 0, 10000,
                      -math.log1p(-q) / cfg.window, 1)
            expectation = 0.0
            challenge_frequency = 0.0
            wrong_frequency = 0.0
            for checks, correct in itertools.product((False, True), repeat=2):
                weight = (q if checks else 1-q) * (a if correct else 1-a)
                rows = ((0.,) * 9, (0., 0., 0., 0., 0., 1., .1 if checks else .9, 0., 0.))
                with patch("research.resolution_trust.economics.make_actors", return_value=(p, c)):
                    episode = play(cfg, Latents(rows, .1 if correct else .9))
                self.assertEqual(episode["proposer"], 0)
                self.assertEqual(episode["proposal_false"], not honest)
                self.assertAlmostEqual(episode["balance_error"], 0)
                expectation += weight * episode["proposer_net"]
                challenge_frequency += weight * episode["challenged"]
                wrong_frequency += weight * episode["final_wrong"]
            expected = ((1-q*a)*(1000+5) - q*a*10 - 2) if not honest else (200 - 2 - q*(1-a)*(1000+10+200))
            self.assertAlmostEqual(expectation, expected)
            self.assertAlmostEqual(challenge_frequency, q)
            self.assertAlmostEqual(wrong_frequency, 1-q*a if not honest else q*(1-a))
            self.assertAlmostEqual(expectation, proposer_values(cfg, (p, c), p)[0 if honest else 1])

    def test_monte_carlo_accounts_all_terminal_states_and_work(self):
        seen = set()
        cfgs = (
            GameConfig(), GameConfig(attention="attentive", accuracy=1),
            GameConfig(honest_proposer=True, proposer_fee=100, challenger_ratio=.001, accuracy=.7),
            GameConfig(honest_proposer=True, proposer_fee=0, proposer_work=10),
        )
        for cfg in cfgs:
            for j in range(200):
                e = play(cfg, draw_latents(10, j, cfg.participants))
                seen.add(e["status"])
                self.assertLess(abs(e["balance_error"]), 1e-8)
                self.assertGreaterEqual(e["reserve_final"], 0)
                if e["status"] == "deferred":
                    self.assertIsNone(e["proposer"])
                    self.assertFalse(e["final_wrong"])
                elif e["checks"]:
                    self.assertGreaterEqual(e["resource_cost"], cfg.proposer_work + cfg.verification_work)
        self.assertEqual(seen, {"correct", "incorrect", "deferred"})

    def test_config_rejects_pseudo_escalation_and_unfunded_parameters(self):
        for kwargs in ({"bond_rule": "exponential"}, {"reward_fraction": 1.1}, {"proposer_fee": -1}, {"pool": 0}):
            with self.assertRaises(ValueError):
                GameConfig(**kwargs)

    def test_neutral_one_monitor_matches_independent_equilibrium_model(self):
        from research.resolution_trust.monitoring_game import GameConfig as MonitorConfig, monitoring_equilibrium
        mc = MonitorConfig(name="independent_crosscheck", watcher_capitals=(2000.,), availability=.9)
        equilibrium = monitoring_equilibrium(mc)
        q = equilibrium["challenge_coverage_given_false"]
        # Align the challenger's 0.001 lock cost; the proposer cost cancels
        # from the lying-versus-truthful comparison checked here.
        cfg = GameConfig(pool=10000, participants=3, bond_rate=.15, proposer_fee=20,
                         proposer_work=5, challenge_work=1, capital_apy=.365, accuracy=.95)
        proposer = Actor(0, 0, 4000, 2000, 0, 0)
        monitor = Actor(1, 0, 0, 2000, -math.log1p(-q)/24, 1)
        counterparty = Actor(2, 10000, 6000, 0, 0, 2)
        truth, false, qt, qf = proposer_values(cfg, (proposer, monitor, counterparty), proposer)
        self.assertEqual(qt, 0)
        self.assertAlmostEqual(qf, q)
        self.assertAlmostEqual(challenge_value(cfg, monitor, 1), equilibrium["correct_challenge_surplus"])
        self.assertAlmostEqual(challenge_value(cfg, monitor, 0), equilibrium["false_challenge_surplus"])
        self.assertAlmostEqual(false-truth, equilibrium["fraud_gain_given_monitoring"])


if __name__ == "__main__":
    unittest.main()
