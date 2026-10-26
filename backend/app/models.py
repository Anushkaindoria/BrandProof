from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ContentStatus(str, Enum):
    DRAFT = "draft"
    AUDITED = "audited"
    CHANGES_REQUIRED = "changes_required"
    RESUBMITTED = "resubmitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVALIDATION = "needs_revalidation"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    users: Mapped[list["User"]] = relationship(back_populates="organization")
    facts: Mapped[list["ApprovedFact"]] = relationship(back_populates="organization")
    policies: Mapped[list["Policy"]] = relationship(back_populates="organization")
    content_items: Mapped[list["ContentItem"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(30))
    organization: Mapped[Organization] = relationship(back_populates="users")


class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    page_reference: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(30), default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovedFact(Base):
    __tablename__ = "approved_facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    product: Mapped[str] = mapped_column(String(120), default="NovaTech X1")
    value: Mapped[str] = mapped_column(String(255))
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(120), default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization: Mapped[Organization] = relationship(back_populates="facts")


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    rule_type: Mapped[str] = mapped_column(String(50))
    rule_value: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(120), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization: Mapped[Organization] = relationship(back_populates="policies")


class Terminology(Base):
    __tablename__ = "terminology"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    prohibited: Mapped[str] = mapped_column(String(120))
    replacement: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ContentItem(Base):
    __tablename__ = "content_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(60), default="Advertisement")
    context: Mapped[str] = mapped_column(String(120), default="NovaTech X1")
    status: Mapped[str] = mapped_column(String(40), default=ContentStatus.DRAFT.value)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("content_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization: Mapped[Organization] = relationship(back_populates="content_items")
    versions: Mapped[list["ContentVersion"]] = relationship(foreign_keys="ContentVersion.content_item_id", back_populates="content_item", cascade="all, delete-orphan")


class ContentVersion(Base):
    __tablename__ = "content_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(120), default="Demo Creator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content_item: Mapped[ContentItem] = relationship(foreign_keys=[content_item_id], back_populates="versions")
    audit_runs: Mapped[list["AuditRun"]] = relationship(back_populates="content_version", cascade="all, delete-orphan")


class AuditRun(Base):
    __tablename__ = "audit_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"), index=True)
    engine_version: Mapped[str] = mapped_column(String(80), default="rules-engine-1.0")
    provider_mode: Mapped[str] = mapped_column(String(80), default="rules-only")
    overall_status: Mapped[str] = mapped_column(String(40), default="changes_required")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content_version: Mapped[ContentVersion] = relationship(back_populates="audit_runs")
    findings: Mapped[list["Finding"]] = relationship(back_populates="audit_run", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_run_id: Mapped[int] = mapped_column(ForeignKey("audit_runs.id"), index=True)
    issue_key: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(30))
    claim_text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(40))
    suggested_correction: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(30), default="medium")
    resolution_status: Mapped[str] = mapped_column(String(30), default="open")
    resolution_reason: Mapped[str] = mapped_column(Text, default="")
    evidence_type: Mapped[str] = mapped_column(String(30), default="fact")
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_label: Mapped[str] = mapped_column(String(255), default="")
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    source_reference: Mapped[str] = mapped_column(String(120), default="")
    audit_run: Mapped[AuditRun] = relationship(back_populates="findings")


class Dependency(Base):
    __tablename__ = "dependencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(30))
    dependency_id: Mapped[int] = mapped_column(Integer)
    dependency_version: Mapped[int] = mapped_column(Integer)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"), unique=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    content_hash: Mapped[str] = mapped_column(String(64))
    passport_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
