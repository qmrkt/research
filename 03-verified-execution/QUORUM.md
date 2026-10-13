# Quorum and attempt-selection model

This executable companion turns the threshold and sampling policies into falsifiable protocol rules. It uses the shared request and result encodings in `PROTOCOL.md`. It does not emulate a TEE. Its public test-secret HMAC authenticator exercises signed-object and state-machine checks under an authentication assumption; it does not establish public-key security, nonexportable keys, genuine attestation, independent hardware, or real model accuracy.

Run after installing this repository:

```sh
python -m research.verified_execution.quorum_experiments --output-dir 03-verified-execution/output/quorum
python -m research.verified_execution.quorum_integration --output-dir 03-verified-execution/output/quorum
python -m research.verified_execution.quorum_protocol_audit --output-path 03-verified-execution/output/quorum/protocol_boundary_audit.json
python -m unittest discover -s tests -p 'test_execution_quorum*.py' -v
```

## Two objects, one agreement rule

An authorization pins the chain, market, request ID, blueprint digest, input snapshot digest, and agreement-policy digest. The latter binds the fixed committee, quorum composition constraints, and attempt policy. Each preauthorized attempt is a child request with its own immutable slot ID. Thus one vote per request means one vote per child request; it does not prohibit a runner from executing several separately authorized slots.

The shared result contains the request digest, snapshot digest, terminal action, Boolean outcome, and semantic-projection digest. The common wire functions validate exact field sets, types, bounded ASCII identifiers, and 32-byte lowercase hexadecimal digests. Boolean `true` is not a version or integer epoch.

Each runner authenticates a separate receipt binding the shared result digest to its own runner ID, run ID, trace root, trace address, measurement, and registration epoch. Honest independent executions can have different roots, addresses, binaries, run IDs, and full receipt digests while agreeing on the shared result. Comparing full receipts is wrong even for deterministic execution. A deterministic descendant agrees only when its committed inputs agree. Comparing only terminal labels is also insufficient if the declared policy requires equality of the semantic projection.

The quorum verifier checks a fixed signer set, distinct voting identities, the authorized policy, matching request/snapshot/result, valid authentication, registered measurement and epoch, validity at acceptance, validity through the declared finalization deadline, and revocation at finalization. Receipt validation does not establish semantic validity by itself: an honest runner must verify the declared execution and projection, and the separate evidence-publication gate must pass. The ledger receives that gate's verdict from the bounded trace protocol; a Boolean in this model is an adapter boundary, not a proof of data availability.

The fixed committee is an authorization assumption. A registrar can invalidate it by fabricating identities before the committee is pinned, or by overriding an already pinned identity if the production registry permits substitution. A registrar that can only issue unrelated keys after immutable assignment cannot automatically compromise this existing request. Registry updates, operator aliases, revocation and committee replacement must obey the same authorization boundary.

## Threshold guarantees

Let the assigned set have `n` voting identities; at most `f` are Byzantine. Authentication is unforgeable for honest keys; honest identities endorse at most one result per request; the request and snapshot cannot change; a valid receipt is checked against its assigned identity. These assumptions concern endorsed execution, not external truth.

**Authenticity.** If `k > f`, every accepted `k`-of-`n` certificate includes at least one honest endorsement. Proof: an all-Byzantine set contains at most `f` identities. This does not guarantee conflict resistance when several outcomes can legitimately arise.

**Conditional liveness.** If `k <= n-f`, an agreeing set of all honest runners can form a certificate despite Byzantine withholding. This additionally requires execution to complete, evidence to become available, messages to reach the finalization service, and honest runners to agree under the declared comparison policy. A censoring coordinator or genuinely divergent stochastic judgments can still stop progress. No delivery or latency claim follows from the cardinality inequality.

**Conflict resistance.** For arbitrary admissible outcomes, `2k > n+f` prevents two conflicting certificates. Their signer sets intersect in at least `2k-n > f` identities, so at least one honest identity would have to endorse both results. The strict inequality matters. At `n=5,k=3,f=1`, signer sets `{0,1,2}` and `{0,3,4}` can endorse opposite results while only signer 0 equivocates. Both certificates pass authentication and each contains honest signers. The executable witness preserves this failure. For deterministic execution where all honest runners necessarily endorse the same result, the stronger semantic assumption can already make `k>f` sufficient; the intersection theorem covers the more general case.

For an arbitrary accepted-quorum family `Q`, replace the cardinality formula with

```
min(|A intersect B| : A,B in Q) > f.
```

Authenticity means no accepted quorum is wholly contained in the compromised set. Conditional liveness means at least one accepted quorum is wholly contained in the available, agreeing honest set. These statements also cover minimum-vendor/operator/registrar constraints. Such constraints can improve one attack surface without improving the minimum intersection.

## Correlated dependency attacks

Do not assign independent compromise probabilities merely because runners carry different vendor names. Model each dependency attack `d` as compromising a set `C_d` of assigned identities, at a declared scenario cost `c_d`. The least-cost all-compromised certificate is exactly

```
min sum(c_d for d in D), subject to some Q in quorum_family
    being contained in union(C_d for d in D).
```

