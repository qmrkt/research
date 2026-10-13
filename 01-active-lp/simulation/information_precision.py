"""80-digit ledger and aggregation check of the sealed information confirmation.

Reuses its fixed worlds, converting saved probabilities with Decimal(str(p)),
renormalizing their tiny serialization residual. No thresholds or rules change.
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict
from decimal import Decimal, localcontext
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from research.active_lp.information_confirmation import confirmatory_regimes, ARMS
from research.active_lp.information_timing import write_csv
from research.active_lp.events import BootstrapMarket, BuyOutcome, LpEnterActive, ResolveMarket, ClaimWinnings
from research.active_lp.reference_math import collateral_required, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import ReferenceParallelLmsrEngine, RESERVE_POOL, create_initial_state
D=Decimal

@lru_cache(maxsize=None)
def decimal_cash(regime,rule,lam,winner,flow,entered):
    if not entered and (rule!='flat' or lam!=0):
        return decimal_cash(regime,'flat',0.,winner,flow,False)
    scheme='linear_lambda_normalized' if rule=='normalized' else 'flat'
    engine=ReferenceParallelLmsrEngine(lp_fee_bps=regime.lp_fee_bps,protocol_fee_bps=25,
        residual_policy=RESERVE_POOL,residual_weight_scheme=scheme,residual_linear_lambda=D(str(lam)))
    state=create_initial_state(3,residual_weight_scheme=scheme,residual_linear_lambda=D(str(lam)))
    funding=collateral_required(D(100),uniform_price_vector(3))
    end=regime.duration_days*86400
    state=engine.apply_event(state,BootstrapMarket(0,'creator',funding,D(100)))
    state=engine.apply_event(state,BuyOutcome(end//3,'public_trader',0,D(regime.pre_shares),D('1e50')))
    if entered:
        state=engine.apply_event(state,LpEnterActive(end//2,'entrant',D(20),D('1e50'),state.pricing.price_vector,D('1e-18')))
    state=engine.apply_event(state,BuyOutcome(2*end//3,'future_trader',flow,D(regime.future_shares),D('1e50')))
    state=engine.apply_event(state,ResolveMarket(end,winner))
    for trader,holdings in list(state.traders.positions_by_trader.items()):
        if holdings[winner]>0:
            state=engine.apply_event(state,ClaimWinnings(end+1,trader,winner,holdings[winner]))
    nav=engine.mark_to_market_nav(state)
    out={}
    for key,sp in state.sponsors.items():
        prefix='founder' if sp.sponsor_id=='creator' else 'entrant'
        deposit=sp.collateral_posted
        cost=deposit*D(str(regime.annual_opportunity_cost))*D(end-sp.entry_timestamp)/D(365*86400)
        out[prefix+'_profit']=nav[key]-deposit-cost
        out[prefix+'_return']=out[prefix+'_profit']/deposit
    return out


def run(input_dir,output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    engine=Path(__file__).with_name('reference_parallel_lmsr.py')
    engine_hash=hashlib.sha256(engine.read_bytes()).hexdigest()
    design={'purpose':'Precision robustness only; no re-selection or empirical claims.',
        'source':'Sealed confirmation64 existing worlds and frozen arms',
        'ledger_precision':80,'aggregation_precision':80,'decision_threshold':'1e-12',
        'probabilities':'Decimal from saved probability strings, then normalized to sum1. Records max initial mass discrepancy.',
        'regimes':[asdict(r) for r in confirmatory_regimes()],
        'engine_sha256':engine_hash}
    text=json.dumps(design,indent=2,sort_keys=True)+'\n'
    path=output_dir/'design.json'
    if path.exists() and path.read_text()!=text: raise ValueError('precision design changed')
    path.write_text(text)
    raw=list(csv.DictReader((input_dir/'worlds.csv').open()))
    original={ (r['regime'],r['rule'],float(r['lambda'])):r for r in csv.DictReader((input_dir/'regime_outcomes.csv').open())}
    rows=[]; max_mass=D(0); minimum_distance=None; decisions=changed=0
    for regime in confirmatory_regimes():
        for rule,lam in ARMS:
            world=[r for r in raw if r['regime']==regime.name and r['rule']==rule and float(r['lambda'])==lam]
            mass=sum(D(r['probability']) for r in world)
            max_mass=max(max_mass,abs(mass-D(1)))
            for r in world:
                r['p']=D(r['probability'])/mass
                r['cash']=decimal_cash(regime,rule,lam,int(r['winner']),int(r['future_flow_direction']),True)
            signal_means={s:sum(r['p']*r['cash']['entrant_profit'] for r in world if int(r['private_signal'])==s)/sum(r['p'] for r in world if int(r['private_signal'])==s) for s in (0,1)}
            public_mean=sum(r['p']*r['cash']['entrant_profit'] for r in world)
            for mean in (*signal_means.values(),public_mean):
                distance=abs(mean-D('1e-12'))
                minimum_distance=distance if minimum_distance is None else min(minimum_distance,distance)
            public_return=private_return=founder_return=D(0)
            pubentry=privateentry=D(0)
            for r in world:
                pub=public_mean>D('1e-12'); private=signal_means[int(r['private_signal'])]>D('1e-12')
                for policy,enter in (('late_public_optional',pub),('late_private_optional',private)):
                    decisions+=1; changed+=enter!=(r[policy+'_enter']=='True')
                public_return+=r['p']*r['cash']['entrant_return']*pub
                private_return+=r['p']*r['cash']['entrant_return']*private
                pubentry+=r['p']*pub; privateentry+=r['p']*private
                actual=r['cash'] if private else decimal_cash(regime,rule,lam,int(r['winner']),int(r['future_flow_direction']),False)
                founder_return+=r['p']*actual['founder_return']
            metrics={'information_value':private_return-public_return,'public_offered_return':public_return,
                'private_offered_return':private_return,'founder_actual_return':founder_return,
                'cohort_gap':private_return-founder_return,'public_entry_rate':pubentry,'private_entry_rate':privateentry}
            baseline=original[(regime.name,rule,lam)]
            for metric,value in metrics.items():
                original_value=D(baseline[metric])
                rows.append({'regime':regime.name,'rule':rule,'lambda':lam,'metric':metric,
                    'original':str(original_value),'precision80':str(value),'difference':str(value-original_value)})
    if hashlib.sha256(engine.read_bytes()).hexdigest()!=engine_hash: raise RuntimeError('engine changed')
    write_csv(output_dir/'comparisons.csv',rows)
    maxdifference=max(abs(D(r['difference'])) for r in rows)
    result={'decision_checks':decisions,'changed_decisions':changed,
        'minimum_conditional_or_public_profit_distance_from_threshold':str(minimum_distance),
        'maximum_absolute_probability_mass_discrepancy_before_normalization':str(max_mass),
        'maximum_absolute_reported_metric_difference':str(maxdifference),
        'engine_sha256':engine_hash,'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'design_sha256':hashlib.sha256(text.encode()).hexdigest(),'comparison_rows':len(rows)}
    (output_dir/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    if changed or maxdifference>D('1e-12'): raise AssertionError(result)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    a=parser.parse_args()
    with localcontext() as ctx:
        ctx.prec=80
        print(json.dumps(run(a.input_dir,a.output_dir),indent=2))
