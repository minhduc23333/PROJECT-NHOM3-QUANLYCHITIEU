from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.receipt import MONEY


class ItemSelection(Base):
    __tablename__ = "item_selections"

    item_id: Mapped[int] = mapped_column(ForeignKey("receipt_items.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SplitDetail(Base):
    __tablename__ = "split_details"
    __table_args__ = (
        UniqueConstraint("receipt_id", "user_id", name="uq_split_receipt_user"),
        CheckConstraint("item_amount >= 0 AND fee_amount >= 0 AND final_amount >= 0", name="ck_split_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_amount: Mapped[Decimal] = mapped_column(MONEY)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY)
    final_amount: Mapped[Decimal] = mapped_column(MONEY)


class Debt(Base):
    __tablename__ = "debts"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_debt_amount_pos"),
        CheckConstraint("debtor_id <> creditor_id", name="ck_debt_not_self"),
        CheckConstraint("status IN ('OPEN','PAID')", name="ck_debt_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), index=True)
    debtor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    creditor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")