The reference enumerates every attack subset. Costs are illustrative units, not measured exploit prices. For three vendor-A runners and two vendor-B runners with `k=3`, one vendor-A attack suffices. Requiring both vendors in every quorum forces both vendor attacks in that restricted attack catalog. Adding a shared registrar attack that can substitute all assigned identities makes one attack sufficient again. A common build pipeline, source provider, TLS trust store or model API can be another shared failure; their consequences differ and must be represented accurately. A false but authentic common source can corrupt every result without compromising any receipt key. This model's dependency-cover calculation concerns compromise of execution endorsements, not a theorem about truth.

The four exact scenarios produce costs `10,1,20,1` (unconstrained vendors; plus shared registrar; constrained vendors; plus shared registrar). Both quorum policies have minimum intersection 1. Vendor constraints alone therefore do not repair the `3-of-5,f=1` conflict witness.

## Selection integrity is a separate property

If an adversary can run an independent stochastic execution `m` times and publish any favorable valid receipt, success is

```
1 - (1-p)^m,
```

where `p` is the favorable probability of one prescribed invocation. At `p=0.1,m=30`, this is `0.9576088417`. The identity follows by taking the complement of all `m` failures. It assumes independent attempts with the same favorable probability; under arbitrary dependence, the union bound is at most `min(1,sum(p_i))`, and perfectly correlated attempts give no amplification. Here “favorable” means attractive to the selecting party, not necessarily incorrect.

The ledger preauthorizes a fixed set of attempt slots before results are known. Its executable profiles are a single required first slot, or an odd fixed number of slots with an all-attempt majority. Every required slot must publish a valid certificate and pass the separate availability gate. An abort or a missing slot at the deadline cancels the parent request. A successful slot cannot be replaced; extra slots, reusing a completed slot, cross-slot receipts and altered snapshots are rejected. “First” refers to the preassigned slot, never the first result that a coordinator elects to disclose. The first-arrival race is not a sampling policy.

This prevents selection among the ledger's completed, authorized slots. It does **not** count hidden invocations inside one slot. A host that can observe candidate outputs and roll back or restart an honestly measured stochastic program can still pick a favorable output before the first visible completion. The tests intentionally include a valid certificate accepted after 29 hidden unfavorable candidates and one favorable candidate. Merely requiring a public start record and forbidding a second public completion does not defeat that attack. The measured execution contract needs reproducible execution for the fixed seed/input, or a separately justified nonrollbackable execution/publish-before-observe mechanism.

### A sharp bound on selective abort

Let `Y` be the prescribed result for each preauthorized request, `E` any favorable event with baseline probability `p=P(Y in E)`, and `A` the event that the request finalizes. Suppose execution integrity has already prevented changing `Y`; the host may only publish it or abort. With completion rate `alpha=P(A)>0`,

```
max(0,(p+alpha-1)/alpha) <= P(Y in E | A) <= min(1,p/alpha).
P(Y in E and A) <= p.
```

Proof: `P(E intersect A)` lies between `max(0,p+alpha-1)` and `min(p,alpha)` by elementary intersection bounds. Divide by `alpha`. Each endpoint is attained by selecting favorable or unfavorable outcomes first, with randomization at the boundary when needed. No independence between abort and outcome is assumed.

This establishes both a useful guarantee and an impossibility. Abort-only power cannot increase favorable resolutions **per authorization** beyond `p`. It can make **every finalized result** favorable by canceling all unfavorable requests: `alpha=p`, conditional favorable frequency 1. Forced recording, complete evidence publication and cancellation alone cannot remove that conditioning. Measuring only finalized markets hides exactly the attack that must be measured. Conversely, an independently established completion lower bound `alpha >= 1-c` yields `P(E|A) <= min(1,p/(1-c))`; this is a measurable operational target, not an automatic consequence of bonds or attestation. No finite economic penalty makes it a cryptographic liveness theorem.

The bound assumes a fixed cohort of authorizations that the adversary cannot silently replace. Allowing the adversary to create new requests after seeing outcomes reintroduces selection at the cohort level. Market creation, authorization count, cancellations and all abandoned attempts must remain in the denominator. Unknown baseline `p` cannot be recovered merely from completed observations; a controlled baseline or a defensible external bound is needed.

### Mechanisms worth developing

1. Commit the question, snapshot, model weights/version, decoding rules, exact inference semantics, slot assignment and aggregation policy before an unpredictable public seed is revealed. Derive each slot seed from the public randomness and its immutable request digest. Threshold randomness or a robust beacon can remove unilateral seed choice under their own availability/bias assumptions. A simple commit-reveal protocol still allows the last revealer to withhold and must specify that failure.
2. Make reexecution under that request and seed return the same result. Counter-based sampling alone does not make a remote model endpoint or nondeterministic floating-point kernels reproducible. Pinned local inference, validated deterministic kernels and committed inputs are promising bounded profiles. This experiment verifies only a deterministic toy function, not an actual model.
3. Separate retrying transport from resampling inference. Replicas retry the identical request/input/seed; they do not generate new seeds on failure. If multiple seeds are necessary, authorize the entire fixed set in advance, publish every required result, and apply the precommitted aggregation rule. Selection-friendly “retry until success” rules defeat the construction.
4. Address abort through availability and outcome disclosure: independent replicas able to recover the identical computation, or mandatory encrypted publication before any selecting party can learn the outcome with a sufficiently live release committee. These need their own security and liveness arguments. They are research directions, not properties demonstrated by the current harness.

