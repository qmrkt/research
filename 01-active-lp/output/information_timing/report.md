# Causal information and optional LP participation

This directory reports a finite-state synthetic intervention on the information available to an LP at a fixed entry opportunity. The model exhibits strictly positive information value, while also recording economically informative nulls. Its experiments distinguish (i) information used to accept or decline the same offer, (ii) committing before versus after public news, and (iii) the allocation of returns between a founder and an optional later entrant. These are different estimands.

All returns below are net of the posted collateral and its simple opportunity cost. Percentages are returns per **offered** collateral, with zero incremental profit on declined offers. A policy that always declines is never described as evidence that liquidity provision is profitable. Positive expected profit conditional on participation does not eliminate realized losses; `policy_summary.csv` reports loss probabilities, lower tails, standard deviations, deployed collateral, and capital days.

## Model and identification

There are three outcomes, bootstrap LMSR depth 100, and entrant depth 20. Canonical bootstrap funding is the minimum `100 log(3)`; extra funding is zero. The 16-case sensitivity study additionally tests bootstrap funding plus 20. A public trade of a fixed number of shares moves the price in a public direction U. U is uniformly distributed among the three outcome labels. The external probability of the eventual winner W, conditional on U, equals the price of the baseline market after that public trade. This external outcome distribution is held fixed across LP policies: adding an early LP cannot change the true event.

By outcome-label symmetry, enumeration conditions on U=0 without changing expected returns. There are nine distinct economic worlds `(W, F)` for the winner and future order direction. The signal labels split their probabilities into 27 outcome-signal or 18 alignment-signal rows; these rows are not independent experimental observations. Conditional on W, the future order buys W with probability eta, and each other outcome with probability `(1-eta)/2`. Quantities, events, W, and F are the same potential environment across LP policies. Prices may respond to the extra depth. There is one public buy and one later buy, no endogenous trader response, no strategic LP competition, and no sell/cancellation event in this study.

An early LP enters at one second, before the public buy at one third of the market duration. A delayed LP decides at half duration, before the future buy at two thirds. Resolution occurs at the end. Canonical duration is 30 days; annual outside-capital return is 5%. LP fees are 100 basis points and protocol fees 25 basis points, with explicit fee sensitivities. The founder remains funded for the entire duration; the delayed LP funds half the duration. The same delayed price, deposit, and clock are presented to informed and public-information policies.

The outcome-signal experiment observes S with `P(S=W)=q`, otherwise each wrong label equally likely. Its uninformative control is **q=1/3**. Conditional on W, S and future order direction are independent. The subsequent flow-alignment extension instead observes a binary noisy signal of `A=1{F=W}` with `P(S=A)=q`. Its uninformative control is **q=1/2**. The latter is a predictive signal about future flow adversity; it does not reveal a price change or realized cashflow. It is a different information hypothesis and is explicitly reported as a follow-up to the original outcome-signal results, not a replacement for them.

For realized entrant profit X (including fees, minus deposit and opportunity cost), the public policy enters iff `E[X] > 0`; the private policy enters iff `E[X|S] > 0`. Expectations are evaluated over all finite states, not estimated from realized test profits. There is no tuned decision threshold, and signal acquisition is assumed free. The information estimand is

`I = (E[max(0, E[X|S])] - max(0, E[X])) / D`.

D is the same offered collateral across signals within a regime. Convexity gives I >= 0. A nondegenerate conditional expectation on both sides of zero gives strict value. Numerical decision ties use a `1e-12` threshold. This general decision result does not imply that a particular signal predicts LP profitability, nor that the uninformed market attracts any LPs.

## Original outcome-signal results

The root files preserve the original 16 predeclared sensitivity cases, including null and unfavorable outcomes. In the canonical case, flat pooled, normalized lambda .15, and isolated-cohort policies all decline, even with a perfect outcome signal. Forced late entry loses 31.63%, 35.39%, and 20.24%, respectively. In this orderflow model, knowing which outcome wins does not necessarily reveal whether dealing against isotropically informed flow is profitable.

The `uninformed_future_flow` case provides a small strict effect under flat pooling: information value 0.1901 percentage points, public entry 0%, private entry 60.09%. Normalized .15 eliminates entry; isolated cohorts have public and private expected returns both 4.1068%, so the signal has no option value. The `high_noise_demand` case supports profitable LP participation under all three rules (flat 39.9939%, normalized 32.3460%, isolated 42.6116%), but everyone enters and information has zero option value. This separates profitability from information value.

The subsequent `outcome_population` study uses 27 equal-weight training regimes and 32 disjoint held-out parameter combinations. Held-out results are:

