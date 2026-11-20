"""Đọc hóa đơn bằng Gemini Vision API (Structured JSON Output + tự đối chiếu số tiền + fallback model)."""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel

from app.core.config import settings
from app.modules.ocr.engine import OcrError, OcrResult
from app.modules.ocr.parser import ROUNDING_TOLERANCE, ParsedItem, ParsedReceipt

log = logging.getLogger(__name__)

_SKIP_MODEL_KEYWORDS = (
    "embedding",
    "imagen",
    "veo",
    "tts",
    "audio",
    "live",
    "aqa",
    "robotics",
    "deep-research",
    "computer-use",
)
_CACHED_FALLBACKS: list[str] | None = None
_UNHEALTHY_UNTIL: dict[str, float] = {}
_PLAIN_JSON_MODELS: set[str] = set()
_LAST_GOOD_MODEL: str | None = None
_COOLDOWN_SEC = 90.0
_PER_CALL_TIMEOUT_SEC = 14.0   # tối đa 14s cho 1 lượt (đủ cho hóa đơn 20+ món)
_TOTAL_BUDGET_SEC = 28.0       # tổng ngân sách tối đa cho toàn bộ AI OCR
_MAX_IMAGE_SIDE = 1400         # ảnh rõ hơn cho bill cầm tay/nhàu nhưng vẫn nhẹ
_GEMINI_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini-ocr")

_BAD_ITEM_KEYWORDS = (
    "tong cong",
    "tong tien",
    "tong thanh toan",
    "tam tinh",
    "cong tien hang",
    "da bao gom giam gia",
    "bao gom giam gia",
    "da lam tron",
    "tien mat",
    "khach dua",
    "tien thua",
    "tien thoi",
    "tra lai",
    "chiet khau",
    "khuyen mai",
    "giam gia",
    "grand total",
    "subtotal",
    "sub total",
    "payment amount",
    "return amount",
    "cash",
)


class _GeminiItem(BaseModel):
    item_name: str
    quantity: float = 1
    unit_price: float
    line_total: float


class _GeminiReceipt(BaseModel):
    merchant_name: str | None = None
    receipt_date: str | None = None  # YYYY-MM-DD
    items: list[_GeminiItem] = []
    subtotal: float | None = None
    tax_amount: float | None = None
    service_fee: float | None = None
    total_amount: float | None = None


