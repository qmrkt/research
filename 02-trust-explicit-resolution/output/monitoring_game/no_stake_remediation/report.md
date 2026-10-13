# Subsequent intervention: full work audits without an additional stake

This experiment responds constructively to the primary study's capital-exclusion result. It is a subsequent mechanism intervention on **all the same 64 regimes**, not an independent confirmation or a preregistered experiment. The design was written to `design.json` before evaluating this intervention. The primary three-arm grid, including its negative outcomes, is unchanged.

The treatment sets `S=0`, `w=1.25c`, and `delta=1`. It changes no exposure, bond, proposer fee, availability, common outage, capital, inspection cost, adjudication accuracy, or audit unit cost. Every completion claim is audited using the same assumed technology. The audit perfectly detects skipped work and withholds the completion payment; honest work has no false flags. This is a stronger service obligation than probabilistic auditing and its full cost is charged. It is not a claim that subjective work is empirically auditable at the assigned cost.

## A construction without the capital penalty

With zero work stake and full work auditing, an available inspector's shirk utility is zero, as is idle utility. Its verification utility is

```
V = w − c + f max(R,0) A(m) > 0,
```

because `w=1.25c>c`. Verification is strictly preferred even when fraud is absent. A slot needs only the original challenge bond `Bc`; no additional capital is required. A neutral correct challenge still requires `R>0`, and the restricted subgame still excludes profitable false challenges. Paying inspection does not override either condition.

Assume the proposer has the same nonnegative truthful participation payoff as in the bounty-only game, both mechanisms have sufficient external funding, and proposer ties select truth. Then the intervention weakly reduces wrong finalization versus the bounty-only equilibrium, under the same common-outage and availability assumptions:

1. If `D≤0`, both mechanisms select truth. If no correct challenge is profitable or possible, their challenge coverage is zero and their final outcome probabilities coincide.
2. Otherwise, the intervention attains `qmax=(1−z)[1−(1−u)^n]`, at least the bounty-only coverage. Fraud advantage `Delta(q)=(1−aq)D−aq(Bp+F)` strictly decreases in `q`.
3. If `Delta(qmax)≤0`, the intervention selects truth, so wrong finalization is zero.
4. If `Delta(qmax)>0`, fraud is strictly optimal at every attainable coverage. Both games therefore submit fraud with probability one. Since intervention coverage is weakly greater, its wrong probability `1−a qmax` is weakly lower.

This proves a feasible compensation construction without requiring an additional work stake. At exact proposer-indifference boundaries, the weak comparison uses the stated truth-on-ties equilibrium selection; it is not an all-equilibrium dominance assertion. The construction requires sufficient audit capacity, genuinely auditable work, funded payments, and the original challenge-capital capacity. It does not cure low adjudicator accuracy, common downtime, or missing challenge capital.

The worst-case external reserve is `F+n(w+cA)`, including an audit for every potential report. Service costs are separate from the modeled free-bond-capital balance, consistently with the primary exact game. This contract exchanges a work-collateral burden for enforceable withholding and full auditing; it does not eliminate the resource cost of verification.

## Every outcome is retained

| Arm | Mean wrong finalization | Zero-fraud regimes | Mean external spending |
|---|---:|---:|---:|
| Original bounty only | 49.09702% | 13 | 5.62998 |
| Original paid, unaudited work stake | 58.53177% | 13 | 10.45820 |
| Original paid, audited work stake | 51.59269% | 23 | 10.67202 |
| Subsequent full audit, zero work stake | **40.72091%** | **27** | **14.47685** |

All 64 intervention regimes launch, have sufficient declared external reserves, retain exactly the bounty-only eligible inspector count, and have positive truthful proposer participation margin (1 up to floating-point error). Exact pure-action best-response regret is zero in every regime.

| Comparison: intervention minus original arm | Mean change in wrong finalization | Improve | Tie | Worsen | Mean additional external spend |
|---|---:|---:|---:|---:|---:|
| Bounty only | **−8.37611 percentage points** | 18 | 46 | 0 | 8.84687 |
| Paid, unaudited | −17.81087 points | 30 | 34 | 0 | 4.01865 |
| Paid, audited work stake | −10.87178 points | 19 | 45 | 0 | 3.80483 |

The intervention's mean audit expense is `0.65690` per resolution opportunity; mean total real cost is `13.31812`. Its required reserve averages `29.47009` and peaks at `90.79820`, below each regime's declared `1,000,000` available reserve. That large budget deliberately removes external-funding scarcity in this paired comparison; the primary capital/budget frontier separately retains funding failures. These are currency-unit values from a grid with varying pool sizes, not a uniform fee percentage or estimated deployment price.

The resulting 40.72% mean error remains high because this grid deliberately includes severe limitations outside the corrected work incentive. No low-error subset replaces the population. The value of this result is the causal mechanism comparison and the constructive sufficient conditions, not a claim that these settings make every market safe.

## Artifacts and reproduction

- `design.json`: every original and treatment configuration, stored before treatment payoff evaluation.
- `equilibria.csv`: all 64 full solver outputs, including coverage, participation, spending, and regrets.
- `pairs.csv`: every paired outcome against each original arm, with eligibility and funding.
- `summary.json`: complete aggregates and hashes of the design, treatment source, unchanged game source, and original comparison data.

From the repository root:

```sh
python -m research.resolution_trust.monitoring_remediation --prepare-only --output-dir 02-trust-explicit-resolution/output/monitoring_game/no_stake_remediation
python -m research.resolution_trust.monitoring_remediation --output-dir 02-trust-explicit-resolution/output/monitoring_game/no_stake_remediation
python -m unittest discover -s tests -p 'test_monitoring_remediation.py' -v
```

The first command saves the design without computing any payoffs. The subsequent command refuses to overwrite a changed design and checks that regenerated bounty outcomes still match the original archived outcomes. Three tests cover the marginal-capital repair, continued challenge/budget constraints, and complete paired-population retention. This is an exact finite-grid analysis; no Monte Carlo or sampling confidence interval is needed, and no inference to a sampled deployment population is asserted.
