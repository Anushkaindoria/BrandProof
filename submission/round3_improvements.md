# Round 3 completed-improvements list

Honest status of each promised improvement. "Implemented" means the code exists and is covered by automated tests; items marked "to confirm" need the team to run them with real dependencies or a Gemini key.

## 1. Gemini AI Content Auditor — implemented, live check to confirm
- Gemini reviews tone, terminology, accessibility and policy, with severity, a one-line reason and evidence citation (`backend/app/ai.py`, `backend/app/main.py: save_audit`).
- Safeguards: evidence IDs validated against organization records; output clamped to known values; high severity needs real evidence; AI findings that restate a rule finding are dropped; AI findings are tagged in the UI.
- Reliability: key sent in a header; 429/5xx retried with backoff; rules-only fallback with the error shown on the audit.
- Settings shows provider and model, and an admin "Test AI connection" button.
- To confirm: run the connection test and `python eval/run_eval.py --gemini` with a real key.

## 2. Smart Correction Engine — implemented
- Minimal, explained edits per finding (`backend/app/corrections.py`, `POST /api/content/{id}/rewrite`).
- Rules supply exact fixes; Gemini edits are kept only if the rules confirm no new violation; the result is re-audited and shown as passing or not.
- UI: per-change accept/reject diff with source badges; applies only the accepted changes.

## 3. Brand Knowledge Extraction — implemented
- Uploaded PDF/text/Markdown to proposed facts, terminology and policies (`backend/app/extraction.py`, `/api/documents/{id}/extract`).
- Rule-based extraction works offline; Gemini proposals are dropped unless their quote and value are found in the document.
- Admin review panel shows the source quote and page, allows editing a value, and approves or rejects. Approving a changed value bumps the fact version and triggers drift.

## Also completed
- Governance fixes (high-severity dismissal gate, submit gate, drift on deactivate, dependency de-duplication, non-destructive startup upgrade).
- Signed passports with a Verify action.
- 62-claim evaluation set and runner.

## Not done
- Brand Manager and External Agency roles; real authentication.
- pgvector retrieval, distributed queue, notifications.
