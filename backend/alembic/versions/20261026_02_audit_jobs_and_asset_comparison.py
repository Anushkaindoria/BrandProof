"""Add retrieval traces, background audit jobs, and visual comparisons."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20261026_02"
down_revision: Union[str, Sequence[str], None] = "69bc25b0951d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    source_columns = {column["name"] for column in inspector.get_columns("source_documents")}
    audit_columns = {column["name"] for column in inspector.get_columns("audit_runs")}
    if "storage_key" not in source_columns:
        op.add_column("source_documents", sa.Column("storage_key", sa.String(length=255), nullable=False, server_default=""))
    if "retrieval_mode" not in audit_columns:
        op.add_column("audit_runs", sa.Column("retrieval_mode", sa.String(length=40), nullable=False, server_default="lexical"))
    if "retrieved_context" not in audit_columns:
        op.add_column("audit_runs", sa.Column("retrieved_context", sa.Text(), nullable=False, server_default="[]"))
    if "asset_comparisons" not in inspector.get_table_names():
        op.create_table(
            "asset_comparisons",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("reference_asset_id", sa.Integer(), sa.ForeignKey("brand_assets.id"), nullable=False),
            sa.Column("candidate_filename", sa.String(length=255), nullable=False),
            sa.Column("candidate_checksum", sa.String(length=64), nullable=False),
            sa.Column("similarity", sa.Float(), nullable=False),
            sa.Column("verdict", sa.String(length=30), nullable=False),
            sa.Column("details", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_asset_comparisons_organization_id", "asset_comparisons", ["organization_id"])
        op.create_index("ix_asset_comparisons_reference_asset_id", "asset_comparisons", ["reference_asset_id"])
    if "audit_jobs" not in inspector.get_table_names():
        op.create_table(
            "audit_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id"), nullable=False),
            sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("audit_run_id", sa.Integer(), sa.ForeignKey("audit_runs.id"), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_audit_jobs_organization_id", "audit_jobs", ["organization_id"])
        op.create_index("ix_audit_jobs_content_item_id", "audit_jobs", ["content_item_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_jobs_content_item_id", table_name="audit_jobs")
    op.drop_index("ix_audit_jobs_organization_id", table_name="audit_jobs")
    op.drop_table("audit_jobs")
    op.drop_index("ix_asset_comparisons_reference_asset_id", table_name="asset_comparisons")
    op.drop_index("ix_asset_comparisons_organization_id", table_name="asset_comparisons")
    op.drop_table("asset_comparisons")
    op.drop_column("audit_runs", "retrieved_context")
    op.drop_column("audit_runs", "retrieval_mode")
    op.drop_column("source_documents", "storage_key")
