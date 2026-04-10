# Resolution Trust Trace Index

This directory contains the traceable outputs behind the trust-explicit resolution paper.

## Scenario families

- `bond_scaling/`
  - `bond_scaling.csv`
  - Flat versus pool-proportional proposer bonds across pool sizes.
- `bond_structure/`
  - `bond_structure.csv`
  - `bond_structure.json`
  - Flat, pool-proportional, linear-escalation, and exponential-escalation comparison.
- `lazy_verifier/`
  - `lazy_verifier.csv`
  - Thin-market and low-attention verification-coverage stress pack.
- `verification_bounty/`
  - `verification_bounty.csv`
  - Verification-bounty sweep across participant counts.
- `challenge_window/`
  - `challenge_window.csv`
  - Challenge-window sweep across challenger attention regimes.
- `adjudicator_accuracy/`
  - `adjudicator_accuracy.csv`
  - Adjudicator-accuracy versus challenge-coverage interaction.
- `honest_majority/`
  - `honest_majority.csv`
  - Honest-proposer baseline.
- `composition/`
  - `composition.csv`
  - Composition proxy experiment. Current version models composition indirectly through higher effective verification attention rather than explicit node-level source corruption.
- `stake_distribution/`
  - `stake_distribution.csv`
  - Stake-concentration sensitivity pack.

## Paper artifacts

- `paper_artifacts/table_bond_scaling.csv`
- `paper_artifacts/table_bond_structure_comparison.csv`
- `paper_artifacts/table_lazy_verifier.csv`
- `paper_artifacts/table_verification_bounty.csv`
- `paper_artifacts/table_challenge_window.csv`
- `paper_artifacts/table_adjudicator_accuracy.csv`
- `paper_artifacts/bond_scaling_false_resolution.svg`
- `paper_artifacts/bond_scaling_false_resolution.pdf`
- `paper_artifacts/verification_bounty_effect.svg`
- `paper_artifacts/verification_bounty_effect.pdf`
- `paper_artifacts/challenge_window_effect.svg`
- `paper_artifacts/challenge_window_effect.pdf`
- `paper_artifacts/paper_artifacts_overview.json`

## Reading guide

- Use `bond_scaling` and `bond_structure` for the proposer-bond argument.
- Use `lazy_verifier`, `verification_bounty`, and `challenge_window` for the verification-coverage argument.
- Use `adjudicator_accuracy` to support the claim that challenge probability dominates adjudicator accuracy.
- Treat `composition` as directional proxy evidence rather than a full explicit source-corruption model.
