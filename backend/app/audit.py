"""Deterministic, evidence-backed audit engine.

The engine deliberately separates rules-only checks from any optional LLM provider.
It never treats similarity as proof and only emits evidence IDs from the supplied set.

Fact checks are generic: any approved fact whose value contains a number and a unit
("5000 mAh", "1 year", "6.1 inches", "65 W") is compared with every matching number
in the submitted text. Legacy issue keys for the seeded NovaTech battery and warranty
facts are kept so existing records and tests keep working.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the engine only needs duck-typed records, so it stays importable without a database
    from .models import ApprovedFact, Policy, Terminology


@dataclass
class FindingDraft:
    issue_key: str
    category: str
    severity: str
    claim_text: str
    explanation: str
    verification_status: str
    suggested_correction: str
    confidence: str
    evidence_type: str | None = None
    evidence_id: int | None = None
    evidence_label: str = ""
    evidence_excerpt: str = ""
    source_reference: str = ""
    # Not persisted: used by the correction engine to build a safe, minimal edit.
    origin: str = "rules"
    span: tuple[int, int] | None = None
    replacement: str | None = None
    fix_kind: str = "none"  # replace | delete | append | none


NUMBER_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)*)\s*-?\s*([A-Za-z%]+)")
# Units that appear in many unrelated phrases ("5 years of updates"): only compared when the
# fact's key words (e.g. "warranty") appear right next to the number.
GENERIC_UNITS = {"year", "month", "week", "day", "hour", "minute", "%", "gb", "tb", "mb", "g", "kg", "mm", "cm", "m", "x", "s"}
UNIT_ALIASES = {"inches": "inch", "in": "inch", "hrs": "hour", "hr": "hour", "mins": "minute", "min": "minute", "yrs": "year", "yr": "year"}
LEGACY_KEYS = {"battery_capacity": "battery", "warranty": "warranty"}
SUPERLATIVE_BASE = ["the best", "best ever", "greatest", "number one", "#1", "revolutionary", "world's best", "worlds best"]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalize_unit(unit: str) -> str:
    value = unit.lower()
    value = UNIT_ALIASES.get(value, value)
    if len(value) > 3 and value.endswith("s") and not value.endswith("ss"):
        value = value[:-1]
    return value


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentence boundaries that do not split decimals such as 6.1."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n+", text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [(begin, end) for begin, end in spans if end > begin]


PROXIMITY_CHARS = 24


def _key_nearby(text: str, match: re.Match[str], tokens: list[str]) -> bool:
    """True when one of the fact's key words sits right next to the number ("2 year warranty")."""
    window = text[max(0, match.start() - PROXIMITY_CHARS): match.end() + PROXIMITY_CHARS].lower()
    return any(token in window for token in tokens)


def _key_tokens(key: str) -> list[str]:
    return [token[:6] for token in re.split(r"[^a-z0-9]+", key.lower()) if len(token) > 3]


def _parse_fact_number(value: str) -> tuple[float, str] | None:
    match = NUMBER_UNIT_RE.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "")), normalize_unit(match.group(2))
    except ValueError:
        return None


NEGATION_RE = re.compile(r"\b(?:not|no|never|without|isn't|aren't|doesn't|don't|cannot|can't)\b[^.!?\n]{0,40}$", re.IGNORECASE)


FOLLOWING_NEGATION_RE = re.compile(r"^\W*(?:is|are|was|were|has|have)?\s*(?:not|never|no)\b", re.IGNORECASE)


def _negated(text: str, start: int, end: int) -> bool:
    """True when the phrase is being denied: "not waterproof" or "water resistance is not certified"."""
    sentence_start = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start), text.rfind("\n", 0, start)) + 1
    return bool(NEGATION_RE.search(text[sentence_start:start])) or bool(FOLLOWING_NEGATION_RE.match(text[end:end + 25]))


def _term_regex(terms: list[str]) -> re.Pattern[str]:
    ordered = sorted({term.strip() for term in terms if term.strip()}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in ordered) + r")(?!\w)", re.IGNORECASE)


def _fact(facts: list[ApprovedFact], key: str) -> ApprovedFact | None:
    return next((item for item in facts if item.key == key and item.active is not False), None)