_PROMPT = """Bạn là chuyên gia kiểm toán và trích xuất dữ liệu hóa đơn bán lẻ Việt Nam.
ƯU TIÊN TUYỆT ĐỐI: CHÍNH XÁC 100% VỀ SỐ TIỀN VÀ SỐ LƯỢNG (tên món có thể hơi rút gọn nhưng KHÔNG ĐƯỢC SAI TIỀN).

Hãy đọc ảnh hóa đơn và trả về JSON đúng cấu trúc:
1. merchant_name: Tên cửa hàng/quán ăn (tiếng Việt có dấu).
2. receipt_date: Ngày in trên hóa đơn theo định dạng YYYY-MM-DD. Chú ý hóa đơn Việt Nam ghi NGÀY/THÁNG/NĂM (DD/MM/YYYY), ví dụ 10/09/2022 -> "2022-09-10". Không rõ thì null.
3. items: CHỈ liệt kê các món hàng/dịch vụ thực sự mua:
   - TUYỆT ĐỐI KHÔNG đưa các dòng tổng kết vào items: Tổng cộng, Tổng tiền hàng, Tạm tính, SubTotal, Total, Payment Amount, Cash, Return Amount, VAT/Thuế, Phí dịch vụ, Giảm giá, Chiết khấu, "(Đã bao gồm giảm giá)", "(Đã làm tròn)", Tiền khách đưa, Tiền mặt, Tiền thừa/Tiền thối, Chuyển khoản.
   - Nếu một món có giá gốc bị gạch ngang và giá giảm bên cạnh (VD: 60,000 gạch ngang, 49,005), CHỈ lấy giá bán thực tế (49005).
   - Chú ý phân biệt dấu phân cách:
     + Tiền VND có thể dùng dấu chấm, phẩy HOẶC KHOẢNG TRẮNG cho hàng nghìn: 113,000 / 113.000 => 113000; 2 160 000 => 2160000; 35 400 000 => 35400000; 50 662 000 => 50662000 (KHÔNG bỏ sót chữ số hàng triệu ở đầu!).
     + Số lượng cân nặng (kg) dùng dấu chấm/phẩy thập phân: 0.49, 1.264, 3,0, 7,2, 12, => 0.49, 1.264, 3, 7.2, 12.
   - Nhìn thật kỹ các chữ số dễ nhầm trên giấy in nhiệt: 1 vs 4 vs 7, 0 vs 6 vs 8 vs 9, 3 vs 8, 5 vs 6.
   - Tự kiểm tra từng dòng: quantity * unit_price phải khớp line_total (cho phép lệch 1-5 đồng do siêu thị làm tròn cân nặng).
4. subtotal: Tạm tính / Tổng tiền hàng trước thuế & phí dịch vụ (bằng VND). Nếu hóa đơn không tách riêng tạm tính và không có thuế/phí thì để null.
5. tax_amount: SỐ TIỀN thuế VAT bằng VND (KHÔNG lấy số phần trăm như 8 hay 10! Nếu không có tiền VAT thì null).
6. service_fee: SỐ TIỀN phí dịch vụ bằng VND (KHÔNG lấy số phần trăm như 5! Nếu không có thì null).
7. total_amount: Tổng tiền thanh toán cuối cùng SAU THUẾ/PHÍ bằng VND.
   - Nếu hóa đơn có SubTotal/Total trước thuế (VD: 834,000), VAT 8% (66,720) và Payment Amount (900,720): thì subtotal=834000, tax_amount=66720, total_amount=900720.
   - Nếu hóa đơn có cả dòng tổng chính xác (VD: "(Đã bao gồm giảm giá) 242,641") và dòng làm tròn tiền mặt ("(Đã làm tròn) 242,000"), ưu tiên số khớp với tổng các món (242641).
   - Tự cộng nhẩm: tổng(line_total của tất cả items) + tax_amount + service_fee PHẢI khớp với total_amount.

Tuyệt đối không tự bịa số liệu nếu ảnh không hiển thị.

CHỈ TRẢ VỀ ĐÚNG 1 OBJECT JSON DUY NHẤT (không markdown, không giải thích) theo mẫu:
{"merchant_name": "...", "receipt_date": "YYYY-MM-DD", "items": [{"item_name": "...", "quantity": 1, "unit_price": 50000, "line_total": 50000}], "subtotal": 50000, "tax_amount": null, "service_fee": null, "total_amount": 50000}"""


def _fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _dec(v: float | int | None) -> Decimal | None:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        if not d.is_finite() or d < 0:
            return None
        return d.quantize(Decimal(1)) if d == d.to_integral_value() else d.normalize()
    except InvalidOperation:
        return None


def _is_summary_item(name: str) -> bool:
    f = re.sub(r"\s+", " ", _fold(name)).strip(" :.-")
    return f in ("total", "sub total", "subtotal", "vat", "tax") or any(k in f for k in _BAD_ITEM_KEYWORDS)


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).upper()
    return any(
        code in msg
        for code in (
            "503", "UNAVAILABLE", "504", "DEADLINE_EXCEEDED", "TIMEOUT",
            "500", "INTERNAL", "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "400", "INVALID_ARGUMENT",
        )
    )


def _discover_fallbacks(client, primary: str) -> list[str]:
    """Lấy danh sách các model Gemini khác hỗ trợ generateContent từ API key hiện tại."""
    global _CACHED_FALLBACKS
    if _CACHED_FALLBACKS is not None:
        return [m for m in _CACHED_FALLBACKS if m != primary]

    candidates: list[str] = []
    try:
        models_iter = _GEMINI_POOL.submit(lambda: list(client.models.list())).result(timeout=4.0)
        for m in models_iter:
            name = (getattr(m, "name", "") or "").removeprefix("models/")
            low = name.lower()
            if not low.startswith("gemini-"):
                continue
            if "flash" not in low:
                continue
            if any(k in low for k in _SKIP_MODEL_KEYWORDS):
                continue
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None)
            if actions and "generateContent" not in actions:
                continue
            candidates.append(name)
    except Exception as exc:
        log.warning("Không lấy được danh sách model dự phòng: %s", exc)
        return []

    def _priority(name: str) -> tuple[int, str]:
        low = name.lower()
        return (0 if ("flash-lite" in low or "lite" in low) else 1, "")

    candidates.sort(reverse=True)
    candidates.sort(key=_priority)
    _CACHED_FALLBACKS = candidates[:5]
    return [m for m in _CACHED_FALLBACKS if m != primary]


