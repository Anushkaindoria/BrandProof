"""Deterministic semantic-style retrieval for local and PostgreSQL fallback use."""

import re
from dataclasses import dataclass

from .models import ApprovedFact, Policy


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


@dataclass
class RetrievedEvidence:
    evidence_type: str
    evidence_id: int
    label: str
    excerpt: str
    source_reference: str
    score: float


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value or "") if len(token) > 2}


def retrieve_context(text: str, facts: list[ApprovedFact], policies: list[Policy], limit: int = 12) -> list[RetrievedEvidence]:
    query = _tokens(text)
    results: list[RetrievedEvidence] = []
    for fact in facts:
        searchable = f"{fact.key} {fact.product} {fact.value} {fact.excerpt} {fact.source_reference}"
        tokens = _tokens(searchable)
        score = len(query & tokens) / max(len(query), 1)
        if fact.value and fact.value.lower() in text.lower():
            score += 0.5
        if fact.product.lower() in text.lower():
            score += 0.25
        if score > 0:
            results.append(RetrievedEvidence("fact", fact.id, f"Approved fact · {fact.key}", fact.excerpt or f"{fact.product}: {fact.value}", fact.source_reference, round(score, 4)))
    for policy in policies:
        searchable = f"{policy.name} {policy.rule_type} {policy.rule_value} {policy.description} {policy.source_reference}"
        tokens = _tokens(searchable)
        score = len(query & tokens) / max(len(query), 1)
        if any(value.strip().lower() in text.lower() for value in policy.rule_value.split("|") if value.strip()):
            score += 0.5
        if score > 0:
            results.append(RetrievedEvidence("policy", policy.id, policy.name, policy.description or policy.rule_value, policy.source_reference, round(score, 4)))
    return sorted(results, key=lambda item: (-item.score, item.evidence_type, item.evidence_id))[:limit]