def _numeric_fact_findings(text: str, facts: list[ApprovedFact]) -> list[FindingDraft]:
    active = [fact for fact in facts if fact.active is not False]
    parsed: list[tuple[ApprovedFact, float, str]] = []
    for fact in active:
        numeric = _parse_fact_number(fact.value)
        if numeric:
            parsed.append((fact, numeric[0], numeric[1]))
    if not parsed:
        return []
    lowered = text.lower()
    products = {(fact.product or "").lower() for fact in active if fact.product}
    same_unit = Counter(((fact.product or "").lower(), unit) for fact, _, unit in parsed)
    observations = []
    for match in NUMBER_UNIT_RE.finditer(text):
        try:
            observations.append((match, float(match.group(1).replace(",", "")), normalize_unit(match.group(2))))
        except ValueError:
            continue

    findings: list[FindingDraft] = []
    for fact, number, unit in parsed:
        product = (fact.product or "").lower()
        if product and product not in lowered and len(products) > 1:
            continue  # several products exist and this text does not mention this one
        need_tokens = unit in GENERIC_UNITS or same_unit[(product, unit)] > 1
        tokens = _key_tokens(fact.key)
        matches = []
        for match, observed, observed_unit in observations:
            if observed_unit != unit:
                continue
            if need_tokens and not _key_nearby(text, match, tokens):
                continue
            matches.append((match, observed))
        if not matches:
            continue
        label = fact.key.replace("_", " ")
        base = LEGACY_KEYS.get(fact.key, slugify(fact.key))
        evidence = dict(evidence_type="fact", evidence_id=fact.id, evidence_label=f"Approved fact · {label}", evidence_excerpt=fact.excerpt or f"{fact.product}: {fact.value}", source_reference=fact.source_reference)
        wrong = [(match, observed) for match, observed in matches if abs(observed - number) > 1e-9]
        if wrong:
            seen: set[str] = set()
            index = 0
            for match, _ in wrong:
                claim = match.group(0)
                if claim.lower() in seen:
                    continue
                seen.add(claim.lower())
                findings.append(FindingDraft(
                    issue_key=f"{base}-mismatch" if index == 0 else f"{base}-mismatch-{index + 1}",
                    category="Factual accuracy",
                    severity="high",
                    claim_text=claim,
                    explanation=f"The submitted {label} claim says {claim}, while the approved product fact is {fact.value}.",
                    verification_status="Contradicted",
                    suggested_correction=fact.value,
                    confidence="high",
                    span=match.span(),
                    replacement=fact.value,
                    fix_kind="replace",
                    **evidence,
                ))
                index += 1
        else:
            match = matches[0][0]
            findings.append(FindingDraft(
                issue_key=f"{base}-supported",
                category="Factual accuracy",
                severity="low",
                claim_text=match.group(0),
                explanation=f"The submitted {label} claim matches the approved value of {fact.value}.",
                verification_status="Supported",
                suggested_correction="",
                confidence="high",
                span=match.span(),
                **evidence,
            ))
    return findings


