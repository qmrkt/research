"""An exactly solved costly-inspection game with paid work and explicit shirking.

Conditional economic model, not a deployment calibration. Neutral inspectors;
false challenges must be unprofitable. Availability and work audits are explicit
exogenous technologies. All money comes from collateral or a prepaid fee reserve.
"""
from __future__ import annotations
import argparse
import csv
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from random import Random
import statistics

TOL=1e-10

@dataclass(frozen=True)
class GameConfig:
    name: str
    pool: float=10000.
    signed_exposure: float=4000.
    proposer_bond: float=1500.
    challenger_bond: float=1500.
    success_fee: float=20.
    proposal_work_cost: float=5.
    capital_rate_per_window: float=.001
    watcher_capitals: tuple[float,...]=(2000.,2000.,2000.)
    availability: float=.6
    common_outage: float=0.
    adjudication_accuracy: float=.95
    challenger_reward_fraction: float=.5
    challenge_work_cost: float=1.
    inspection_work_cost: float=2.
    completion_payment: float=0.
    audit_probability: float=0.
    work_stake: float=0.
    audit_unit_cost: float=.2
    proposer_capital: float=2000.
    external_reserve: float=100.


def coverage(m,n,u,z=0.):
    return (1-z)*(-math.expm1(n*math.log1p(-u*m))) if n and u*m<1 else (1-z if n and u*m>=1 else 0.)


def bounty_share(m,n,u):
    # Conditional on this inspector being available and actually working; common
    # outage has already been ruled out by its own availability.
    if n==0: return 0.
    if u*m < 1e-12: return 1.
    return coverage(m,n,u)/(n*u*m)


def inspection_best_response_mix(k,R,n,u,f=1.):
    """Symmetric equilibrium effort when conditional fraud f is fixed."""
    if n==0 or u==0: return 0.
    if k < -TOL: return 1.
    if R<=0 or k>=f*R-TOL: return 0.
    if k<=f*R*bounty_share(1.,n,u)+TOL: return 1.
    lo,hi=0.,1.
    for _ in range(80):
        mid=(lo+hi)/2
        if f*R*bounty_share(mid,n,u)>k: lo=mid
        else: hi=mid
    return (lo+hi)/2


def validate(c):
    if c.pool<=0 or abs(c.signed_exposure)>c.pool+TOL:
        raise ValueError('single-market signed exposure must lie in [-pool,pool]')
    if min(c.proposer_bond,c.challenger_bond,c.success_fee,c.inspection_work_cost,c.completion_payment,c.work_stake,c.audit_unit_cost,c.proposal_work_cost,c.capital_rate_per_window,c.challenge_work_cost,c.external_reserve)<0:
        raise ValueError('negative money or costs')
    if any(not 0<=x<=1 for x in (c.availability,c.common_outage,c.adjudication_accuracy,c.challenger_reward_fraction,c.audit_probability)):
        raise ValueError('invalid probability')


