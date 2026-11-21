"""allow receipts without a group

Revision ID: b5f7c9a2d4e6
Revises: a1c3e5f70b21
Create Date: 2026-11-12 10:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5f7c9a2d4e6"
down_revision: str | Sequence[str] | None = "a1c3e5f70b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.alter_column("group_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.alter_column("group_id", existing_type=sa.Integer(), nullable=False)
