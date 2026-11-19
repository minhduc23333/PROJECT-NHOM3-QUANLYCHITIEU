"""Glue: chạy OCR cho một hóa đơn DRAFT, parse, rồi ghi vào DB.

Luồng: receipt (ocr_status=PENDING|FAILED) -> run_ocr -> parse_receipt
       -> DONE (điền merchant/ngày/tiền + receipt_items) | FAILED (nhập tay).
Không bao giờ ghi ở trạng thái VERIFIED/SETTLED và không đụng payer_id.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.deps import get_group_membership
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Receipt, ReceiptItem, User
from app.modules.ocr.engine import OcrError, OcrResult
from app.modules.ocr.parser import ParsedReceipt
from app.modules.ocr.pipeline import read_receipt
from app.modules.ocr.preprocess import ImageError
from app.modules.receipts.uploads import resolve_image_path

log = logging.getLogger(__name__)

_MONEY_LIMIT = Decimal(9999999999999)  # Numeric(15,2): chừa chỗ cho 2 chữ số thập phân


def extract(image_path: str) -> tuple[ParsedReceipt, OcrResult]:
    """Ảnh -> (dữ liệu có cấu trúc, text thô). Ném OcrError/ImageError nếu OCR hỏng."""
    parsed, raw = read_receipt(str(resolve_image_path(image_path)))
    return parsed, raw


def _lock_still_draft(db: Session, receipt: Receipt) -> None:
    """OCR chạy lâu (tới OCR_TIMEOUT_SEC). Trong lúc đó hóa đơn có thể đã được xác nhận/chốt ở request khác:
    khóa dòng + đọc lại trạng thái trước khi ghi để không ghi đè hóa đơn đã khóa."""
    db.refresh(receipt, with_for_update=True)
    if receipt.status != "DRAFT":
        db.rollback()
        raise Conflict("Hóa đơn đã được xác nhận/chốt trong lúc chạy OCR, kết quả OCR bị bỏ qua")


def process_receipt(
    db: Session, user: User, receipt_id: int
) -> tuple[Receipt, ParsedReceipt | None, str | None, str | None]:
    """Trả (receipt, parsed, raw_text, error). OCR hỏng: parsed/raw_text = None và error = lý do cụ thể."""
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFound("Không tìm thấy hóa đơn")
    if receipt.group_id is not None:
        get_group_membership(db, receipt.group_id, user.id)       # 404 / 403
    if receipt.uploaded_by != user.id:
        raise Forbidden("Chỉ người tải hóa đơn mới được chạy OCR")
    if receipt.status != "DRAFT":
        raise Conflict("Chỉ hóa đơn DRAFT mới chạy OCR được")
    if receipt.ocr_status == "DONE":
        raise Conflict("Hóa đơn đã có kết quả OCR; hãy sửa trực tiếp thay vì chạy lại")

    try:
        parsed, raw = extract(receipt.image_path)
    except (OcrError, ImageError) as exc:       # gồm OcrTimeout (là con của OcrError)
        log.warning("OCR thất bại receipt=%s: %s", receipt_id, exc)
        _lock_still_draft(db, receipt)
        receipt.ocr_status = "FAILED"
        db.commit()
        db.refresh(receipt)
        return receipt, None, None, str(exc)

    _lock_still_draft(db, receipt)
    receipt.ocr_status = parsed.ocr_status
    if parsed.ocr_status == "DONE":
        receipt.merchant_name = parsed.merchant_name
        receipt.receipt_date = parsed.receipt_date
        for attr in ("subtotal", "tax_amount", "service_fee", "total_amount"):
            value = getattr(parsed, attr)
            if value is not None and value >= _MONEY_LIMIT:
                value = None                     # số quá lớn = đọc sai, để trống
            setattr(receipt, attr, value)
        db.execute(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id))
        db.add_all(
            ReceiptItem(
                receipt_id=receipt.id,
                item_name=i.item_name,
                quantity=i.quantity,
                unit_price=i.unit_price,
                line_total=i.line_total,
            )
            for i in parsed.items
        )
    db.commit()
    db.refresh(receipt)
    return receipt, parsed, raw.text, None
