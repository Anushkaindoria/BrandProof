from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FactCreate(BaseModel):
    key: str = Field(min_length=2, max_length=120)
    product: str = "NovaTech X1"
    value: str = Field(min_length=1, max_length=255)
    source_reference: str = "Admin entry"
    excerpt: str = ""


class PolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    rule_type: str = "prohibited_claim"
    rule_value: str = Field(min_length=1, max_length=255)
    description: str = ""
    source_reference: str = "Admin entry"


class ContentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    content_type: str = "Advertisement"
    context: str = "NovaTech X1"
    text: str = Field(min_length=1)


class VersionCreate(BaseModel):
    text: str = Field(min_length=1)


class ReviewCreate(BaseModel):
    decision: str
    comment: str = ""


class ResolveCreate(BaseModel):
    action: str
    reason: str = ""
    corrected_text: str | None = None


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def finding_dict(finding: Any) -> dict[str, Any]:
    return {
        "id": finding.id,
        "issue_key": finding.issue_key,
        "category": finding.category,
        "severity": finding.severity,
        "claim_text": finding.claim_text,
        "explanation": finding.explanation,
        "verification_status": finding.verification_status,
        "suggested_correction": finding.suggested_correction,
        "confidence": finding.confidence,
        "resolution_status": finding.resolution_status,
        "resolution_reason": finding.resolution_reason,
        "evidence": {
            "type": finding.evidence_type,
            "id": finding.evidence_id,
            "label": finding.evidence_label,
            "excerpt": finding.evidence_excerpt,
            "source_reference": finding.source_reference,
        } if finding.evidence_id else None,
    }