def run_rules_audit(text: str, facts: list[ApprovedFact], policies: list[Policy], terminology: list[Terminology]) -> list[FindingDraft]:
    findings: list[FindingDraft] = _numeric_fact_findings(text, facts)
    water = _fact(facts, "water_resistance")
    active_terms = [item for item in terminology if item.active is not False]
    term_map = {item.prohibited.lower(): item.replacement for item in active_terms}

    waterproof_match = next(
        (
            match
            for match in re.finditer(
                r"\b(?:fully\s+|completely\s+|totally\s+|100%\s+)?(?:waterproof|water[- ]resistant|water[- ]resistance)\b(?:\s+(?:protection|design|body|build|phone|device|casing))?",
                text,
                re.IGNORECASE,
            )
            if not _negated(text, match.start(), match.end())  # "not waterproof" is honest copy, not a claim
        ),
        None,
    )
    if waterproof_match and water and re.match(r"\s*(not|no|none)\b", water.value.lower()):
        claim = waterproof_match.group(0).strip()
        findings.append(FindingDraft(
            issue_key="waterproof-unsupported",
            category="Claim support",
            severity="high",
            claim_text=claim,
            explanation="The approved record says water resistance is not officially certified, so an absolute waterproof claim is not supported.",
            verification_status="Contradicted" if "waterproof" in claim.lower() else "Insufficient evidence",
            suggested_correction="everyday protection",
            confidence="high",
            evidence_type="fact",
            evidence_id=water.id,
            evidence_label="Approved fact · water resistance",
            evidence_excerpt=water.excerpt or f"{water.product}: {water.value}",
            source_reference=water.source_reference,
            span=waterproof_match.span(),
            replacement="everyday protection",
            fix_kind="replace",
        ))

    superlative_policy = next((p for p in policies if p.active is not False and p.rule_type == "superlative"), None)
    superlative_terms = list(SUPERLATIVE_BASE)
    if superlative_policy:
        superlative_terms += [value for value in superlative_policy.rule_value.split("|") if value.strip()]
    superlative_match = _term_regex(superlative_terms).search(text)
    if superlative_match:
        tail = re.compile(r"(?:\s+(?:phone|smartphone|device|ever|yet|in the world|on the market))*", re.IGNORECASE).match(text, superlative_match.end())
        end = tail.end() if tail else superlative_match.end()
        claim = text[superlative_match.start():end]
        strong = bool(re.match(r"(the best|best ever|number one|#1|world'?s best)", claim, re.IGNORECASE))
        replacement = "Designed to make your everyday mobile experience feel effortless" if strong else "thoughtfully designed"
        findings.append(FindingDraft(
            issue_key="unsupported-superlative",
            category="Policy compliance",
            severity="medium",
            claim_text=claim,
            explanation="This comparative or superlative statement needs approved evidence before publication.",
            verification_status="Insufficient evidence",
            suggested_correction=replacement,
            confidence="medium",
            evidence_type="policy" if superlative_policy else None,
            evidence_id=superlative_policy.id if superlative_policy else None,
            evidence_label=superlative_policy.name if superlative_policy else "Brand policy · unsupported superlatives",
            evidence_excerpt=superlative_policy.description if superlative_policy else "No approved evidence for a universal ranking claim.",
            source_reference=superlative_policy.source_reference if superlative_policy else "Review required",
            span=(superlative_match.start(), end),
            replacement=replacement,
            fix_kind="replace",
        ))

    for policy in policies:
        if policy.active is False:
            continue
        if policy.rule_type in {"prohibited_claim", "prohibited_term"}:
            for prohibited in [value.strip() for value in policy.rule_value.split("|") if value.strip()]:
                match = re.search(rf"\b{re.escape(prohibited)}\b", text, re.IGNORECASE)
                if match and not any(f.claim_text.lower() == match.group(0).lower() and f.evidence_id == policy.id for f in findings) and not (prohibited.lower() == "waterproof" and any(f.issue_key == "waterproof-unsupported" for f in findings)):
                    replacement = term_map.get(prohibited.lower())
                    base_explanation = policy.description or f"The term '{prohibited}' is prohibited by the approved brand policy."
                    findings.append(FindingDraft(
                        issue_key=f"policy-{policy.id}-{prohibited.lower().replace(' ', '-')}",
                        category="Policy compliance",
                        severity="high" if policy.rule_type == "prohibited_claim" else "medium",
                        claim_text=match.group(0),
                        explanation=base_explanation if replacement else f"{base_explanation} Remove or rephrase this wording.",
                        verification_status="Contradicted",
                        suggested_correction=replacement or "",
                        confidence="high",
                        evidence_type="policy",
                        evidence_id=policy.id,
                        evidence_label=policy.name,
                        evidence_excerpt=policy.description,
                        source_reference=policy.source_reference,
                        span=match.span(),
                        replacement=replacement if replacement else "",
                        fix_kind="replace" if replacement else "delete",
                    ))

        if policy.rule_type in {"required_phrase", "required_disclaimer"} and policy.rule_value.lower() not in text.lower():
            findings.append(FindingDraft(
                issue_key=f"missing-required-{policy.id}",
                category="Policy compliance",
                severity="high",
                claim_text="[required phrase missing]",
                explanation=f"This content does not include the required approved phrase: {policy.rule_value}.",
                verification_status="Contradicted",
                suggested_correction=policy.rule_value,
                confidence="high",
                evidence_type="policy",
                evidence_id=policy.id,
                evidence_label=policy.name,
                evidence_excerpt=policy.description or policy.rule_value,
                source_reference=policy.source_reference,
                replacement=policy.rule_value,
                fix_kind="append",
            ))

    for item in active_terms:
        match = re.search(rf"\b{re.escape(item.prohibited)}\b", text, re.IGNORECASE)
        if match and not any(f.issue_key == "waterproof-unsupported" and match.group(0).lower() in f.claim_text.lower() for f in findings):
            findings.append(FindingDraft(
                issue_key=f"term-{item.id}",
                category="Terminology",
                severity="medium",
                claim_text=match.group(0),
                explanation=f"Use the approved terminology instead of '{item.prohibited}'.",
                verification_status="Contradicted",
                suggested_correction=item.replacement,
                confidence="high",
                evidence_type="terminology",
                evidence_id=item.id,
                evidence_label=f"Terminology · {item.prohibited}",
                evidence_excerpt=f"Approved replacement: {item.replacement}",
                source_reference="Brand vocabulary",
                span=match.span(),
                replacement=item.replacement,
                fix_kind="replace",
            ))

    return findings
