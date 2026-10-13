# Verified execution: bounded research protocol, version 1

This specification gives the working paper a complete executable commitment and evidence layer. It is a restricted source/add/branch/terminal grammar, not the product's general DAG interpreter. It executes actual typed operations, RSA source verification, canonical serialization, Merkle proofs, semantic checks and a bounded reveal/challenge lifecycle. The hardware tiers remain architectural: this prototype does not run in, remotely attest, or measure a TEE.

The implementation is `simulation/protocol.py`; an independently written Node implementation, `simulation/independent_verifier.mjs`, checks the canonical bytes and Merkle construction without invoking Python. Node does not independently implement the full DAG interpreter or RSA. The compiled AVM artifact and its own measurements are specified in `avm/README.md`.

```sh
python -m research.verified_execution.protocol_experiments --output-dir 03-verified-execution/output/protocol
python -m unittest discover -s tests -p 'test_execution_protocol.py' -v
```

Runtime Python dependencies are standard library only. Node is required for the independent cross-language experiment. Commands assume the repository research package has been installed. Every generated experiment records its configuration before evaluation, source SHA-256 digests, raw vectors, independent-verifier responses, platform/runtime versions and an output manifest. There is no random seed because the conformance and attack cases are deterministic and enumerated. Timing repeats measure this host's implementation; they are not independent market observations or confidence intervals for production performance.

## 1. Exact data and hash encoding

`canonical(value)` is a deliberately restricted JSON profile, not a general implementation of RFC 8785. It permits null, Booleans, integers in `[-(2^53-1), 2^53-1]`, ASCII strings, arrays and string-keyed objects. Object keys are ordered lexicographically; arrays retain order; there is no whitespace. ASCII strings use JSON's usual short escapes for backspace, tab, newline, form feed and carriage return, quote/backslash escaping, and lowercase `\u00xx` escapes for remaining control characters; ASCII DEL (0x7f) is always escaped as `\u007f`. There is no Unicode normalization because non-ASCII input is rejected. Floats, `NaN`, duplicate keys, alternate number spellings, noncanonical escapes, excess nesting (more than 32) and unknown schema fields are rejected. A parsed message must re-encode to exactly the received bytes. JSON Boolean `false` and integer `0` remain different values. The object byte limit is 278,528; a trace leaf is at most 4,096 bytes.

A digest is represented in objects as exactly 64 lowercase hexadecimal characters. Integer widths in binary envelopes are specified separately below. `H` is SHA-256; all domain tags are literal ASCII followed by exactly one NUL byte. For an object `x`,

```
object_digest(tag,x) = H(ASCII(tag) || 0x00 || canonical(x))
```

Distinct domain tags are `QM_EXEC_BLUEPRINT_V1`, `QM_EXEC_SOURCE_V1`, `QM_EXEC_SNAPSHOT_V1`, `QM_EXEC_POLICY_V1`, `QM_EXEC_REQUEST_V1`, `QM_EXEC_SEMANTICS_V1`, `QM_EXEC_RESULT_V1`, `QM_EXEC_CONTEXT_V1`, and `QM_EXEC_WHOLE_TRACE_V1`. `QM_EXEC_SOURCE_V1` signs source-body bytes rather than returning an externally used standalone body digest. The domain is in the preimage; a bare digest does not reveal its version. Callers must supply and check the versioned object type.

## 2. Trusted request, snapshot, result and per-run context

The verifier receives the immutable committed blueprint and authorized request from trusted market state. An attacker cannot replace those inputs when challenging or finalizing. The exact request keys are:

```
version: 1
chain_id: bounded nonempty ASCII string
market_id: bounded nonempty ASCII string
request_id: bounded nonempty ASCII string
blueprint_digest: digest of the complete validated blueprint
snapshot_digest: digest of the complete signed snapshot
agreement_policy_digest: digest of the declared equivalence/committee policy
```

The first three identifiers are at most 128 characters. Request identity denotes an authorized execution slot; this module's context binding does not itself enforce who may occupy that slot or how many attempts are allowed. The companion `quorum.py` model enforces assignment, single eligible attempt and complete attempt publication.

