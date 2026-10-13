# Costly inspection, compensation, and capital

This is a conditional economic experiment supporting the resolution paper. It solves an explicit verify/shirk/idle game and independently simulates its cash flows. It establishes when compensated verification can support truthful proposing, and identifies the funding, audit, and capital conditions needed for that conclusion. None of the parameter values is a deployment calibration.

The main design was saved locally before its outcomes were evaluated in `design.json`; this is not an external preregistration. The later capital frontier and boundary audit are explicitly subsequent descriptive checks. No rule or coefficient was selected to maximize these results.

## Mechanism and assumptions

A single proposer has funded single-market outcome exposure `D = payoff(false) − payoff(true)`, with `|D| ≤ L`. The default is `L=10,000`, `D=4,000`. Its truthful outside option is the value of a later truthful resolution, without the present service costs. Abstention earns no incremental service payoff; it is recorded as no proposal, not correct finalization. This excludes early-unlock benefits and an explicit fallback delay game.

The proposer posts `Bp`. A successfully accepted proposal earns a prepaid external fee `F`, including if the accepted proposal is false. A corrected proposer loses `Bp` and receives no fee. An unsuccessful challenger loses `Bc` entirely to the protocol, with **no proposer defense reward**. A successful challenger receives `eta Bp`, and the remaining proposer bond goes to the protocol. Undisputed and winning bonds are returned. Fees, bounties, and slashes are transfers; work and opportunity costs are recorded separately.

Inspectors hold no outcome positions and perfectly learn truth when they incur inspection cost `c`. Adjudication is correct with probability `a`. The module rejects configurations with a profitable false challenge, so this is a restricted subgame of the separate operational simulator. If `h` is filing work and `kappa` the capital cost per bond per window, define:

```
cC = h + kappa Bc
R  = a eta Bp − (1−a) Bc − cC
T  = (1−a) eta Bp − a Bc − cC.
```

An inspector files a correct challenge only if `R>0`; the permitted subgame requires `T≤0`, with no filing at a zero-surplus tie. Inspection coverage and challenge coverage therefore differ when `R≤0`. The broader operational simulator permits position-motivated false challenges; those are not silently ruled out there.

There are `n` capital-eligible inspector slots. A slot must have free capital `K≥Bc+S`, where `S` is its work stake, so work and challenge collateral can be posted together. These free-capital balances cover the bonds; real service expenses are represented in utility rather than deducted a second time from the collateral balance. The proposer separately needs `Kp≥Bp`. This models competition for an inspector's capital between its two duties, not portfolio-wide capital reservations across simultaneous markets.

With probability `z`, all inspectors are unavailable. Conditional on common uptime, each is independently available with probability `u`. The proposer acts before observing common uptime or individual availability. Available inspectors then choose verify, fake completion (shirk), or idle. Only verify discovers a false proposal. If several discover it, the first claimant is chosen uniformly, and only that claimant posts `Bc` or earns the bounty.

Verified work earns `w`. A reported completion is independently audited with probability `delta`, at real and externally funded cost `cA`; an audit perfectly detects skipped work, withholds `w`, and slashes `S`. Honest work has no false flags. An idle slot makes no completion claim, earns nothing, and is not audited. This presumes an independently enforceable audit of real work; an executor's self-authored receipt is insufficient. The study does not demonstrate that such an audit technology exists for every blueprint.

## Deterrence and scaled bonds

Let `q` be the probability a false proposal is actually challenged, and `r=aq` the probability it is corrected. Relative to truthful proposing with the same work cost, fraud has incremental expected payoff:

```
Delta = (1−r)D − r(Bp+F).
```

For `D>0` and `r>0`, fraud is weakly deterred exactly when

```
Bp+F ≥ [(1−r)/r]D,
q ≥ D/[a(D+Bp+F)].
```

At `r=0`, any positive `D` remains profitable relative to truth. Fees enter this expression because correction loses the accepted-proposal fee; they are not free funding. If `D(L)≥kL` for fixed `k>0` and correction stays bounded by `rbar<1`, sublinear `Bp(L)+F(L)=o(L)` cannot deter fraud for arbitrarily large `L`. This proves the need for scaling in that regime, without proving any universal bond fraction.

