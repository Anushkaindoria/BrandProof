"""Deterministic, evidence-backed audit engine for the demo workspace.

The engine deliberately separates rules-only checks from any optional LLM provider.
It never treats similarity as proof and only emits evidence IDs from the supplied set.
"""

import re
from dataclasses import dataclass

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


def _fact(facts: list[ApprovedFact], key: str) -> ApprovedFact | None:
    return next((item for item in facts if item.key == key and item.active is not False), None)


def run_rules_audit(text: str, facts: list[ApprovedFact], policies: list[Policy], terminology: list[Terminology]) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    battery = _fact(facts, "battery_capacity")
    water = _fact(facts, "water_resistance")
    warranty = _fact(facts, "warranty")

    battery_match = re.search(r"(\d{3,5})\s*mAh", text, re.IGNORECASE)
    if battery_match:
        observed = battery_match.group(1)
        approved_number_match = re.search(r"\d+", battery.value) if battery else None
        if battery and approved_number_match and observed != approved_number_match.group(0):
            findings.append(FindingDraft(
                issue_key="battery-mismatch",
                category="Factual accuracy",
                severity="high",
                claim_text=battery_match.group(0),
                explanation=f"The submitted battery claim says {observed} mAh, while the approved product fact is {battery.value}.",
                verification_status="Contradicted",
                suggested_correction=f"Enjoy a {battery.value} battery designed for everyday use.",
                confidence="high",
                evidence_type="fact",
                evidence_id=battery.id,
                evidence_label=f"Approved fact · {battery.key.replace('_', ' ')}",
                evidence_excerpt=battery.excerpt or f"{battery.product}: {battery.value}",
                source_reference=battery.source_reference,
            ))
        elif battery:
            findings.append(FindingDraft(
                issue_key="battery-supported",
                category="Factual accuracy",
                severity="low",
                claim_text=battery_match.group(0),
                explanation=f"The submitted battery claim matches the approved value of {battery.value}.",
                verification_status="Supported",
                suggested_correction="",
                confidence="high",
                evidence_type="fact",
                evidence_id=battery.id,
                evidence_label=f"Approved fact · {battery.key.replace('_', ' ')}",
                evidence_excerpt=battery.excerpt or f"{battery.product}: {battery.value}",
                source_reference=battery.source_reference,
            ))

    waterproof_match = re.search(r"\b(waterproof|fully waterproof|water resistant|water-resistant)\b[^.!?]*", text, re.IGNORECASE)
    if waterproof_match:
        claim = waterproof_match.group(0).strip()
        if water and water.value.lower().startswith("not officially"):
            findings.append(FindingDraft(
                issue_key="waterproof-unsupported",
                category="Claim support",
                severity="high",
                claim_text=claim,
                explanation="The approved record says water resistance is not officially certified, so an absolute waterproof claim is not supported.",
                verification_status="Contradicted" if "waterproof" in claim.lower() else "Insufficient evidence",
                suggested_correction="Replace with: Built for everyday moments, without claiming official waterproof certification.",
                confidence="high",
                evidence_type="fact",
                evidence_id=water.id,
                evidence_label="Approved fact · water resistance",
                evidence_excerpt=water.excerpt or f"{water.product}: {water.value}",
                source_reference=water.source_reference,
            ))

    superlative_match = re.search(r"\b(the best|best ever|greatest|number one|#1|revolutionary|world'?s best)\b[^.!?]*", text, re.IGNORECASE)
    superlative_policy = next((p for p in policies if p.active is not False and p.rule_type == "superlative"), None)
    if superlative_match:
        findings.append(FindingDraft(
            issue_key="unsupported-superlative",
            category="Policy compliance",
            severity="medium",
            claim_text=superlative_match.group(0).strip(),
            explanation="This comparative or superlative statement needs approved evidence before publication.",
            verification_status="Insufficient evidence",
            suggested_correction="Try: Designed to make your everyday mobile experience feel effortless.",
            confidence="medium",
            evidence_type="policy" if superlative_policy else None,
            evidence_id=superlative_policy.id if superlative_policy else None,
            evidence_label=superlative_policy.name if superlative_policy else "Brand policy · unsupported superlatives",
            evidence_excerpt=superlative_policy.description if superlative_policy else "No approved evidence for a universal ranking claim.",
            source_reference=superlative_policy.source_reference if superlative_policy else "Review required",
        ))

    for policy in policies:
        if policy.active is False:
            continue
        if policy.rule_type in {"prohibited_claim", "prohibited_term"}:
            for prohibited in [value.strip() for value in policy.rule_value.split("|") if value.strip()]:
                match = re.search(rf"\b{re.escape(prohibited)}\b", text, re.IGNORECASE)
                if match and not any(f.claim_text.lower() == match.group(0).lower() and f.evidence_id == policy.id for f in findings) and not (prohibited.lower() == "waterproof" and any(f.issue_key == "waterproof-unsupported" for f in findings)):
                    findings.append(FindingDraft(
                        issue_key=f"policy-{policy.id}-{prohibited.lower().replace(' ', '-')}",
                        category="Policy compliance",
                        severity="high" if policy.rule_type == "prohibited_claim" else "medium",
                        claim_text=match.group(0),
                        explanation=policy.description or f"The term '{prohibited}' is prohibited by the approved brand policy.",
                        verification_status="Contradicted",
                        suggested_correction=f"Remove or replace '{prohibited}' according to the approved policy.",
                        confidence="high",
                        evidence_type="policy",
                        evidence_id=policy.id,
                        evidence_label=policy.name,
                        evidence_excerpt=policy.description,
                        source_reference=policy.source_reference,
                    ))

        if policy.rule_type in {"required_phrase", "required_disclaimer"} and policy.rule_value.lower() not in text.lower():
            findings.append(FindingDraft(
                issue_key=f"missing-required-{policy.id}",
                category="Policy compliance",
                severity="high",
                claim_text="[required phrase missing]",
                explanation=f"This content does not include the required approved phrase: {policy.rule_value}.",
                verification_status="Contradicted",
                suggested_correction=f"Add the required phrase: {policy.rule_value}",
                confidence="high",
                evidence_type="policy",
                evidence_id=policy.id,
                evidence_label=policy.name,
                evidence_excerpt=policy.description or policy.rule_value,
                source_reference=policy.source_reference,
            ))

    for item in terminology:
        if item.active is False:
            continue
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
            ))

    if warranty and re.search(r"\b\d+\s*year warranty\b", text, re.IGNORECASE):
        match = re.search(r"\b\d+\s*year warranty\b", text, re.IGNORECASE)
        if match and warranty.value.lower() not in match.group(0).lower():
            findings.append(FindingDraft(
                issue_key="warranty-mismatch",
                category="Factual accuracy",
                severity="high",
                claim_text=match.group(0),
                explanation=f"The submitted warranty claim conflicts with the approved value of {warranty.value}.",
                verification_status="Contradicted",
                suggested_correction=f"Includes a {warranty.value} limited warranty.",
                confidence="high",
                evidence_type="fact",
                evidence_id=warranty.id,
                evidence_label="Approved fact · warranty",
                evidence_excerpt=warranty.excerpt or f"{warranty.product}: {warranty.value}",
                source_reference=warranty.source_reference,
            ))

    return findings
