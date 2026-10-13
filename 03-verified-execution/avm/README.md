# AVM verification benchmark

Pinned build: Python 3.12, PuyaPy 5.7.1 (`-O 2`), AVM 11, go-algorand 5.0.3 stable (`2dc9524e`), consensus v42. Dependencies are in `requirements.lock`; compiled programs are in `compiled/`.

## Run

From this `avm/` directory:

```sh
uv venv --python 3.12 /tmp/question-avm-venv
uv pip install --python /tmp/question-avm-venv/bin/python -r requirements.lock
```

Download and checksum-verify the matching [go-algorand release](https://github.com/algorand/go-algorand/releases/tag/v5.0.3-stable). The recorded macOS archive is `node_stable_darwin-universal_5.0.3.tar.gz`, SHA-256 `86a75733172d68732e59ad7f9fe49984200d148b27b183f6ae04defe926d5e04`.

```sh
PATH=/tmp/question-avm-venv/bin:$PATH /tmp/question-avm-venv/bin/python \
  run_private_network.py --bin-dir /path/to/unpacked/bin --compile \
  --output /tmp/avm-recheck

/tmp/question-avm-venv/bin/python audit_results.py \
  --results /tmp/avm-recheck/results.json
```

The harness starts and removes a fresh private ledger; it does not touch AlgoKit LocalNet. `--compile` rebuilds `compiled/`; omit it to use the included programs. Audit the published responses without a node using any Python 3.10+ environment:

```sh
python3 audit_results.py --results ../output/avm/results.json
```

Results and raw signed-request/algod-response pairs are in [`../output/avm/`](../output/avm/). Exact costs and verdicts are audited; identifiers, RPC timings and serialization-size boundaries may vary.

## Scope and limits

The kernel verifies indexed Merkle openings and optional Ed25519 receipts against fixed proposal state, for power-of-two counts from 1 to 64. It treats record payloads as bytes. Canonical JSON, source authenticity, complete execution semantics, registration, attestation and publication/settlement lifecycles are separate checks. Keys are disposable test fixtures. Accepted primary groups were confirmed without simulation overrides.

Each application call contributes 700 opcode units; payments contribute none. Individual arguments/stack values are limited to 4,096 bytes and combined arguments to 16,384. Consensus v42 charges 0.1 microAlgo per combined argument byte above 2,048, rounded up; fees do not buy opcode budget. The whole-trace baseline is a single-buffer hash, so an oversized trace is recorded as a failure. RPC timings include local HTTP/SDK overhead. Full measurements and interpretation are in the [paper](../verified-execution.pdf).
