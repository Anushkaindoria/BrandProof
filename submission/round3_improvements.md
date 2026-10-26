# Round 3 improvements

The roadmap below contains exactly three substantial product improvements. None is represented as completed in Round 2.

## 1. Advanced evidence-backed claim verification

**Round 2 that works:** exact fact lookup, regex claim extraction for key numerical/marketing patterns, terminology checks, policy checks, source-linked findings, and explicit insufficient-evidence status.

**Incomplete:** claim decomposition is narrow, evidence quality is not scored, semantic retrieval is not implemented, and the optional provider adapter is not shipped.

**Round 3 capability:** build a claim decomposition service that separates a sentence into atomic factual, comparative, and implied claims; index approved source chunks with pgvector plus full-text fallback; rank evidence quality and freshness; and validate provider JSON against Pydantic schemas before persistence.

**Success test:** on a curated benchmark of at least 100 synthetic claims, measure source precision, contradiction recall, unsupported-claim routing, and fabricated-source rate. Target zero fabricated source IDs and a measured improvement over the Round 2 rules baseline.

**Database/API changes:** add `source_chunks`, `claim_spans`, `evidence_quality`, and retrieval metadata; extend audit and evidence endpoints with retrieval scores, source provenance, and model/provider telemetry.

## 2. Verifiable proof-carrying content

**Round 2 that works:** SHA-256 content hashes, version-specific audit records, dependency version snapshots, reviewer identity, approval timestamp, and a viewable passport API.

**Incomplete:** passport presentation is basic, approval invalidation is relational rather than cryptographically signed, and there is no reproducible audit bundle export.

**Round 3 capability:** create signed, exportable provenance bundles containing normalized content, policy/fact snapshots, engine/provider configuration, finding resolutions, reviewer signature, and deterministic replay metadata. Automatically invalidate approval on any hash or dependency mismatch.

**Success test:** replay an exported bundle from a clean environment and reproduce the same content hash, evidence IDs, findings, and decision state; verify every modified version is rejected by passport validation.

**Database/API changes:** add `passport_bundles`, `provenance_events`, signature metadata, replay manifests, and a `validate` endpoint that returns the exact mismatch reason.

## 3. Proactive Brand Drift Radar

**Round 2 that works:** audit dependencies connect content versions to fact/policy IDs and versions; changed facts mark affected approved content as needing revalidation; the UI explains the changed dependency.

**Incomplete:** policy and asset impact analysis is basic, prioritization is not available, and revalidation is not scheduled or batched.

**Round 3 capability:** expand dependency extraction across source chunks, policies, assets, terms, and claim spans; compute impact confidence and risk priority; provide reviewer queues, bulk re-audit, notifications, and a change diff for each affected content item.

**Success test:** use a dependency fixture with related and unrelated fact/policy changes and verify only semantically dependent items are selected, ordered by risk, and cleared after a successful re-audit.

**Database/API changes:** add dependency confidence and impact reason fields, change events, drift priority, queue assignment, bulk re-audit endpoints, and notification state.