def monitoring_equilibrium(c: GameConfig) -> dict:
    validate(c)
    n=sum(K+TOL>=c.challenger_bond+c.work_stake for K in c.watcher_capitals)
    a=c.adjudication_accuracy
    challenge_cost=c.challenge_work_cost+c.capital_rate_per_window*c.challenger_bond
    R=a*c.challenger_reward_fraction*c.proposer_bond-(1-a)*c.challenger_bond-challenge_cost
    false_challenge=(1-a)*c.challenger_reward_fraction*c.proposer_bond-a*c.challenger_bond-challenge_cost
    if false_challenge>TOL:
        raise ValueError('profitable false challenge: outside neutral-inspector subgame')
    stake_cost=c.capital_rate_per_window*c.work_stake
    shirk_utility=(1-c.audit_probability)*c.completion_payment-c.audit_probability*c.work_stake-stake_cost
    outside=max(0.,shirk_utility)
    k=c.inspection_work_cost+stake_cost-c.completion_payment+outside
    qmax=coverage(1,n,c.availability,c.common_outage) if R>TOL else 0.
    truth_pay=c.success_fee-c.proposal_work_cost-c.capital_rate_per_window*c.proposer_bond
    required_reserve=c.success_fee+n*(c.completion_payment+c.audit_unit_cost)
    if c.audit_probability==0: required_reserve-=n*c.audit_unit_cost
    launch=c.external_reserve+TOL>=required_reserve
    capital_ok=c.proposer_capital+TOL>=c.proposer_bond
    def delta(q):
        r=a*q
        return (1-r)*c.signed_exposure-r*(c.proposer_bond+c.success_fee)
    # If truthful entry is loss-making, every submitted proposal must be false.
    # Check the inspection best response to that off-path posterior explicitly.
    status='equilibrium'; submits=True
    if truth_pay < -TOL:
        f=1.
        m=inspection_best_response_mix(k,max(R,0),n,c.availability)
        q=coverage(m,n,c.availability,c.common_outage) if R>TOL else 0.
        if truth_pay+delta(q)<=TOL:
            submits=False; status='no_profitable_proposal'
    elif c.signed_exposure<=TOL:
        f=0.; m=1. if k < -TOL and n and c.availability else 0.
    elif R<=TOL or not n or c.availability==0 or c.common_outage==1:
        f=1.; m=1. if k < -TOL and n and c.availability else 0.
    elif k < -TOL:
        m=1.; f=1. if delta(qmax)>TOL else 0.
    elif delta(qmax)>TOL:
        f=1.; m=inspection_best_response_mix(k,R,n,c.availability)
    else:
        # Proposer indifference pins challenge coverage; inspector indifference
        # pins fraud prevalence. Paid effort k=0 is a weak boundary equilibrium.
        qstar=c.signed_exposure/(a*(c.signed_exposure+c.proposer_bond+c.success_fee))
        target=qstar/(1-c.common_outage)
        mstar=-math.expm1(math.log1p(-min(target,1.))/n)/c.availability if target<1 else 1/c.availability
        mstar=min(1.,max(0.,mstar))
        fstar=max(0.,k)/(R*bounty_share(mstar,n,c.availability))
        if fstar<=1+TOL:
            m=mstar; f=min(1.,fstar)
        else:
            f=1.; m=inspection_best_response_mix(k,R,n,c.availability)
    if not launch: submits=False; status='insufficient_external_reserve'
    if not capital_ok: submits=False; status='proposer_capital_ineligible'
    qinspect=coverage(m,n,c.availability,c.common_outage)
    q=qinspect if R>TOL else 0.
    correction=a*q
    shirk=1-m if shirk_utility>TOL else 0.
    reports=m+shirk
    active_probability=(1-c.common_outage)*c.availability
    expected_inspections=n*active_probability*m if submits else 0.
    expected_shirks=n*active_probability*shirk if submits else 0.
    expected_reports=expected_inspections+expected_shirks
    external=(c.success_fee*(1-f*correction)+c.completion_payment*(expected_inspections+(1-c.audit_probability)*expected_shirks)+c.audit_probability*c.audit_unit_cost*expected_reports) if submits else 0.
    real_cost=(c.proposal_work_cost+c.capital_rate_per_window*c.proposer_bond+c.inspection_work_cost*expected_inspections+stake_cost*expected_reports+c.audit_probability*c.audit_unit_cost*expected_reports+f*q*challenge_cost) if submits else 0.
    verify_utility=c.completion_payment-c.inspection_work_cost-stake_cost+f*max(R,0)*bounty_share(m,n,c.availability)
    # Maximum pure-action gains; verifies closed-form equilibrium independently.
    inspector_regret=(max(verify_utility,shirk_utility,0.)-(m*verify_utility+shirk*shirk_utility)) if n and active_probability>0 and submits else 0.
    proposer_util=truth_pay+f*delta(q)
    proposer_regret=max(truth_pay,truth_pay+delta(q),0.)-proposer_util if submits else max(0.,truth_pay,truth_pay+delta(q))
    if not launch or not capital_ok: proposer_regret=0.
    result={**asdict(c),'eligible_watchers':n,'truthful_participation_margin':truth_pay,
        'required_external_reserve':required_reserve,'funding_feasible':launch,'status':status,
        'submitted':submits,'fraud_given_submission':f,'inspect_given_available':m,'shirk_given_available':shirk,
        'inspection_coverage':qinspect,'challenge_coverage_given_false':q,'correction_given_false':correction,
        'false_finalization_rate':float(submits)*f*(1-correction),'no_proposal_rate':float(not submits),
        'accepted_correct_rate':float(submits)*(1-f*(1-correction)),
        'correct_challenge_surplus':R,'false_challenge_surplus':false_challenge,
        'audit_effort_margin':c.audit_probability*(c.completion_payment+c.work_stake)-c.inspection_work_cost,
        'shirking_utility':shirk_utility,'effective_inspection_cost':k,
        'max_possible_correction':a*qmax,'fraud_gain_given_monitoring':delta(q),
        'expected_inspections':expected_inspections,'expected_shirks':expected_shirks,
        'expected_external_spend':external,'expected_real_cost':real_cost,
        'inspector_best_response_regret':max(0.,inspector_regret),'proposer_best_response_regret':max(0.,proposer_regret)}
    if max(result['inspector_best_response_regret'],result['proposer_best_response_regret'])>1e-7:
        raise AssertionError(result)
    return result


