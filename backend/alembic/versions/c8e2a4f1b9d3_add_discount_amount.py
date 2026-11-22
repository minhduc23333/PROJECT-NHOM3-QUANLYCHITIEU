"""add discount_amount to receipts

Revision ID: c8e2a4f1b9d3
Revises: b5f7c9a2d4e6
Create Date: 2026-11-21 08:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e2a4f1b9d3"
down_revision: str | Sequence[str] | None = "b5f7c9a2d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.add_column(sa.Column("discount_amount", sa.Numeric(precision=15, scale=2), nullable=True))
        batch.create_check_constraint("ck_receipt_discount_nonneg", "COALESCE(discount_amount,0) >= 0")


def downgrade() -> None:
    with op.batch_alter_table("receipts") as batch:
        batch.drop_constraint("ck_receipt_discount_nonneg", type_="check")
        batch.drop_column("discount_amount")