def _prepare_image_bytes(path: Path) -> tuple[bytes, str]:
    """Thu gọn ảnh quá lớn về <= 1280px (JPEG q=85) để gửi Gemini nhanh (~2-4s) mà chữ vẫn sắc nét."""
    raw = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    try:
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            h, w = img.shape[:2]
            if max(h, w) > _MAX_IMAGE_SIDE or len(raw) > 400_000:
                scale = min(1.0, _MAX_IMAGE_SIDE / max(h, w))
                if scale < 1.0:
                    img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ok:
                    return enc.tobytes(), "image/jpeg"
    except Exception:
        pass
    return raw, mime


def _make_client(genai, types):
    try:
        return genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=int(_PER_CALL_TIMEOUT_SEC * 1000)),
        )
    except Exception:
        return genai.Client(api_key=settings.GEMINI_API_KEY)


def _extract_json_text(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s or "{}"


def _call_model(
    client, types, model_name: str, img_bytes: bytes, mime: str, prompt: str, timeout: float = _PER_CALL_TIMEOUT_SEC
) -> _GeminiReceipt:
    def _do():
        contents = [types.Part.from_bytes(data=img_bytes, mime_type=mime), prompt]
        thinking_cls = getattr(types, "ThinkingConfig", None)

        configs: list[tuple[bool, dict]] = []
        if model_name not in _PLAIN_JSON_MODELS:
            c1: dict = {
                "response_mime_type": "application/json",
                "response_schema": _GeminiReceipt,
                "temperature": 0.0,
            }
            if thinking_cls is not None and "lite" not in model_name.lower():
                try:
                    c1["thinking_config"] = thinking_cls(thinking_budget=0)
                except Exception:
                    pass
            configs.append((False, c1))
        # Dự phòng khi model trên endpoint /v1/ không hỗ trợ response_schema hoặc response_mime_type
        configs.append((True, {"response_mime_type": "application/json", "temperature": 0.0}))
        configs.append((True, {"temperature": 0.0}))

        last_err: Exception | None = None
        for is_plain, cfg_kwargs in configs:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )
                if is_plain:
                    _PLAIN_JSON_MODELS.add(model_name)
                raw_json = _extract_json_text(resp.text or "{}")
                return _GeminiReceipt.model_validate_json(raw_json)
            except Exception as exc:
                last_err = exc
                err_up = str(exc).upper()
                if "400" in err_up or "INVALID_ARGUMENT" in err_up:
                    continue
                raise
        raise last_err or OcrError(f"Model '{model_name}' từ chối cấu hình JSON")

    fut = _GEMINI_POOL.submit(_do)
    try:
        return fut.result(timeout=max(2.0, timeout))
    except FutureTimeout as exc:
        fut.cancel()
        raise OcrError(f"503 TIMEOUT: Model '{model_name}' phản hồi quá {timeout:.0f}s") from exc


def _to_parsed(data: _GeminiReceipt) -> ParsedReceipt:
    parsed_date = None
    if data.receipt_date:
        try:
            parsed_date = date.fromisoformat(data.receipt_date[:10])
        except ValueError:
            parsed_date = None

    items: list[ParsedItem] = []
    for it in data.items:
        name = (it.item_name or "").strip()[:255]
        if not name or _is_summary_item(name):
            continue
        q = _dec(it.quantity)
        u = _dec(it.unit_price)
        t = _dec(it.line_total)
        if q is None or q <= 0:
            q = Decimal(1)
        if u is None and t is not None and q > 0:
            u = (t / q).quantize(Decimal("0.01"))
        if t is None and u is not None:
            t = (q * u).quantize(Decimal("0.01"))
        if u is not None and t is not None and t > 0:
            items.append(ParsedItem(name, q, u, t))

    subtotal = _dec(data.subtotal)
    tax = _dec(data.tax_amount)
    fee = _dec(data.service_fee)
    total = _dec(data.total_amount)

    # Chặn lỗi nhận nhầm phần trăm (8%, 10%, 5%) thành tiền VND (8đ, 10đ, 5đ)
    items_sum = sum((i.line_total for i in items), Decimal(0))
    if tax is not None and 0 < tax < Decimal(100):
        base = subtotal if subtotal is not None else items_sum
        if total is None or abs((base + tax + (fee or 0)) - total) >= abs((base + (fee or 0)) - total):
            tax = None
    if fee is not None and 0 < fee < Decimal(100):
        base = subtotal if subtotal is not None else items_sum
        if total is None or abs((base + (tax or 0) + fee) - total) >= abs((base + (tax or 0)) - total):
            fee = None

    parsed = ParsedReceipt(
        merchant_name=data.merchant_name.strip()[:255] if data.merchant_name else None,
        receipt_date=parsed_date,
        items=items,
        subtotal=subtotal,
        tax_amount=tax,
        service_fee=fee,
        total_amount=total,
    )
    _attach_warnings(parsed)
    return parsed


