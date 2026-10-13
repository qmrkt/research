# Run the liquidity experiments

Python 3.10+, standard library. Commands run from the repository root.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python scripts/check_research.py
```

## Experiments

Use a different output directory to preserve the checked-in results. Full runs can take tens of minutes.

```sh
.venv/bin/python -m research.active_lp.publication_validation --output 01-active-lp/output/publication_validation
.venv/bin/python -m research.active_lp.historical_calibration --output 01-active-lp/output/historical_calibration
.venv/bin/python -m research.active_lp.fpmm_validation --output 01-active-lp/output/fpmm_validation
.venv/bin/python -m research.active_lp.fixed_point_validation --output 01-active-lp/output/fixed_point_validation
.venv/bin/python -m research.active_lp.safety_validation --output 01-active-lp/output/safety_validation
.venv/bin/python -m research.active_lp.information_timing --output-dir 01-active-lp/output/information_timing --mc-draws 20000
.venv/bin/python -m research.active_lp.information_timing --population outcome --output-dir 01-active-lp/output/information_timing/outcome_population
.venv/bin/python -m research.active_lp.information_timing --population flow_alignment --output-dir 01-active-lp/output/information_timing/flow_alignment
.venv/bin/python -m research.active_lp.information_frontier --output-dir 01-active-lp/output/information_timing/frontier
.venv/bin/python -m research.active_lp.information_confirmation --output-dir 01-active-lp/output/information_timing/confirmation
.venv/bin/python -m research.active_lp.information_precision --input-dir 01-active-lp/output/information_timing/confirmation --output-dir 01-active-lp/output/information_timing/confirmation_precision
```

These directories contain the revised paper's results, configurations and source hashes. Other output directories retain earlier experiments. Methods and interpretation are in the [paper](active-lp-paper.pdf).

## Build the PDF

With Tectonic installed:

```sh
cd 01-active-lp
tectonic --keep-logs active-lp-paper.tex
```
