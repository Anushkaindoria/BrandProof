"""Smart correction engine: minimal edits, each explained, verified by the rules.

Design: AI proposes, rules verify, humans decide.

1. The deterministic rules produce exact edits for every open rule finding. These are
   guaranteed replacements taken from approved facts, terminology and policies.
2. Gemini-suggested replacements for tone, accessibility and similar findings (already
   stored with the audit) are added only if the claim text really occurs in the draft and
   the edit cannot introduce any new rule violation.
3. The finished rewrite is re-audited by the rules engine and the result is returned, so
   the creator sees whether the rewrite passes before accepting it.

Nothing here is saved automatically: the creator reviews each change and chooses which to
apply, then the normal audit and human review flow continues.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .audit import FindingDraft, run_rules_audit

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Change:
    id: str
    kind: str  # replace | delete | append
    original: str
    replacement: str
    reason: str
    source: str  # rules | gemini
    issue_key: str
    severity: str = "medium"
    start: int | None = None
    end: int | None = None


def _reason(draft: FindingDraft) -> str:
    cite = f" Source: {draft.source_reference}." if draft.source_reference else ""
    return f"{draft.explanation}{cite}"


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and begin < span[1] for begin, end in taken)


def deterministic_changes(drafts: list[FindingDraft], text: str) -> list[Change]:
    candidates: list[Change] = []
    for draft in drafts:
        if draft.verification_status == "Supported" or draft.fix_kind == "none":
            continue
        if draft.fix_kind == "append":
            if draft.replacement:
                candidates.append(Change("", "append", "", draft.replacement, _reason(draft), "rules", draft.issue_key, draft.severity))
            continue
        span = draft.span
        if not span:
            index = text.find(draft.claim_text)
            if index < 0:
                continue
            span = (index, index + len(draft.claim_text))
        kind = "replace" if draft.replacement else "delete"
        candidates.append(Change("", kind, text[span[0]:span[1]], draft.replacement or "", _reason(draft), "rules", draft.issue_key, draft.severity, span[0], span[1]))

    accepted: list[Change] = []
    taken: list[tuple[int, int]] = []
    seen_appends: set[str] = set()
    for change in sorted(candidates, key=lambda item: (SEVERITY_RANK.get(item.severity, 1), item.start if item.start is not None else 10**9)):
        if change.kind == "append":
            if change.replacement.lower() in seen_appends:
                continue
            seen_appends.add(change.replacement.lower())
            accepted.append(change)
            continue
        span = (change.start or 0, change.end or 0)
        if _overlaps(span, taken):
            continue
        taken.append(span)
        accepted.append(change)
    return accepted


def _find_free(text: str, needle: str, taken: list[tuple[int, int]]) -> int | None:
    lowered, target = text.lower(), needle.lower()
    position = lowered.find(target)
    while position >= 0:
        if not _overlaps((position, position + len(needle)), taken):
            return position
        position = lowered.find(target, position + 1)
    return None


def ai_changes(text: str, ai_findings: list[dict[str, Any]], taken: list[tuple[int, int]]) -> list[Change]:
    """Turn stored AI suggestions into edits, discarding anything that cannot be applied safely."""
    changes: list[Change] = []
    spans = list(taken)
    for finding in ai_findings:
        claim = str(finding.get("claim_text") or "").strip()
        replacement = str(finding.get("suggested_correction") or "").strip()
        if not claim or not replacement or replacement == claim or claim.startswith("["):
            continue
        if len(replacement) > len(claim) * 3 + 120:
            continue
        start = _find_free(text, claim, spans)
        if start is None:
            continue
        end = start + len(claim)
        spans.append((start, end))
        changes.append(Change("", "replace", text[start:end], replacement, str(finding.get("explanation") or "Suggested by the AI auditor."), "gemini", str(finding.get("issue_key") or "ai-finding"), str(finding.get("severity") or "medium"), start, end))
    return changes


def apply_changes(text: str, changes: list[Change]) -> str:
    edits = sorted((c for c in changes if c.kind in {"replace", "delete"} and c.start is not None and c.end is not None), key=lambda c: c.start or 0, reverse=True)
    result = text
    for change in edits:
        result = result[: change.start] + (change.replacement if change.kind == "replace" else "") + result[change.end:]
    if any(c.kind == "delete" for c in edits):
        result = re.sub(r"[ \t]{2,}", " ", result)
        result = re.sub(r"[ \t]+([.,!?;:])", r"\1", result)
        result = result.lstrip(" \t")
        if text[:1].isupper() and result[:1].islower():
            result = result[:1].upper() + result[1:]
    for change in changes:
        if change.kind == "append" and change.replacement and change.replacement.lower() not in result.lower():
            result = result.rstrip() + "\n" + change.replacement
    return result


def _open_keys(text: str, facts: list[Any], policies: list[Any], terminology: list[Any]) -> dict[str, FindingDraft]:
    return {draft.issue_key: draft for draft in run_rules_audit(text, facts, policies, terminology) if draft.verification_status != "Supported"}


def build_rewrite(text: str, facts: list[Any], policies: list[Any], terminology: list[Any], ai_findings: list[dict[str, Any]] | None = None, accepted_ids: set[str] | None = None) -> dict[str, Any]:
    """Propose edits. With ``accepted_ids`` only those changes are applied (the creator's accept/reject choices)."""
    drafts = run_rules_audit(text, facts, policies, terminology)
    rule_changes = deterministic_changes(drafts, text)
    base_keys = set(_open_keys(apply_changes(text, rule_changes), facts, policies, terminology))
    taken = [(c.start, c.end) for c in rule_changes if c.start is not None and c.end is not None]

    kept: list[Change] = []
    dropped = 0
    for candidate in ai_changes(text, ai_findings or [], taken):
        trial = apply_changes(text, rule_changes + kept + [candidate])
        if set(_open_keys(trial, facts, policies, terminology)) <= base_keys:
            kept.append(candidate)
        else:
            dropped += 1

    changes = sorted(rule_changes + kept, key=lambda c: (c.start is None, c.start or 0))
    for number, change in enumerate(changes, start=1):
        change.id = f"c{number}"
    applied = changes if accepted_ids is None else [change for change in changes if change.id in accepted_ids]
    rewritten = apply_changes(text, applied)
    remaining = _open_keys(rewritten, facts, policies, terminology)
    return {
        "method": "gemini+rules" if kept else "rules",
        "original_text": text,
        "rewritten_text": rewritten,
        "changes": [asdict(change) for change in changes],
        "verification": {
            "passed": not remaining,
            "open_before": len([d for d in drafts if d.verification_status != "Supported"]),
            "remaining": [{"issue_key": key, "claim_text": draft.claim_text, "explanation": draft.explanation} for key, draft in remaining.items()],
        },
        "dropped_ai_changes": dropped,
        "applied_ids": [change.id for change in applied],
    }
