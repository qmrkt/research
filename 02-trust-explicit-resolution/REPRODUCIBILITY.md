# Reproducing the resolution paper

Run from the repository root with Python 3.10+. Simulations and tests use the standard library. Installation requires access to the pinned build backend. Figure generation additionally uses matplotlib 3.10.8; the PDF build uses Tectonic.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/check_research.py
```

The final command builds and tests an installed wheel outside the checkout.

## Experiments

Use fresh output directories; the funded-game experiment refuses to overwrite a nonempty directory.

```sh
.venv/bin/python -m research.resolution_trust.economy_validation --output-dir /tmp/resolution-economy-rerun
.venv/bin/python -m research.resolution_trust.economy_audit --output-dir /tmp/resolution-economy-rerun
.venv/bin/python -m research.resolution_trust.monitoring_game --output-dir /tmp/resolution-monitoring-rerun
.venv/bin/python -m research.resolution_trust.monitoring_remediation --output-dir /tmp/resolution-monitoring-rerun/no_stake_remediation
.venv/bin/python -m research.resolution_trust.blueprint_experiments --output-dir /tmp/resolution-blueprint-rerun
cp 02-trust-explicit-resolution/output/monitoring_game/boundary_audit.py /tmp/resolution-monitoring-rerun/boundary_audit.py
.venv/bin/python /tmp/resolution-monitoring-rerun/boundary_audit.py
```

| Experiment | Saved outputs |
|---|---|
| Funded dispute game and accounting audit | [output/economy_validation/](output/economy_validation/) |
| Inspection equilibria, Monte Carlo, boundaries and zero-stake variant | [output/monitoring_game/](output/monitoring_game/) |
| Source composition and authenticated trace vectors | [output/blueprint_protocol/](output/blueprint_protocol/) |

To audit the saved funded-game episodes:

```sh
.venv/bin/python -m research.resolution_trust.economy_audit --output-dir 02-trust-explicit-resolution/output/economy_validation
```

Each output directory includes its configuration, seeds where applicable, results and provenance files. RSA keys in `simulation/fixtures/TEST_ONLY_RSA_KEYS.json` are public test fixtures.

## Figures and PDF

The figure renderer reads the saved outputs above; input paths are recorded in `figures/provenance.json`.

```sh
.venv/bin/python -m pip install matplotlib==3.10.8
.venv/bin/python scripts/render_resolution_figures.py
cd 02-trust-explicit-resolution
tectonic -X compile trust-explicit-resolution.tex --keep-logs
```
