"""Glue: chạy OCR cho một hóa đơn DRAFT, parse, rồi ghi vào DB.

Luồng: receipt (ocr_status=PENDING|FAILED) -> run_ocr -> parse_receipt
       -> DONE (điền merchant/ngày/tiền + receipt_items) | FAILED (nhập tay).
Không bao giờ ghi ở trạng thái VERIFIED/SETTLED và không đụng payer_id.
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_group_membership
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Receipt, ReceiptItem, User
from app.modules.ocr.engine import OcrError, OcrResult
from app.modules.ocr.parser import ParsedReceipt
from app.modules.ocr.pipeline import read_receipt
from app.modules.ocr.preprocess import ImageError
from app.modules.receipts import categories
from app.modules.receipts.uploads import resolve_image_path

log = logging.getLogger(__name__)

_MONEY_LIMIT = Decimal(9999999999999)  # Numeric(15,2): chừa chỗ cho 2 chữ số thập phân


_AUTO_MIN_CONF = 65.0


def _money_metrics(parsed: ParsedReceipt) -> tuple[bool, bool, int, Decimal]:
    if parsed.ocr_status != "DONE" or not parsed.items or parsed.total_amount is None or parsed.total_amount <= 0:
        return False, False, len(parsed.items), Decimal("999999999")
    items_sum = sum((i.line_total for i in parsed.items), Decimal(0))
    fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
    disc = parsed.discount_amount or Decimal(0)
    bad_items = sum(
        1
        for i in parsed.items
        if abs(i.quantity * i.unit_price - i.line_total) > max(Decimal(5), i.line_total * Decimal("0.005"))
    )
    sub_diff = abs(items_sum - parsed.subtotal) if parsed.subtotal is not None else Decimal(0)
    tot_diff = abs(items_sum + fees - disc - parsed.total_amount)
    diff = max(sub_diff, tot_diff)
    return diff <= Decimal(5) and bad_items == 0, diff <= Decimal(1000) and bad_items == 0, bad_items, diff


def _is_money_reliable(parsed: ParsedReceipt, ocr: OcrResult) -> tuple[bool, str]:
    if parsed.ocr_status != "DONE":
        return False, "OCR cục bộ không đọc được hóa đơn"
    if not parsed.items:
        return False, "chưa đọc được dòng món nào"
    if parsed.total_amount is None or parsed.total_amount <= 0:
        return False, "thiếu tổng tiền thanh toán"
    if parsed.warnings:
        return False, f"có {len(parsed.warnings)} cảnh báo cần đối chiếu"
    exact, _, bad_items, diff = _money_metrics(parsed)
    if bad_items > 0:
        return False, f"{bad_items} dòng món lệch SL × đơn giá"
    if not exact:
        return False, f"tổng món + thuế/phí lệch tổng hóa đơn {diff}đ"
    if ocr.boxes and ocr.mean_conf < _AUTO_MIN_CONF:
        return False, f"độ tin cậy OCR thấp ({ocr.mean_conf:.0f}%)"
    return True, "ok"


def _is_local_usable(parsed: ParsedReceipt, ocr: OcrResult) -> bool:
    """Chặn lưu kết quả Tesseract rác (độ tin cậy < 50% hoặc tên món vô nghĩa kiểu 'ay') làm DONE."""
    if parsed.ocr_status != "DONE" or not parsed.items:
        return False
    if ocr.boxes and ocr.mean_conf < 50.0:
        return False
    good_names = sum(1 for i in parsed.items if sum(c.isalpha() for c in i.item_name) >= 3)
    return good_names >= max(1, len(parsed.items) // 2)


def _accuracy_rank(parsed: ParsedReceipt, *, is_ai: bool = False) -> tuple:
    if parsed.ocr_status != "DONE":
        return (0, 0, 0, 0, 0, 0, 0)
    exact, within_round, bad_items, diff = _money_metrics(parsed)
    has_total = 1 if (parsed.total_amount is not None and parsed.total_amount > 0) else 0
    rel_err = float(diff / parsed.total_amount) if has_total else 1e9
    return (
        1 if exact else 0,
        1 if within_round else 0,
        -bad_items,
        -rel_err,
        has_total,
        1 if is_ai else 0,
        len(parsed.items),
    )


def _extract_gemini(resolved: str) -> tuple[ParsedReceipt, OcrResult]:
    from app.modules.ocr.gemini_ocr import read_receipt_gemini

    return read_receipt_gemini(resolved)


def _extract_auto(resolved: str) -> tuple[ParsedReceipt, OcrResult]:
    """Có GEMINI_API_KEY -> chỉ tin Gemini (đọc chuẩn hơn hẳn Tesseract; Tesseract hay đọc SAI mà vẫn "khớp" tiền).
    Gemini lỗi thì báo lỗi rõ ràng để nhập tay, KHÔNG lặng lẽ dùng kết quả Tesseract có thể sai.
    Không có key -> dùng OCR cục bộ như cũ."""
    if settings.GEMINI_API_KEY:
        return _extract_gemini(resolved)
    return read_receipt(resolved)


def extract(image_path: str) -> tuple[ParsedReceipt, OcrResult]:
    """Ảnh -> (dữ liệu có cấu trúc, text thô). Ném OcrError/ImageError nếu OCR hỏng."""
    resolved = str(resolve_image_path(image_path))
    engine_mode = (settings.OCR_ENGINE or "auto").strip().lower()
    if engine_mode == "auto":
        return _extract_auto(resolved)
    if engine_mode == "gemini":
        return _extract_gemini(resolved)
    parsed, raw = read_receipt(resolved)
    return parsed, raw


def _format_qty(q: Decimal) -> str:
    s = format(q.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _normalize_items_for_db(parsed: ParsedReceipt) -> None:
    """Giữ nguyên 100% thành tiền từng món trên hóa đơn:
    - Món cân ký (>2 số lẻ như 1.264 kg hoặc làm tròn siêu thị như 0.49 × 24.900 = 12.199đ) đưa số cân vào tên món,
      đặt SL = 1 và đơn giá = đúng thành tiền in trên hóa đơn (61.943đ, 12.199đ).
    - Nếu tổng các món + thuế + phí lớn hơn tổng thực trả một khoản làm tròn siêu thị (<= 1.000đ,
      VD: BHX 242.642đ -> thanh toán 242.000đ), tự ghi phần chênh lệch (642đ) vào discount_amount
      để giữ nguyên cả giá từng món lẫn đúng số tiền thực trả 242.000đ."""
    cent = Decimal("0.01")
    for item in parsed.items:
        if item.line_total <= 0:
            continue
        q_db = item.quantity.quantize(cent, rounding=ROUND_HALF_UP)
        expected_db = (q_db * item.unit_price).quantize(cent, rounding=ROUND_HALF_UP)
        if expected_db == item.line_total and item.quantity == q_db:
            continue
        is_fractional = item.quantity != item.quantity.to_integral_value()
        raw_diff = item.quantity * item.unit_price - item.line_total
        within_rounding = abs(raw_diff) <= max(Decimal(50), item.line_total * Decimal("0.02"))
        if item.quantity != q_db or (is_fractional and within_rounding):
            q_str = _format_qty(item.quantity)
            suffix = f" ({q_str})"
            if suffix not in item.item_name:
                item.item_name = f"{item.item_name[: 255 - len(suffix)]}{suffix}"
            item.quantity = Decimal(1)
            item.unit_price = item.line_total

    if parsed.items and parsed.total_amount is not None:
        items_sum = sum((i.line_total for i in parsed.items), Decimal(0))
        fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
        implied_discount = items_sum + fees - parsed.total_amount
        disc = parsed.discount_amount or Decimal(0)
        if Decimal(0) < implied_discount <= Decimal(1000):
            parsed.subtotal = items_sum
            parsed.discount_amount = implied_discount
            parsed.warnings = [
                w for w in parsed.warnings if "khác tạm tính" not in w and "khác tổng thanh toán" not in w
            ]
        elif disc > 0 and Decimal(0) < abs(implied_discount - disc) <= Decimal(5) and implied_discount >= 0:
            parsed.subtotal = items_sum
            parsed.discount_amount = implied_discount
            parsed.warnings = [
                w for w in parsed.warnings if "khác tạm tính" not in w and "khác tổng thanh toán" not in w
            ]
        elif parsed.subtotal is not None and Decimal(0) < abs(items_sum - parsed.subtotal) <= Decimal(5):
            parsed.subtotal = items_sum
            if disc == 0 and Decimal(0) < abs(items_sum + fees - parsed.total_amount) <= Decimal(5):
                parsed.total_amount = items_sum + fees
            parsed.warnings = [
                w for w in parsed.warnings if "khác tạm tính" not in w and "khác tổng thanh toán" not in w
            ]


def _lock_still_draft(db: Session, receipt: Receipt) -> None:
    """OCR chạy lâu (tới OCR_TIMEOUT_SEC). Trong lúc đó hóa đơn có thể đã được xác nhận/chốt ở request khác:
    khóa dòng + đọc lại trạng thái trước khi ghi để không ghi đè hóa đơn đã khóa."""
    db.refresh(receipt, with_for_update=True)
    if receipt.status != "DRAFT":
        db.rollback()
        raise Conflict("Hóa đơn đã được xác nhận/chốt trong lúc chạy OCR, kết quả OCR bị bỏ qua")


def _mark_failed(db: Session, receipt: Receipt, reason: str):
    _lock_still_draft(db, receipt)
    receipt.ocr_status = "FAILED"
    db.commit()
    db.refresh(receipt)
    return receipt, None, None, reason


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
        return _mark_failed(db, receipt, str(exc))
    except Exception as exc:  # noqa: BLE001  lỗi OpenCV/bộ nhớ/hệ điều hành...: vẫn trả FAILED để nhập tay, không 500
        log.exception("OCR lỗi không lường trước receipt=%s", receipt_id)
        return _mark_failed(db, receipt, f"Lỗi khi đọc ảnh: {exc}")

    _lock_still_draft(db, receipt)
    receipt.ocr_status = parsed.ocr_status
    if parsed.ocr_status == "DONE":
        _normalize_items_for_db(parsed)
        receipt.merchant_name = parsed.merchant_name
        receipt.receipt_date = parsed.receipt_date
        if not receipt.category:  # gợi ý theo từ khóa, không bao giờ đè danh mục người dùng đã chọn
            receipt.category = categories.suggest(parsed.merchant_name, [i.item_name for i in parsed.items])
        for attr in ("subtotal", "tax_amount", "service_fee", "discount_amount", "total_amount"):
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
