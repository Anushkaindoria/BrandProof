import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import FindingDraft, run_rules_audit
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .main_helpers import make_hash
from .models import (
    ApprovedFact,
    ApprovalRecord,
    AuditEvent,
    AuditRun,
    ContentItem,
    ContentStatus,
    ContentVersion,
    Dependency,
    Finding,
    Organization,
    Policy,
    ReviewDecision,
    SourceDocument,
    Terminology,
    User,
)
from .schemas import ContentCreate, FactCreate, PolicyCreate, ResolveCreate, ReviewCreate, VersionCreate, finding_dict
from .seed import seed_database


app = FastAPI(title="BrandProof AI API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    seed_database()


def demo_org(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.demo.is_(True)))
    if not org:
        raise HTTPException(status_code=503, detail="Demo workspace is not initialized")
    return org


def serialize_fact(fact: ApprovedFact) -> dict:
    return {"id": fact.id, "key": fact.key, "product": fact.product, "value": fact.value, "version": fact.version, "active": fact.active, "source_reference": fact.source_reference, "excerpt": fact.excerpt, "updated_at": fact.updated_at.isoformat() if fact.updated_at else None}


def serialize_policy(policy: Policy) -> dict:
    return {"id": policy.id, "name": policy.name, "rule_type": policy.rule_type, "rule_value": policy.rule_value, "description": policy.description, "version": policy.version, "active": policy.active, "source_reference": policy.source_reference}


def serialize_version(db: Session, version: ContentVersion) -> dict:
    latest_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == version.id).order_by(AuditRun.created_at.desc())).first()
    findings = latest_audit.findings if latest_audit else []
    return {"id": version.id, "version_number": version.version_number, "text": version.text, "content_hash": version.content_hash, "created_by": version.created_by, "created_at": version.created_at.isoformat(), "audit": serialize_audit(latest_audit) if latest_audit else None}


def serialize_audit(audit: AuditRun | None) -> dict | None:
    if not audit:
        return None
    return {"id": audit.id, "engine_version": audit.engine_version, "provider_mode": audit.provider_mode, "overall_status": audit.overall_status, "created_at": audit.created_at.isoformat(), "findings": [finding_dict(item) for item in audit.findings]}


def serialize_item(db: Session, item: ContentItem) -> dict:
    current = db.get(ContentVersion, item.current_version_id) if item.current_version_id else None
    latest_audit = None
    if current:
        latest_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == current.id).order_by(AuditRun.created_at.desc())).first()
    return {"id": item.id, "title": item.title, "content_type": item.content_type, "context": item.context, "status": item.status, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "current_version": serialize_version(db, current) if current else None, "latest_audit": serialize_audit(latest_audit)}


def save_audit(db: Session, item: ContentItem, version: ContentVersion, org: Organization) -> AuditRun:
    facts = list(db.scalars(select(ApprovedFact).where(ApprovedFact.organization_id == org.id, ApprovedFact.active.is_(True))))
    policies = list(db.scalars(select(Policy).where(Policy.organization_id == org.id, Policy.active.is_(True))))
    terminology = list(db.scalars(select(Terminology).where(Terminology.organization_id == org.id, Terminology.active.is_(True))))
    drafts = run_rules_audit(version.text, facts, policies, terminology)
    unresolved = [draft for draft in drafts if draft.verification_status != "Supported"]
    audit = AuditRun(content_version_id=version.id, provider_mode="rules-only" if not settings.llm_api_key else settings.llm_provider, overall_status="changes_required" if unresolved else "passed")
    db.add(audit)
    db.flush()
    for draft in drafts:
        if draft.evidence_id and draft.evidence_type in {"fact", "policy"}:
            if draft.evidence_type == "fact":
                evidence = db.get(ApprovedFact, draft.evidence_id)
            else:
                evidence = db.get(Policy, draft.evidence_id)
            if not evidence or evidence.organization_id != org.id:
                continue
            dependency_version = evidence.version
            db.add(Dependency(content_version_id=version.id, dependency_type=draft.evidence_type, dependency_id=draft.evidence_id, dependency_version=dependency_version))
        db.add(Finding(audit_run_id=audit.id, issue_key=draft.issue_key, category=draft.category, severity=draft.severity, claim_text=draft.claim_text, explanation=draft.explanation, verification_status=draft.verification_status, suggested_correction=draft.suggested_correction, confidence=draft.confidence, evidence_type=draft.evidence_type or "none", evidence_id=draft.evidence_id, evidence_label=draft.evidence_label, evidence_excerpt=draft.evidence_excerpt, source_reference=draft.source_reference))
    item.status = ContentStatus.CHANGES_REQUIRED.value if unresolved else ContentStatus.AUDITED.value
    db.add(AuditEvent(organization_id=org.id, event_type="audit_completed", message=f"Audited {item.title} version {version.version_number} using {audit.provider_mode}."))
    db.commit()
    db.refresh(audit)
    return audit


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "brandproof-api", "mode": "demo" if settings.demo_mode else "configured"}


