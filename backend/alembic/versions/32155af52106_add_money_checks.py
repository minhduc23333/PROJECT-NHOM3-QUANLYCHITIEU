"""add money checks

Revision ID: 32155af52106
Revises: 9fd272b1d0e7
Create Date: 2026-11-03 12:41:39.008471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32155af52106'
down_revision: Union[str, Sequence[str], None] = '9fd272b1d0e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECKS = {
    "receipts": [
        ("ck_receipt_amounts",
         "COALESCE(subtotal,0) >= 0 AND COALESCE(tax_amount,0) >= 0 "
         "AND COALESCE(service_fee,0) >= 0 AND COALESCE(total_amount,0) >= 0"),
    ],
    "receipt_items": [
        ("ck_item_nonneg", "quantity >= 0 AND unit_price >= 0 AND line_total >= 0"),
    ],
    "split_details": [
        ("ck_split_nonneg", "item_amount >= 0 AND fee_amount >= 0 AND final_amount >= 0"),
    ],
    "debts": [
        ("ck_debt_amount_pos", "amount > 0"),
        ("ck_debt_not_self", "debtor_id <> creditor_id"),
    ],
}


def upgrade() -> None:
    for table, checks in CHECKS.items():
        with op.batch_alter_table(table) as batch:
            for name, cond in checks:
                batch.create_check_constraint(name, cond)


def downgrade() -> None:
    for table, checks in CHECKS.items():
        with op.batch_alter_table(table) as batch:
            for name, _ in checks:
                batch.drop_constraint(name, type_="check")