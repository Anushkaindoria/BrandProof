"""Initial BrandProof relational schema.

The application models are the source of truth for this first migration.
SQLAlchemy handles the ContentItem/ContentVersion cycle by emitting the
deferred foreign-key constraint on dialects that support ALTER TABLE.
"""

from typing import Sequence, Union

from alembic import op

from app.db import Base
from app import models  # noqa: F401


revision: str = "69bc25b0951d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
