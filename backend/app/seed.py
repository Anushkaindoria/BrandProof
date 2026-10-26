from sqlalchemy import select, text

from .db import Base, SessionLocal, engine
from .models import (
    ApprovedFact,
    AuditEvent,
    AuditRun,
    ContentItem,
    ContentStatus,
    ContentVersion,
    Dependency,
    Finding,
    Organization,
    Policy,
    SourceDocument,
    Terminology,
    User,
)
from .audit import run_rules_audit
from .main_helpers import make_hash
from .config import settings


DEMO_TEXT = "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!"


def seed_database(reset: bool = False):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        organization = db.scalar(select(Organization).where(Organization.name == "BrandProof Demo Workspace"))
        if organization and not reset:
            return organization.id
        if organization and reset:
            db.close()
            if settings.database_url.startswith("sqlite"):
                reset_db = SessionLocal()
                reset_db.execute(text("PRAGMA foreign_keys=OFF"))
                for table in reversed(list(Base.metadata.tables.values())):
                    reset_db.execute(text(f'DROP TABLE IF EXISTS "{table.name}"'))
                reset_db.commit()
                reset_db.close()
            else:
                Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            db = SessionLocal()

        organization = Organization(name="BrandProof Demo Workspace", demo=True)
        db.add(organization)
        db.flush()
        users = [
            User(organization_id=organization.id, name="Maya Chen", email="maya@demo.brandproof.ai", role="creator"),
            User(organization_id=organization.id, name="Jordan Lee", email="jordan@demo.brandproof.ai", role="reviewer"),
            User(organization_id=organization.id, name="Avery Patel", email="avery@demo.brandproof.ai", role="admin"),
        ]
        db.add_all(users)
        source = SourceDocument(
            organization_id=organization.id,
            filename="NovaTech_X1_Product_Brief.pdf",
            excerpt="NovaTech X1 battery capacity is 5000 mAh. Water resistance is not officially certified. Warranty is 1 year.",
            page_reference="Page 2",
            status="approved",
        )
        db.add(source)
        db.flush()
        facts = [
            ApprovedFact(organization_id=organization.id, key="battery_capacity", product="NovaTech X1", value="5000 mAh", source_document_id=source.id, source_reference="NovaTech_X1_Product_Brief.pdf · p. 2", excerpt="Battery capacity: 5000 mAh.", version=1),
            ApprovedFact(organization_id=organization.id, key="water_resistance", product="NovaTech X1", value="Not officially certified", source_document_id=source.id, source_reference="NovaTech_X1_Product_Brief.pdf · p. 2", excerpt="Water resistance: Not officially certified.", version=1),
            ApprovedFact(organization_id=organization.id, key="warranty", product="NovaTech X1", value="1 year", source_document_id=source.id, source_reference="NovaTech_X1_Product_Brief.pdf · p. 2", excerpt="Warranty: 1 year.", version=1),
        ]
        db.add_all(facts)
        policies = [
            Policy(organization_id=organization.id, name="No unsupported waterproof claims", rule_type="prohibited_claim", rule_value="waterproof", description="Do not describe NovaTech X1 as waterproof when official certification is absent.", source_document_id=source.id, source_reference="NovaTech_X1_Product_Brief.pdf · p. 2"),
            Policy(organization_id=organization.id, name="Unsupported superlatives require proof", rule_type="superlative", rule_value="best|greatest|#1", description="Universal rankings and superlatives need approved evidence or human review.", source_document_id=source.id, source_reference="Brand Messaging Standards · p. 4"),
            Policy(organization_id=organization.id, name="Human approval for high-risk content", rule_type="approval", rule_value="reviewer_required", description="High-risk factual or policy findings require an authorized reviewer.", source_reference="Governance Handbook · p. 1"),
        ]
        db.add_all(policies)
        db.add(Terminology(organization_id=organization.id, prohibited="waterproof", replacement="everyday protection", active=True))
        db.flush()

        item = ContentItem(organization_id=organization.id, title="NovaTech X1 launch ad", content_type="Advertisement", context="NovaTech X1", status=ContentStatus.AUDITED.value)
        db.add(item)
        db.flush()
        version = ContentVersion(content_item_id=item.id, version_number=1, text=DEMO_TEXT, content_hash=make_hash(DEMO_TEXT), created_by="Maya Chen")
        db.add(version)
        db.flush()
        item.current_version_id = version.id
        drafts = run_rules_audit(DEMO_TEXT, facts, policies, [db.scalar(select(Terminology).where(Terminology.organization_id == organization.id))])
        seeded_audit = AuditRun(content_version_id=version.id, engine_version="rules-engine-1.0", provider_mode="rules-only", overall_status="changes_required")
        db.add(seeded_audit)
        db.flush()
        for draft in drafts:
            if draft.evidence_id and draft.evidence_type in {"fact", "policy"}:
                evidence = db.get(ApprovedFact if draft.evidence_type == "fact" else Policy, draft.evidence_id)
                if evidence:
                    db.add(Dependency(content_version_id=version.id, dependency_type=draft.evidence_type, dependency_id=draft.evidence_id, dependency_version=evidence.version))
            db.add(Finding(audit_run_id=seeded_audit.id, issue_key=draft.issue_key, category=draft.category, severity=draft.severity, claim_text=draft.claim_text, explanation=draft.explanation, verification_status=draft.verification_status, suggested_correction=draft.suggested_correction, confidence=draft.confidence, evidence_type=draft.evidence_type or "none", evidence_id=draft.evidence_id, evidence_label=draft.evidence_label, evidence_excerpt=draft.evidence_excerpt, source_reference=draft.source_reference))
        audit = AuditEvent(organization_id=organization.id, event_type="seeded", message="Demo workspace seeded with the NovaTech X1 illustrative campaign.")
        db.add(audit)
        db.commit()
        return organization.id
    finally:
        db.close()
