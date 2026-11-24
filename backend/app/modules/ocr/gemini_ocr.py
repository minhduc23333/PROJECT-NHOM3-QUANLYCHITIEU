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
_MAX_MODELS_TRIED = 6          # số model tối đa thử cho 1 lượt đọc
<<<<<<< HEAD
_MAX_AUDIT_ROUNDS = 1          # tối đa 1 lượt tự kiểm toán lại khi số tiền chưa khớp (tránh treo lâu)
_MAX_IMAGE_SIDE = 1800         # đủ nét cho chữ nhỏ trên hóa đơn nhưng upload & xử lý nhanh hơn nhiều
_JPEG_QUALITY = 85


def _per_call_timeout() -> float:
    return max(8.0, float(settings.GEMINI_CALL_TIMEOUT_SEC))


def _normalize_model_name(name: str) -> str:
    """Chuẩn hóa model ID đọc từ cấu hình .env; ví dụ 'gemini 3.5-flash' -> 'gemini-3.5-flash'."""
    normalized = (name or "").strip().removeprefix("models/")
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"^gemini(?=[0-9])", "gemini-", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def _configured_models(primary: str) -> list[str]:
    names = [primary] + [
        name.strip()
        for name in (settings.GEMINI_FALLBACK_MODELS or "").split(",")
        if name.strip()
    ]
    result: list[str] = []
    for name in names:
        normalized = _normalize_model_name(name)
        if normalized and normalized not in result:
            result.append(normalized)
    return result
=======
_MAX_AUDIT_ROUNDS = 2          # số lượt tự kiểm toán lại khi số tiền chưa khớp
_MAX_IMAGE_SIDE = 2600         # giữ ảnh thật nét (hóa đơn cầm tay/nhàu/chữ nhỏ) - ưu tiên chính xác hơn tốc độ
_JPEG_QUALITY = 92


def _per_call_timeout() -> float:
    return max(20.0, float(settings.GEMINI_CALL_TIMEOUT_SEC))
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6


def _total_budget() -> float:
    return max(_per_call_timeout(), float(settings.GEMINI_TOTAL_BUDGET_SEC))
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
    discount_amount: float | None = None
    total_amount: float | None = None