def _item_mismatch(item: ParsedItem) -> Decimal:
    return abs(item.quantity * item.unit_price - item.line_total)


def _attach_warnings(parsed: ParsedReceipt) -> None:
    parsed.warnings = []
    for i in parsed.items:
        tol = max(Decimal(5), i.line_total * Decimal("0.005"))
        if _item_mismatch(i) > tol:
            parsed.warnings.append(
                f"Dòng '{i.item_name}': {i.quantity} × {i.unit_price} ≠ {i.line_total}, cần kiểm tra"
            )
    if parsed.items:
        s = sum((i.line_total for i in parsed.items), Decimal(0))
        if parsed.subtotal is not None and abs(s - parsed.subtotal) > ROUNDING_TOLERANCE:
            parsed.warnings.append(f"Tổng các dòng món ({s}) khác tạm tính ({parsed.subtotal})")
        if parsed.total_amount is not None:
            fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
            if parsed.subtotal is None and abs(s + fees - parsed.total_amount) > ROUNDING_TOLERANCE:
                parsed.warnings.append(
                    f"Tổng các dòng món + thuế + phí ({s + fees}) khác tổng thanh toán ({parsed.total_amount}): cần kiểm tra"
                )
            elif parsed.subtotal is not None:
                expected = parsed.subtotal + fees
                if abs(expected - parsed.total_amount) > ROUNDING_TOLERANCE:
                    parsed.warnings.append(
                        f"Tổng thanh toán ({parsed.total_amount}) khác tạm tính + VAT + phí ({expected})"
                    )


def _audit_issues(parsed: ParsedReceipt) -> list[str]:
    """Liệt kê các lỗi số tiền nghiêm trọng để AI tự kiểm toán lại ở lượt 2."""
    issues: list[str] = []
    if not parsed.items:
        issues.append("Chưa đọc được dòng món hàng nào.")
    if parsed.total_amount is None or parsed.total_amount <= 0:
        issues.append("Chưa đọc được tổng tiền thanh toán (total_amount).")
    for i in parsed.items:
        if _item_mismatch(i) > max(Decimal(50), i.line_total * Decimal("0.02")):
            issues.append(
                f"Món '{i.item_name}' lệch toán học: SL {i.quantity} × đơn giá {i.unit_price} ≠ thành tiền {i.line_total}."
            )
    if parsed.items and parsed.total_amount is not None:
        items_sum = sum((i.line_total for i in parsed.items), Decimal(0))
        fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
        if parsed.subtotal is not None and abs(items_sum - parsed.subtotal) > ROUNDING_TOLERANCE:
            issues.append(f"Tổng các dòng món ({items_sum}) khác tạm tính ({parsed.subtotal}).")
        diff = abs(items_sum + fees - parsed.total_amount)
        if diff > ROUNDING_TOLERANCE:
            issues.append(
                f"Tổng các món ({items_sum}) + thuế/phí ({fees}) = {items_sum + fees}, "
                f"khác tổng hóa đơn ({parsed.total_amount}), lệch {diff} đồng."
            )
    return issues


def _accuracy_rank(parsed: ParsedReceipt) -> tuple:
    """Xếp hạng kết quả theo độ chuẩn xác về TIỀN (cao hơn = tốt hơn)."""
    if parsed.ocr_status != "DONE":
        return (0, 0, 0, 0, 0, 0)
    items_sum = sum((i.line_total for i in parsed.items), Decimal(0))
    fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
    has_total = 1 if (parsed.total_amount is not None and parsed.total_amount > 0) else 0
    bad_items = sum(1 for i in parsed.items if _item_mismatch(i) > max(Decimal(5), i.line_total * Decimal("0.005")))
    if has_total and parsed.items:
        diff = abs(items_sum + fees - parsed.total_amount)
        exact = 1 if diff <= Decimal(5) else 0
        within_round = 1 if diff <= ROUNDING_TOLERANCE else 0
        rel_err = float(diff / parsed.total_amount)
    else:
        exact, within_round, rel_err = 0, 0, 1e9
    return (exact, within_round, -bad_items, -rel_err, has_total, len(parsed.items))


