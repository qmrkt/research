"""Subsequent solver-boundary audit; no parameter selection or calibration.

Run from any directory using the installed research package. This audit samples
boundary-rich inputs and verifies the solver's independent pure-action regrets.
The publication experiment's design.json and results are not selected by this.
"""
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
from random import Random
from research.resolution_trust import monitoring_game as game


def run():
    rng=Random(321091)
    rows=[]; max_regret=0.
    for i in range(3000):
        b=rng.choice((0.,10.,100.,1000.))
        w=rng.choice((0.,.5,3.,20.)); s=rng.choice((0.,2.,20.))
        n=rng.choice((0,1,3,8))
        c=game.GameConfig(str(i),pool=10000,
            signed_exposure=rng.choice((-1000.,0.,1.,100.,10000.)),
            proposer_bond=b,challenger_bond=b,success_fee=rng.choice((0.,5.,20.)),
            proposal_work_cost=rng.choice((0.,5.,100.)),watcher_capitals=(2000.,)*n,
            availability=rng.choice((0.,.3,1.)),common_outage=rng.choice((0.,.3,1.)),
            adjudication_accuracy=rng.choice((0.,.5,.9,1.)),challenger_reward_fraction=.5,
            completion_payment=w,work_stake=s,audit_probability=rng.choice((0.,.1,.5,1.)),
            inspection_work_cost=rng.choice((0.,.1,2.,1000.)),external_reserve=1000.)
        try:
            r=game.monitoring_equilibrium(c)
            regret=max(r['inspector_best_response_regret'],r['proposer_best_response_regret'])
            max_regret=max(max_regret,regret)
            assert regret<1e-7
            rows.append({**asdict(c),'status':r['status'],'max_regret':regret})
        except ValueError as e:
            assert str(e)=='profitable false challenge: outside neutral-inspector subgame'
            rows.append({**asdict(c),'status':'excluded_profitable_false_challenge','max_regret':''})
    output=Path(__file__).resolve().parent
    with (output/'boundary_cases.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    result={'seed':321091,'attempted':len(rows),
        'valid_solved':sum(r['max_regret']!='' for r in rows),
        'excluded_profitable_false_challenge':sum(r['max_regret']=='' for r in rows),
        'max_equilibrium_regret':max_regret,
        'source_sha256':hashlib.sha256(Path(game.__file__).read_bytes()).hexdigest(),
        'audit_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'boundary_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': run()