_PROMPT = """Bạn là chuyên gia kiểm toán và trích xuất dữ liệu hóa đơn bán lẻ Việt Nam.
ƯU TIÊN TUYỆT ĐỐI: CHÍNH XÁC 100% VỀ SỐ TIỀN VÀ SỐ LƯỢNG (tên món có thể hơi rút gọn nhưng KHÔNG ĐƯỢC SAI TIỀN).

Hãy đọc ảnh hóa đơn THẬT KỸ, từng dòng từ trên xuống dưới (ảnh có thể bị nghiêng, nhàu, cầm tay, chụp mờ, chữ nhỏ, có thể là bill nhiệt hoặc bảng viết tay). Đếm số dòng món trong ảnh và đảm bảo KHÔNG bỏ sót dòng nào (hóa đơn dài 18-30 món vẫn phải đủ hết). Dòng cuối cùng thường là tổng tiền thanh toán: đối chiếu nó với tổng các món.
Trả về JSON đúng cấu trúc:
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
   - Nếu hóa đơn ghi gộp kiểu "Buffet Người Lớn  6  139,000  834,000" thì đó là MỘT món: quantity=6, unit_price=139000, line_total=834000.
   - Tên món phải chép đúng như trên hóa đơn (giữ tiếng Việt có dấu), không tự dịch, không viết tắt, không bịa tên khác.
   - Ngày in có thể ghi "Ngày in: 29/03/2019" hoặc "Time in: 10-12-2024" -> luôn đọc theo thứ tự NGÀY-THÁNG-NĂM của hóa đơn rồi đổi sang YYYY-MM-DD. Nếu hóa đơn có cả ngày in lẫn ngày giờ khác thì ưu tiên ngày in/ngày thanh toán.
4. subtotal: Tạm tính / Tổng tiền hàng trước thuế & phí dịch vụ (bằng VND). Nếu hóa đơn không tách riêng tạm tính và không có thuế/phí thì để null.
5. tax_amount: SỐ TIỀN thuế VAT bằng VND (KHÔNG lấy số phần trăm như 8 hay 10! Nếu không có tiền VAT thì null).
6. service_fee: SỐ TIỀN phí dịch vụ bằng VND (KHÔNG lấy số phần trăm như 5! Nếu không có thì null).
7. discount_amount: SỐ TIỀN giảm giá, chiết khấu, voucher HOẶC phần làm tròn giảm xuống (số DƯƠNG bằng VND).
   - Ví dụ hóa đơn có "Tổng tiền hàng: 242,641" và "Thanh toán (Đã làm tròn): 242,000" => subtotal=242641, discount_amount=641, total_amount=242000.
   - Nếu không có giảm giá/làm tròn thì null.
8. total_amount: Tổng tiền THỰC TRẢ cuối cùng (sau thuế, phí và đã trừ giảm giá/làm tròn) bằng VND.
   - Nếu hóa đơn có SubTotal/Total trước thuế (VD: 834,000), VAT 8% (66,720) và Payment Amount (900,720): thì subtotal=834000, tax_amount=66720, discount_amount=null, total_amount=900720.
   - Nếu hóa đơn có cả dòng "Tổng tiền hàng: 242,641" và "Thanh toán (Đã làm tròn): 242,000": lấy total_amount=242000 (số thực trả), subtotal=242641 và discount_amount=641.
   - Nếu hóa đơn có tạm tính trước thuế (VD: 160,909) + thuế VAT (VD: 13,091) nhưng tổng thanh toán cuối cùng (VD: 174,000) bằng đúng tổng các món (VD: 159,000 + 15,000 = 174,000) vì giá món đã bao gồm thuế: đặt subtotal = tổng các món (174000), tax_amount = 0, và total_amount = tổng thực trả cuối cùng (174000).
   - Tự cộng nhẩm: tổng(line_total của tất cả items) + tax_amount + service_fee - discount_amount PHẢI khớp với total_amount.

Tuyệt đối không tự bịa số liệu nếu ảnh không hiển thị.

CHỈ TRẢ VỀ ĐÚNG 1 OBJECT JSON DUY NHẤT (không markdown, không giải thích) theo mẫu:
{"merchant_name": "...", "receipt_date": "YYYY-MM-DD", "items": [{"item_name": "...", "quantity": 1, "unit_price": 50000, "line_total": 50000}], "subtotal": 50000, "tax_amount": null, "service_fee": null, "discount_amount": null, "total_amount": 50000}"""


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
            "403", "PERMISSION_DENIED",
        )
    )


def _discover_fallbacks(client, primary: str) -> list[str]:
    """Lấy danh sách các model Gemini khác hỗ trợ generateContent từ API key hiện tại."""
    global _CACHED_FALLBACKS
    if _CACHED_FALLBACKS is not None:
        return [m for m in _CACHED_FALLBACKS if m != primary]

    candidates: list[str] = []
    try:
        models_iter = _GEMINI_POOL.submit(lambda: list(client.models.list())).result(timeout=15.0)
        for m in models_iter:
            name = (getattr(m, "name", "") or "").removeprefix("models/")
            low = name.lower()
            if not low.startswith("gemini-"):
                continue
            if "flash" not in low and "pro" not in low and "argon" not in low and "carbon" not in low:
                continue
            if "lite" in low or any(k in low for k in _SKIP_MODEL_KEYWORDS):
                continue
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None)
            if actions and "generateContent" not in actions:
                continue
            candidates.append(name)
    except Exception as exc:
        log.warning("Không lấy được danh sách model dự phòng: %s", exc)
        return []

<<<<<<< HEAD
    candidates = [_normalize_model_name(name) for name in candidates]
    candidates = [
        name for name in dict.fromkeys(candidates)
        if name != _normalize_model_name(primary)
        and not any(k in name for k in ("preview", "exp-", "omni-", "carbon", "argon"))
    ]
    candidates.sort(
        key=lambda name: (
            "lite" not in name.lower(),
            "flash" not in name.lower(),
            name,
        ),
        reverse=True,
    )