For example, whole-pool exposure, `a=.9`, and no accepted fee require challenge probability `1/[.9(1+rho)]`. A 10% bond requires `1.0101`, which is impossible. A 15% bond requires `0.966184`. Ten to fifteen percent is therefore not an unconditional security prescription.

Conditional on a false proposal, wrong finalization decomposes as `(1−q)+q(1−a)`: no challenge plus incorrect adjudication after challenge. The first term exceeds the second when `q<1/(2−a)`. This is an exact conditional comparison; it does not establish that improving coverage is always the cheapest intervention or more valuable than improving accuracy.

## Solving endogenous inspection

Let each available inspector verify with probability `m`, and let `f` be fraud probability conditional on a proposal. Then:

```
q_inspect(m) = (1−z)[1−(1−u m)^n]
A(m) = [1−(1−u m)^n]/(n u m),   A(0)=1.
```

`A` is the probability an inspector wins the filing race conditional on working. It equals `E[1/(1+X)]` for `X~Binomial(n−1,um)`. A separate test verifies the identity by enumerating the competitor count. Common outage does not enter `A`: an inspector's own availability establishes common uptime. `q=q_inspect` if `R>0`, otherwise actual challenge coverage is zero.

Write `kS=kappa S`. Available-inspector payoffs are:

```
V = w − c − kS + f R A(m)   (verify, when R>0)
H = (1−delta)w − delta S − kS   (fake completion)
I = 0                         (idle).
k = c + kS − w + max(0,H).
```

For `R≤0`, there is no challenge bounty term in `V`. When `k>0`, the symmetric interior equilibrium requires both proposer and inspector indifference. In the no-outage case:

```
q* = D/[a(D+Bp+F)]
m* = [1−(1−q*)^(1/n)]/u
f* = k/[R A(m*)].
```

For `z>0`, replace `q*` by `q*/(1−z)` inside the formula for `m*`. These are interior formulas only when both mixing probabilities lie strictly between zero and one and truthful proposing covers its own costs. The implementation evaluates pure and boundary cases separately, then checks every available pure-action deviation.

With no routine pay or stake, `k=c>0`. If fraud is absent, inspection earns `−c`, so positive routine inspection cannot be a best response. With `D>0`, no inspection makes fraud attractive; a mixed equilibrium or all-fraud boundary can result. More inspectors share the bounty, so increasing identities does not imply greater equilibrium coverage.

When paid work is not audited, `H=w−kS`. If this is positive, `k=c`: compensation also rewards shirking and does not remove the incentive to save inspection cost. By contrast,

```
w > c+kS                    (verify beats idle even at f=0)
delta(w+S) > c               (verify beats shirking even at f=0)
```

make verification strictly optimal whenever available. If `R>0`, `T≤0`, capital and funding suffice, and `a(1−z)[1−(1−u)^n] > D/(D+Bp+F)` for `D>0`, false proposing is strictly worse than truth. Truth also beats abstention when `F > proposal_work_cost + kappa Bp`. This is the conditional compensation theorem. It supplies an enforcement condition rather than assuming paid agents work by fiat.

The solver selects a symmetric equilibrium with stated ties; it does not claim equilibrium uniqueness. At zero measure availability information sets, no inspector deviation is counted. If truthful service is loss-making, the solver checks the false-only submission posterior and its inspection best response: profitable fraud can still enter, otherwise there is no proposal. An insufficient external reserve or proposer capital prevents launch.

## Funding and real costs

The reserve must cover `F+n(w+cA)` in the worst case with positive audit probability, or `F+nw` with no audits. This is conservative even if most slots are usually unavailable. A shortfall produces no proposal and no accepted correct outcome. Slashes go to the protocol and do not finance a completion promise retroactively. Budget feasibility and monetary conservation are checked on every simulated episode.

Expected external spend and real cost are separate outputs. External spend includes accepted fees, earned completion payments, and audit payments. Real cost includes proposal work, inspection work on honest and false submissions, filing work, audit work, and opportunity cost of bonds actually posted. Bond and fee transfers are not incorrectly added to real resource cost.

