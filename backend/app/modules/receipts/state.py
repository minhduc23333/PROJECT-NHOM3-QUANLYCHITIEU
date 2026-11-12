"""Máy trạng thái của hóa đơn: DRAFT → VERIFIED → SETTLED.

    DRAFT ──verify──▶ VERIFIED ──settle──▶ SETTLED (khóa vĩnh viễn)
      ▲                  │
      └── sửa dữ liệu ───┘   (đổi thứ ảnh hưởng chia tiền → tự quay về DRAFT)

Mọi thay đổi `receipt.status` PHẢI đi qua `transition()` để không ai nhảy cóc
(vd DRAFT → SETTLED) hoặc mở lại hóa đơn đã chốt.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import Debt, Receipt, SplitDetail

DRAFT = "DRAFT"
VERIFIED = "VERIFIED"
SETTLED = "SETTLED"

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({VERIFIED}),
    VERIFIED: frozenset({DRAFT, SETTLED}),
    SETTLED: frozenset(),  # trạng thái cuối
}

# Các trường đầu hóa đơn làm thay đổi kết quả chia tiền. merchant/ngày/category thì không.
SPLIT_FIELDS = frozenset({"subtotal", "tax_amount", "service_fee", "total_amount"})

ERR_SETTLED = "RECEIPT_SETTLED"
ERR_BAD_TRANSITION = "INVALID_STATUS_TRANSITION"
ERR_HAS_PAID_DEBT = "RECEIPT_HAS_PAID_DEBT"


def is_settled(receipt: Receipt) -> bool:
    return receipt.status == SETTLED


def require_not_settled(receipt: Receipt) -> None:
    """Khóa sau chốt: mọi thao tác sửa dữ liệu hóa đơn đều gọi hàm này đầu tiên."""
    if is_settled(receipt):
        raise Conflict("Hóa đơn đã chốt, không thể chỉnh sửa", code=ERR_SETTLED)


def transition(receipt: Receipt, target: str, *, message: str | None = None) -> None:
    """Đổi trạng thái nếu hợp lệ, ngược lại 409. Không commit — người gọi tự commit."""
    if target not in ALLOWED_TRANSITIONS.get(receipt.status, frozenset()):
        if is_settled(receipt):
            raise Conflict("Hóa đơn đã chốt, không thể chỉnh sửa", code=ERR_SETTLED)
        raise Conflict(
            message or f"Không thể chuyển hóa đơn từ {receipt.status} sang {target}",
            code=ERR_BAD_TRANSITION,
        )
    receipt.status = target


def reopen_if_split_inputs_changed(db: Session, receipt: Receipt, changed: bool) -> None:
    """Dữ liệu ảnh hưởng chia tiền đổi khi đang VERIFIED → về DRAFT để xác nhận lại.

    Kết quả chia cũ (split_details + nợ OPEN) không còn đúng nên bị xóa theo.
    Nếu đã có khoản nợ PAID thì không cho sửa (số tiền đã được trả không thể đổi âm thầm).
    """
    if not changed or receipt.status != VERIFIED:
        return
    paid = db.scalar(select(Debt.id).where(Debt.receipt_id == receipt.id, Debt.status == "PAID").limit(1))
    if paid is not None:
        db.rollback()  # bỏ các thay đổi chưa commit + nhả khóa dòng
        raise Conflict(
            "Hóa đơn đã có khoản nợ được thanh toán, không thể sửa dữ liệu chia tiền",
            code=ERR_HAS_PAID_DEBT,
        )
    db.execute(delete(Debt).where(Debt.receipt_id == receipt.id, Debt.status == "OPEN"))
    db.execute(delete(SplitDetail).where(SplitDetail.receipt_id == receipt.id))
    transition(receipt, DRAFT)