=======
    candidates.sort(reverse=True)          # bản mới (số lớn) lên trước
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6
    _CACHED_FALLBACKS = candidates[:5]
    return [m for m in _CACHED_FALLBACKS if m != primary]


def _prepare_image_bytes(path: Path) -> tuple[bytes, str]:
    """Chỉ thu gọn ảnh cực lớn (> _MAX_IMAGE_SIDE px) để vừa giới hạn upload; ảnh thường gửi nguyên bản cho nét nhất."""
    raw = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    try:
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            h, w = img.shape[:2]
            if max(h, w) > _MAX_IMAGE_SIDE:
                scale = _MAX_IMAGE_SIDE / max(h, w)
                img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
                if ok:
                    return enc.tobytes(), "image/jpeg"
    except Exception:
        pass
    return raw, mime


def _make_client(genai, types):
<<<<<<< HEAD
    timeout_ms = int(_per_call_timeout() * 1000)
    try:
        return genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
=======
    try:
        return genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=int(_per_call_timeout() * 1000)),
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6
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
    client, types, model_name: str, img_bytes: bytes, mime: str, prompt: str, timeout: float | None = None
) -> _GeminiReceipt:
    timeout = _per_call_timeout() if timeout is None else timeout
    def _do():
        contents = [types.Part.from_bytes(data=img_bytes, mime_type=mime), prompt]
        thinking_cls = getattr(types, "ThinkingConfig", None)
<<<<<<< HEAD
        afc_cls = getattr(types, "AutomaticFunctionCallingConfig", None)
=======
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6

        configs: list[tuple[bool, dict]] = []
        if model_name not in _PLAIN_JSON_MODELS:
            base: dict = {
                "response_mime_type": "application/json",
                "response_schema": _GeminiReceipt,
                "temperature": 0.0,
            }
            level = (settings.GEMINI_THINKING_LEVEL or "").strip().lower()
            if thinking_cls is not None and level in ("low", "medium", "high") and "lite" not in model_name.lower():
                # Cho model "suy nghĩ" kỹ để đọc đúng từng chữ số. Model/SDK không hỗ trợ -> tự rơi xuống cấu hình sau.
                try:
                    configs.append((False, {**base, "thinking_config": thinking_cls(thinking_level=level)}))
                except Exception:
                    pass
            configs.append((False, base))
        # Dự phòng khi model trên endpoint /v1/ không hỗ trợ response_schema hoặc response_mime_type
        configs.append((True, {"response_mime_type": "application/json", "temperature": 0.0}))
        configs.append((True, {"temperature": 0.0}))

        last_err: Exception | None = None
        for is_plain, cfg_kwargs in configs:
            try:
<<<<<<< HEAD
                call_cfg = dict(cfg_kwargs)
                if afc_cls is not None:
                    call_cfg["automatic_function_calling"] = afc_cls(disable=True)
                resp = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**call_cfg),