@app.get("/api/bootstrap")
def bootstrap(role: str = "creator", db: Session = Depends(get_db)):
    org = demo_org(db)
    user = db.scalar(select(User).where(User.organization_id == org.id, User.role == role)) or db.scalar(select(User).where(User.organization_id == org.id))
    return {"organization": {"id": org.id, "name": org.name, "demo": org.demo}, "user": {"id": user.id, "name": user.name, "role": user.role}, "provider_mode": "rules-only" if not settings.llm_api_key else settings.llm_provider}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    org = demo_org(db)
    items = list(db.scalars(select(ContentItem).where(ContentItem.organization_id == org.id)))
    audits = list(db.scalars(select(AuditRun).join(ContentVersion, AuditRun.content_version_id == ContentVersion.id).join(ContentItem, ContentVersion.content_item_id == ContentItem.id).where(ContentItem.organization_id == org.id).order_by(AuditRun.created_at.desc())))
    findings = list(db.scalars(select(Finding).join(AuditRun, Finding.audit_run_id == AuditRun.id).join(ContentVersion, AuditRun.content_version_id == ContentVersion.id).join(ContentItem, ContentVersion.content_item_id == ContentItem.id).where(ContentItem.organization_id == org.id)))
    recent = [{"type": event.event_type, "message": event.message, "created_at": event.created_at.isoformat()} for event in db.scalars(select(AuditEvent).where(AuditEvent.organization_id == org.id).order_by(AuditEvent.created_at.desc()).limit(8))]
    by_category: dict[str, int] = {}
    for finding in findings:
        if finding.resolution_status != "resolved":
            by_category[finding.category] = by_category.get(finding.category, 0) + 1
    return {"reviewed": len(audits), "unresolved_findings": sum(1 for f in findings if f.resolution_status != "resolved" and f.verification_status != "Supported"), "awaiting_approval": sum(1 for item in items if item.status == ContentStatus.RESUBMITTED.value), "needs_revalidation": sum(1 for item in items if item.status == ContentStatus.NEEDS_REVALIDATION.value), "findings_by_category": by_category, "recent_activity": recent, "items": [serialize_item(db, item) for item in items]}


@app.get("/api/knowledge")
def knowledge(db: Session = Depends(get_db)):
    org = demo_org(db)
    return {"facts": [serialize_fact(item) for item in db.scalars(select(ApprovedFact).where(ApprovedFact.organization_id == org.id).order_by(ApprovedFact.id))], "policies": [serialize_policy(item) for item in db.scalars(select(Policy).where(Policy.organization_id == org.id).order_by(Policy.id))], "terminology": [{"id": item.id, "prohibited": item.prohibited, "replacement": item.replacement, "active": item.active} for item in db.scalars(select(Terminology).where(Terminology.organization_id == org.id))], "documents": [{"id": item.id, "filename": item.filename, "page_reference": item.page_reference, "status": item.status, "excerpt": item.excerpt} for item in db.scalars(select(SourceDocument).where(SourceDocument.organization_id == org.id))]}


@app.post("/api/facts")
def create_fact(payload: FactCreate, db: Session = Depends(get_db)):
    org = demo_org(db)
    fact = ApprovedFact(organization_id=org.id, **payload.model_dump(), version=1, active=True)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return serialize_fact(fact)


@app.patch("/api/facts/{fact_id}")
def update_fact(fact_id: int, payload: FactCreate, db: Session = Depends(get_db)):
    org = demo_org(db)
    fact = db.get(ApprovedFact, fact_id)
    if not fact or fact.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Approved fact not found")
    fact.key, fact.product, fact.value, fact.source_reference, fact.excerpt = payload.key, payload.product, payload.value, payload.source_reference, payload.excerpt
    fact.version += 1
    fact.updated_at = datetime.utcnow()
    deps = list(db.scalars(select(Dependency).where(Dependency.dependency_type == "fact", Dependency.dependency_id == fact.id, Dependency.dependency_version < fact.version)))
    affected_ids = {dep.content_version_id for dep in deps}
    for version_id in affected_ids:
        version = db.get(ContentVersion, version_id)
        if version:
            item = db.get(ContentItem, version.content_item_id)
            if item and item.status == ContentStatus.APPROVED.value:
                item.status = ContentStatus.NEEDS_REVALIDATION.value
    db.add(AuditEvent(organization_id=org.id, event_type="fact_updated", message=f"Updated {fact.key} to version {fact.version}; {len(affected_ids)} dependent version(s) flagged."))
    db.commit()
    return {"fact": serialize_fact(fact), "affected_versions": len(affected_ids)}


