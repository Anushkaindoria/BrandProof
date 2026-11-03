"""Round 3: proposed knowledge items, finding origin and resolver."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20261102_03"
down_revision: Union[str, Sequence[str], None] = "20261026_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    finding_columns = {column["name"] for column in inspector.get_columns("findings")}
    if "resolved_by" not in finding_columns:
        op.add_column("findings", sa.Column("resolved_by", sa.String(length=120), nullable=False, server_default=""))
    if "origin" not in finding_columns:
        op.add_column("findings", sa.Column("origin", sa.String(length=20), nullable=False, server_default="rules"))
    if "proposed_items" not in inspector.get_table_names():
        op.create_table(
            "proposed_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("source_documents.id"), nullable=False),
            sa.Column("item_type", sa.String(length=20), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("quote", sa.Text(), nullable=False, server_default=""),
            sa.Column("page_reference", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("method", sa.String(length=30), nullable=False, server_default="rules"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("decided_by", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("resulting_record_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_proposed_items_organization_id", "proposed_items", ["organization_id"])
        op.create_index("ix_proposed_items_source_document_id", "proposed_items", ["source_document_id"])


def downgrade() -> None:
    op.drop_index("ix_proposed_items_source_document_id", table_name="proposed_items")
    op.drop_index("ix_proposed_items_organization_id", table_name="proposed_items")
    op.drop_table("proposed_items")
    op.drop_column("findings", "origin")
    op.drop_column("findings", "resolved_by")
