# Executed blueprint and source-composition validation

All rates below are exact expectations under stated synthetic probabilities. They are not field estimates or Monte Carlo confidence intervals.

The suite executes and independently verifies every one-source and three-source Boolean/absent state (30 canonical protocol vectors). Exact weighted states reference those full traces.

| Experiment | Wrong per offer | Correct per offer | Cancel | Wrong given decision |
|---|---:|---:|---:|---:|
| independent_error_005_1 | 0.050000 | 0.950000 | 0.000000 | 0.050000 |
| independent_error_005_3 | 0.007250 | 0.992750 | 0.000000 | 0.007250 |
| independent_error_0145_3 | 0.056978 | 0.943022 | 0.000000 | 0.056978 |
| common_error_matched_0145_3 | 0.106525 | 0.893475 | 0.000000 | 0.106525 |
| independent_error_and_outage_3 | 0.004672 | 0.854848 | 0.140480 | 0.005436 |
| common_outage_3 | 0.005800 | 0.794200 | 0.200000 | 0.007250 |
| forced_1_corrupt | 0.000000 | 1.000000 | 0.000000 | 0.000000 |
| forced_2_corrupt | 1.000000 | 0.000000 | 0.000000 | 1.000000 |
| forced_1_withheld | 0.000000 | 1.000000 | 0.000000 | 0.000000 |
| forced_2_withheld | 0.000000 | 0.000000 | 1.000000 | undefined |
| choice_shared0_budget2_static | 0.079380 | 0.731025 | 0.189595 | 0.097951 |
| choice_shared0_budget2_adaptive | 0.079380 | 0.877230 | 0.043390 | 0.082981 |
| choice_shared0_budget4_static | 0.079380 | 0.731025 | 0.189595 | 0.097951 |
| choice_shared0_budget4_adaptive | 0.119971 | 0.844334 | 0.035695 | 0.124412 |
| choice_shared1_budget3_static | 0.972000 | 0.000000 | 0.028000 | 1.000000 |

A one-corrupt deterministic 2-of-3 majority cannot resolve wrongly when all other reports are true; two corrupted reporters can. With natural source errors, a single attacker can combine with an honest source error, so the zero-error threshold is not a population error bound.

The independent authority minimum cost for two controlled reports is 6 units (2+4); a common upstream controlling all reports reduces it to 3. These are stipulated authority costs, not measured hacking costs. Adaptive attackers observe the realized errors and availability before selecting a cost-constrained action.

Canonical fabricated traces pass the consistency checker and fail authenticated verification. Authentically signed common errors pass both and can finalize wrongly. Authentication proves origin under a key assumption, not factual correctness. Missing/late trace data blocks the proposal and leads to the explicit hard-timeout cancellation; it is never counted as a correct answer.

The publication abstraction is an append-only available byte log with a trusted clock. This demonstrates the gate and failure transition; it does not measure real network retrieval, prove IPFS availability, or implement consensus. LLM/human fixtures validate only authenticated reported I/O, not model or human accuracy.
