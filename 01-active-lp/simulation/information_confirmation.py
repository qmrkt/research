"""New sealed regime evaluation of the already-selected lambda .005.

The random design is fixed and written before evaluating any payoffs. The .005
coefficient and .15 comparison are never selected or altered using these data.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from random import Random
import statistics
from research.active_lp.information_timing import TimingRegime, write_csv
from research.active_lp.information_frontier import allocation_rows

REGIME_SEED=1047293
BOOTSTRAP_SEED=1047299
ARMS=(('flat',0.),('normalized',.005),('normalized',.15))


def confirmatory_regimes():
    rng=Random(REGIME_SEED)
    return tuple(TimingRegime(f'confirm_{i:03d}',
        pre_shares=rng.randint(5,110),future_shares=rng.randint(10,300),
        flow_accuracy=rng.uniform(.34,.85),signal_accuracy=rng.uniform(.55,.95),
        lp_fee_bps=rng.choice((75,150,250)),duration_days=rng.choice((14,45,90)),
        annual_opportunity_cost=rng.choice((.02,.08))) for i in range(64))


def percentile(values,q):
    ordered=sorted(values)
    x=(len(ordered)-1)*q
    lo=int(x); hi=min(lo+1,len(ordered)-1)
    return ordered[lo]+(x-lo)*(ordered[hi]-ordered[lo])


def bootstrap_interval(differences):
    # Independent regime draws define the synthetic population. Resample whole
    # paired regimes, preserving policy covariance and their finite-state means.
    rng=Random(BOOTSTRAP_SEED)
    samples=[statistics.mean(rng.choices(differences,k=len(differences))) for _ in range(10000)]
    return {'paired_mean_difference':statistics.mean(differences),
        'paired_median_difference':statistics.median(differences),
        'ci95_lower':percentile(samples,.025),'ci95_upper':percentile(samples,.975),
        'negative_regimes':sum(x < -1e-12 for x in differences),
        'zero_regimes':sum(abs(x)<=1e-12 for x in differences),
        'positive_regimes':sum(x > 1e-12 for x in differences)}


def run(output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    regimes=confirmatory_regimes()
    engine_path=Path(__file__).with_name('reference_parallel_lmsr.py')
    engine_hash=hashlib.sha256(engine_path.read_bytes()).hexdigest()
    design={'status':'Locally sealed new confirmatory parameter sample, generated after selecting .005 on the prior train population; not external preregistration.',
        'frozen_arms':[{'rule':r,'lambda':l} for r,l in ARMS],
        'regime_seed':REGIME_SEED,'regime_count':64,
        'parameter_distribution':'Independently draw integer pre5..110, future10..300; uniform eta .34..85 and signal accuracy .55..95; uniform choice LPfees75/150/250, duration14/45/90days, outside APR .02/.08. Three outcomes, binary flow-alignment signal, protocol25bps, depth100+20, minimal bootstrap funding.',
        'regimes':[asdict(r) for r in regimes],
        'estimands':['same-date information advantage','informed entrant offered return minus founder actual unconditional return'],
        'bootstrap':{'unit':'whole paired regime','replicates':10000,'seed':BOOTSTRAP_SEED,'interval':'paired percentile95%; uncertainty over stipulated synthetic parameter distribution, not real-world evidence'},
        'reporting':'All64 regimes and arms, no retuning. Report public profitability/preservation, private participation, positive founder/entrant count and all changes.',
        'reference_engine_sha256':engine_hash}
    text=json.dumps(design,indent=2,sort_keys=True)+'\n'
    design_path=output_dir/'design.json'
    if design_path.exists() and design_path.read_text()!=text: raise ValueError('confirmatory design changed')
    design_path.write_text(text)
    summaries,worlds,effects=[],[],[]
    by_arm={}
    for rule,lam in ARMS:
        records=[]
        for regime in regimes:
            rows,raw,effect=allocation_rows(regime,rule,lam)
            summaries.extend(rows); worlds.extend(raw); effects.append(effect)
            p={r['policy']:r for r in rows}
            private=p['late_private_optional']; public=p['late_public_optional']
            records.append({'regime':regime.name,'rule':rule,'lambda':lam,
                'information_value':effect['private_information_value'],
                'public_offered_return':public['entrant_offered_return'],
                'private_offered_return':private['entrant_offered_return'],
                'public_entry_rate':public['entry_rate'],'private_entry_rate':private['entry_rate'],
                'founder_actual_return':private['founder_unconditional_return'],
                'cohort_gap':private['offered_entrant_minus_actual_founder_gap'],
                'founder_and_private_profitable':private['founder_unconditional_return']>1e-12 and private['entrant_offered_return']>1e-12})
        by_arm[(rule,lam)]=records
    base=by_arm[('flat',0.)]
    baseline_public_profitable={r['regime'] for r in base if r['public_offered_return']>1e-12}
    aggregates=[]
    for (rule,lam),rows in by_arm.items():
        aggregate={'rule':rule,'lambda':lam,'regime_count':len(rows)}
        for key in ('information_value','public_offered_return','private_offered_return','public_entry_rate','private_entry_rate','founder_actual_return','cohort_gap'):
            aggregate['mean_'+key]=statistics.mean(r[key] for r in rows)
        aggregate['public_profitable_regimes']=sum(r['public_offered_return']>1e-12 for r in rows)
        aggregate['baseline_public_profitable_regimes_preserved']=sum(r['public_offered_return']>1e-12 for r in rows if r['regime'] in baseline_public_profitable)
        aggregate['private_profitable_regimes']=sum(r['private_offered_return']>1e-12 for r in rows)
        aggregate['founder_and_private_profitable_regimes']=sum(r['founder_and_private_profitable'] for r in rows)
        aggregates.append(aggregate)
    contrasts=[]
    for arm in (('normalized',.005),('normalized',.15)):
        for metric in ('information_value','cohort_gap','public_offered_return','private_offered_return','public_entry_rate','private_entry_rate','founder_actual_return'):
            diffs=[r[metric]-b[metric] for r,b in zip(by_arm[arm],base)]
            contrasts.append({'rule':arm[0],'lambda':arm[1],'metric':metric,**bootstrap_interval(diffs)})
    if hashlib.sha256(engine_path.read_bytes()).hexdigest()!=engine_hash:
        raise RuntimeError('Reference source changed during sealed evaluation; preserve design, rerun')
    write_csv(output_dir/'summary.csv',aggregates)
    write_csv(output_dir/'paired_contrasts.csv',contrasts)
    write_csv(output_dir/'regime_outcomes.csv',[r for rows in by_arm.values() for r in rows])
    write_csv(output_dir/'cohort_allocation.csv',summaries)
    write_csv(output_dir/'worlds.csv',worlds)
    write_csv(output_dir/'causal_effects.csv',effects)
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'design_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'reference_engine_sha256':engine_hash,
        'summary':aggregates,'contrasts':contrasts,'world_rows':len(worlds)}
    (output_dir/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(run(args.output_dir),indent=2))