The base agreement-policy object is exactly `{version:1,equivalence:"complete-deterministic-semantics"}`. The only permitted extension adds **both** `quorum_policy_digest` and `attempt_policy_digest`, each a lowercase 32-byte digest, without changing the equivalence rule. The extended policy binds the composition with the committee/attempt state machine. The runner and full verifier receive the policy object and require its digest to match the request. They do not silently reinterpret exact semantic equivalence as label-only agreement.

A snapshot is `{version:1,reports:[signed_report]}` in this one-source grammar. All report preimages are embedded in the source record. There is no unresolvable evidence pointer or omitted attachment. The signed report binds the request's chain, market, request identifier and blueprint, but does not bind the request digest itself: that digest includes the snapshot, so doing so would be circular.

The exact shared result keys are:

```
version: 1
request_digest: request hash
snapshot_digest: pinned snapshot hash
terminal_action: "resolve"
outcome: Boolean
semantic_projection_digest: QM_EXEC_SEMANTICS_V1 hash of the full record array
```

The narrow reference grammar always reaches a Boolean result. Cancellation, withholding and committee fallback are lifecycle states, not extra successful terminal values. The result digest uses `QM_EXEC_RESULT_V1`.

The exact run context is `{request_digest,snapshot_digest,run_id,runner_id,measurement}`. Identifiers are bounded strings, and measurement is a 32-byte digest. `QM_EXEC_CONTEXT_V1` hashes this object. Different run identifiers, operators or measurements therefore produce different trace roots while honest executions over the same request/snapshot produce the same result digest. `measurement` is unauthenticated metadata unless an additional attestation/key-registration layer checks it.

The complete trace object is `{version:1,context,records,result}`. A canonical whole-trace baseline hashes this entire object under `QM_EXEC_WHOLE_TRACE_V1`. The Merkle root hashes the records and context; the receipt binds that root **and** the separately shared result digest. An isolated Merkle root does not by itself bind an uncommitted external result object.

## 3. Bounded typed blueprint and full trace semantics

The blueprint has exact keys `version`, `profile`, `source_authority`, `source_key`, `min_observed_at`, `max_observed_at`, and `nodes`. Version is 1 and profile is `question.execution.branch-chain.v1`. The source public key is a canonical 2048-bit RSA modulus and integer exponent 65537. Uppercase, extra leading zeros, `0x` prefixes and Boolean exponents are rejected, preventing alternate serialized key identities.

For `4 <= n <= 64`, the nodes, in order, are:

1. Index 0: one authenticated integer source, with no parent.
2. Indices 1 through `n-4`: integer addition by exactly 1, each consuming the previous node's output. This range is empty for n=4.
3. Index `n-3`: compare the preceding integer with the fixed threshold `n` using `>=`.
4. Indices `n-2` and `n-1`: terminals selected by Boolean true and false, respectively. Both have the comparison as their sole parent.

Each node is exactly `{index,node_id,kind,parent,params}`; IDs are `n000`, `n001`, etc., and kinds are `source`, `add`, `ge` or `terminal`. The validator checks this complete grammar, order, unique positions, parent list and parameters against the committed blueprint. This is a total single-pass program. Arbitrary expressions, joins, dynamic loops and in-graph retries are outside this profile; extending it requires a new validated grammar and soundness argument.

Every node gets one record, including the inactive terminal. A record is exactly:

```
index, node_id, kind, status, input, output, edge_taken
```

The source's input contains the full snapshot, its output is the authenticated integer, and its edge points to the next node. Each add/compare input must equal its declared parent's output **with JSON type preserved**. An add emits input+1 and the next node ID. The compare emits a Boolean and the chosen terminal ID. Both terminals record the compare's Boolean input. The selected terminal has status `ok`, emits that Boolean and has a null next edge; the other has status `skipped`, output null and next edge null. Exactly one terminal succeeds. The shared result must match that terminal and the hash of the full semantic record array.

The source value is bounded by `[-(2^53-1), (2^53-1)-64]`, so the bounded addition chain cannot overflow the exact integer profile. `run` produces the records. `verify_trace` independently checks the rules and does not invoke `run`. A successful check establishes a valid abstract execution over the declared inputs. It does not prove a historical process actually performed those steps; an attacker can construct a consistent witness without executing the designated binary.

