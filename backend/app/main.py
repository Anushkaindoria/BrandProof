import json
import hashlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .audit import FindingDraft, run_rules_audit
from .ai import AIProviderError, call_gemini
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .main_helpers import make_hash
from .models import (
    ApprovedFact,
    ApprovalRecord,
    AuditEvent,
    AuditRun,
    AuditJob,
    AssetComparison,
    BrandAsset,
    ContentItem,
    ContentStatus,
    ContentVersion,
    Dependency,
    ExtractedClaim,
    Finding,
    Organization,
    Policy,
    ReviewDecision,
    SourceDocument,
    Terminology,
    User,
    UserRoleEvent,
)
from .schemas import ContentCreate, FactCreate, FactUpdate, PolicyCreate, PolicyUpdate, ResolveCreate, ReviewCreate, RoleUpdate, TerminologyCreate, TerminologyUpdate, VersionCreate, finding_dict
from .seed import seed_database
from .retrieval import retrieve_context
from .storage import get_storage


app = FastAPI(title="BrandProof AI API", version="0.2.0")
audit_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="brandproof-audit")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    if settings.demo_mode and settings.database_url.startswith("sqlite"):
        inspector = inspect(engine)
        audit_columns = {column["name"] for column in inspector.get_columns("audit_runs")} if inspector.has_table("audit_runs") else set()
        source_columns = {column["name"] for column in inspector.get_columns("source_documents")} if inspector.has_table("source_documents") else set()
        required_tables = {"asset_comparisons", "audit_jobs"}
        if inspector.has_table("audit_runs") and ({"provider_error", "retrieval_mode", "retrieved_context"} - audit_columns or "storage_key" not in source_columns or not required_tables.issubset(set(inspector.get_table_names()))):
            seed_database(reset=True)
            return
    Base.metadata.create_all(bind=engine)
    seed_database()


def demo_org(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.demo.is_(True)))
    if not org:
        raise HTTPException(status_code=503, detail="Demo workspace is not initialized")
    return org


def current_user(db: Session, role_header: str | None, default_role: str | None = None) -> User:
    role = role_header or default_role
    if role not in {"creator", "reviewer", "admin"}:
        raise HTTPException(status_code=401, detail="A valid demo role is required")
    org = demo_org(db)
    user = db.scalar(select(User).where(User.organization_id == org.id, User.role == role))
    if not user:
        raise HTTPException(status_code=403, detail="Demo role is not available in this workspace")
    return user


def require_role(db: Session, role_header: str | None, allowed: set[str], default_role: str | None = None) -> User:
    user = current_user(db, role_header, default_role)
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{user.role}' cannot perform this action")
    return user


def serialize_fact(fact: ApprovedFact) -> dict:
    return {"id": fact.id, "key": fact.key, "product": fact.product, "value": fact.value, "version": fact.version, "active": fact.active, "source_reference": fact.source_reference, "excerpt": fact.excerpt, "updated_at": fact.updated_at.isoformat() if fact.updated_at else None}


def serialize_policy(policy: Policy) -> dict:
    return {"id": policy.id, "name": policy.name, "rule_type": policy.rule_type, "rule_value": policy.rule_value, "description": policy.description, "version": policy.version, "active": policy.active, "source_reference": policy.source_reference}


def serialize_asset(asset: BrandAsset) -> dict:
    return {"id": asset.id, "filename": asset.filename, "asset_type": asset.asset_type, "mime_type": asset.mime_type, "checksum": asset.checksum, "status": asset.status, "version": asset.version, "active": asset.active, "created_at": asset.created_at.isoformat()}


def safe_storage_key(org_id: int, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{org_id}/{uuid.uuid4().hex}{suffix}"


def serialize_claim(claim: ExtractedClaim) -> dict:
    return {"id": claim.id, "claim_text": claim.claim_text, "claim_type": claim.claim_type, "entity": claim.entity, "structured_value": claim.structured_value, "position_start": claim.position_start, "position_end": claim.position_end}


def serialize_version(db: Session, version: ContentVersion) -> dict:
    latest_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == version.id).order_by(AuditRun.created_at.desc())).first()
    findings = latest_audit.findings if latest_audit else []
    return {"id": version.id, "version_number": version.version_number, "text": version.text, "content_hash": version.content_hash, "created_by": version.created_by, "created_at": version.created_at.isoformat(), "audit": serialize_audit(latest_audit) if latest_audit else None}