## Designed controls: exact solutions and Monte Carlo

There are 15 designed configurations, three fixed seeds per configuration, and 20,000 episodes per seed: **900,000 episodes**. The table reports exact equilibria, not rounded Monte Carlo estimates. Rates are unconditional on an offered resolution opportunity except `q`, which is challenge coverage conditional on a false proposal.

| Configuration | Fraud rate | Challenge coverage q | Wrong finalization | Mean external spend |
|---|---:|---:|---:|---:|
| Bounty only | 0.47191% | 76.27765% | 0.129946% | 19.93161 |
| Paid, unaudited | 0.47191% | 76.27765% | 0.129946% | 25.33161 |
| Paid, audited | 0% | 93.6% | 0% | 25.58000 |
| Paid, weak audit delta=.1 | 0.35393% | 76.27765% | 0.097460% | 25.18757 |
| One bounty-only inspector | 100% | 60% | 43% | 8.6 |
| Eight bounty-only inspectors | 0.54372% | 76.27765% | 0.149721% | See CSV |
| Paid, common outage z=.3 | 100% | 65.52% | 37.756% | See CSV |
| Paid, whole-pool exposure, a=.9 | 100% | 93.6% | 15.76% | See CSV |
| Paid, whole-pool exposure, a=.95 | 0% | 93.6% | 0% | See CSV |

The paid audited default uses `w=3`, `S=2`, `delta=.5`, `c=2`. Its audit incentive margin is `.5`, truthful proposer participation margin is `13.5`, and worst-case external reserve is `29.6`. The corresponding unaudited regime has shirking probability `36.5068%` among available inspectors. The audited arm has no shirking and uses the entire available coverage; it does not force anyone to participate against their payoffs.

Additional controls are deliberately adverse. No challenge capital gives 100% wrong finalization. An inaccurate adjudicator (`a=.6`) gives 93.6% inspection coverage but negative correct-challenge surplus, zero actual challenge coverage, and 100% wrong finalization. Insufficient external reserve, and uncompensated proposer work under the paid default, give no proposal; these are not successes. Negative signed exposure selects truth. A much larger bounty supports rarer fraud but lower challenge coverage. All 15 configurations are retained in `equilibria.csv`.

Across 225 metric/seed estimates, 137 have nonzero Monte Carlo standard error. Their largest standardized deviation from the exact result is `2.4364`; 133 of 137 nominal 95% intervals cover the exact value. These are descriptive validation checks, not 137 independent hypothesis tests. Maximum per-episode money-balance error is `1.45e−15`. The exact solver's maximum pure-action regret over the designed and fresh experiments is `2.82e−14`.

## All 64 fresh regimes, including negative outcomes

The fixed fresh seed is `908731`. It samples 64 regimes before payoff evaluation from pools 100/1,000/10,000; bond fractions .05/.1/.15/.3/.6; inspector counts 1/3/8; availability .2/.5/.8; common outages 0/.1/.25; accuracy uniform .7–.99; signed exposure uniform −.25 to 1 times pool; and inspection cost uniform .1–10. Individual capital is .5/1/2/5 times the bond. Full configurations, including every random draw, are in `design.json` and `fresh_regimes.csv`.

Every regime has three arms: bounty only, unaudited compensation, and audited compensation. The paid arms both use `w=1.25c` and `S=3c`; the audited arm sets `delta=.5`. All have a truthful proposer service margin of 1 and sufficient external reserve, so differences do not come from silently dropping unprofitable proposer cases.

| Arm, all 64 regimes | Mean wrong finalization | Mean external spend | Zero-fraud regimes | No-proposal regimes |
|---|---:|---:|---:|---:|
| Bounty only | 49.09702% | 5.62998 | 13 | 0 |
| Paid, unaudited | 58.53177% | 10.45820 | 13 | 0 |
| Paid, audited | 51.59269% | 10.67202 | 23 | 0 |

Holding the paid contract and its capital requirement fixed, adding enforceable audits reduces mean wrong finalization by **6.93909 percentage points**: 12 regimes improve, 52 tie, none worsen. Relative to bounty only, however, paid audited verification **increases** mean wrong finalization by **2.49567 points**: 12 improve, 16 worsen, 36 tie. The work stake excludes some otherwise eligible inspectors in 40 of 64 regimes, including all 16 worse cases. The same-eligibility subgroup has 24 regimes and a 6.71802-point reduction; this subgroup is descriptive and is not substituted for the full-population result.