def simulate(c,result,seed,episodes,keep=100):
    rng=Random(seed)
    eligible=[i for i,K in enumerate(c.watcher_capitals) if K+TOL>=c.challenger_bond+c.work_stake]
    totals={k:[] for k in ('false_finalization_rate','expected_inspections','expected_shirks','expected_external_spend','expected_real_cost')}
    traces=[]; max_error=0.; max_spend=0.
    for t in range(episodes):
        if not result['submitted']:
            record={k:0. for k in totals}; record.update({'fraud':False,'challenged':False,'corrected':False,'proposer':0.,'watchers':0.,'protocol':0.,'external':0.,'auditor':0.,'counterparty':0.,'money_balance':0.})
        else:
            fraud=rng.random()<result['fraud_given_submission']
            up=rng.random()>=c.common_outage
            inspectors=[]; shirks=[]; reports=[]
            for i in eligible:
                if up and rng.random()<c.availability:
                    x=rng.random()
                    if x<result['inspect_given_available']: inspectors.append(i); reports.append(i)
                    elif x<result['inspect_given_available']+result['shirk_given_available']: shirks.append(i); reports.append(i)
            ledger={'proposer':0.,'watchers':0.,'protocol':0.,'external':0.,'auditor':0.,'counterparty':0.}
            audit_count=0
            for i in reports:
                audited=rng.random()<c.audit_probability
                audit_count+=audited
                if audited:
                    ledger['external']-=c.audit_unit_cost; ledger['auditor']+=c.audit_unit_cost
                if i in shirks and audited:
                    ledger['watchers']-=c.work_stake; ledger['protocol']+=c.work_stake
                else:
                    ledger['external']-=c.completion_payment; ledger['watchers']+=c.completion_payment
            challenged=bool(fraud and inspectors and result['correct_challenge_surplus']>TOL)
            corrected=challenged and rng.random()<c.adjudication_accuracy
            if challenged:
                rng.choice(inspectors)  # fair first claimant; group ledger unchanged
                if corrected:
                    ledger['proposer']-=c.proposer_bond
                    ledger['watchers']+=c.challenger_reward_fraction*c.proposer_bond
                    ledger['protocol']+=(1-c.challenger_reward_fraction)*c.proposer_bond
                else:
                    ledger['watchers']-=c.challenger_bond; ledger['protocol']+=c.challenger_bond
            wrong=fraud and not corrected
            if wrong:
                ledger['proposer']+=c.signed_exposure; ledger['counterparty']-=c.signed_exposure
            if not corrected:
                ledger['proposer']+=c.success_fee; ledger['external']-=c.success_fee
            real=c.proposal_work_cost+c.capital_rate_per_window*c.proposer_bond+len(inspectors)*c.inspection_work_cost+len(reports)*c.capital_rate_per_window*c.work_stake+audit_count*c.audit_unit_cost+challenged*(c.challenge_work_cost+c.capital_rate_per_window*c.challenger_bond)
            record={'false_finalization_rate':float(wrong),'expected_inspections':len(inspectors),'expected_shirks':len(shirks),'expected_external_spend':-ledger['external'],'expected_real_cost':real,'fraud':fraud,'challenged':challenged,'corrected':corrected,**ledger,'money_balance':sum(ledger.values())}
        max_error=max(max_error,abs(record['money_balance'])); max_spend=max(max_spend,record['expected_external_spend'])
        if abs(record['money_balance'])>1e-8 or record['expected_external_spend']>c.external_reserve+1e-8:
            raise AssertionError(record)
        for k in totals: totals[k].append(record[k])
        if t<keep: traces.append({'config':c.name,'seed':seed,'episode':t,**record})
    summaries=[]
    for metric,values in totals.items():
        avg=statistics.mean(values); se=statistics.stdev(values)/math.sqrt(episodes)
        summaries.append({'config':c.name,'seed':seed,'episodes':episodes,'metric':metric,'exact':result[metric],
            'mean':avg,'standard_error':se,'ci95_lower':avg-1.96*se,'ci95_upper':avg+1.96*se,
            'error':avg-result[metric],'max_money_balance_error':max_error,'max_external_spend':max_spend})
    return summaries,traces


