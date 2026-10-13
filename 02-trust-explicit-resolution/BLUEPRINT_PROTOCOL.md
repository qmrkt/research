# Executable Boolean blueprint profile, version 1

This is a complete small research protocol for the paper, independent of the current product implementation. It specifies and executes one useful source-composition path. It does not claim to implement every workflow expressible by the paper's eight step types, to prove real-world facts, or to provide a deployed data-availability service.

Run the experiments from the repository's installed research package:

```sh
python -m research.resolution_trust.blueprint_experiments --output-dir 02-trust-explicit-resolution/output/blueprint_protocol
python -m unittest discover -s tests -p test_blueprint_protocol.py -v
```

Runtime dependencies are Python's standard library. `simulation/fixtures/TEST_ONLY_RSA_KEYS.json` deliberately contains public **test** private keys. They enable repeatable signature vectors, not operational authentication. An actual deployment must pin independent public keys and keep their corresponding signing keys unavailable to the executor. The small RSA implementation is a research reference, not a reviewed production cryptographic library.

## 1. Immutable market and blueprint state

A market commits its identifier, initial execution time, and the SHA-256 root of a validated blueprint before execution. The caller supplies this trusted market context to the verifier; a proposer cannot choose a different market, start, or blueprint. The committed blueprint includes:

- Profile `question.blueprint.boolean.v1`, blueprint version 1, and an event identifier.
- Positive integer source window, availability window, retry delay, maximum runs, and maximum nodes.
- One to thirteen distinct report nodes followed by three terminal declarations; the total node bound is sixteen. The provided experiments use one or three reports. Maximum runs is eight.
- Each report's unique identifier/authority, pinned 2048-bit RSA public key with exponent 65537, report type, and exact request object.
- Every terminal's complete ordered parent list, fixed strict-majority threshold, and one expression from the grammar below.

Two names sharing a key cannot count as independent votes. Key identity is the numeric modulus/exponent pair, so hex case or leading zeros cannot create extra authority identities. Distinct keys do **not** establish independent real-world information; common upstream dependencies remain part of the declared trust assumptions and experiments.

Report types are existing vocabulary items: `api_fetch`, `market_evidence`, `llm_judge`, and `human_judge`. All four mean “obtain the authenticated Boolean output from this declared external authority” in this narrow profile. The latter two use explicit request/model/prompt or panel metadata. Their fixtures prove only reported-I/O binding. They do not execute a model, assess a human, or prove the report is correct. The `wait` vocabulary item is represented by the fixed run envelope here rather than tested as an in-graph node.

## 2. Typed DAG and total decision semantics

Every report is a root. The graph has an edge from every report to each of `submit_result`, `cancel_market`, and `defer_resolution`. There are no other edges and no back-edges. Each node owns its output object; shared mutable context and conflicting writes are absent. All terminal joins wait for all declared report statuses, including unavailable reports. Execution order is ascending report identifier followed by ascending terminal identifier. This deterministic serialization represents logically independent reports; it is not a network-concurrency performance claim.

Every report contributes `false`, `true`, or `null` (unavailable). Let `count(v)` count distinct declared authorities whose authenticated report equals Boolean `v`. The threshold `k` is fixed at creation and satisfies `n/2 < k <= n`. It is never reduced to a majority of whichever sources happened to be available. Hence at most one Boolean can qualify.

The entire condition grammar is:

| Expression | Meaning | Permitted terminal |
|---|---|---|
| `has_quorum` | Exactly one Boolean has at least `k` reports | `submit_result` |
| `no_quorum_retry` | Neither Boolean qualifies and `run_id < max_runs` | `defer_resolution` |
| `no_quorum_final` | Neither Boolean qualifies and `run_id = max_runs` | `cancel_market` |

The active terminal emits, respectively, `{action: resolve, outcome: v}`, `{action: defer, next_start: start + retry_delay}`, or `{action: cancel}`. Inactive terminal declarations are explicitly recorded with status `skipped` and empty output. Exactly one terminal succeeds. There is no arbitrary expression evaluation, implicit priority, hidden fallback, or ninth “quorum” step type. The quorum is the precisely defined condition on existing terminal types.

The validator rejects unknown versions/types/fields, dangling or incomplete joins, internal cycles, duplicate identifiers/keys, inconsistent thresholds, invalid conditions, and exceeded budgets. An invalid blueprint has no execution semantics and cannot produce an accepted proposal.

## 3. Source evidence and authenticated publication

