"""Economic identity, equilibrium, shirking and funded-ledger regression tests."""
from dataclasses import replace
from math import comb
import unittest
from research.resolution_trust.monitoring_game import (
    GameConfig, monitoring_equilibrium, simulate, coverage, bounty_share,
)

class MonitoringGameTests(unittest.TestCase):
    def setUp(self):
        self.base=GameConfig('test')
        self.paid=replace(self.base,completion_payment=3.,audit_probability=.5,work_stake=2.)

    def test_signed_exposure_and_adjudication_bound(self):
        honest=monitoring_equilibrium(replace(self.base,signed_exposure=-4000.))
        self.assertEqual(honest['fraud_given_submission'],0.)
        for rho in (.1,.15):
            required=1/(.9*(1+rho))
            if rho==.1: self.assertGreater(required,1.)
            else: self.assertAlmostEqual(required,.966183574879227,places=12)
        weak=monitoring_equilibrium(replace(self.paid,adjudication_accuracy=.6))
        self.assertGreater(weak['inspection_coverage'],.9)
        self.assertLess(weak['correct_challenge_surplus'],0.)
        self.assertEqual(weak['challenge_coverage_given_false'],0.)
        self.assertEqual(weak['false_finalization_rate'],1.)

    def test_mixed_equilibrium_matches_closed_form_single_inspector(self):
        c=replace(self.base,signed_exposure=100.,proposer_bond=100.,challenger_bond=100.,
            availability=1.,watcher_capitals=(200.,),adjudication_accuracy=1.,challenger_reward_fraction=1.)
        r=monitoring_equilibrium(c)
        q=100/(100+100+c.success_fee)
        R=100-c.challenge_work_cost-c.capital_rate_per_window*100
        self.assertAlmostEqual(r['inspect_given_available'],q,places=12)
        self.assertAlmostEqual(r['fraud_given_submission'],c.inspection_work_cost/R,places=12)
        self.assertAlmostEqual(r['fraud_gain_given_monitoring'],0.,places=10)
        self.assertLess(r['inspector_best_response_regret'],1e-10)

    def test_bounty_sharing_matches_enumerated_competitors(self):
        for n in (1,3,8):
            for u,m in ((.6,.2),(1.,1.),(.3,.9)):
                p=u*m
                enumerated=sum(comb(n-1,j)*p**j*(1-p)**(n-1-j)/(j+1) for j in range(n))
                self.assertAlmostEqual(bounty_share(m,n,u),enumerated,places=12)

    def test_paid_unaudited_work_shirks_and_does_not_restore_coverage(self):
        base=monitoring_equilibrium(self.base)
        unaudited=monitoring_equilibrium(replace(self.paid,audit_probability=0.))
        paid=monitoring_equilibrium(self.paid)
        self.assertAlmostEqual(base['fraud_given_submission'],unaudited['fraud_given_submission'],places=12)
        self.assertAlmostEqual(base['inspection_coverage'],unaudited['inspection_coverage'],places=12)
        self.assertGreater(unaudited['expected_shirks'],0.)
        self.assertEqual(paid['inspect_given_available'],1.)
        self.assertEqual(paid['fraud_given_submission'],0.)
        self.assertGreater(paid['audit_effort_margin'],0.)

    def test_capital_funding_and_proposer_work_are_real_constraints(self):
        no_capital=monitoring_equilibrium(replace(self.paid,watcher_capitals=(1500.,)*3))
        self.assertEqual(no_capital['eligible_watchers'],0)
        self.assertEqual(no_capital['false_finalization_rate'],1.)
        unfunded=monitoring_equilibrium(replace(self.paid,external_reserve=1.))
        self.assertEqual(unfunded['status'],'insufficient_external_reserve')
        self.assertEqual(unfunded['no_proposal_rate'],1.)
        self.assertEqual(unfunded['accepted_correct_rate'],0.)
        unpaid=monitoring_equilibrium(replace(self.paid,success_fee=0.))
        self.assertEqual(unpaid['status'],'no_profitable_proposal')
        self.assertEqual(unpaid['no_proposal_rate'],1.)

    def test_competition_and_correlated_downtime(self):
        self.assertAlmostEqual(coverage(1.,8,.6,.3),.7*(1-.4**8),places=12)
        r=monitoring_equilibrium(replace(self.paid,common_outage=.3))
        self.assertGreater(r['fraud_given_submission'],0.)
        self.assertLessEqual(r['correction_given_false'],.7*.95)
        with self.assertRaisesRegex(ValueError,'profitable false challenge'):
            monitoring_equilibrium(replace(self.base,proposer_bond=10000.,challenger_bond=1.))

    def test_absent_monitoring_and_loss_making_truth_boundaries(self):
        # A never-reached availability information set has no ex-ante deviation.
        down=monitoring_equilibrium(replace(self.base,common_outage=1.))
        self.assertEqual(down['false_finalization_rate'],1.)
        self.assertEqual(down['expected_inspections'],0.)
        self.assertEqual(down['inspector_best_response_regret'],0.)
        # Zero proposer payment does not imply abstention: profitable fraud can
        # still pay the work cost when nobody can challenge it.
        fraud=monitoring_equilibrium(replace(self.base,success_fee=0.,watcher_capitals=()))
        self.assertTrue(fraud['submitted'])
        self.assertEqual(fraud['false_finalization_rate'],1.)
        self.assertLess(fraud['truthful_participation_margin'],0.)
        # With no exposure and costly truthful work, abstention is genuine.
        idle=monitoring_equilibrium(replace(self.base,success_fee=0.,signed_exposure=0.))
        self.assertEqual(idle['no_proposal_rate'],1.)
        self.assertEqual(idle['accepted_correct_rate'],0.)

    def test_every_simulated_episode_balances_money_and_reserve(self):
        for c in (self.base,self.paid,replace(self.paid,audit_probability=0.),replace(self.paid,common_outage=.3)):
            r=monitoring_equilibrium(c)
            summaries,traces=simulate(c,r,71297,10000,100)
            self.assertLess(max(x['max_money_balance_error'] for x in summaries),1e-8)
            self.assertLessEqual(max(x['max_external_spend'] for x in summaries),c.external_reserve)
            for row in summaries:
                self.assertLessEqual(abs(row['error']),6*row['standard_error']+1e-10)
            self.assertTrue(all(abs(t['money_balance'])<1e-8 for t in traces))

if __name__=='__main__':
    unittest.main()
