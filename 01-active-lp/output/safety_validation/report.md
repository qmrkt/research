# Historical safety regressions

These exact event sequences reproduce the old 64-outcome low-tail diagnostic and the cancellation-refund failure. Both reference and compressed Decimal models now pass their state-aware checks. This is a designed regression bundle, not a population safety estimate.

| Model / path | Terminal assets | Senior reserve | Free residual | Rejected requests | Claim orders |
| --- | ---: | ---: | ---: | ---: | ---: |
| reference/low_tail | 668.642829276 | 500.000000000 | 168.642829276 | 0 | 6 |
| reference/refund_failure | 1120.249234540 | 1044.260698614 | 75.988535926 | 1 | 24 |
| compressed/low_tail | 668.642829276 | 500.000000000 | 168.642829276 | 0 | 6 |
| compressed/refund_failure | 1120.249234540 | 1044.260698614 | 75.988535926 | 1 | 24 |

After the low-tail winner claim, the creator's obsolete losing-outcome component entry is approximately −189.464309 while its realized winning-outcome residual is +60.535691. No losing outcome can become payable after resolution; the actual aggregate reserve and cash ledger remain funded.

In the cancellation trace, the final sell would leave refundable cost basis underfunded by 22.448755. It is rejected atomically; the prior profitable sell remains executed. Every still-open position receives its full remaining cost basis after cancellation. The rejected immediate sell quote is retained in events.jsonl.

All 60 payout orders conserve recipient entitlements and finish with no senior liabilities or unexplained non-fee assets. Each event's cash flow is independently quoted before application; maximum quote-versus-cash error is 4.05E-77 and cumulative-ledger error is 1E-76.

Run `python -m research.active_lp.safety_validation` to reproduce. config.json freezes the sequences; provenance.json and manifest.json identify sources and output hashes; events.jsonl includes all requests, rejected quotes, reserves and checks; claim_orders.jsonl records each complete payout order. low_tail.json reproduces the original compact trace. certified_math_audit.md records the separate numerical proof audit and its scope.
