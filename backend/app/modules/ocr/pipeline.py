"""Điều phối OCR nhiều lượt: ảnh -> thử vài cách xử lý/chế độ Tesseract -> parse từng kết quả -> giữ kết quả tốt nhất.

Vì sao không chạy đúng một lượt: một cách tiền xử lý không bao giờ hợp mọi ảnh (chữ in nhiệt nhạt, ảnh chụp
nghiêng, nền bàn gần màu giấy, ảnh bị xoay 90°...). Thay vì đoán trước, ta thử lần lượt và dùng chính
parser để chấm điểm: kết quả nào ra tổng tiền, các dòng món cộng khớp tạm tính/tổng thì thắng.
Dừng sớm ngay khi có kết quả "đủ tốt" nên ảnh sạch vẫn chỉ tốn một lượt OCR.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from functools import partial

import cv2

from app.core.config import settings
from app.modules.ocr.engine import OcrError, OcrResult, _run_with_timeout, detect_rotation, recognize
from app.modules.ocr.parser import ParsedReceipt, parse_receipt
from app.modules.ocr.preprocess import ImageError, iter_variants, load_image, rotate90

log = logging.getLogger(__name__)

BUDGET_RATIO = 0.7        # chỉ bắt đầu lượt mới khi đã dùng < 70% OCR_TIMEOUT_SEC
LOW_CONF = 55.0           # độ tin cậy trung bình (0..100) dưới mức này -> cảnh báo người dùng đối chiếu kỹ


@dataclass
class Attempt:
    name: str
    parsed: ParsedReceipt
    ocr: OcrResult
    score: float


def _items_sum(p: ParsedReceipt) -> Decimal:
    return sum((i.line_total for i in p.items), Decimal(0))


def _consistent(p: ParsedReceipt) -> bool:
    """Các con số tự khớp nhau (dấu hiệu mạnh nhất rằng OCR đọc đúng)."""
    if p.total_amount is None or not p.items:
        return False
    fees = (p.tax_amount or 0) + (p.service_fee or 0)
    base = p.subtotal if p.subtotal is not None else _items_sum(p)
    return _items_sum(p) == base and base + fees == p.total_amount


def score(p: ParsedReceipt, ocr: OcrResult) -> float:
    s = 0.0
    if p.total_amount is not None:
        s += 5
    if p.subtotal is not None:
        s += 2
    s += min(len(p.items), 15)
    # món có SL × đơn giá = thành tiền khớp (không bị cảnh báo 'Dòng ...') đáng tin hơn món phải tự chỉnh
    s += 0.5 * (len(p.items) - sum(w.startswith("Dòng") for w in p.warnings))
    if p.receipt_date is not None:
        s += 1
    if p.merchant_name:
        s += 0.5
    if _consistent(p):
        s += 7
    elif p.total_amount and p.items:
        # đọc thiếu/sai món thì tổng các món lệch xa tổng tiền: chỉ thưởng khi tiệm cận > 50% (0..4)
        base = p.subtotal if p.subtotal is not None else p.total_amount - (p.tax_amount or 0) - (p.service_fee or 0)
        if base and base > 0:
            closeness = 1.0 - float(abs(_items_sum(p) - base) / base)
            s += 4 * max(0.0, (closeness - 0.5) / 0.5)
    s -= 1.5 * len(p.warnings)
    s += ocr.mean_conf / 50     # 0..2: phân định khi hai kết quả ngang điểm
    return s


def is_good(p: ParsedReceipt) -> bool:
    return _consistent(p) and not p.warnings


def _next_variant(gen):
    """Lấy biến thể tiếp theo; lỗi OpenCV ở một biến thể không làm hỏng cả lượt OCR."""
    while True:
        try:
            return next(gen)
        except StopIteration:
            return None
        except cv2.error as exc:   # pragma: no cover - phụ thuộc ảnh
            log.warning("Tiền xử lý lỗi, bỏ qua biến thể: %s", exc)
            return None


def _empty(p: ParsedReceipt) -> bool:
    return not p.items and p.total_amount is None


def _read(image_path: str, budget: float) -> tuple[ParsedReceipt, OcrResult]:
    started = time.monotonic()
    img = load_image(image_path)
    attempts: list[Attempt] = []
    first_error: OcrError | None = None

    def time_left() -> bool:
        return time.monotonic() - started < budget

    def run(name: str, im, psm: int) -> Attempt | None:
        nonlocal first_error
        try:
            res = recognize(im, psm)
        except OcrError as exc:
            if not attempts:   # lượt đầu đã lỗi (thiếu Tesseract/ngôn ngữ...) thì thử tiếp cũng vô ích
                raise
            first_error = first_error or exc
            log.warning("OCR lượt '%s' lỗi: %s", name, exc)
            return None
        parsed = parse_receipt(res.lines)
        att = Attempt(name, parsed, res, score(parsed, res))
        attempts.append(att)
        log.info("OCR '%s' psm=%d: score=%.1f items=%d total=%s conf=%.0f warnings=%d (%.1fs)",
                 name, psm, att.score, len(parsed.items), parsed.total_amount, res.mean_conf,
                 len(parsed.warnings), time.monotonic() - started)
        return att

    def best() -> Attempt:
        return max(attempts, key=lambda a: a.score)

    gen = iter_variants(img)
    first = _next_variant(gen)
    if first is None:
        raise OcrError("Không xử lý được ảnh")
    variants: list[tuple[str, object]] = [first]
    att = run(first[0], first[1], 6)
    if att is not None and is_good(att.parsed):
        return _finish(att, attempts)

    turn = 0

    def search_rotation(ks) -> Attempt | None:
        """Thử xoay ảnh đầu tiên; chỉ tin hướng mới khi kết quả tốt hơn rõ rệt (có tổng, hoặc >= 2 món):
        một món rác là chưa đủ. Tìm được thì các biến thể sau dùng luôn hướng đó."""
        nonlocal turn
        base_score = max((a.score for a in attempts), default=0.0)
        for k in ks:
            if not k or not time_left():
                continue
            rot = run(f"{first[0]}/rot{k * 90}", rotate90(first[1], k), 6)
            if rot is not None and rot.score >= base_score + 3 and (
                rot.parsed.total_amount is not None or len(rot.parsed.items) >= 2
            ):
                turn = k
                variants[0] = (f"{first[0]}/rot{k * 90}", rotate90(first[1], k))
                return rot
        return None

    # Lượt đầu không ra gì (không món, không tổng): hoặc ảnh bị xoay 90/180/270 độ, hoặc việc cắt/xử lý ảnh chưa hợp.
    # OSD của Tesseract chỉ hướng rõ ràng (khác 0) -> thử đúng hướng đó ngay. OSD bảo ảnh đã thẳng (0) -> bỏ qua
    # xoay. OSD không biết (None) -> thử các biến thể ảnh trước (rẻ), dò xoay mù để cuối.
    blind_rotation = False
    if att is None or _empty(att.parsed):
        guess = detect_rotation(first[1])
        if guess:
            rot = search_rotation([guess, *[k for k in (2, 1, 3) if k != guess]])
            if rot is not None and is_good(rot.parsed):
                return _finish(rot, attempts)
        blind_rotation = guess is None

    # Các biến thể xử lý ảnh còn lại (nhị phân Otsu, ảnh không cắt...)
    while time_left() and (v := _next_variant(gen)) is not None:
        im = rotate90(v[1], turn) if turn else v[1]
        variants.append((v[0], im))
        att = run(v[0], im, 6)
        if att is not None and is_good(att.parsed):
            return _finish(att, attempts)

    if blind_rotation and all(_empty(a.parsed) or a.score < 8 for a in attempts):
        rot = search_rotation([2, 1, 3])
        if rot is not None and is_good(rot.parsed):
            return _finish(rot, attempts)

    # Cùng ảnh đầu tiên nhưng chia cột kiểu khác (psm 4 = một cột chữ cỡ khác nhau)
    if time_left():
        run(f"{variants[0][0]}/psm4", variants[0][1], 4)

    if not attempts:
        raise first_error or OcrError("Không xử lý được ảnh")
    return _finish(best(), attempts)


def _reconcile_total(best: Attempt, attempts: list[Attempt]) -> None:
    """Chữ số cuối của tổng tiền hay bị đọc nhầm (9.010.000 -> 9.010.006). Nếu tổng các món (+thuế, phí)
    đúng bằng tổng tiền mà một lượt đọc KHÁC đọc được thì lấy giá trị đó: hai nguồn độc lập cùng khớp."""
    p = best.parsed
    if p.total_amount is None or not p.items or p.subtotal is not None:
        return
    expected = _items_sum(p) + (p.tax_amount or 0) + (p.service_fee or 0)
    if expected == p.total_amount:
        return
    for other in attempts:
        if other is not best and other.parsed.total_amount == expected:
            log.info("Đối chiếu chéo: tổng %s -> %s (khớp tổng các món)", p.total_amount, expected)
            p.total_amount = expected
            p.warnings = [w for w in p.warnings if "khác tổng thanh toán" not in w]
            return


def _finish(att: Attempt, attempts: list[Attempt] | None = None) -> tuple[ParsedReceipt, OcrResult]:
    if attempts:
        _reconcile_total(att, attempts)
    p = att.parsed
    log.info("OCR chọn '%s' (score %.1f)", att.name, att.score)
    conf = att.ocr.mean_conf
    if p.ocr_status == "DONE" and 0 < conf < LOW_CONF:
        p.warnings.append(f"Độ tin cậy OCR thấp (~{conf:.0f}%): hãy đối chiếu kỹ các số với ảnh hóa đơn")
    return p, att.ocr


def read_receipt(image_path: str, timeout: float | None = None) -> tuple[ParsedReceipt, OcrResult]:
    """Ảnh -> (ParsedReceipt, OcrResult) tốt nhất tìm được. Ném OcrTimeout/OcrError/ImageError khi thất bại.

    Có timeout cứng (OCR_TIMEOUT_SEC); ngân sách thử thêm lượt mới chỉ bằng BUDGET_RATIO của nó để
    thường trả kết quả tốt nhất-đến-lúc-đó thay vì quá hạn và bỏ hết.
    """
    total = settings.OCR_TIMEOUT_SEC if timeout is None else timeout
    return _run_with_timeout(partial(_read, budget=total * BUDGET_RATIO), image_path, total)


__all__ = ["read_receipt", "score", "is_good", "ImageError", "OcrError"]
