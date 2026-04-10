# Active LP Research Package

This package holds the research simulator for the active-LP LMSR design.

Initial modules:

- `types.py`: shared enums and aliases
- `state.py`: top-level market, trader, sponsor, and treasury state objects
- `events.py`: event dataclasses for deterministic and stochastic scenario runners
- `metrics.py`: canonical evaluation outputs and invariant result type
- `runner.py`: protocol interfaces for engines, invariants, metrics, and scenario execution
- `reference_math.py`: independent high-precision LMSR oracle
- `reference_parallel_lmsr.py`: Layer A exact benchmark engine, invariants, and scenario runner
- `scenarios.py`: deterministic scenario definitions and config schema
- `experiments.py`: batch runner and JSONL/CSV export helpers
- `monte_carlo.py`: randomized scenario generation and sweep helpers
- `adversarial_search.py`: targeted fairness-tail search scenarios
- `reporting.py`: aggregate summaries and paper-facing report artifacts
- `figures.py`: dependency-free SVG figures for paper/report workflows
- `sweep_presets.py`: named sweep presets (`paper_quick`, `paper_core`)
- `cli.py`: `python -m research.active_lp` entrypoint

Current workflow:

1. run deterministic scenarios through `ExperimentRunner`
2. export JSONL / CSV artifacts with `write_experiment_results`
3. aggregate results into summary tables with `write_aggregated_report`
4. generate SVG figures with `write_figure_pack`
5. run randomized sweeps with `run_monte_carlo_sweep`
6. run targeted tail search with `run_adversarial_search`
7. implement Layer B and Layer C against the same scenario/output interface