An evidence body binds its schema, blueprint root, market, event, run, node, report type, authority, exact request root, observation time, and Boolean value. Its signature covers the domain `question.evidence.v1`, a zero byte, and the canonical body bytes. The fixture signature scheme is strict RSASSA-PKCS1-v1_5 with SHA-256, following RFC 8017 sections 8.2 and 9.2. Verification compares the entire encoded block, including length, padding and SHA-256 DigestInfo; it does not accept a substring match. Evidence references hash the entire signed object under the evidence domain.

The publication layer is an explicit idealized assumption: an append-only, publicly readable byte log with a trustworthy clock and immutable named source slots. Publishing arbitrary content-addressed bytes does not reserve a source slot. Named-slot admission first verifies the signature against a pinned authority registry and checks its node identity and that observation time is no later than publication. Only the first authenticated publication for `(market, run, authority)` occupies that slot. Later replacement/equivocation cannot change that run's vote. Signed observation time must also fall inside the run's source window. Source-key compromise can create an authenticated lie and is modeled as source corruption.

At `source_deadline = start + source_window`, a missing/late source slot yields an unavailable report. The runner cannot omit a timely slot that the publication layer contains: the verifier compares every trace reference against the corresponding public slot. This checks declared input completeness relative to the publication service. It does not prove a provider made a network request, independently certify the provider's clock, or prove there was no other unpublished real-world evidence.

Real deployments must implement this publication abstraction with available on-chain data, a specified DA layer, or an explicitly trusted retrieval checker. A CID or hash alone does not instantiate it. The experiments do not measure network availability, IPFS pinning, consensus, or latency. They test the decision rules given observable publication events and deadlines.

## 4. Canonical complete trace and independent verifier

The canonical data profile permits null, Booleans, ASCII strings, integers with absolute value at most `2^53-1`, arrays, and string-keyed objects. Floats, duplicate keys, non-ASCII strings and unknown fields are rejected. Objects have lexicographically sorted keys; arrays preserve order; JSON has no whitespace; ASCII control characters, quotes and backslashes use JSON escapes. The byte limit is 262,144. Parsing requires re-encoding to exactly the input bytes. Equality is JSON-type-aware: Boolean false is not integer zero.

The trace root is `SHA256("question.trace.v1" || 0x00 || canonical(trace))`. The trace contains the trace and blueprint versions, blueprint root, market/event/run identity, fixed start and deadlines, previous trace root, and the complete ordered step array. Every step binds its index, node ID/type, exact input, exact output, status, and evidence-reference list. The final terminal object is also bound. Changing the status, path, references or input while preserving the eventual answer still changes the committed object. Blueprint and request roots use their own domains.

Verification has three separate layers:

1. **Consistency.** Independently validate the graph and replay report bindings, input/output snapshots, fixed-threshold counts, selected/skipped terminals, budgets, and prior-run links. `check_consistency` does not invoke the runner and deliberately does not validate signatures. Fabricated but coherent inputs can pass it.
2. **Authenticity.** Retrieve every referenced source object and verify its pinned signature, identity, request, event/run binding, and time window. A coherent invented transcript cannot pass without a valid authority signature under the cryptographic assumption. An authentic erroneous source can pass.
3. **Publication and deadlines.** The full trace and all referenced objects must exist in the declared publication layer by their deadlines and match their roots. An omitted source slot, unavailable object, or late trace blocks the proposal. A stale root cannot authorize fresh bytes.

Thus a collision-resistant trace root binds a transcript; it does not demonstrate that the transcript was honestly produced. Source authenticity is an additional assumption/check. Factual correctness remains external. The vectors include a fresh-root fabrication that passes consistency but fails authentication, and an authentically signed common error that passes every gate but resolves wrongly.

## 5. Cross-run retries, blocked proposals and finality

Run 1 begins at the immutable initial start. A valid deferred run allows a full restart at exactly `start + retry_delay`; only the previous full trace root and this scheduling state carry forward. No report values are silently retained. Fresh evidence binds the new run number. Every prior run must itself verify as deferred, identities must match, and run IDs must be consecutive. The retry delay must be at least the source plus availability window. Internal graph loops are forbidden.

The trace publication deadline is `start + source_window + availability_window`. Finalization is pending before it. At or after it, the verifier either accepts the declared resolve/cancel/defer action or marks the proposal blocked. A missing trace is an invalid proposal, not a correct resolution and not proof of the other outcome. A blocked proposal cannot create a verified retry transition. A valid replacement for the same run may be checked using data already published by that run's deadlines.