=======
                resp = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**cfg_kwargs),
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6
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
    discount = _dec(data.discount_amount)
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

    # Hóa đơn đã gộp VAT vào giá món (VD: tổng món 174.000 = tổng trả 174.000, nhưng bill có in tạm tính trước thuế + VAT)
    if items and total is not None and subtotal is not None and (tax or 0) > 0:
        fees_with_tax = (tax or Decimal(0)) + (fee or Decimal(0))
        disc = discount or Decimal(0)
        if (
            abs(items_sum - total) <= ROUNDING_TOLERANCE
            and abs(subtotal + fees_with_tax - disc - total) <= ROUNDING_TOLERANCE
            and items_sum > subtotal
        ):
            subtotal = items_sum
            tax = Decimal(0)

    # Nếu không có subtotal nhưng có items + total + fees/discount khớp trong ngưỡng làm tròn, điền subtotal = items_sum
    if items and total is not None and subtotal is None:
        fees = (tax or Decimal(0)) + (fee or Decimal(0))
        disc = discount or Decimal(0)
        if abs(items_sum + fees - disc - total) <= ROUNDING_TOLERANCE:
            subtotal = items_sum

    parsed = ParsedReceipt(
        merchant_name=data.merchant_name.strip()[:255] if data.merchant_name else None,
        receipt_date=parsed_date,
        items=items,
        subtotal=subtotal,
        tax_amount=tax,
        service_fee=fee,
        discount_amount=discount,
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
            disc = parsed.discount_amount or Decimal(0)
            if parsed.subtotal is None and abs(s + fees - disc - parsed.total_amount) > ROUNDING_TOLERANCE:
                parsed.warnings.append(
                    f"Tổng các dòng món + thuế + phí - giảm giá ({s + fees - disc}) khác tổng thanh toán ({parsed.total_amount}): cần kiểm tra"
                )
            elif parsed.subtotal is not None:
                expected = parsed.subtotal + fees - disc
                if abs(expected - parsed.total_amount) > ROUNDING_TOLERANCE:
                    parsed.warnings.append(
                        f"Tổng thanh toán ({parsed.total_amount}) khác tạm tính + VAT + phí - giảm giá ({expected})"
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
        disc = parsed.discount_amount or Decimal(0)
        if parsed.subtotal is not None and abs(items_sum - parsed.subtotal) > ROUNDING_TOLERANCE:
            issues.append(f"Tổng các dòng món ({items_sum}) khác tạm tính ({parsed.subtotal}).")
        diff = abs(items_sum + fees - disc - parsed.total_amount)
        if diff > ROUNDING_TOLERANCE:
            issues.append(
                f"Tổng các món ({items_sum}) + thuế/phí ({fees}) - giảm giá ({disc}) = {items_sum + fees - disc}, "
                f"khác tổng hóa đơn ({parsed.total_amount}), lệch {diff} đồng."
            )
    return issues


def _accuracy_rank(parsed: ParsedReceipt) -> tuple:
    """Xếp hạng kết quả theo độ chuẩn xác về TIỀN (cao hơn = tốt hơn)."""
    if parsed.ocr_status != "DONE":
        return (0, 0, 0, 0, 0, 0)
    items_sum = sum((i.line_total for i in parsed.items), Decimal(0))
    fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))
    disc = parsed.discount_amount or Decimal(0)
    has_total = 1 if (parsed.total_amount is not None and parsed.total_amount > 0) else 0
    bad_items = sum(1 for i in parsed.items if _item_mismatch(i) > max(Decimal(5), i.line_total * Decimal("0.005")))
    if has_total and parsed.items:
        diff = abs(items_sum + fees - disc - parsed.total_amount)
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
<<<<<<< HEAD
    primary = _normalize_model_name(settings.GEMINI_MODEL)
    last_exc: Exception | None = None

    # Thứ tự: model đã chạy tốt gần nhất -> model hợp lệ dò được từ API key -> cấu hình trong .env.
    configured = _configured_models(primary)
    discovered = _discover_fallbacks(client, primary)
    ordered: list[str] = []
    if _LAST_GOOD_MODEL and _UNHEALTHY_UNTIL.get(_LAST_GOOD_MODEL, 0) <= now:
        ordered.append(_LAST_GOOD_MODEL)
    for m in discovered:
        if _UNHEALTHY_UNTIL.get(m, 0) <= now and m not in ordered:
            ordered.append(m)
    for m in configured:
        if _UNHEALTHY_UNTIL.get(m, 0) <= now and m not in ordered:
            ordered.append(m)