**Deterministic retry proposition.** For fixed request `R`, fixed authorized seed `s`, and an exactly deterministic function `F`, every invocation returns `F(R,s)`. Therefore reexecuting any number of times creates no new candidate result and cannot amplify a favorable event within that authorization. This is immediate from functional equality. It says nothing about biased seed choice, changed snapshots, new authorizations, hidden remote-provider state, cancellation or selective finalization. Combining reproducible execution with the selective-abort bound gives an auditable per-authorization guarantee while making remaining liveness power explicit.

**Conditional replica-completion corollary.** Strengthen the construction with an unbiased post-commit seed, `k>f`, an available agreeing honest quorum for every required slot, independent submission paths, complete evidence publication, and no unilateral host cancellation. Every accepted output then equals the predetermined aggregate of `F(R,s)` results, and a valid aggregate always completes: authenticity supplies an honest endorsement, determinism identifies its value, and the available honest quorum supplies a recoverable certificate for every required slot. Completion is one, so the selective-abort bound collapses to the baseline probability. This is a design theorem under explicit availability assumptions, not a measured property of the current cancellation-capable ledger. Individual replica failures must never cancel a request while a valid honest quorum can still recover it.

## Evidence and interpretation

The frozen `output/quorum/design.json` specifies 16 Bernoulli cells (`p` in `0.01,0.1,0.3,0.5`; attempts in `1,3,10,30`), 20 seeds and 1,000 paired observations per seed/cell: **320,000 raw observations**. Every observation retains its seed, cell, episode index and complete outcome bitmask. The audit rejects duplicate or missing rows and recomputes the summary independently from those bitmasks. Exact probabilities are the primary evidence; simulation checks the implementation and illustrates effect sizes. Wilson intervals describe Monte Carlo sampling uncertainty, not empirical uncertainty about real TEE or model error rates. Auxiliary majority columns use a fixed strict-majority rule, with ties mapped to false for even sizes; only odd-size majorities are implemented by the ledger profile.

At `p=0.1,m=30`, choosing the best candidate yields **95.63%** favorable published results (95% Wilson interval **95.34–95.90%**), versus **9.97%** for the predetermined first slot (95% interval **9.56–10.39%**). Publishing only favorable first-slot outputs produces **100% favorable finalized outputs**, but completes only **9.97%** of authorizations. No interpretation of the finalization-only cohort can replace that denominator. The predetermined majority of three has exact favorable probability **2.8%**, compared with **27.1%** for best-of-three; observed values are **2.66%** and **27.44%**. This changes the declared decision procedure, so it is useful only when majority aggregation is itself the intended market rule.

Exact checks cover **240 `(n,k,f)` configurations**, **3,586 fault sets**, and **65,280 event/selection pairs** on an eight-element probability space. The sharp abort bounds have zero violations, and both endpoints are attained. Seventeen certificate vectors include three accepted controls and fourteen rejected attacks. The tests retain accepted conflict, hidden-restart and selective-abort counterexamples as expected outcomes rather than concealing them as failed experiments. Ten thousand deterministic toy requests are rerun 30 times each (**300,000 reexecutions**) with zero changed results; 1,018 requests have a favorable initial result. That is repeatability evidence for the toy function only.

Registration lifecycle tests enforce epoch and measurement binding, expiry through the request deadline, revocation before finalization, and distinct fixed voting identities across key aliases. They do not validate genuine vendor attestation certificates, trusted hardware clocks or real key nonexportability. The source and output hashes, Python runtime, frozen design and raw observation audit are in `output/quorum/manifest.json`.

A subsequent integration design, explicitly recorded as follow-up work in `integration_design.json`, connects actual authenticated wire traces to the honest signer adapter, quorum certificate and mandatory reveal state machine. Three independently contextualized traces have different roots and one shared result digest; all three pass source authentication and complete semantic checks before receipt issuance. An authentic but wrong common source still produces an accepted wrong outcome relative to the synthetic world label. A host-fabricated source preimage is internally consistent after rehashing but is rejected before an honest receipt is issued. An unregistered measurement is also rejected. Withholding one required trace leaves an otherwise valid certificate unable to pass the all-traces availability gate. All five vectors have their expected outcomes. These integration checks plus the quorum/attempt conformance suite comprise 21 tests; the follow-up is not represented as preregistered or held-out evidence.

A further independent code audit exercised 35 honest traces at 4, 5, 7, 16 and 64 slots with source values at numeric and branch boundaries. All 672 memberships passed and none of those honest records produced a false local-fault conviction. The reproducible command and full rows are retained in `quorum_protocol_audit.py` and `protocol_boundary_audit.json`. This audit was recorded after its first execution and rerun verbatim; it is a boundary regression check, not a new preregistered experiment or a proof covering arbitrary programs.
