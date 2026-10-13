# Run and build

Run from the repository root. Python 3.10+ is required; the recorded environment used Python 3.12.1 and Node.js 22.22.2. The protocol experiment requires `node` on `PATH`. Python experiments and unit tests use the standard library.

## Install and test

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/check_research.py
```

The package check builds and installs all three research packages in a clean temporary environment. To run only this paper's tests:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_execution_protocol.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_execution_quorum.py' -v
```

## Experiments and audits

Fresh output directories preserve the published results:

```sh
.venv/bin/python -m research.verified_execution.protocol_experiments --output-dir /tmp/execution-protocol-rerun
.venv/bin/python -m research.verified_execution.quorum_experiments --output-dir /tmp/execution-quorum-rerun
.venv/bin/python -m research.verified_execution.quorum_integration --output-dir /tmp/execution-quorum-rerun
.venv/bin/python -m research.verified_execution.quorum_protocol_audit --output-path /tmp/execution-quorum-rerun/protocol_boundary_audit.json
```

Audit the saved selection observations without regenerating them:

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from research.verified_execution.quorum_experiments import audit_raw
directory = Path('03-verified-execution/output/quorum')
summary = json.loads((directory / 'selection_summary.json').read_text())
print(json.dumps(audit_raw(directory, summary), indent=2))
PY
```

Saved artifacts: [`output/protocol/`](output/protocol/), [`output/quorum/`](output/quorum/), and [`output/avm/`](output/avm/). Each study records its configuration, source hashes and results. Final package/build hashes are in `output/package_verification.json` and `output/revision_manifest.json`.

## AVM benchmark

See [AVM run instructions](avm/README.md) for the pinned environment, private-ledger benchmark and saved-response audit.

## Figures and PDF

```sh
.venv/bin/python -m pip install matplotlib==3.10.8
.venv/bin/python scripts/render_execution_figures.py
cd 03-verified-execution
tectonic -X compile verified-execution.tex --keep-logs
```

The renderer reads saved publication results. The PDF build used Tectonic 0.15.0 and local `sections/`, TikZ sources and `figures/`.

RSA/HMAC/Ed25519 keys are public test fixtures. The AVM benchmark measures a verification kernel, not a deployed TEE or complete resolution service; see [its scope and resource limits](avm/README.md). Timing, private-ledger identifiers and build metadata vary by machine. Protocol rules and experiment assumptions are in [PROTOCOL.md](PROTOCOL.md), [QUORUM.md](QUORUM.md) and the paper.
