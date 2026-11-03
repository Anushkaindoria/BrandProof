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

## Round 3 demonstration sequence (use this one)

1. **Upload a guideline.** As Administrator, open Brand Knowledge and upload a short guideline PDF or text file that states a new fact (for example "Charging speed: 65 W"), a banned word and a rule.
2. **Extract and approve.** In Knowledge extraction, choose the document and click Extract proposals. Show a fact with its source quote and page, then Approve it. Point out that nothing became evidence until approval.
3. **Submit the bad ad.** As Creator, audit: "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!" Show the three flags with their evidence, and the Rule check and AI suggestion badges.
4. **Show the gate.** Try to dismiss the battery finding as Creator. It is refused: high-severity findings need a reviewer.
5. **Smart rewrite.** Click Suggest rewrite. Show each change with its reason, reject one, apply the rest, and show the rules check result. Run the audit again on the new version.
6. **Approve.** Submit, switch to Reviewer, approve.
7. **Verify the passport.** Open Content History, view the passport, click Verify passport and show all four checks pass.
8. **Drift.** As Administrator, change an approved fact. Show the Verify passport result now reports changed evidence, and the content appears in Brand Drift.
9. **Settings.** Show the provider and model, and Test AI connection. Mention the rules-only fallback if Gemini is unavailable.

## What to say about safety

Rules stay authoritative. Gemini proposes; code verifies; a human decides. If Gemini is down the audit still runs on rules and says so.