A leaf count is only a cheap sanity check. The adversarial corpus includes `A,A,C`-style duplication, a substituted unrelated node, reordered nodes, broken parent linkage, wrong outputs, wrong branch, both terminals active, wrong skipped output, Boolean/number substitution, wrong terminal result, wrong projection, request/snapshot replay, omitted source preimage and an unknown record field. All fifteen attacks retain sixteen records and obtain a fresh valid Merkle root. All memberships verify; the semantic checker rejects each attack.

## 4. Count-bound indexed Merkle commitments

`context32` is the raw context digest. `u64(x)` is an unsigned eight-byte big-endian integer. For each canonical record payload `P_i`:

```
L_i = H("QM_EXEC_LEAF_V1" || 0x00 || context32
        || u64(n) || u64(i) || H(P_i))
I(a,b) = H("QM_EXEC_NODE_V1" || 0x00 || a32 || b32)
Z_i = H("QM_EXEC_PAD_V1" || 0x00 || context32 || u64(n) || u64(i))
R = H("QM_EXEC_ROOT_V1" || 0x00 || context32 || u64(n) || inner_root32)
```

Trees are nonempty. The next power-of-two width determines depth; positions from `n` to width−1 contain the distinct deterministic `Z_i` values. Internal nodes combine adjacent left/right children in order. There is no odd-leaf duplication, sorted-pair convention, null-as-empty-leaf ambiguity or unconstrained padding.

An inclusion proof is the ordered list of sibling hashes from leaf to root. Verification requires `1 <= n <= 64`, integer `0 <= i < n`, exactly `ceil(log2(n))` siblings, exact hash widths, context equality, and payload at most 4,096 bytes. At each level, a sibling subtree entirely beyond `n` must equal the independently computed padding subtree. The verifier reconstructs the wrapped root. Boolean indices, extra/short paths, count changes, wrong positions and malformed wholly padded sibling subtrees encountered by the path are rejected. A partly padded sibling is an opaque subtree commitment to this verifier; a single path does not prove all global padding is canonical. Full reconstruction or all indexed openings exposes that remaining condition.

The prototype supports non-power-of-two counts; the compiled AVM benchmark deliberately restricts its accepted counts to powers of two up to 64 and rejects unsupported counts. This restriction removes padded-subtree reconstruction from the measured contract. Both use exactly the same envelope on their shared domain.

Starting from bytes, ordinary power-of-two membership requires `ceil(log2(n))+3` SHA-256 calls: payload hash, leaf-envelope hash, path hashes and root-wrapper hash. A prehashed-leaf or path-only estimate is a different operation. Canonical parsing, semantic replay, signatures, state access and transaction framing are additional work.

**Indexed binding proposition.** Assume SHA-256 collision resistance and the specified shape/encoding checks. An accepted proof fixes the payload at the committed `(context,n,index)` up to a hash collision. Supplying a second different payload at the same position, changing count/context under the same root, or replacing a padding subtree requires a collision in the payload, leaf, internal or root envelope. Proof: take the first differing preimage on the path between the two root reconstructions. Fixed-width envelopes/domain separation and exact proof depth exclude encoding and shape aliases. This proposition is computational binding, not a proof that all n payloads are available or semantically valid.

**Semantic completeness proposition.** For a validated blueprint, if the verifier accepts all n records and the result link, those records describe the unique abstract execution of this grammar on the pinned authenticated snapshot. Proof: the source rule determines index 0; induction over the add chain uniquely determines integer outputs; the comparison uniquely determines the branch; the two terminal rules permit exactly one successful terminal; the final check binds that terminal and the entire record projection. No argument depends on count alone. The conclusion is conditional on source authentication and does not establish source truth.

## 5. Authenticated targeted faults and signed receipts

`verify_local_fault` accepts a committed child payload and membership path, plus its committed parent's payload and membership path for nonroot nodes. The blueprint fixes the child and parent indices; the challenger cannot substitute a convenient unrelated parent. The function first verifies memberships in the **same** context/count/root, then checks the committed local identity, typed parent link, output and transition. The source case needs only its own leaf because its complete signed input is embedded there. Wrong result linkage and whole projection equality are separate checks.

A verified inclusion proof alone never establishes fraud. An invalid proof is rejected challenger evidence, not a reason to slash the proposer. The targeted tests show that a wrong add output is actionable with its two valid memberships, while corrupting either membership or supplying a counterfeit parent causes rejection of the challenge.

