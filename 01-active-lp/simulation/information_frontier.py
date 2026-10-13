"""Transparent follow-up: participation/correction frontier and cohort allocation.

The initial outcome and flow-alignment studies remain archived. This extension
expands the near-zero lambda grid and adds the founder's actual counterfactual
payoff when the entrant declines. It never selects a rule on held-out regimes.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import statistics
from research.active_lp.information_timing import (
    TimingRegime, causal_regimes, evaluate_regime, effect_row, population_regimes,
    write_csv, YEAR_SECONDS,
)
from research.active_lp.events import BootstrapMarket, BuyOutcome, LpEnterActive, ResolveMarket, ClaimWinnings
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    ReferenceParallelLmsrEngine, ReferenceInvariantChecker, create_initial_state,
    RESERVE_POOL, STRICT_ALL_CLAIMED,
)
D = Decimal
GRID = (0, .000001, .00001, .0001, .00025, .0005, .001, .0025, .005,
        .01, .025, .05, .075, .1, .15, .25, .5, 1, 2, 4)

@lru_cache(maxsize=None)
def founder_cash(pre, future, fee, extra, days, rule, lam, winner, flow, entered):
    # With no entrant there is one cohort: its return is rule independent.
    if not entered and (rule != 'flat' or lam != 0):
        return founder_cash(pre, future, fee, extra, days, 'flat', 0, winner, flow, False)
    policy = STRICT_ALL_CLAIMED if rule == 'isolated_cohort' else RESERVE_POOL
    scheme = 'linear_lambda_normalized' if rule == 'normalized' else 'flat'
    engine = ReferenceParallelLmsrEngine(lp_fee_bps=fee, protocol_fee_bps=25,
        residual_policy=policy, residual_weight_scheme=scheme, residual_linear_lambda=D(str(lam)))
    state = create_initial_state(3, residual_weight_scheme=scheme, residual_linear_lambda=D(str(lam)))
    end = days * 86400
    with high_precision():
        funding = collateral_required(D(100), uniform_price_vector(3)) + D(extra)
    state = engine.apply_event(state, BootstrapMarket(0, 'creator', funding, D(100)))
    if pre:
        state = engine.apply_event(state, BuyOutcome(end//3, 'public_trader', 0, D(pre), D('1e50')))
    if entered:
        state = engine.apply_event(state, LpEnterActive(end//2, 'entrant', D(20), D('1e50'), state.pricing.price_vector, D('1e-18')))
    if future:
        state = engine.apply_event(state, BuyOutcome(2*end//3, 'future_trader', flow, D(future), D('1e50')))
    state = engine.apply_event(state, ResolveMarket(end, winner))
    for trader, holdings in list(state.traders.positions_by_trader.items()):
        if holdings[winner] > 0:
            state = engine.apply_event(state, ClaimWinnings(end+1, trader, winner, holdings[winner]))
    checks = ReferenceInvariantChecker(residual_policy=policy).check_all(state)
    if any(not c.passed for c in checks):
        raise AssertionError([asdict(c) for c in checks if not c.passed])
    nav = engine.mark_to_market_nav(state)
    out = {}
    for key,sponsor in state.sponsors.items():
        prefix = 'founder' if sponsor.sponsor_id == 'creator' else 'entrant'
        out[prefix+'_deposit'] = float(sponsor.collateral_posted)
        out[prefix+'_cash_profit'] = float(nav[key]-sponsor.collateral_posted)
    return out


def allocation_rows(regime, rule, lam):
    summaries, raw = evaluate_regime(regime, rule, lam, 'flow_alignment')
    effect = effect_row(summaries)
    aggregates = []
    for policy in ('late_committed','late_public_optional','late_private_optional'):
        weighted_profit = weighted_return = entered_return = entered_profit = entry_rate = 0.0
        for row in raw:
            entered = row[policy+'_enter']
            cash = founder_cash(regime.pre_shares, regime.future_shares, regime.lp_fee_bps,
                regime.bootstrap_extra, regime.duration_days, rule, lam, row['winner'],
                row['future_flow_direction'], entered)
            profit = cash['founder_cash_profit']-cash['founder_deposit']*regime.annual_opportunity_cost*regime.duration_days/365
            ret = profit/cash['founder_deposit']
            row[policy+'_founder_net_profit'] = profit
            row[policy+'_founder_return'] = ret
            if entered:
                # Independently executed founder path must reproduce entrant cash.
                if abs(cash['entrant_cash_profit']-row['late_cash_profit']) > 1e-10:
                    raise AssertionError('paired founder/entrant path differs')
            p = row['probability']
            weighted_profit += p*profit; weighted_return += p*ret
            entered_profit += p*profit*entered; entered_return += p*ret*entered
            entry_rate += p*entered
        entrant_summary = next(s for s in summaries if s['policy']==policy)
        entrant_offered = entrant_summary['mean_return_per_offered_capital']
        entrant_conditional = entrant_offered/entry_rate if entry_rate > 1e-12 else None
        founder_conditional = entered_return/entry_rate if entry_rate > 1e-12 else None
        aggregates.append({**asdict(regime), 'regime':regime.name,'rule':rule,'lambda':lam,'policy':policy,
            'entry_rate':entry_rate,'entrant_offered_return':entrant_offered,
            'entrant_conditional_return':entrant_conditional,
            'founder_mean_net_profit':weighted_profit,'founder_unconditional_return':weighted_return,
            'founder_conditional_net_profit':entered_profit/entry_rate if entry_rate > 1e-12 else None,
            'founder_conditional_return':founder_conditional,
            'offered_entrant_minus_actual_founder_gap':entrant_offered-weighted_return,
            'conditional_entrant_minus_founder_gap':entrant_conditional-founder_conditional if entry_rate > 1e-12 else None,
            'information_value':effect['private_information_value'],
            'committed_early_late_effect':effect['committed_delay_effect']})
    return aggregates, raw, effect


def run(output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    train,holdout = population_regimes('train'),population_regimes('holdout')
    sensitivities = tuple(replace(r, signal_accuracy=.5) if r.name=='uninformative_signal' else r for r in causal_regimes())
    design = {
        'status':'Transparent subsequent extension after initial outcome/alignment population outcomes, frozen before this expanded grid and founder-payoff run. No external preregistration.',
        'signal':'Same binary flow-alignment signal as preceding extension; accuracy .5 is null.',
        'purpose':'Separate fundamental information option value from normalized weighting cohort-return-gap target. Expand near-zero grid without selecting on holdout.',
        'grid':GRID,'train':[asdict(r) for r in train],'holdout':[asdict(r) for r in holdout],
        'sensitivities':[asdict(r) for r in sensitivities],
        'founder_definition':'Founder is always funded from t=0. On entrant declines the entire market is rerun without entrant depth/collateral; founder profit is NOT zeroed. Conditional founder return additionally conditions on entrant entry. Deduct founder full-duration 5% APR opportunity cost.',
        'gap_definitions':{'offered':'Entrant net profit / offered collateral (declines zero), minus founder unconditional net return under same actual policy.', 'conditional':'Entrant minus founder net return, both conditional on entrant entry; separately reported, not used as the information estimand.'},
        'selection':'Retain previous strict constraint (every flat public-profitable train regime remains profitable, and mean private entry at least half baseline). Select among expanded grid on train only. Also report nonselected frontier without imposing this normative constraint.',
        'boundary':'If positive feasible candidates exist but selected is zero, report zero as grid optimum; this is not an impossibility theorem over untested lambdas. If max feasible positive is below first infeasible, preserve bracket rather than assert exact cutoff.',
    }
    text=json.dumps(design,indent=2,sort_keys=True)+'\n'
    path=output_dir/'design.json'
    if path.exists() and path.read_text()!=text: raise ValueError('design changed')
    path.write_text(text)
    all_rows,worlds,effects,frontier=[],[],[],[]
    baseline_eligible=None; baseline_entry=None
    for split,regimes in (('train',train),('holdout',holdout)):
        for lam in GRID:
            current=[]
            for regime in regimes:
                rows,raw,effect=allocation_rows(regime,'normalized',lam)
                all_rows.extend({'split':split,**r} for r in rows)
                worlds.extend({'split':split,**r} for r in raw)
                effects.append({'split':split,**effect}); current.extend(rows)
            by={p:[r for r in current if r['policy']==p] for p in ('late_committed','late_public_optional','late_private_optional')}
            if split=='train' and lam==0:
                baseline_eligible={r['regime'] for r in by['late_committed'] if r['entrant_offered_return']>1e-12}
                baseline_entry=statistics.mean(r['entry_rate'] for r in by['late_private_optional'])
            preserved=sum(r['entrant_offered_return']>1e-12 for r in by['late_committed'] if r['regime'] in baseline_eligible) if split=='train' else None
            private_entry=statistics.mean(r['entry_rate'] for r in by['late_private_optional'])
            item={'split':split,'lambda':lam,'mean_information_value':statistics.mean(r['information_value'] for r in by['late_committed']),
                'mean_public_return':statistics.mean(r['entrant_offered_return'] for r in by['late_public_optional']),
                'mean_private_return':statistics.mean(r['entrant_offered_return'] for r in by['late_private_optional']),
                'public_entry_rate':statistics.mean(r['entry_rate'] for r in by['late_public_optional']),
                'private_entry_rate':private_entry,'baseline_profitable_train_preserved':preserved,
                'strict_train_feasible':preserved==len(baseline_eligible) and private_entry>=.5*baseline_entry-1e-12 if split=='train' else None}
            for p,rows in by.items():
                for name in ('founder_unconditional_return','offered_entrant_minus_actual_founder_gap'):
                    item[p+'_'+name]=statistics.mean(r[name] for r in rows)
                active=[r for r in rows if r['conditional_entrant_minus_founder_gap'] is not None]
                item[p+'_active_regimes']=len(active)
                item[p+'_conditional_gap_among_active_regimes']=statistics.mean(r['conditional_entrant_minus_founder_gap'] for r in active) if active else None
            frontier.append(item)
    # Separate bootstrap/fees/signal/flow/lockup sensitivities, not selection data.
    for regime in sensitivities:
        for rule,lam in (('flat',0.),('normalized',.15),('isolated_cohort',0.)):
            rows,raw,effect=allocation_rows(regime,rule,lam)
            all_rows.extend({'split':'sensitivity',**r} for r in rows)
            worlds.extend({'split':'sensitivity',**r} for r in raw)
            effects.append({'split':'sensitivity',**effect})
    feasible=[r for r in frontier if r['split']=='train' and r['strict_train_feasible']]
    selected=min(feasible,key=lambda r:(r['mean_information_value'],r['lambda']))
    write_csv(output_dir/'frontier.csv',frontier)
    write_csv(output_dir/'cohort_allocation.csv',all_rows)
    write_csv(output_dir/'worlds.csv',worlds)
    write_csv(output_dir/'causal_effects.csv',effects)
    result={'selected_lambda':selected['lambda'],'selection':selected,
        'strict_feasible_lambdas':[r['lambda'] for r in feasible],
        'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'design_sha256':hashlib.sha256(text.encode()).hexdigest(),'world_rows':len(worlds),
        'reference_engine_sha256':hashlib.sha256(Path(__file__).with_name('reference_parallel_lmsr.py').read_bytes()).hexdigest()}
    (output_dir/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.output_dir),indent=2))