def serialize_audit(audit: AuditRun | None) -> dict | None:
    if not audit:
        return None
    return {"id": audit.id, "engine_version": audit.engine_version, "provider_mode": audit.provider_mode, "provider_error": audit.provider_error, "retrieval_mode": audit.retrieval_mode, "retrieved_context": json.loads(audit.retrieved_context or "[]"), "overall_status": audit.overall_status, "created_at": audit.created_at.isoformat(), "claims": [serialize_claim(item) for item in audit.claims], "findings": [finding_dict(item) for item in audit.findings]}


def serialize_item(db: Session, item: ContentItem) -> dict:
    current = db.get(ContentVersion, item.current_version_id) if item.current_version_id else None
    latest_audit = None
    if current:
        latest_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == current.id).order_by(AuditRun.created_at.desc())).first()
    return {"id": item.id, "title": item.title, "content_type": item.content_type, "context": item.context, "status": item.status, "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(), "current_version": serialize_version(db, current) if current else None, "latest_audit": serialize_audit(latest_audit)}


def revision_comparison(db: Session, item: ContentItem) -> dict | None:
    versions = list(db.scalars(select(ContentVersion).where(ContentVersion.content_item_id == item.id).order_by(ContentVersion.version_number.desc()).limit(2)))
    if len(versions) < 2:
        return None
    current, previous = versions
    current_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == current.id).order_by(AuditRun.created_at.desc())).first()
    previous_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == previous.id).order_by(AuditRun.created_at.desc())).first()
    current_keys = {finding.issue_key for finding in current_audit.findings} if current_audit else set()
    previous_keys = {finding.issue_key for finding in previous_audit.findings} if previous_audit else set()
    return {"from_version": previous.version_number, "to_version": current.version_number, "resolved_issues": sorted(previous_keys - current_keys), "new_issues": sorted(current_keys - previous_keys), "remaining_issues": sorted(current_keys & previous_keys)}