**Local-fault soundness.** Under indexed binding and correct local checker semantics, an accepted targeted fault demonstrates a contradiction in the committed transcript: a malformed committed record, a parent/output mismatch, a wrong typed computation or an illegal transition. A valid complete trace cannot produce such a fault. The claim does not establish that a challenge will actually be submitted, that every semantic fault has the same compact witness, or that a ledger directly implements every off-chain predicate.

For the AVM benchmark, an Ed25519 receipt signs the 32-byte digest

```
H("QM_EXEC_AVM_RECEIPT_V1" || 0x00 || context32 || u64(n)
  || root32 || result_digest32)
```

The contract reconstructs this projection from registered state and verifies the signature against its pinned public key. The digest includes result and trace, while allowing distinct per-run receipts to endorse the same shared result. This is signature validity under a registered test key; it is not remote attestation. On-chain canonical JSON or full DAG replay is not included in the AVM membership/signature measurement.

## 6. Source authentication, shared-host forgery and freshness

A source body has exactly `version`, `chain_id`, `market_id`, `request_id`, `blueprint_digest`, `authority`, `observed_at`, `value`, and `data`. Version is 1, value is the bounded integer, and data is an ASCII source payload of at most 1,024 characters. Each identity must match the request and pinned source authority. Observation time must lie in the blueprint's declared inclusive window. These provider observation times are distinct from ledger-round lifecycle counters; a signature authenticates the provider's timestamp claim, not an independent physical clock.

A report is `{body,signature}`, where the signature is strict RSASSA-PKCS1-v1_5/SHA-256 over `"QM_EXEC_SOURCE_V1" || 0x00 || canonical(body)`. The verifier checks all 256 bytes of the encoded message, including the padding and SHA-256 DigestInfo, not a digest substring. The fixture key file is copied from the prior paper's published RSA research fixtures and deliberately includes public **test** private keys. It must never be used for real authentication. The small modular-exponentiation implementation is a reference checker, not an audited production cryptographic library.

The source experiment compares one and three distinct signing authorities under four controlled conditions: authentic truth, host fabrication with authentication disabled, the same host fabrication with authentication required, and an authentic common source error. A single host can invent all three unauthenticated responses without compromising any endpoint. With each response authenticated against an independent pinned key, the same mutation fails signature verification. Three authentic signatures on the same false report still pass. The last case is a positive control for the distinction between authenticity and truth, not a protocol failure disguised as an accepted accuracy test. These eight vectors exercise the authentication primitive on one or three signed Boolean reports, separate from the one-source integer DAG grammar. They do not pretend to execute a three-source DAG and do not measure actual provider compromise rates, TLS behavior or vendor independence.

## 7. Enforceable bounded availability before a challenge window

`RevealSession` is a concrete ordered-ledger state machine. It assumes persistent public ledger data and clock progress, not an IPFS gateway or trusted retrieval report. The reference implementation stores revealed records in memory to emulate that data surface. Deploying this rule requires placing the bytes in an actual persistent ledger/DA layer and paying its costs. The AVM benchmark measures membership/signature checks, not a deployment of the complete reveal lifecycle or its storage/publication costs.

At proposal, market state fixes the request, blueprint, context, root, result, reveal window and challenge window. The blueprint fixes count n. The complete blueprint and agreement policy are market state; every remaining evidence preimage is in the leaf array. Accepted reveal transactions authenticate `(index,payload,proof)` against the stored root. Duplicate indices, malformed proof paths, noncanonical payloads and oversized payloads are rejected. The source snapshot must therefore be supplied as actual bytes if the source position is to be revealed. The source position counts only after the full snapshot/report/body structure and signature bytes are disclosed and the snapshot digest equals the pinned request. A freshly committed placeholder cannot satisfy this gate. Source authenticity, truth and transition correctness remain semantic checks.

The states and exact boundaries are:

| State | Transition |
|---|---|
| `revealing` | Accept each unique leaf only while `now < proposed_at + reveal_window`. |
| `revealing` → `unavailable` | At or after the reveal deadline if any leaf is missing. This proposal cannot finalize or reopen. |
| `revealing` → `challenging` | On the final distinct valid reveal, set `challenge_deadline = now + challenge_window`. |
| `challenging` → `rejected` | Before the challenge deadline, an authenticated semantic challenge succeeds. |
| `challenging` → `finalized` | At or after the challenge deadline, if no successful challenge has rejected the proposal. |

