from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

MONEY = Numeric(15, 2)   # DECIMAL, không dùng float cho tiền


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','VERIFIED','SETTLED')", name="ck_receipt_status"),
        CheckConstraint(
            "COALESCE(subtotal,0) >= 0 AND COALESCE(tax_amount,0) >= 0 "
            "AND COALESCE(service_fee,0) >= 0 AND COALESCE(total_amount,0) >= 0",
            name="ck_receipt_amounts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    image_path: Mapped[str] = mapped_column(String(500))
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    receipt_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY)
    tax_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    service_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    total_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    category: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    ocr_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReceiptItem(Base):
    __tablename__ = "receipt_items"
    __table_args__ = (
        CheckConstraint("quantity >= 0 AND unit_price >= 0 AND line_total >= 0", name="ck_item_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    item_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=1)
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)