def save_audit(db: Session, item: ContentItem, version: ContentVersion, org: Organization) -> AuditRun:
    facts = list(db.scalars(select(ApprovedFact).where(ApprovedFact.organization_id == org.id, ApprovedFact.active.is_(True))))
    policies = list(db.scalars(select(Policy).where(Policy.organization_id == org.id, Policy.active.is_(True))))
    terminology = list(db.scalars(select(Terminology).where(Terminology.organization_id == org.id, Terminology.active.is_(True))))
    retrieved = retrieve_context(version.text, facts, policies)
    drafts = run_rules_audit(version.text, facts, policies, terminology)
    provider_error = ""
    provider_mode = "rules-only"
    if settings.llm_api_key and settings.llm_provider.lower() == "gemini":
        try:
            ai_findings = call_gemini(version.text, facts, policies)
            provider_mode = settings.llm_provider
            existing_keys = {draft.issue_key for draft in drafts}
            for ai_finding in ai_findings:
                if ai_finding.issue_key in existing_keys:
                    continue
                evidence = db.get(ApprovedFact if ai_finding.evidence_type == "fact" else Policy, ai_finding.evidence_id) if ai_finding.evidence_id and ai_finding.evidence_type in {"fact", "policy"} else None
                drafts.append(FindingDraft(issue_key=ai_finding.issue_key, category=ai_finding.category, severity=ai_finding.severity, claim_text=ai_finding.claim_text, explanation=ai_finding.explanation, verification_status=ai_finding.verification_status, suggested_correction=ai_finding.suggested_correction, confidence=ai_finding.confidence, evidence_type=ai_finding.evidence_type, evidence_id=ai_finding.evidence_id if evidence and evidence.organization_id == org.id else None, evidence_label=getattr(evidence, "name", getattr(evidence, "key", "")), evidence_excerpt=getattr(evidence, "description", getattr(evidence, "excerpt", "")), source_reference=getattr(evidence, "source_reference", "")))
        except AIProviderError as exc:
            provider_mode = f"{settings.llm_provider}-error-fallback"
            provider_error = str(exc)
    elif settings.llm_api_key:
        provider_mode = f"{settings.llm_provider}-not-supported-fallback"
        provider_error = f"Configured provider '{settings.llm_provider}' has no adapter; deterministic rules were used."
    unresolved = [draft for draft in drafts if draft.verification_status != "Supported"]
    audit = AuditRun(content_version_id=version.id, provider_mode=provider_mode, provider_error=provider_error, retrieval_mode="lexical", retrieved_context=json.dumps([item.__dict__ for item in retrieved]), overall_status="changes_required" if unresolved else "passed")
    db.add(audit)
    db.flush()
    for sentence_match in re.finditer(r"[^.!?]+[.!?]?", version.text):
        claim_text = sentence_match.group(0).strip()
        if claim_text:
            claim_type = "promotional" if re.search(r"\b(best|waterproof|revolutionary|guarantee|number one|#1)\b", claim_text, re.I) else "statement"
            number_match = re.search(r"\b\d+(?:\.\d+)?\s*(?:mAh|year|years|%|mm|kg)\b", claim_text, re.I)
            db.add(ExtractedClaim(audit_run_id=audit.id, claim_text=claim_text, claim_type=claim_type, entity=item.context, structured_value=number_match.group(0) if number_match else "", position_start=sentence_match.start(), position_end=sentence_match.end()))
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