No challenge clock runs before complete reveal. Exact-deadline late reveal is rejected. A full reveal at time 9 with ten-round challenge duration cannot finalize until time 19. No-reveal and one-missing-leaf proposals become unavailable at time 10. The latest time at which an entirely revealed proposal becomes eligible for finalization is bounded by `proposed_at + reveal_window + challenge_window`; construction rejects clocks whose derived deadlines exceed the exact integer profile. This is an eligibility bound, not a bound on the eventual finalization transaction. Timeout invocation is permissionless in the modeled interface; actual progress still requires transaction inclusion. `unavailable` is proposal cancellation, not evidence for the opposite factual outcome; market-level replacement and adjudication policy are separate.

**Availability-before-finalization proposition.** In any legal execution of this state machine, `finalized` implies every one of the n committed leaf byte strings was publicly supplied before the challenge window began, including every source preimage committed by the request, and the full prescribed window elapsed. Proof: only `challenging` can become `finalized`; entry into `challenging` requires n distinct valid indexed reveals; every index is bounded by n, so no duplication can cover an omitted slot; the source-slot gate requires complete snapshot preimages matching the immutable request; the deadline is created only on that transition. Persistent access afterward is the ledger's availability/retention assumption. A hash alone never establishes this fact.

Availability is distinct from truth and semantic validity. An attacker can reveal a complete but wrong transcript and win if nobody challenges. The corpus deliberately includes that accepted control. A source record with missing referenced content is rejected by the positive disclosure gate before the challenge window can open; the state machine still does not silently run every semantic check at finalization. Stronger finalization can require positive full verification, with its different costs and trust surface declared explicitly.

This all-reveal profile makes the enforcement claim precise but exposes a tradeoff: it guarantees evidence delivery by spending O(n) publication bytes. Merkle commitments then reduce subsequent selective dispute evidence; they do not reduce the baseline publication cost. A trigger-only reveal scheme could avoid many publications but would retain a checker/trigger assumption for global availability unless another positive DA gate is specified.

## 8. Reproducible evidence and measured comparison

The frozen suite publishes:

- 23 canonical byte cases; 64 tree constructions; 2,656 proof cases, including all 2,080 valid count/index positions and 576 invalid cases. Python and independently written Node agree exactly.
- Six valid semantic traces for both branches at 4, 16 and 64 records; fifteen newly committed count-preserving semantic attacks, all rejected.
- Eight one-/three-source authentication controls, and ten reveal/challenge lifecycle traces with exact events/deadlines.
- A two-run worked example with equal shared result digests and different trace roots, runner identifiers and measurement metadata.
- Local timing repetitions for full-trace hashing, one-leaf Merkle verification, full/single-leaf canonical parsing, full semantic replay with source RSA verification, and a two-leaf local check.

The byte baseline is canonical **whole-trace hashing**, not an uncommitted output. Both whole-trace hashing and Merkle hashing detect postcommitment modification. Merkle's incremental benefit is selective authenticated disclosure and compact local evidence. On the worked traces:

| Records | Full trace | One leaf + path + index | Child + parent, two paths + indices |
|---:|---:|---:|---:|
| 4 | 2,166 B | 170 B | 1,433 B |
| 16 | 3,356 B | 234 B | 468 B |
| 64 | 8,156 B | 299 B | 598 B |

The one-leaf column selects the comparison at n=4 and a middle add at n=16/64. A local transition check needs its parent; the four-node parent is the 1,191-byte source record, explaining the larger two-leaf case. Stored roots/request/context/count and ordinary transaction framing are excluded equally. Proofs are separate paths, not an optimized multiproof. Complete publication still costs every leaf plus its reveal framing/proof.

In the recorded Python measurements, whole-trace hash-only verification is faster than one-leaf Merkle verification at all three sizes. Canonical parsing and full semantic replay are different, more expensive operations; their timings are reported separately. The experiment therefore supports a disclosure-size and dispute-locality result, not a universal CPU speedup. Full raw timing batches are in `output/protocol/disclosure_benchmarks.json`; hardware/software context is in `summary.json`. No microbenchmark result is promoted to a mainnet end-to-end latency, fee or throughput claim.
