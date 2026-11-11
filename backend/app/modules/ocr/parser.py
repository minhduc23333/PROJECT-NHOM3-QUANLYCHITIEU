"""Parser: text/dòng OCR thô -> dữ liệu hóa đơn có cấu trúc (task T05E170).

Hàm thuần, không phụ thuộc OCR engine/DB. Nguyên tắc BR-10: trường nào không
nhận ra thì để None, tuyệt đối không tự bịa số liệu.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

MIN_LINE_TOTAL = Decimal("1000")  # VND: giá món < 1.000đ gần như chắc chắn là số khác (số bàn, địa chỉ...)
MAX_MONEY = Decimal("999999999")  # lớn hơn thường là số điện thoại/mã số thuế, không phải tiền


@dataclass
class ParsedItem:
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass
class ParsedReceipt:
    merchant_name: str | None = None
    receipt_date: date | None = None
    items: list[ParsedItem] = field(default_factory=list)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    service_fee: Decimal | None = None
    total_amount: Decimal | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        """Các trường chưa nhận ra -> UI đánh dấu để người dùng nhập."""
        out = []
        if not self.merchant_name:
            out.append("merchant_name")
        if self.receipt_date is None:
            out.append("receipt_date")
        if not self.items:
            out.append("items")
        if self.subtotal is None:
            out.append("subtotal")
        if self.total_amount is None:
            out.append("total_amount")
        return out

    @property
    def ocr_status(self) -> str:
        """FAILED = không trích được gì dùng được -> chuyển nhập tay."""
        return "DONE" if (self.items or self.total_amount is not None) else "FAILED"


# ---------- chuẩn hóa chuỗi ----------

def fold(s: str) -> str:
    """Hạ chữ thường + bỏ dấu tiếng Việt để so khớp từ khóa chịu được OCR sai dấu."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


_MONEY_TOKEN = re.compile(r"(?<![\w])(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{1,2})?(?![\w])(?!\s*%)")


def parse_money(token: str) -> Decimal | None:
    """'1.250.000' / '125,000' / '35000' / '35.000đ' -> Decimal VND. Sai định dạng -> None."""
    t = re.sub(r"(?i)(vnđ|vnd|đ|d)$", "", token.strip().replace(" ", "")).strip()
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        value = Decimal(re.sub(r"[.,]", "", t))
    elif re.fullmatch(r"\d+", t):
        value = Decimal(t)
    elif re.fullmatch(r"\d+[.,]\d{1,2}", t):
        value = Decimal(t.replace(",", "."))
    else:
        return None
    return value if value <= MAX_MONEY else None


def money_tokens(line: str) -> list[tuple[int, Decimal]]:
    """[(vị trí, giá trị)] các số tiền trong dòng; bỏ số đi kèm dấu %."""
    out = []
    for m in _MONEY_TOKEN.finditer(line):
        v = parse_money(m.group(0))
        if v is not None:
            out.append((m.start(), v))
    return out


# ---------- phân loại dòng ----------

_SUMMARY_KEYS = [
    ("subtotal", ("tam tinh", "tong tien hang", "cong tien hang", "subtotal", "sub total", "sub-total")),
    ("tax", ("vat", "gtgt", "thue", "tax")),
    ("service", ("phi dich vu", "phi phuc vu", "phi pv", "service charge", "service fee", "service")),
    ("total", ("tong cong", "tong thanh toan", "tong tien", "tong so tien", "can thanh toan",
               "phai thanh toan", "thanh toan", "grand total", "total", "tong")),
]
_SKIP_KEYS = ("khach dua", "tien thua", "tra lai", "tien mat", "the ", "giam gia", "discount",
              "dt:", "d/c", "sdt", "tel", "hotline", "mst", "ma so thue", "dia chi", "address",
              "so hoa don", "hoa don so", "ban so", "thu ngan", "cashier", "so bill", "bill no")
_HEADER_WORDS = ("hoa don", "phieu", "bill", "receipt", "invoice", "dia chi", "dt", "tel",
                 "sdt", "mst", "hotline", "wifi", "website", "www", "http", "ten mon", "stt")


def classify_summary(folded: str) -> str | None:
    """Từ khóa xuất hiện sớm nhất trong dòng thắng (ưu tiên theo thứ tự khi hòa)."""
    best: tuple[int, int, str] | None = None
    for prio, (kind, keys) in enumerate(_SUMMARY_KEYS):
        for k in keys:
            pos = folded.find(k)
            if pos != -1 and (best is None or (pos, prio) < best[:2]):
                best = (pos, prio, kind)
    return best[2] if best else None


_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)")


def find_date(lines: list[str]) -> date | None:
    for line in lines:
        for m in _DATE_RE.finditer(line):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            try:
                return date(y, mo, d)
            except ValueError:
                continue
    return None