def designed_configs():
    base=GameConfig('bounty_only')
    paid=replace(base,name='paid_audited',completion_payment=3.,audit_probability=.5,work_stake=2.)
    return (base, replace(paid,name='paid_unaudited',audit_probability=0.),paid,
        replace(paid,name='paid_weak_audit',audit_probability=.1),
        replace(paid,name='unfunded_proposal_work',success_fee=0.),
        replace(paid,name='no_challenge_capital',watcher_capitals=(100.,100.,100.)),
        replace(paid,name='budget_shortfall',external_reserve=10.),
        replace(paid,name='whole_pool_exposure_90pct_judge',signed_exposure=10000.,adjudication_accuracy=.9),
        replace(paid,name='whole_pool_exposure_95pct_judge',signed_exposure=10000.),
        replace(paid,name='common_outage',common_outage=.3),
        replace(paid,name='truth_winner',signed_exposure=-4000.),
        replace(base,name='one_watcher',watcher_capitals=(2000.,)),
        replace(base,name='eight_watchers',watcher_capitals=(2000.,)*8),
        replace(paid,name='inaccurate_judge',adjudication_accuracy=.6),
        replace(base,name='rare_fraud_high_reward',proposer_bond=10000.,challenger_bond=10000.,watcher_capitals=(15000.,)*3,proposer_capital=15000.))


def fresh_configs():
    rng=Random(908731)
    configs=[]
    for i in range(64):
        L=rng.choice((100.,1000.,10000.)); bond=rng.choice((.05,.1,.15,.3,.6))*L
        cost=rng.uniform(.1,10); n=rng.choice((1,3,8))
        c=GameConfig(f'fresh_{i:03d}',pool=L,signed_exposure=rng.uniform(-.25,1)*L,
            proposer_bond=bond,challenger_bond=bond,success_fee=6+.001*bond,
            watcher_capitals=tuple(rng.choice((.5,1.,2.,5.))*bond for _ in range(n)),
            availability=rng.choice((.2,.5,.8)),common_outage=rng.choice((0.,.1,.25)),
            adjudication_accuracy=rng.uniform(.7,.99),inspection_work_cost=cost,
            audit_unit_cost=.1*cost,proposer_capital=2*bond,external_reserve=1e6)
        configs.extend((c,replace(c,name=c.name+'_paid_unaudited',completion_payment=1.25*cost,work_stake=3*cost),
            replace(c,name=c.name+'_paid_audited',completion_payment=1.25*cost,work_stake=3*cost,audit_probability=.5)))
    return tuple(configs)