=======
    primary = settings.GEMINI_MODEL
    last_exc: Exception | None = None

    # Thứ tự: model đã chạy tốt gần nhất -> GEMINI_MODEL -> GEMINI_FALLBACK_MODELS -> model tự dò từ API key.
    configured = [primary] + [m.strip() for m in (settings.GEMINI_FALLBACK_MODELS or "").split(",") if m.strip()]
    ordered: list[str] = []
    if _LAST_GOOD_MODEL and _UNHEALTHY_UNTIL.get(_LAST_GOOD_MODEL, 0) <= now and _LAST_GOOD_MODEL in configured:
        ordered.append(_LAST_GOOD_MODEL)
    for m in configured:
        if _UNHEALTHY_UNTIL.get(m, 0) <= now and m not in ordered:
            ordered.append(m)
    if len(ordered) < 3:
        for m in _discover_fallbacks(client, primary):
            if _UNHEALTHY_UNTIL.get(m, 0) <= now and m not in ordered:
                ordered.append(m)
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6
    if not ordered:
        ordered.append(primary)
    ordered = ordered[:_MAX_MODELS_TRIED]

    for model_name in ordered:
        rem = deadline - time.monotonic()
        if rem < 5.0:
            break
        try:
            data = _call_model(client, types, model_name, img_bytes, mime, prompt, timeout=min(_per_call_timeout(), rem))
            _UNHEALTHY_UNTIL.pop(model_name, None)
            _LAST_GOOD_MODEL = model_name
            log.info("Gemini OCR thành công với model '%s'", model_name)
            return data, model_name
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                raise OcrError(f"Lỗi gọi Gemini API: {exc}") from exc
            msg = str(exc).upper()
            if "404" in msg or "NOT_FOUND" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
                _UNHEALTHY_UNTIL[model_name] = time.monotonic() + 3600.0   # key không có quyền / model chưa tồn tại
            else:
                _UNHEALTHY_UNTIL[model_name] = time.monotonic() + _COOLDOWN_SEC
            log.warning("Model '%s' không khả dụng (%s) -> chuyển nhanh model dự phòng", model_name, exc)

    raise OcrError(
        f"Gemini không đọc được hóa đơn (đã thử {', '.join(ordered)}): {last_exc}. "
        "Kiểm tra GEMINI_API_KEY, quyền dùng model và kết nối mạng trong backend/.env"
    ) from last_exc


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

    deadline = time.monotonic() + _total_budget()
    img_bytes, mime = _prepare_image_bytes(path)
    client = _make_client(genai, types)

    # Lượt 1: Đọc cấu trúc hóa đơn
    data1, used_model = _invoke_with_fallback(client, types, img_bytes, mime, _PROMPT, deadline)
    parsed1 = _to_parsed(data1)

    # Tự kiểm toán: nếu số tiền chưa khớp thì cho model soi lại (tối đa _MAX_AUDIT_ROUNDS lượt) rồi chọn kết quả khớp nhất.
    best_data, best_parsed = data1, parsed1
    for round_no in range(_MAX_AUDIT_ROUNDS):
        issues = _audit_issues(best_parsed)
        rem = deadline - time.monotonic()
        if not issues or rem < 10.0:
            break
        log.warning(
            "Gemini (%s) lệch tiền (%s) -> lượt tự kiểm toán %d/%d", used_model, "; ".join(issues), round_no + 1, _MAX_AUDIT_ROUNDS
        )
        audit_prompt = (
            f"{_PROMPT}\n\n"
            f"CẢNH BÁO KIỂM TOÁN TỪ LƯỢT ĐỌC TRƯỚC:\n"
            f"JSON lượt trước: {json.dumps(best_data.model_dump(), ensure_ascii=False)}\n"
            "Các lỗi sai số tiền phát hiện được:\n- "
            + "\n- ".join(issues)
            + "\nHãy soi thật kỹ từng chữ số trên ảnh (đặc biệt số 1/4/7, 0/6/8/9, giá gạch ngang, "
            "món bị sót hoặc dòng tổng bị nhầm thành món) và trả về JSON đã sửa CHÍNH XÁC 100%."
        )
        try:
            data2 = _call_model(client, types, used_model, img_bytes, mime, audit_prompt, timeout=min(_per_call_timeout(), rem))
            parsed2 = _to_parsed(data2)
            if _accuracy_rank(parsed2) > _accuracy_rank(best_parsed):
                log.info("Gemini lượt kiểm toán %d cải thiện độ chính xác số tiền -> chọn kết quả mới", round_no + 1)
                best_data, best_parsed = data2, parsed2
        except Exception as exc:
            log.warning("Gemini lượt kiểm toán lỗi (%s), giữ kết quả tốt nhất hiện có", exc)
            break

    return best_parsed, OcrResult(lines=[json.dumps(best_data.model_dump(), ensure_ascii=False)])