def run_audit_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AuditJob, job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()
        org = db.get(Organization, job.organization_id)
        item = db.get(ContentItem, job.content_item_id)
        if not org or not item or not item.current_version_id:
            raise ValueError("Audit target no longer exists")
        version = db.get(ContentVersion, item.current_version_id)
        audit = save_audit(db, item, version, org)
        job = db.get(AuditJob, job_id)
        job.status = "completed"
        job.audit_run_id = audit.id
        job.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(AuditJob, job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


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
    by_issue: dict[str, int] = {}
    for finding in findings:
        if finding.resolution_status != "resolved":
            by_category[finding.category] = by_category.get(finding.category, 0) + 1
            by_issue[finding.issue_key] = by_issue.get(finding.issue_key, 0) + 1
    reviewed_items = sum(1 for item in items if item.status not in {ContentStatus.DRAFT.value, ContentStatus.CHANGES_REQUIRED.value})
    return {"reviewed": reviewed_items, "audit_runs": len(audits), "provider_mode": "rules-only" if not settings.llm_api_key else settings.llm_provider, "unresolved_findings": sum(1 for f in findings if f.resolution_status != "resolved" and f.verification_status != "Supported"), "awaiting_approval": sum(1 for item in items if item.status == ContentStatus.RESUBMITTED.value), "needs_revalidation": sum(1 for item in items if item.status == ContentStatus.NEEDS_REVALIDATION.value), "findings_by_category": by_category, "common_violations": [{"issue_key": key, "count": count} for key, count in sorted(by_issue.items(), key=lambda pair: pair[1], reverse=True)[:5]], "recent_activity": recent, "items": [serialize_item(db, item) for item in items]}


@app.get("/api/knowledge")
def knowledge(db: Session = Depends(get_db)):
    org = demo_org(db)
    return {"facts": [serialize_fact(item) for item in db.scalars(select(ApprovedFact).where(ApprovedFact.organization_id == org.id).order_by(ApprovedFact.id))], "policies": [serialize_policy(item) for item in db.scalars(select(Policy).where(Policy.organization_id == org.id).order_by(Policy.id))], "terminology": [{"id": item.id, "prohibited": item.prohibited, "replacement": item.replacement, "active": item.active} for item in db.scalars(select(Terminology).where(Terminology.organization_id == org.id))], "documents": [{"id": item.id, "filename": item.filename, "page_reference": item.page_reference, "status": item.status, "excerpt": item.excerpt} for item in db.scalars(select(SourceDocument).where(SourceDocument.organization_id == org.id))], "assets": [serialize_asset(item) for item in db.scalars(select(BrandAsset).where(BrandAsset.organization_id == org.id).order_by(BrandAsset.id))]}


@app.post("/api/facts")
def create_fact(payload: FactCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    fact = ApprovedFact(organization_id=org.id, **payload.model_dump(), version=1, active=True)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return serialize_fact(fact)


@app.patch("/api/facts/{fact_id}")
def update_fact(fact_id: int, payload: FactUpdate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    fact = db.get(ApprovedFact, fact_id)
    if not fact or fact.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Approved fact not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(fact, key, value)
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


@app.post("/api/facts/{fact_id}/deactivate")
def deactivate_fact(fact_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    fact = db.get(ApprovedFact, fact_id)
    if not fact or fact.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Approved fact not found")
    fact.active = False
    fact.version += 1
    db.commit()
    return serialize_fact(fact)


@app.post("/api/policies")
def create_policy(payload: PolicyCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    policy = Policy(organization_id=org.id, **payload.model_dump(), version=1, active=True)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return serialize_policy(policy)


@app.patch("/api/policies/{policy_id}")
def update_policy(policy_id: int, payload: PolicyUpdate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    policy = db.get(Policy, policy_id)
    if not policy or policy.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Policy not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    policy.version += 1
    affected_ids = {dep.content_version_id for dep in db.scalars(select(Dependency).where(Dependency.dependency_type == "policy", Dependency.dependency_id == policy.id, Dependency.dependency_version < policy.version))}
    for version_id in affected_ids:
        version = db.get(ContentVersion, version_id)
        item = db.get(ContentItem, version.content_item_id) if version else None
        if item and item.status == ContentStatus.APPROVED.value:
            item.status = ContentStatus.NEEDS_REVALIDATION.value
    db.add(AuditEvent(organization_id=org.id, event_type="policy_updated", message=f"Updated {policy.name} to version {policy.version}; {len(affected_ids)} dependent version(s) flagged."))
    db.commit()
    return {"policy": serialize_policy(policy), "affected_versions": len(affected_ids)}


@app.post("/api/policies/{policy_id}/deactivate")
def deactivate_policy(policy_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    policy = db.get(Policy, policy_id)
    if not policy or policy.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.active = False
    policy.version += 1
    db.commit()
    return serialize_policy(policy)


@app.post("/api/terminology")
def create_terminology(payload: TerminologyCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    from .models import Terminology
    term = Terminology(organization_id=org.id, **payload.model_dump(), active=True)
    db.add(term)
    db.commit()
    db.refresh(term)
    return {"id": term.id, "prohibited": term.prohibited, "replacement": term.replacement, "active": term.active}


@app.patch("/api/terminology/{term_id}")
def update_terminology(term_id: int, payload: TerminologyUpdate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    term = db.get(Terminology, term_id)
    if not term or term.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Terminology record not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(term, key, value)
    db.commit()
    return {"id": term.id, "prohibited": term.prohibited, "replacement": term.replacement, "active": term.active}


@app.get("/api/users")
def list_users(role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    return {"users": [{"id": user.id, "name": user.name, "email": user.email, "role": user.role} for user in db.scalars(select(User).where(User.organization_id == org.id).order_by(User.id))]}


@app.patch("/api/users/{user_id}/role")
def update_user_role(user_id: int, payload: RoleUpdate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    actor = require_role(db, role, {"admin"})
    org = demo_org(db)
    user = db.get(User, user_id)
    if not user or user.organization_id != org.id:
        raise HTTPException(status_code=404, detail="User not found")
    old_role = user.role
    user.role = payload.role
    db.add(UserRoleEvent(user_id=user.id, organization_id=org.id, old_role=old_role, new_role=user.role))
    db.add(AuditEvent(organization_id=org.id, event_type="role_changed", message=f"Administrator {actor.name} changed {user.name} from {old_role} to {user.role}."))
    db.commit()
    return {"id": user.id, "name": user.name, "role": user.role}


@app.get("/api/content")
def list_content(db: Session = Depends(get_db)):
    org = demo_org(db)
    return {"items": [serialize_item(db, item) for item in db.scalars(select(ContentItem).where(ContentItem.organization_id == org.id).order_by(ContentItem.updated_at.desc()))]}


@app.post("/api/content")
def create_content(payload: ContentCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "admin"}, default_role="creator")
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
    response["revision_comparison"] = revision_comparison(db, item)
    decisions = list(db.scalars(select(ReviewDecision).where(ReviewDecision.content_version_id.in_([version.id for version in versions])).order_by(ReviewDecision.created_at.desc()))) if versions else []
    response["review_decisions"] = [{"id": decision.id, "decision": decision.decision, "comment": decision.comment, "created_at": decision.created_at.isoformat()} for decision in decisions]
    return response


@app.post("/api/content/{content_id}/versions")
def create_version(content_id: int, payload: VersionCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "admin"}, default_role="creator")
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
def audit_content(content_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "reviewer", "admin"}, default_role="creator")
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Content version not found")
    version = db.get(ContentVersion, item.current_version_id)
    audit = save_audit(db, item, version, org)
    return {"content": serialize_item(db, item), "audit": serialize_audit(audit)}


@app.post("/api/content/{content_id}/audit/jobs")
def queue_audit(content_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    actor = require_role(db, role, {"creator", "reviewer", "admin"}, default_role="creator")
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Content version not found")
    job = AuditJob(organization_id=org.id, content_item_id=item.id, requested_by=actor.id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    audit_executor.submit(run_audit_job, job.id)
    return {"id": job.id, "status": job.status, "content_id": item.id, "created_at": job.created_at.isoformat()}


@app.get("/api/audit/jobs/{job_id}")
def get_audit_job(job_id: int, db: Session = Depends(get_db)):
    org = demo_org(db)
    job = db.get(AuditJob, job_id)
    if not job or job.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Audit job not found")
    return {"id": job.id, "status": job.status, "content_id": job.content_item_id, "audit_run_id": job.audit_run_id, "error": job.error, "created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat()}


@app.post("/api/content/{content_id}/submit")
def submit_content(content_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "admin"}, default_role="creator")
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
def review_content(content_id: int, payload: ReviewCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    if payload.decision not in {"approve", "request_changes", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be approve, request_changes, or reject")
    reviewer = require_role(db, role, {"reviewer"}, default_role="reviewer")
    org = demo_org(db)
    item = db.get(ContentItem, content_id)
    if not item or item.organization_id != org.id or not item.current_version_id:
        raise HTTPException(status_code=404, detail="Review target not found")
    version = db.get(ContentVersion, item.current_version_id)
    if item.status != ContentStatus.RESUBMITTED.value:
        raise HTTPException(status_code=409, detail="Only submitted content versions can receive a review decision")
    latest_audit = db.scalars(select(AuditRun).where(AuditRun.content_version_id == version.id).order_by(AuditRun.created_at.desc())).first()
    if payload.decision == "approve" and (not latest_audit or any(finding.verification_status != "Supported" and finding.resolution_status != "resolved" for finding in latest_audit.findings)):
        raise HTTPException(status_code=409, detail="Approval requires a current audit with no unresolved unsupported findings")
    if payload.decision == "approve":
        item.status = ContentStatus.APPROVED.value
        passport = {"content_id": item.id, "version_id": version.id, "content_hash": version.content_hash, "policy_versions": [{"id": dep.dependency_id, "version": dep.dependency_version} for dep in db.scalars(select(Dependency).where(Dependency.content_version_id == version.id, Dependency.dependency_type == "policy"))], "fact_versions": [{"id": dep.dependency_id, "version": dep.dependency_version} for dep in db.scalars(select(Dependency).where(Dependency.content_version_id == version.id, Dependency.dependency_type == "fact"))], "audit_engine_version": latest_audit.engine_version if latest_audit else "rules-engine-1.0", "audit_findings": [finding_dict(finding) for finding in latest_audit.findings] if latest_audit else [], "reviewer": reviewer.name, "decision": "approved", "approved_at": datetime.utcnow().isoformat(), "notice": "This passport records review evidence and process; it is not a mathematical guarantee of truth or legal compliance."}
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
def resolve_finding(finding_id: int, payload: ResolveCreate, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "reviewer", "admin"}, default_role="creator")
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.action not in {"accept", "dismiss", "edit"}:
        raise HTTPException(status_code=422, detail="Action must be accept, dismiss, or edit")
    audit = db.get(AuditRun, finding.audit_run_id)
    version = db.get(ContentVersion, audit.content_version_id) if audit else None
    item = db.get(ContentItem, version.content_item_id) if version else None
    if not item or item.organization_id != demo_org(db).id:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.action == "edit" and payload.corrected_text:
        finding.suggested_correction = payload.corrected_text
    finding.resolution_status = "resolved"
    finding.resolution_reason = payload.reason or payload.action
    if audit and item:
        remaining = [item for item in audit.findings if item.verification_status != "Supported" and item.resolution_status != "resolved"]
        if not remaining and item.status == ContentStatus.CHANGES_REQUIRED.value:
            item.status = ContentStatus.AUDITED.value
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
async def upload_content(file: UploadFile = File(...), role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "admin"}, default_role="creator")
    if not file.filename or Path(file.filename).suffix.lower() not in {".txt", ".md", ".pdf"}:
        raise HTTPException(status_code=415, detail="Supported file types are .txt, .md, and .pdf")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB demo limit")
    page_count = 0
    try:
        if file.filename.lower().endswith(".pdf"):
            from io import BytesIO
            reader = PdfReader(BytesIO(raw))
            page_count = len(reader.pages)
            text = "\n".join(f"[Page {index + 1}]\n{page.extract_text() or ''}" for index, page in enumerate(reader.pages))
        else:
            text = raw.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not extract text from upload: {exc}") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="The uploaded file contains no extractable text")
    org = demo_org(db)
    page_reference = f"Pages 1-{page_count}" if page_count else "Extracted text"
    storage_key = safe_storage_key(org.id, Path(file.filename).name)
    try:
        get_storage().put(storage_key, raw, file.content_type or "application/octet-stream")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    document = SourceDocument(organization_id=org.id, filename=Path(file.filename).name, excerpt=text[:1000], page_reference=page_reference, storage_key=storage_key, status="unreviewed")
    db.add(document)
    db.commit()
    return {"filename": document.filename, "text": text, "document_id": document.id, "status": "unreviewed"}


@app.post("/api/documents/{document_id}/approve")
def approve_document(document_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    actor = require_role(db, role, {"admin"})
    org = demo_org(db)
    document = db.get(SourceDocument, document_id)
    if not document or document.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Source document not found")
    document.status = "approved"
    db.add(AuditEvent(organization_id=org.id, event_type="document_approved", message=f"Administrator {actor.name} approved source document {document.filename}."))
    db.commit()
    return {"id": document.id, "filename": document.filename, "status": document.status}


@app.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), asset_type: str = "logo", role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    allowed = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    if not file.filename or Path(file.filename).suffix.lower() not in allowed:
        raise HTTPException(status_code=415, detail="Supported asset types are PNG, JPG, SVG, and WEBP")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Asset exceeds the 10 MB demo limit")
    org = demo_org(db)
    storage_key = safe_storage_key(org.id, Path(file.filename).name)
    try:
        get_storage().put(storage_key, raw, file.content_type or "application/octet-stream")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    asset = BrandAsset(organization_id=org.id, filename=Path(file.filename).name, asset_type=asset_type, storage_key=storage_key, mime_type=file.content_type or "application/octet-stream", checksum=hashlib.sha256(raw).hexdigest(), status="unreviewed")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return serialize_asset(asset)


def image_similarity(reference: bytes, candidate: bytes) -> tuple[float, str]:
    try:
        from PIL import Image, ImageChops, ImageStat
        reference_image = Image.open(BytesIO(reference)).convert("RGB")
        candidate_image = Image.open(BytesIO(candidate)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"Both files must be readable raster images: {exc}") from exc
    reference_image.thumbnail((128, 128))
    candidate_image = candidate_image.resize(reference_image.size)
    difference = ImageChops.difference(reference_image, candidate_image)
    mean_error = sum(ImageStat.Stat(difference).mean) / 3
    similarity = max(0.0, min(1.0, 1.0 - mean_error / 255.0))
    verdict = "match" if similarity >= 0.92 else "review" if similarity >= 0.70 else "mismatch"
    return round(similarity, 4), verdict


@app.post("/api/assets/{asset_id}/compare")
async def compare_asset(asset_id: int, file: UploadFile = File(...), role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin", "creator", "reviewer"}, default_role="creator")
    org = demo_org(db)
    reference = db.get(BrandAsset, asset_id)
    if not reference or reference.organization_id != org.id or reference.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved asset in this workspace can be compared")
    if Path(reference.filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=422, detail="The approved reference must be a PNG, JPG, or WEBP asset")
    if not file.filename or Path(file.filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="Visual comparison supports PNG, JPG, and WEBP files")
    candidate = await file.read()
    if len(candidate) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Candidate asset exceeds the 10 MB demo limit")
    try:
        reference_bytes = get_storage().get(reference.storage_key)
        similarity, verdict = image_similarity(reference_bytes, candidate)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Approved asset bytes are unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    comparison = AssetComparison(organization_id=org.id, reference_asset_id=reference.id, candidate_filename=Path(file.filename).name, candidate_checksum=hashlib.sha256(candidate).hexdigest(), similarity=similarity, verdict=verdict, details="Local pixel comparison after RGB normalization and 128px thumbnail scaling.")
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return {"id": comparison.id, "reference_asset_id": reference.id, "candidate_filename": comparison.candidate_filename, "similarity": comparison.similarity, "verdict": comparison.verdict, "details": comparison.details, "created_at": comparison.created_at.isoformat()}


@app.get("/api/assets/{asset_id}/comparisons")
def asset_comparisons(asset_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin", "creator", "reviewer"}, default_role="creator")
    org = demo_org(db)
    asset = db.get(BrandAsset, asset_id)
    if not asset or asset.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Brand asset not found")
    comparisons = db.scalars(select(AssetComparison).where(AssetComparison.organization_id == org.id, AssetComparison.reference_asset_id == asset.id).order_by(AssetComparison.created_at.desc())).all()
    return {"items": [{"id": item.id, "candidate_filename": item.candidate_filename, "similarity": item.similarity, "verdict": item.verdict, "details": item.details, "created_at": item.created_at.isoformat()} for item in comparisons]}


@app.post("/api/assets/{asset_id}/approve")
def approve_asset(asset_id: int, role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"admin"})
    org = demo_org(db)
    asset = db.get(BrandAsset, asset_id)
    if not asset or asset.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Brand asset not found")
    asset.status = "approved"
    db.commit()
    return serialize_asset(asset)


@app.post("/api/content/upload-image")
async def upload_image_for_ocr(file: UploadFile = File(...), role: str | None = Header(default=None, alias="X-Demo-Role"), db: Session = Depends(get_db)):
    require_role(db, role, {"creator", "admin"}, default_role="creator")
    if not file.filename or Path(file.filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="Supported image types are PNG, JPG, and WEBP")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB demo limit")
    try:
        from io import BytesIO
        from PIL import Image
        import pytesseract
        image = Image.open(BytesIO(raw))
        text = pytesseract.image_to_string(image)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="OCR dependencies are not installed") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OCR is unavailable on this machine: {exc}") from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="No text was detected in the image")
    return {"filename": Path(file.filename).name, "text": text, "mode": "tesseract-ocr"}