def write_csv(path,rows):
    if not rows: return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader();w.writerows(rows)


def summarize_frontiers(output_dir,fresh_rows):
    # This additional descriptive grid is recorded separately after the first
    # study; it is not used to select or tune any rule in the frozen experiment.
    grid={'status':'Subsequent descriptive capital/budget feasibility grid; no optimization or held-out performance claim.',
        'bond_fraction':[.05,.1,.15,.3,.6],'watchers':[1,3,8],
        'capital_per_watcher':[500.,1500.,2000.,5000.,10000.],
        'external_reserve':[20.,25.,30.,50.,100.],'adjudication_accuracy':[.8,.9,.95],
        'fixed':'Pool10000,D4000,availability.6,F20,workc2,w3,delta.5,S2,auditcost.2,proposer capital10000.'}
    (output_dir/'capital_frontier_design.json').write_text(json.dumps(grid,indent=2)+'\n')
    from itertools import product
    frontier=[]
    for i,(rho,n,K,M,a) in enumerate(product(grid['bond_fraction'],grid['watchers'],grid['capital_per_watcher'],grid['external_reserve'],grid['adjudication_accuracy'])):
        c=GameConfig(f'capital_{i:04d}',proposer_bond=rho*10000,challenger_bond=rho*10000,
            watcher_capitals=(K,)*n,external_reserve=M,adjudication_accuracy=a,proposer_capital=10000.,
            completion_payment=3.,audit_probability=.5,work_stake=2.)
        r=monitoring_equilibrium(c)
        frontier.append({k:r[k] for k in ('name','proposer_bond','challenger_bond','watcher_capitals','external_reserve','adjudication_accuracy','eligible_watchers','status','truthful_participation_margin','required_external_reserve','fraud_given_submission','challenge_coverage_given_false','false_finalization_rate','accepted_correct_rate','expected_external_spend')})
    write_csv(output_dir/'capital_frontier.csv',frontier)
    base={r['name']:r for r in fresh_rows if '_paid_' not in r['name']}
    arms={suffix:{r['name'].replace('_'+suffix,''):r for r in fresh_rows if r['name'].endswith(suffix)} for suffix in ('paid_unaudited','paid_audited')}
    pairs=[]
    for key,b in base.items():
        u,a=arms['paid_unaudited'][key],arms['paid_audited'][key]
        pairs.append({'regime':key,'base_wrong':b['false_finalization_rate'],'unaudited_wrong':u['false_finalization_rate'],'audited_wrong':a['false_finalization_rate'],
            'audit_minus_unaudited':a['false_finalization_rate']-u['false_finalization_rate'],
            'audited_minus_bounty':a['false_finalization_rate']-b['false_finalization_rate'],
            'bounty_eligible':b['eligible_watchers'],'paid_eligible':a['eligible_watchers'],
            'base_external_spend':b['expected_external_spend'],'unaudited_external_spend':u['expected_external_spend'],'audited_external_spend':a['expected_external_spend']})
    write_csv(output_dir/'fresh_pairs.csv',pairs)
    aggregates=[]
    for label,rows in (('bounty_only',list(base.values())),('paid_unaudited',list(arms['paid_unaudited'].values())),('paid_audited',list(arms['paid_audited'].values()))):
        aggregates.append({'arm':label,'regimes':len(rows),'mean_false_finalization':statistics.mean(r['false_finalization_rate'] for r in rows),
            'mean_challenge_coverage':statistics.mean(r['challenge_coverage_given_false'] for r in rows),
            'mean_external_spend':statistics.mean(r['expected_external_spend'] for r in rows),
            'zero_fraud_regimes':sum(r['fraud_given_submission']==0 for r in rows),
            'no_proposal_regimes':sum(not r['submitted'] for r in rows)})
    write_csv(output_dir/'fresh_summary.csv',aggregates)