The market's hard deadline is `initial_start + (max_runs-1)*retry_delay + source_window + availability_window + 1`. The extra clock unit makes the final valid run's acceptance deadline precede timeout. At the hard deadline, any unresolved market cancels by timeout. After any resolve/cancel/timeout action the market is terminal; no run may reopen it. `ResolutionSession` implements this envelope. This is an explicit cancellation/liveness policy, not a proof that every market reaches a factual decision.

## 6. Conditional composition and authority-cost propositions

**Fixed-threshold integrity.** Assume correct and available uncorrupted reports, no other errors, signature unforgeability for uncompromised authorities, and correct execution/publication. For an `n`-source threshold `k`, a false accepted Boolean requires at least `k` false reports. Therefore fewer than `k` controlled sources cannot cause a wrong decision. If `k` sources can submit the same false value, they can cause one. For 2-of-3, one corrupt report is tolerated; two suffice. Proof: the accepted false value must meet the explicit count predicate. This is a threshold fact, not a novel general oracle theorem.

**Availability threshold.** With otherwise correct reports, withholding fewer than `n-k+1` leaves at least `k` true reports and preserves a decision; withholding `n-k+1` can force defer/cancel. Missing reports never lower `k`. Natural source errors can change both conclusions, which is why they are separate experimental treatments.

**Authority cover.** Let each attackable authority `a` have nonnegative cost `c_a` and control a declared set of report nodes `S_a`. Under the preceding assumptions, the minimum wrong-decision cost is

`min { sum(c_a for a in A) : |union(S_a for a in A)| >= k }`.

For withholding, replace `k` by `n-k+1`. This is a weighted authority-cover problem; it is not necessarily an ordinary graph minimum cut when authorities overlap. Independent source costs 2, 4 and 6 give threshold cost 6. A shared upstream controlling all reports for cost 3 lowers it to 3 even with three distinct signing keys. These are stipulated units, not observed compromise costs. The lower bound also ceases to apply if other natural errors supply some of the false votes.

**Independent-error benchmark.** With three independent available Boolean reporters, each wrong with probability `e`, 2-of-3 is wrong with probability `3e^2-2e^3`. A common shock that makes all three wrong with probability `c`, followed otherwise by independent error `e`, gives `c+(1-c)(3e^2-2e^3)`. The source marginal error is `c+(1-c)e`. Matching this marginal in an independent-source treatment isolates dependence rather than comparing sources of different average quality.

## 7. Frozen experiments and evidence index

`output/blueprint_protocol/config.json` is written before evaluation. There is no fitted parameter or random seed: probabilities are enumerated exactly as rational numbers. The suite executes all thirty possible Boolean/absent vectors for one and three sources and validates each through the actual protocol. Forty experiments enumerate 1,670 weighted latent states, with references to those executable counterfactual traces. These repeated uses are not independent observations and receive no sampling confidence intervals. Uncertainty about real source quality/costs is outside the chosen model.

Treatments cover independent errors, common error shocks at matched source marginal quality, independent/common outages, fixed one-/two-source corruption, one-/two-source withholding, and ex ante/adaptive cost-constrained authority choice. Adaptive attackers observe realized errors and availability before choosing an action; this is a strong adversary, stated explicitly. Corruption changes reports without repairing exogenous outages. The objective maximizes wrong-decision probability under a budget, breaking ties by lower cost and fixed action IDs. It is not an equilibrium or a behavioral deterrence model.

The summary reports wrong, correct, cancelled, blocked and deferred rates per offered run, decision rate, wrong conditional on decision, attempted-action rate and cost. Trace attack vectors separately exercise invalid states; ordinary authenticated source-state enumeration is not expected to produce verifier-blocked proposals. Cancellation is never counted as correctness or deterrence.

The machine-readable worked example includes complete blueprint bytes and key pins, a defer-to-resolve two-run chain, full source objects, publication events, canonical trace roots and verifier results. Additional participant/LLM/human fixtures demonstrate that authentic external judgments can still be wrong. Full test vectors, tampering vectors, exact weighted rows, source hashes and file manifest are saved alongside it. Economic challenge probabilities, budgets, bonds and adjudication are deliberately separate interfaces; the protocol does not assume that a detected error will be challenged.

Primary signature specification: [RFC 8017](https://www.rfc-editor.org/rfc/rfc8017), sections 8.2 and 9.2. All quorum/cost/error propositions above are stated with their assumptions and directly checked against the executable finite-state cases.
