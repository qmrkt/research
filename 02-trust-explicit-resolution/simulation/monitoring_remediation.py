"""Subsequent full-audit, zero-work-stake intervention on all 64 old regimes.

This responds to an observed capital tradeoff; it is not a preregistered test or
a new population. The original three-arm study and all negative results remain.
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import statistics
from . import monitoring_game as game


def zero_stake_contract(c):
    return replace(c,name=c.name+'_full_audit_zero_stake',completion_payment=1.25*c.inspection_work_cost,
                   audit_probability=1.,work_stake=0.)


def prepare(output):
    bases=tuple(c for c in game.fresh_configs() if '_paid_' not in c.name)
    design={'status':'Subsequent mechanism remediation responding to observed work-stake capital exclusion. Not preregistered, not independent confirmation, no parameter tuning on new outcomes.',
        'population':'Every one of the original 64 fresh base regimes, seed908731; retain original 3-arm outputs and negative results.',
        'intervention':'S=0; w=1.25c; delta=1. All other parameters, including free capital K and audit unit cost cA, unchanged.',
        'hypothesis':'Given the restricted neutral-inspector game, funded reserve, and profitable truthful proposing, full verifiable audits with w>c preserve eligible count and weakly reduce wrong finalization versus bounty only. This is conditional on a perfect enforceable work audit; no audit technology is established empirically.',
        'reporting':'All64 paired outcomes, each original comparator, inspector eligibility, reserve feasibility, spending, exact best-response regret; no Monte Carlo or deployment-population confidence interval.',
        'base_configs':[asdict(c) for c in bases],
        'intervention_configs':[asdict(zero_stake_contract(c)) for c in bases]}
    output.mkdir(parents=True,exist_ok=True)
    text=json.dumps(design,sort_keys=True,indent=2)+'\n'
    path=output/'design.json'
    if path.exists() and path.read_text()!=text:
        raise ValueError('Existing subsequent design differs; use a new output directory')
    path.write_text(text)
    return bases,text


def run(output,prepare_only=False):
    bases,design_text=prepare(output)
    if prepare_only: return {'status':'design saved; no payoffs evaluated','regimes':len(bases)}
    original_path=output.parent/'fresh_regimes.csv'
    with original_path.open() as f: originals={r['name']:r for r in csv.DictReader(f)}
    exact=[]; pairs=[]
    for c in bases:
        intervention=zero_stake_contract(c)
        r=game.monitoring_equilibrium(intervention)
        b=game.monitoring_equilibrium(c)
        # Detect any unnoticed drift in the frozen primary mechanism/results.
        assert abs(b['false_finalization_rate']-float(originals[c.name]['false_finalization_rate']))<1e-12
        assert r['eligible_watchers']==b['eligible_watchers']
        exact.append(r)
        row={'regime':c.name,'eligible_watchers':r['eligible_watchers'],
            'wrong_intervention':r['false_finalization_rate'],'fraud_intervention':r['fraud_given_submission'],
            'challenge_coverage_intervention':r['challenge_coverage_given_false'],
            'status':r['status'],'funding_feasible':r['funding_feasible'],
            'required_external_reserve':r['required_external_reserve'],'external_reserve':r['external_reserve'],
            'expected_external_spend':r['expected_external_spend'],'expected_real_cost':r['expected_real_cost'],
            'expected_inspections':r['expected_inspections'],
            'expected_audit_spend':r['audit_unit_cost']*r['expected_inspections'],
            'truthful_participation_margin':r['truthful_participation_margin']}
        for label,suffix in (('bounty',''),('unaudited','_paid_unaudited'),('staked_audited','_paid_audited')):
            old=originals[c.name+suffix]
            row['wrong_'+label]=float(old['false_finalization_rate'])
            row['delta_wrong_vs_'+label]=r['false_finalization_rate']-float(old['false_finalization_rate'])
            row['delta_external_spend_vs_'+label]=r['expected_external_spend']-float(old['expected_external_spend'])
            row['eligible_'+label]=int(old['eligible_watchers'])
        pairs.append(row)
    game.write_csv(output/'equilibria.csv',exact)
    game.write_csv(output/'pairs.csv',pairs)
    contrasts={}
    for label in ('bounty','unaudited','staked_audited'):
        delta=[p['delta_wrong_vs_'+label] for p in pairs]
        contrasts[label]={'mean_difference_wrong':statistics.mean(delta),
            'improved':sum(d < -1e-10 for d in delta),'tied':sum(abs(d)<=1e-10 for d in delta),
            'worse':sum(d > 1e-10 for d in delta),
            'mean_difference_external_spend':statistics.mean(p['delta_external_spend_vs_'+label] for p in pairs)}
    summary={'regimes':len(exact),'launched':sum(r['submitted'] for r in exact),
        'reserve_feasible':sum(r['funding_feasible'] for r in exact),
        'unchanged_eligibility_vs_bounty':sum(p['eligible_watchers']==p['eligible_bounty'] for p in pairs),
        'mean_false_finalization':statistics.mean(r['false_finalization_rate'] for r in exact),
        'zero_fraud_regimes':sum(r['fraud_given_submission']==0 for r in exact),
        'mean_expected_external_spend':statistics.mean(r['expected_external_spend'] for r in exact),
        'mean_expected_real_cost':statistics.mean(r['expected_real_cost'] for r in exact),
        'mean_expected_audit_spend':statistics.mean(p['expected_audit_spend'] for p in pairs),
        'mean_required_external_reserve':statistics.mean(r['required_external_reserve'] for r in exact),
        'max_required_external_reserve':max(r['required_external_reserve'] for r in exact),
        'minimum_truthful_participation_margin':min(r['truthful_participation_margin'] for r in exact),
        'max_equilibrium_regret':max(max(r['inspector_best_response_regret'],r['proposer_best_response_regret']) for r in exact),
        'contrasts':contrasts,
        'design_sha256':hashlib.sha256(design_text.encode()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'game_source_sha256':hashlib.sha256(Path(game.__file__).read_bytes()).hexdigest(),
        'primary_results_sha256':hashlib.sha256(original_path.read_bytes()).hexdigest()}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--prepare-only',action='store_true')
    args=p.parse_args()
    print(json.dumps(run(args.output_dir,args.prepare_only),indent=2))
