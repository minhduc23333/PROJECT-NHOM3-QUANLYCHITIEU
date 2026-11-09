"""add debt status check

Revision ID: a1c3e5f70b21
Revises: 32155af52106
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1c3e5f70b21'
down_revision: Union[str, Sequence[str], None] = '32155af52106'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("debts") as batch:
        batch.create_check_constraint("ck_debt_status", "status IN ('OPEN','PAID')")


def downgrade() -> None:
    with op.batch_alter_table("debts") as batch:
        batch.drop_constraint("ck_debt_status", type_="check")
