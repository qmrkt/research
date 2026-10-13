# Liquidity simulations

Python 3.10+, standard library. Run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m research.active_lp --help
.venv/bin/python -m research.active_lp deterministic --output-dir /tmp/active-lp-example
```

The `active-lp` command exposes the same CLI. See [run instructions](../REPRODUCIBILITY.md) for the paper's experiments and [saved results](../output/).

Package verification:

```sh
.venv/bin/python scripts/check_research.py
```

Vendored helper attribution and license: [_vendor/provenance.json](_vendor/provenance.json), [_vendor/LICENSE.lmsr_math](_vendor/LICENSE.lmsr_math).