def _invoke_with_fallback(
    client, types, img_bytes: bytes, mime: str, prompt: str, deadline: float
) -> tuple[_GeminiReceipt, str]:
    global _LAST_GOOD_MODEL
    now = time.monotonic()
    primary = settings.GEMINI_MODEL
    last_exc: Exception | None = None

    ordered: list[str] = []
    if _LAST_GOOD_MODEL and _UNHEALTHY_UNTIL.get(_LAST_GOOD_MODEL, 0) <= now:
        ordered.append(_LAST_GOOD_MODEL)
    if _UNHEALTHY_UNTIL.get(primary, 0) <= now and primary not in ordered:
        ordered.append(primary)
    for m in _discover_fallbacks(client, primary):
        if _UNHEALTHY_UNTIL.get(m, 0) <= now and m not in ordered:
            ordered.append(m)
    if not ordered:
        ordered.append(primary)
    ordered = ordered[:4]

    for model_name in ordered:
        rem = deadline - time.monotonic()
        if rem < 2.5:
            break
        try:
            data = _call_model(client, types, model_name, img_bytes, mime, prompt, timeout=min(_PER_CALL_TIMEOUT_SEC, rem))
            _UNHEALTHY_UNTIL.pop(model_name, None)
            _LAST_GOOD_MODEL = model_name
            log.info("Gemini OCR thành công với model '%s'", model_name)
            return data, model_name
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                raise OcrError(f"Lỗi gọi Gemini API: {exc}") from exc
            msg = str(exc).upper()
            if "404" in msg or "NOT_FOUND" in msg:
                _UNHEALTHY_UNTIL[model_name] = time.monotonic() + 3600.0
            else:
                _UNHEALTHY_UNTIL[model_name] = time.monotonic() + _COOLDOWN_SEC
            log.warning("Model '%s' không khả dụng (%s) -> chuyển nhanh model dự phòng", model_name, exc)

    raise OcrError(f"Gemini AI đang bận/quá hạn: {last_exc}") from last_exc


def read_receipt_gemini(image_path: str) -> tuple[ParsedReceipt, OcrResult]:
    if not settings.GEMINI_API_KEY:
        raise OcrError("Thiếu GEMINI_API_KEY trong file backend/.env")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise OcrError("Chưa cài google-genai (pip install google-genai)") from exc

    path = Path(image_path)
    if not path.is_file():
        raise OcrError(f"Không tìm thấy file ảnh: {image_path}")

    deadline = time.monotonic() + _TOTAL_BUDGET_SEC
    img_bytes, mime = _prepare_image_bytes(path)
    client = _make_client(genai, types)

    # Lượt 1: Đọc cấu trúc hóa đơn
    data1, used_model = _invoke_with_fallback(client, types, img_bytes, mime, _PROMPT, deadline)
    parsed1 = _to_parsed(data1)

    # Lượt 2 (tự kiểm toán): CHỈ chạy nếu lệch tiền VÀ còn đủ thời gian (>= 6s)
    issues = _audit_issues(parsed1)
    rem = deadline - time.monotonic()
    if issues and rem >= 6.0:
        log.warning("Gemini lượt 1 (%s) lệch tiền (%s) -> chạy lượt 2 tự kiểm toán", used_model, "; ".join(issues))
        audit_prompt = (
            f"{_PROMPT}\n\n"
            f"CẢNH BÁO KIỂM TOÁN TỪ LƯỢT ĐỌC TRƯỚC:\n"
            f"JSON lượt trước: {json.dumps(data1.model_dump(), ensure_ascii=False)}\n"
            "Các lỗi sai số tiền phát hiện được:\n- "
            + "\n- ".join(issues)
            + "\nHãy soi thật kỹ từng chữ số trên ảnh (đặc biệt số 1/4/7, 0/6/8/9, giá gạch ngang, "
            "món bị sót hoặc dòng tổng bị nhầm thành món) và trả về JSON đã sửa CHÍNH XÁC 100%."
        )
        try:
            data2 = _call_model(client, types, used_model, img_bytes, mime, audit_prompt, timeout=min(8.0, rem))
            parsed2 = _to_parsed(data2)
            if _accuracy_rank(parsed2) > _accuracy_rank(parsed1):
                log.info("Gemini lượt 2 cải thiện độ chính xác số tiền -> chọn lượt 2")
                return parsed2, OcrResult(lines=[json.dumps(data2.model_dump(), ensure_ascii=False)])
        except Exception as exc:
            log.warning("Gemini lượt 2 lỗi (%s), giữ kết quả lượt 1", exc)

    return parsed1, OcrResult(lines=[json.dumps(data1.model_dump(), ensure_ascii=False)])