| Rule | Information value (percentage points) | Public return | Private return | Public entry | Private entry | Strict-value regimes |
|---|---:|---:|---:|---:|---:|---:|
| Flat pool | 0.2762 | 0.5061% | 0.7823% | 12.50% | 11.10% | 6/32 |
| Normalized .15 | 0.1959 | 0% | 0.1959% | 0% | 7.83% | 4/32 |
| Isolated cohorts | 0 | 2.4601% | 2.4601% | 25% | 25% | 0/32 |

Private information can reduce the frequency of entry while increasing expected profit: a useful signal can tell an LP to avoid loss-making offers.

## Flow-adversity information results

The `flow_alignment` follow-up uses the same training/held-out economic grids, changing only the signal target. It produces substantial strict information value at an unchanged entry opportunity:

| Rule | Information value (percentage points) | Public return | Private return | Public entry | Private entry | Strict-value regimes |
|---|---:|---:|---:|---:|---:|---:|
| Flat pool | 3.5822 | 0.5061% | 4.0884% | 12.50% | 24.75% | 16/32 |
| Normalized .15 | 2.7607 | 0% | 2.7607% | 0% | 15.38% | 10/32 |
| Isolated cohorts | 5.7453 | 2.4601% | 8.2054% | 25% | 43% | 28/32 |

For a concrete strict-value illustration, pre-trade 10 shares, future trade 240 shares, flow alignment probability .5, and signal accuracy .8 (`train_007`) give a flat entrant deposit of 22.6614. Conditional expected net profits are +14.3903 after a favorable signal and -9.5817 after an adverse signal. Public entry has expected net return 10.6097%; the optional informed policy has 31.7507%, entering half the time. This is direct support for the strict sign-crossing mechanism. It is one illustrative member of a fully reported population, not the sole evidentiary case.

## Correction and participation are separate questions

A normalized residual weighting correction is an allocation rule, not a method for destroying all decision-theoretic value of information. The experiments report its effect on information value separately from cohort return gaps. In the flow-alignment train population, .15 lowers the mean information advantage from 3.6850 to 3.1068 percentage points but also reduces public entry from 18.52% to 11.11% and private entry from 23.11% to 17.48%. In the held-out population it eliminates public entry. These are participation tradeoffs, not a free improvement.

Moreover, .15 *increases* information value in the three train regimes whose public entry remains profitable: `train_006` 7.5098 to 9.2774 points, `train_007` 21.1409 to 22.7046 points, and `train_015` 10.2902 to 11.9070 points. A correction can reduce public expected profit more than informed optional profit. This does not by itself establish whether it improves the separate founder/entrant allocation target.

The first train-only lambda sweep imposed a deliberately conservative safeguard: every public-profitable flat train regime must remain public-profitable, and mean private participation must retain at least half its flat level. It selected lambda zero from its initial grid. The safeguard is a stated normative constraint, not a necessary welfare axiom. The `frontier` extension expands the grid below .01 and reports all participation/return tradeoffs, including options that violate that strict safeguard. It also measures the founder's actual payoff in both entry and decline worlds, so founder income is never set to zero merely because the entrant declines. The extension was designed after inspecting the initial outcomes; its held-out frontier is descriptive and does not choose lambda.

## Expanded correction frontier and founder returns

The expanded train-only grid includes 0, .000001, .00001, .0001, .00025, .0005, .001, .0025, .005, .01, .025, .05, .075, .1, .15, .25, .5, 1, 2, and 4. **Lambda .005 is the grid optimum under the strict original safeguard**, preserving all five public-profitable train regimes and unchanged aggregate private participation. All grid values through .005 are feasible; .01 is not. This is a grid optimum with a feasibility boundary bracketed between .005 and .01, not a claim about an exact continuous optimum. The original coarser-grid zero result is retained rather than overwritten.

On the held-out grid, the selected .005 retains the same public and private participation rates while slightly reducing both information advantage and the ex ante late-versus-founder return gap. The following larger coefficients are a descriptive frontier, not additional rules selected on held-out performance:

| Lambda | Information value (points) | Public return | Private return | Public entry | Private entry | Founder actual return | Informed entrant minus founder (points) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 3.5822 | 0.5061% | 4.0884% | 12.50% | 24.75% | -7.3712% | 11.4595 |
| .005 (train selected) | 3.5494 | 0.4793% | 4.0287% | 12.50% | 24.75% | -7.3575% | 11.3862 |
| .025 | 3.4353 | 0.3743% | 3.8096% | 12.50% | 22.38% | -7.2951% | 11.1047 |
| .075 | 3.1794 | 0.1276% | 3.3070% | 12.50% | 22.38% | -7.1791% | 10.4861 |
| .15 | 2.7607 | 0% | 2.7607% | 0% | 15.38% | -6.8827% | 9.6434 |