def run(output_dir,episodes=20000):
    output_dir.mkdir(parents=True,exist_ok=True)
    designed=designed_configs(); fresh=fresh_configs();seeds=(730001,730003,730009)
    design={'status':'Local plan written before outcomes; not external preregistration or empirical calibration.',
        'game':'Symmetric Bayes-Nash verify/shirk/idle subgame with truth/false/abstain proposer; neutral checkers, no profitable false challenges, perfect inspection of submitted content, noisy adjudication, independent availability conditional on common uptime. Proposer does not observe common outage before acting.',
        'audit_assumption':'Probability delta is effective detection of skipped work under an independently enforceable work audit, not inference from a self-reported receipt. Honest work has no false flags in this model. No such audit technology is empirically established here.',
        'fees':'Accepted proposal receives F from prepaid external reserve, including a falsely accepted proposal. No defense reward; failed challenge bond entirely to protocol. Successful challenger receives eta of proposer bond; remainder protocol. Paid work is outcome neutral; fraudulent fake work can be audited/slashed.',
        'funding':'Worst-case external reserve F+n(w+audit unit cost), or F+nw when no audits; unused money remains external. Work stake S and challenge bond Bc require simultaneous free capital Bc+S. Monetary transfers balance; real costs separately recorded.',
        'selection':'No fitted coefficient or performance-selected regime. All designed controls and64 fresh base regimes with3 arms are reported.',
        'designed':[asdict(c) for c in designed],'fresh_seed':908731,'fresh':[asdict(c) for c in fresh],
        'mc_seeds':seeds,'mc_episodes_per_seed_config':episodes,
        'raw_trace_retention':'First100 episodes per seed/config; all episode streams deterministically regenerable. Money/reserve assertions run on every episode, not just retained traces.'}
    text=json.dumps(design,sort_keys=True,indent=2)+'\n'
    p=output_dir/'design.json'
    if p.exists() and p.read_text()!=text: raise ValueError('design changed; use new directory')
    p.write_text(text)
    exact=[monitoring_equilibrium(c) for c in designed]
    fresh_rows=[monitoring_equilibrium(c) for c in fresh]
    mc=[];traces=[]
    for c,r in zip(designed,exact):
        for seed in seeds:
            m,t=simulate(c,r,seed,episodes);mc.extend(m);traces.extend(t)
    # Conditional deterrence frontier independent of behavioral equilibrium.
    bounds=[]
    for d in (.1,.4,1.):
        for rho in (.05,.1,.15,.3,.6):
            for a in (.6,.8,.9,.95,.99):
                required=d/(a*(d+rho))
                bounds.append({'exposure_over_pool':d,'bond_over_pool':rho,'adjudication_accuracy':a,'challenge_coverage_required_no_fee':required,'feasible_with_perfect_coverage':required<=1})
    write_csv(output_dir/'equilibria.csv',exact);write_csv(output_dir/'fresh_regimes.csv',fresh_rows)
    write_csv(output_dir/'monte_carlo.csv',mc);write_csv(output_dir/'episode_samples.csv',traces)
    write_csv(output_dir/'deterrence_frontier.csv',bounds)
    summarize_frontiers(output_dir,fresh_rows)
    result={'design_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'designed_configs':len(designed),'fresh_base_regimes':64,'fresh_rows':len(fresh_rows),
        'mc_episodes':len(designed)*len(seeds)*episodes,'max_money_balance_error':max(r['max_money_balance_error'] for r in mc),
        'max_equilibrium_regret':max(max(r['inspector_best_response_regret'],r['proposer_best_response_regret']) for r in exact+fresh_rows)}
    (output_dir/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--episodes',type=int,default=20000)
    a=p.parse_args();print(json.dumps(run(a.output_dir,a.episodes),indent=2))
