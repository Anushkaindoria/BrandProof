# BrandProof AI judge demo script

## Two-minute pitch

“BrandProof AI catches brand risk before it becomes public. Instead of giving a generic chatbot answer, it compares content against an organization’s approved facts, policies, and terminology, then carries the evidence into a human review workflow. A creator can fix a claim, re-audit the exact new version, and send it to an authorized reviewer. Once approved, the version gets a content passport. When a product fact changes, BrandProof does not invalidate everything — it identifies the dependent content that needs revalidation.”

## Demonstration sequence

1. Open the Dashboard. Point out that the metrics and activity are persisted demo records, not invented performance claims.
2. Open **Content Audit** and choose **NovaTech X1 launch ad**.
3. Run the audit. Show the three seeded findings: 7000 mAh conflicts with 5000 mAh, waterproof is unsupported because certification is absent, and “best phone ever” needs approved evidence.
4. Click/read the evidence panel on the battery issue: `NovaTech_X1_Product_Brief.pdf · p. 2` and the approved 5000 mAh excerpt.
5. Replace the copy with: “Meet the NovaTech X1 with a 5000 mAh battery and a 1 year warranty.” Run the audit again. Emphasize that this is a new content version and stale findings are not silently reused.
6. Submit the clean version for review. Switch the visible demo role to Reviewer and open **Review Queue**.
7. Add a review comment, approve the reviewed version, and open **Content History** to view the expanded version hash and passport record.
8. Switch to Brand Administrator. Update an approved fact through the knowledge/API workflow, approve a source document if one was uploaded, then open **Brand Drift** to show the dependent content marked for revalidation.

## Technical differentiators

- Deterministic checks for high-risk exact facts, rather than an arbitrary overall score.
- Evidence references are restricted to retrieved organization records; fabricated source IDs are not accepted.
- Immutable content versions and human approval are separate from automated analysis.
- Dependency-aware change impact avoids invalidating unrelated approvals.
- Explicit rules-only mode keeps the demo reliable and honest without an API key; Gemini semantic suggestions are available when configured and provider failures remain visible.

## Explain the Round 3 roadmap

Round 2 proves the workflow. Round 3 will deepen it in exactly three places: better claim decomposition and evidence quality, a reproducible signed provenance bundle, and proactive prioritized drift analysis across more dependency types. Each roadmap item has a benchmark or replay test, not just a UI promise.