The founder always commits at the start. The table uses its unconditional net return under the same informed optional entrant policy, rerunning the actual no-entrant market whenever that LP declines. Thus a positive ex ante entrant/founder gap includes the value of avoiding losing markets; it is not a same-state cohort allocation comparison. `cohort_allocation.csv` separately reports both parties' returns conditional on entrant entry. Averaging conditional gaps over active regimes additionally changes composition when entry changes, so it must not be substituted for the primary offered-capital estimand.

Average founder return is negative across this deliberately broad grid, which includes highly adverse flow. The table does not establish a self-funding equilibrium throughout the population. Eight of 32 held-out regimes have both the founder and informed entrant strictly positive expected returns at lambda 0, .005, and .075; six do at .15. These counts are descriptive, not used for selection.

A concrete profitable-market illustration also clarifies the two correction targets. In `train_007`, flat informed entry produces entrant offered return 31.7507% and founder actual return 14.1169%, a 17.6337-point ex ante gap. Normalized .15 produces 27.2809% and 15.0389%, a 12.2420-point gap. Public LP entry remains profitable at 4.5763%, and informed entry stays at 50%. Thus the correction improves that ex ante allocation target with positive founder and LP participation, even though the same-date information advantage rises from 21.1409 to 22.7046 points. Conditional on entrant entry, the late-minus-founder gap is already negative (-4.9603 points flat, -15.7439 normalized). A claim that this rule equalizes all three quantities would be false.

The separate alignment sensitivity suite preserves the null canonical and bootstrap-plus-20 results. In its high-noise-demand case, all three mechanisms support positive public and informed entry, and the alignment signal has strict value: flat 7.5098 points, normalized .15 9.2774, isolated 6.4628. No bootstrap excess is required for those strict information effects.

## Sealed 64-regime confirmation

After freezing the train-selected coefficient .005, a new design sampled 64 regimes with seed 1047293 and wrote their complete parameter list before evaluating outcomes. It independently samples public-trade shares 5–110, future shares 10–300, flow alignment probability .34–.85, signal accuracy .55–.95, LP fees from 75/150/250 basis points, duration from 14/45/90 days, and annual outside return from 2%/8%. All use minimal bootstrap funding. Only flat zero, frozen normalized .005, and the historical .15 comparison are evaluated. There is no coefficient reselection on these results. `confirmation/design.json` retains the sealed design and `confirmation/worlds.csv` every finite state.

| Rule | Information value (points) | Public return | Private return | Public entry | Private entry | Founder actual return | Entrant minus founder (points) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Flat | 5.7636 | 2.4939% | 8.2575% | 14.06% | 24.41% | -5.7904% | 14.0479 |
| Frozen normalized .005 | 5.7302 | 2.4599% | 8.1901% | 14.06% | 24.41% | -5.7747% | 13.9648 |
| Historical normalized .15 | 4.9442 | 1.5928% | 6.5369% | 14.06% | 22.03% | -5.1662% | 11.7031 |

For .005 minus flat, the mean information-value change is **-0.0334 percentage points**, with paired regime-bootstrap 95% interval **[-0.0491, -0.0182]**. The ex ante cohort-gap change is **-0.0831 points**, interval **[-0.1057, -0.0612]**. All nine baseline public-profitable regimes, all 32 private-profitable regimes, and all 17 jointly founder/private-profitable regimes remain profitable. Entry decisions are unchanged in every regime. The cohort gap improves in 32 regimes, ties in 32, and worsens in none. Information advantage falls in 23, ties in 32, and rises in nine, demonstrating again that the two correction targets differ. The nine increases occur in public-profitable regimes, where the correction reduces public expected profit faster than private optional profit.

The historical .15 coefficient retains all nine public-profitable regimes in this new sample, unlike its outcome on the earlier 32-case grid. It reduces the mean ex ante cohort gap by 2.3447 points (95% interval [-2.9861, -1.7290]) and information value by 0.8194 points (interval [-1.2251, -0.4302]), while private-profitable regimes fall from 32 to 29 and mean private entry from 24.41% to 22.03%. This is a stronger reduction with a participation cost, not evidence of a universally appropriate coefficient.