@app.post("/api/policies")
def create_policy(payload: PolicyCreate, db: Session = Depends(get_db)):
    org = demo_org(db)
    policy = Policy(organization_id=org.id, **payload.model_dump(), version=1, active=True)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return serialize_policy(policy)


@app.get("/api/content")
def list_content(db: Session = Depends(get_db)):
    org = demo_org(db)
    return {"items": [serialize_item(db, item) for item in db.scalars(select(ContentItem).where(ContentItem.organization_id == org.id).order_by(ContentItem.updated_at.desc()))]}


@app.post("/api/content")
def create_content(payload: ContentCreate, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = ContentItem(organization_id=org.id, title=payload.title, content_type=payload.content_type, context=payload.context, status=ContentStatus.DRAFT.value)
    db.add(item)
    db.flush()
    version = ContentVersion(content_item_id=item.id, version_number=1, text=payload.text, content_hash=make_hash(payload.text), created_by="Demo Creator")
    db.add(version)
    db.flush()
    item.current_version_id = version.id
    db.add(AuditEvent(organization_id=org.id, event_type="content_created", message=f"Created {item.title}."))
    db.commit()
    db.refresh(item)
    return serialize_item(db, item)


@app.get("/api/content/{content_id}")
def get_content(content_id: int, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Content not found")
    versions = list(db.scalars(select(ContentVersion).where(ContentVersion.content_item_id == item.id).order_by(ContentVersion.version_number.desc())))
    response = serialize_item(db, item)
    response["versions"] = [serialize_version(db, version) for version in versions]
    decisions = list(db.scalars(select(ReviewDecision).where(ReviewDecision.content_version_id.in_([version.id for version in versions])).order_by(ReviewDecision.created_at.desc()))) if versions else []
    response["review_decisions"] = [{"id": decision.id, "decision": decision.decision, "comment": decision.comment, "created_at": decision.created_at.isoformat()} for decision in decisions]
    return response


@app.post("/api/content/{content_id}/versions")
def create_version(content_id: int, payload: VersionCreate, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Content not found")
    latest_number = db.scalar(select(func.max(ContentVersion.version_number)).where(ContentVersion.content_item_id == item.id)) or 0
    version = ContentVersion(content_item_id=item.id, version_number=latest_number + 1, text=payload.text, content_hash=make_hash(payload.text), created_by="Demo Creator")
    item.status = ContentStatus.DRAFT.value
    db.add(version)
    db.flush()
    item.current_version_id = version.id
    db.add(AuditEvent(organization_id=org.id, event_type="revision_saved", message=f"Saved {item.title} version {version.version_number}."))
    db.commit()
    return serialize_version(db, version)


@app.post("/api/content/{content_id}/audit")
def audit_content(content_id: int, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Content version not found")
    version = db.get(ContentVersion, item.current_version_id)
    audit = save_audit(db, item, version, org)
    return {"content": serialize_item(db, item), "audit": serialize_audit(audit)}


@app.post("/api/content/{content_id}/submit")
def submit_content(content_id: int, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Content not found")
    if item.status == ContentStatus.CHANGES_REQUIRED.value:
        raise HTTPException(status_code=409, detail="Resolve or review the remaining findings before submitting")
    item.status = ContentStatus.RESUBMITTED.value
    db.add(AuditEvent(organization_id=org.id, event_type="submitted_for_review", message=f"{item.title} version {item.current_version_id} submitted for human review."))
    db.commit()
    return serialize_item(db, item)


@app.post("/api/content/{content_id}/review")
def review_content(content_id: int, payload: ReviewCreate, db: Session = Depends(get_db)):
    if payload.decision not in {"approve", "request_changes", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be approve, request_changes, or reject")
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    reviewer = db.scalar(select(User).where(User.organization_id == org.id, User.role == "reviewer"))
    if not item or item.organization_id != org.id or not reviewer or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Review target not found")
    version = db.get(ContentVersion, item.current_version_id)
    if payload.decision == "approve":
        item.status = ContentStatus.APPROVED.value
        passport = {"content_id": item.id, "version_id": version.id, "content_hash": version.content_hash, "policy_versions": [{"id": dep.dependency_id, "version": dep.dependency_version} for dep in db.scalars(select(Dependency).where(Dependency.content_version_id == version.id, Dependency.dependency_type == "policy") )], "fact_versions": [{"id": dep.dependency_id, "version": dep.dependency_version} for dep in db.scalars(select(Dependency).where(Dependency.content_version_id == version.id, Dependency.dependency_type == "fact"))], "audit_engine_version": "rules-engine-1.0", "reviewer": reviewer.name, "approved_at": datetime.utcnow().isoformat(), "notice": "This passport records review evidence and process; it is not a mathematical guarantee of truth or legal compliance."}
        db.add(ApprovalRecord(content_version_id=version.id, reviewer_id=reviewer.id, decision="approved", content_hash=version.content_hash, passport_json=json.dumps(passport)))
    elif payload.decision == "request_changes":
        item.status = ContentStatus.CHANGES_REQUIRED.value
    else:
        item.status = ContentStatus.REJECTED.value
    db.add(ReviewDecision(content_version_id=version.id, reviewer_id=reviewer.id, decision=payload.decision, comment=payload.comment))
    db.add(AuditEvent(organization_id=org.id, event_type="review_decision", message=f"Reviewer {reviewer.name} recorded {payload.decision} for {item.title}."))
    db.commit()
    return serialize_item(db, item)


@app.post("/api/findings/{finding_id}/resolve")
def resolve_finding(finding_id: int, payload: ResolveCreate, db: Session = Depends(get_db)):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.action not in {"accept", "dismiss", "edit"}:
        raise HTTPException(status_code=422, detail="Action must be accept, dismiss, or edit")
    finding.resolution_status = "resolved"
    finding.resolution_reason = payload.reason or payload.action
    return_value = finding_dict(finding)
    db.commit()
    return return_value


@app.get("/api/history")
def history(db: Session = Depends(get_db)):
    org = demo_org(db)
    items = list(db.scalars(select(ContentItem).where(ContentItem.organization_id == org.id).order_by(ContentItem.updated_at.desc())))
    return {"items": [serialize_item(db, item) for item in items]}


@app.get("/api/content/{content_id}/passport")
def passport(content_id: int, db: Session = Depends(get_db)):
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Passport not found")
    record = db.scalar(select(ApprovalRecord).where(ApprovalRecord.content_version_id == item.current_version_id))
    if not record:
        raise HTTPException(status_code=404, detail="No approved passport exists for this version")
    return json.loads(record.passport_json)


@app.get("/api/drift")
def drift(db: Session = Depends(get_db)):
    org = demo_org(db)
    items = list(db.scalars(select(ContentItem).where(ContentItem.organization_id == org.id, ContentItem.status == ContentStatus.NEEDS_REVALIDATION.value)))
    results = []
    for item in items:
        version = db.get(ContentVersion, item.current_version_id)
        deps = list(db.scalars(select(Dependency).where(Dependency.content_version_id == version.id))) if version else []
        changed = []
        for dep in deps:
            current = db.get(ApprovedFact if dep.dependency_type == "fact" else Policy, dep.dependency_id)
            if current and current.version > dep.dependency_version:
                changed.append({"type": dep.dependency_type, "id": current.id, "name": getattr(current, "key", getattr(current, "name", "unknown")), "previous_version": dep.dependency_version, "current_version": current.version, "current_value": getattr(current, "value", getattr(current, "description", ""))})
        if changed:
            results.append({"content": serialize_item(db, item), "changes": changed})
    return {"items": results}


@app.post("/api/content/upload")
async def upload_content(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or Path(file.filename).suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=415, detail="Supported file types are .txt, .md, and .pdf")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB demo limit")
    try:
        if file.filename.lower().endswith(".pdf"):
            from io import BytesIO
            reader = PdfReader(BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = raw.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not extract text from upload: {exc}") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="The uploaded file contains no extractable text")
    org = demo_org(db)
    document = SourceDocument(organization_id=org.id, filename=Path(file.filename).name, excerpt=text[:1000], page_reference="Extracted text", status="unreviewed")
    db.add(document)
    db.commit()
    return {"filename": document.filename, "text": text, "document_id": document.id, "status": "unreviewed"}