def find_merchant(lines: list[str]) -> str | None:
    """Dòng chữ đầu tiên (trong 6 dòng đầu) trông như tên cửa hàng."""
    for line in lines[:6]:
        s = line.strip(" -_*=.:|")
        f = fold(s)
        letters = sum(c.isalpha() for c in s)
        digits = sum(c.isdigit() for c in s)
        if letters < 3 or digits > letters * 0.3:
            continue
        if any(w in f for w in _HEADER_WORDS):
            continue
        return s[:255]
    return None


_QTY_PREFIX = re.compile(r"^\s*(\d{1,2})\s*[xX*]\s+")
_INDEX_PREFIX = re.compile(r"^\s*\d{1,2}[.)]\s+")
_QTY_SUFFIX = re.compile(r"\s+[xX*]?\s*(\d{1,2})\s*$")


def _clean_name(name: str) -> str:
    name = re.sub(r"[|_]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -:.,*x")
    return name[:255]


def parse_item_line(line: str) -> tuple[ParsedItem | None, str | None]:
    """Một dòng món -> (ParsedItem, warning). Không phải dòng món -> (None, None)."""
    text = _INDEX_PREFIX.sub("", line)   # bỏ số thứ tự "1. " đầu dòng
    tokens = money_tokens(text)
    if not tokens:
        return None, None

    prefix_qty: Decimal | None = None
    m = _QTY_PREFIX.match(text)
    if m:
        prefix_qty = Decimal(m.group(1))
        text = text[m.end():]
        tokens = money_tokens(text)
        if not tokens:
            return None, None

    first_pos = tokens[0][0]
    name = _clean_name(text[:first_pos])
    values = [v for _, v in tokens]

    # SL nằm ngay trước các số tiền: "Cà phê 2 35.000 70.000" -> "2" bị coi là số tiền nhỏ
    qty: Decimal | None = prefix_qty
    if qty is None and len(values) >= 2 and values[0] == values[0].to_integral_value() and 1 <= values[0] <= 99 \
            and not re.search(r"[.,]\d{3}", text[tokens[0][0]:tokens[0][0] + 6]):
        qty, values = values[0], values[1:]
    if qty is None:
        m2 = _QTY_SUFFIX.search(name)
        if m2 and len(name) > m2.end() - m2.start() + 1:
            qty, name = Decimal(m2.group(1)), _clean_name(name[: m2.start()])

    if sum(c.isalpha() for c in name) < 2:
        return None, None

    warning = None
    if len(values) >= 2:                       # ... đơn giá, thành tiền
        unit_price, line_total = values[-2], values[-1]
        if qty is None:
            qty = Decimal(1)
        if qty * unit_price != line_total:
            warning = f"Dòng '{name}': {qty} × {unit_price} ≠ {line_total}, cần kiểm tra"
    else:                                      # chỉ có 1 số = thành tiền
        line_total = values[0]
        if qty is None:
            qty, unit_price = Decimal(1), line_total
        elif line_total % qty == 0:
            unit_price = line_total / qty
        else:
            qty, unit_price = Decimal(1), line_total
            warning = f"Dòng '{name}': không suy ra được đơn giá, cần kiểm tra"
    if line_total < MIN_LINE_TOTAL:
        return None, None
    return ParsedItem(name, qty, unit_price, line_total), warning


def parse_receipt(lines: list[str]) -> ParsedReceipt:
    """Entry point: danh sách dòng OCR (trên -> dưới) -> ParsedReceipt."""
    lines = [l.strip() for l in lines if l and l.strip()]
    result = ParsedReceipt(merchant_name=find_merchant(lines), receipt_date=find_date(lines))

    in_items_zone = True  # sau khi gặp dòng tổng kết đầu tiên thì không nhận dòng món nữa
    totals_seen: dict[str, Decimal] = {}
    for line in lines:
        f = fold(line)
        if any(k in f for k in _SKIP_KEYS) or _DATE_RE.search(line):
            continue
        kind = classify_summary(f)
        if kind:
            tokens = money_tokens(line)
            if tokens:  # dòng tiêu đề như "HÓA ĐƠN THANH TOÁN" không có số -> chưa hết vùng món
                in_items_zone = False
                # lấy số cuối dòng; "tổng" lặp lại nhiều lần -> lấy lần xuất hiện cuối
                totals_seen[kind] = tokens[-1][1]
            continue
        if in_items_zone:
            item, warning = parse_item_line(line)
            if item:
                result.items.append(item)
                if warning:
                    result.warnings.append(warning)

    result.subtotal = totals_seen.get("subtotal")
    result.tax_amount = totals_seen.get("tax")
    result.service_fee = totals_seen.get("service")
    result.total_amount = totals_seen.get("total")

    if result.subtotal is not None and result.items:
        s = sum(i.line_total for i in result.items)
        if s != result.subtotal:
            result.warnings.append(f"Tổng các dòng món ({s}) khác tạm tính ({result.subtotal})")
    if result.total_amount is not None and result.subtotal is not None:
        expected = result.subtotal + (result.tax_amount or 0) + (result.service_fee or 0)
        if expected != result.total_amount:
            result.warnings.append(f"Tổng thanh toán ({result.total_amount}) khác tạm tính + VAT + phí ({expected})")
    return result