Thus the study supports the audit incentive mechanism and a feasible compensation region, while rejecting an unconditional claim that adding compensation and work collateral improves every capital distribution. Increasing `S` can enforce work and simultaneously reduce monitoring capacity. The full paired outcomes are in `fresh_pairs.csv`; no negative case is removed. Exact finite-grid results do not have Monte Carlo uncertainty, and this chosen synthetic distribution is not a sampled deployment population.

A [subsequent constructive intervention](no_stake_remediation/README.md) retains all 64 regimes and removes the additional work stake while auditing every completion. It preserves every bounty-only capital-eligible count and reduces mean wrong finalization by 8.37611 percentage points versus bounty only (18 improve, 46 tie, none worsen), at an additional mean external expenditure of 8.84687. Its separate pre-evaluation design, proof, full paired outcomes, and stronger audit assumptions are reported without replacing the primary three-arm findings above.

## Subsequent capital and budget frontier

`capital_frontier_design.json` declares a separate descriptive 1,125-case grid of bond fraction, inspector count, inspector capital, external reserve, and adjudicator accuracy. It retains the default paid audited contract. There are 873 launch-feasible configurations and 252 reserve shortfalls. Among launches, 186 yield truthful finalization with probability one, and 495 have no eligible challenger and yield false finalization. These counts describe the chosen grid, not deployment frequencies or an optimized rule. `capital_frontier.csv` exposes every point so a reader can see the simultaneous budget and capital constraints.

## Validation and reproduction

From the repository root, after the standard editable installation:

```sh
python -m research.resolution_trust.monitoring_game --output-dir 02-trust-explicit-resolution/output/monitoring_game
python -m unittest discover -s tests -p 'test_monitoring_game.py' -v
python 02-trust-explicit-resolution/output/monitoring_game/boundary_audit.py
```

The eight regression tests cover the signed-exposure bound, adjudication and filing incentives, a closed-form single-inspector mixed equilibrium, independently enumerated bounty competition, audited versus unaudited work, money and reserve conservation, proposer participation, capital exclusions, common outage, and profitable-fraud versus abstention boundaries. The separate operational simulator's test suite also cross-checks the one-inspector challenge payoffs and proposer fraud-versus-truth payoff against this solver.

The subsequent boundary audit samples 3,000 boundary-rich configurations at seed `321091`: zero or full availability/outage/accuracy, zero bonds or costs, zero inspector counts, loss-making truth, and audit extremes. It solves all 2,434 cases within the neutral-inspector subgame with maximum pure-action regret `1.67e−16`. The other 566 are explicitly rejected because false challenges are profitable; these are model exclusions, not silently accepted equilibria. Full inputs and exclusions are in `boundary_cases.csv`. This audit found and repaired only a diagnostic at common outage probability one, where conditional inspector availability is a zero-probability event; none of the main experiment's outcomes changed.

`manifest.json` records main design and source hashes. `boundary_validation.json` records the boundary script and source hashes. `monte_carlo.csv` contains every seed-level estimate and uncertainty summary. `episode_samples.csv` retains the first 100 episodes per seed/configuration, not all 900,000; the complete streams are deterministically regenerable. Accounting and reserve assertions execute on every episode before trace retention.

## What must be measured or supplied before deployment

The theorem requires credible signed exposure, actual eligible-monitor capital, availability and correlated downtime, inspection and filing costs, conditional adjudication accuracy, and a funded proposer/verification budget. The paid-work theorem additionally requires a real work-audit mechanism with specified detection, error, and cost properties. The model assumes perfect detection when audited, no honest audit false positives, neutral inspectors, homogeneous eligible-slot costs, unobserved common outages at proposal time, and bounded funded slots. It does not establish Sybil resistance, solve collusion or bribery, include external correlated positions, or reserve capital across concurrent markets. These are substantive inputs to the claim, not parameters the simulation empirically estimates.
