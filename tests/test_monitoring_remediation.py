"""No-work-stake auditing must preserve capital and satisfy actual incentives."""
from dataclasses import replace
import unittest
from research.resolution_trust.monitoring_game import GameConfig, fresh_configs, monitoring_equilibrium
from research.resolution_trust.monitoring_remediation import zero_stake_contract


class MonitoringRemediationTests(unittest.TestCase):
    def test_marginal_bond_capital_is_preserved_and_work_is_incentivized(self):
        c=GameConfig('marginal_capital',watcher_capitals=(1500.,)*3)
        bounty=monitoring_equilibrium(c)
        staked=monitoring_equilibrium(replace(c,completion_payment=2.5,work_stake=6.,audit_probability=.5))
        corrected=monitoring_equilibrium(zero_stake_contract(c))
        self.assertEqual(bounty['eligible_watchers'],3)
        self.assertEqual(staked['eligible_watchers'],0)
        self.assertEqual(corrected['eligible_watchers'],3)
        self.assertEqual(corrected['inspect_given_available'],1.)
        self.assertEqual(corrected['shirking_utility'],0.)
        self.assertGreater(corrected['audit_effort_margin'],0.)
        self.assertEqual(corrected['false_finalization_rate'],0.)

    def test_audit_does_not_override_capital_budget_or_challenge_economics(self):
        c=zero_stake_contract(GameConfig('limits'))
        no_challenger=monitoring_equilibrium(replace(c,watcher_capitals=(1499.,)*3))
        self.assertEqual(no_challenger['false_finalization_rate'],1.)
        bad_judge=monitoring_equilibrium(replace(c,adjudication_accuracy=.6))
        self.assertEqual(bad_judge['inspect_given_available'],1.)
        self.assertEqual(bad_judge['challenge_coverage_given_false'],0.)
        self.assertEqual(bad_judge['false_finalization_rate'],1.)
        no_reserve=monitoring_equilibrium(replace(c,external_reserve=20.))
        self.assertEqual(no_reserve['status'],'insufficient_external_reserve')
        self.assertEqual(no_reserve['accepted_correct_rate'],0.)

    def test_every_original_regime_is_retained_and_funded(self):
        bases=[c for c in fresh_configs() if '_paid_' not in c.name]
        self.assertEqual(len(bases),64)
        for c in bases:
            b=monitoring_equilibrium(c)
            a=monitoring_equilibrium(zero_stake_contract(c))
            with self.subTest(c.name):
                self.assertEqual(a['eligible_watchers'],b['eligible_watchers'])
                self.assertTrue(a['funding_feasible'])
                self.assertTrue(a['submitted'])
                self.assertLessEqual(a['false_finalization_rate'],b['false_finalization_rate']+1e-12)
                self.assertLessEqual(a['expected_external_spend'],a['required_external_reserve'])
                self.assertLess(max(a['proposer_best_response_regret'],a['inspector_best_response_regret']),1e-10)


if __name__=='__main__': unittest.main()