Intervals use 10,000 paired whole-regime bootstrap resamples with seed 1047299. They describe uncertainty over the specified synthetic parameter distribution, not uncertainty about real-world market behavior. Exact finite-state expectations are computed within each regime. The conservative .005 effect is modest in economic magnitude, but its direction transfers to a new sealed population while preserving observed participation. Mean founder return remains negative across the broad sample, so the result supports a correction mechanism and profitable subregions, not a claim of equilibrium viability for every market.

## Early versus delayed commitment

The average held-out committed early-to-late change is -10.4123 percentage points under flat pooling, -14.9299 under normalized .15, and +3.5426 under isolated cohorts. These comparisons change the liquidity path, collateral price, fee exposure, and duration of capital lockup. They are not the fixed-opportunity information effect. In particular, a general information option theorem does not imply that later committed LP entry dominates earlier committed entry in every market.

## Reproduction and validation

From an installed checkout:

```sh
python -m research.active_lp.information_timing --output-dir /tmp/information-original --mc-draws 20000
python -m research.active_lp.information_timing --population outcome --output-dir /tmp/information-outcome
python -m research.active_lp.information_timing --population flow_alignment --output-dir /tmp/information-alignment
python -m research.active_lp.information_frontier --output-dir /tmp/information-frontier
python -m research.active_lp.information_confirmation --output-dir /tmp/information-confirmation
python -m research.active_lp.information_precision --input-dir /tmp/information-confirmation --output-dir /tmp/information-precision
python -m unittest discover -s tests -p test_information_timing.py -v
```

Each study writes its design before evaluating that study. This is local design freezing, **not external preregistration**. Designs, raw world probabilities/payoffs/decisions, policy summaries, selection scores, negative controls, and source hashes are retained. The module changed after the original 16-case run to add the explicitly separated population extensions; the historical manifest records the original module hash. The initial files are retained intact. Later source changes do not retroactively alter their registration status. The complete expanded frontier was rerun after the final fee-withdrawal rounding repair: every CSV is byte-identical, recorded with current engine hash and output hashes in `frontier/reproduction_check.json`. No fee withdrawals occur in these information experiments.

Three independent simulation seeds (724901, 824903, 924907), with 20,000 draws each, replicate the exactly enumerated information effects using paired draws across rules and policies. Monte Carlo is a numerical check of this synthetic population, not independent real-world evidence. Of the 210 nonzero-standard-error alignment replication rows, 196 (93.3%) normal 95% intervals cover the finite-state expectation; all 48 nonzero-standard-error outcome-population rows cover it. Largest absolute errors are 0.5372 and 0.3372 percentage points. Some rows are duplicated because selected lambda zero equals flat; rows and reused seeds are not independent hypothesis tests. Exact expected effects have no Monte Carlo sampling uncertainty. All uninformative-channel controls and the no-flow isolated-cohort control produce zero information value.

The primary reference cost/price logarithms use 80-digit Decimal contexts; the original information runs use the ambient 28-digit Decimal context for ledger arithmetic and binary64 probability/expectation aggregation. The supplemental `confirmation_precision` run recomputes all 64 confirmation regimes and all three frozen arms with 80-digit ledger arithmetic and 80-digit Decimal aggregation of the saved probabilities (renormalizing a maximum probability-mass discrepancy of 1.30e-16). All 6,912 entry-decision checks agree. Across 1,344 comparisons of regime-level key expectations and participation rates, the maximum absolute difference is 4e-16. The smallest distance of a public or conditional expected profit from the decision threshold is 0.01307805 collateral units. The reported results are therefore unaffected by the lower-precision aggregation or the 1e-12 tie threshold in this confirmation sample. These are precision comparisons, not additional economic samples.

The regression suite tests null channels, probability normalization, identical delayed entry prices/collateral across information treatments, zero profit on declines, signal-quality monotonicity in a strict-value case, normalized lambda-zero equivalence, the isolated no-flow control, and a closed-form check that declined entry preserves the founder's actual LMSR profit rather than zeroing it. Five tests pass. Both engines' separate economic safety suites cover trades, sell rejections, cancellation backing, actual winning payout branches, and claim ordering; those guarantees are not inferred from this buy-only information experiment.

Limits include the fixed synthetic population, a single entrant, free signals, risk-neutral exact Bayesian decisions, exogenous order sizes, no endogenous fee/volume response, no financing constraints beyond the posted deposit, and no simultaneous LP competition. Training/held-out parameter separation checks transfer within this model family, not across empirical market mechanisms. The strong supported claim is that future underwriting information can create an economically material participation option at a fixed public entry price. The strength and distributional effects of a residual correction remain dependent on its target, participation constraints, and market environment.
