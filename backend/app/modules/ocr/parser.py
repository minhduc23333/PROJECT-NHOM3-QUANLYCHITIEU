"""Parser: text/dòng OCR thô -> dữ liệu hóa đơn có cấu trúc (task T05E170).

Hàm thuần, không phụ thuộc OCR engine/DB. Nguyên tắc BR-10: trường nào không
nhận ra thì để None, tuyệt đối không tự bịa số liệu.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import product

ROUNDING_TOLERANCE = Decimal(1000)
MIN_LINE_TOTAL = Decimal(1000)  # VND: giá món < 1.000đ gần như chắc chắn là số khác (số bàn, địa chỉ...)
MAX_MONEY = Decimal(999999999)  # lớn hơn thường là số điện thoại/mã số thuế, không phải tiền


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
# Dòng tổng kết: hóa đơn VN hay viết "50 662 000" (khoảng trắng làm dấu nghìn). Chỉ dùng cho dòng tổng,
# vì ở dòng món "2 150 000" có thể là SL=2 rồi đơn giá 150 000 -> không thể đoán chắc.
_MONEY_TOKEN_SPACED = re.compile(r"(?<![\w])(\d{1,3}(?:[.,\s]\d{3})+|\d+)(?:[.,]\d{1,2})?(?![\w])(?!\s*%)")


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


def money_tokens(line: str, *, spaced: bool = False) -> list[tuple[int, Decimal]]:
    """[(vị trí, giá trị)] các số tiền trong dòng; bỏ số đi kèm dấu % và số 0 (nhiễu OCR).

    spaced=True: nhận cả "50 662 000" (khoảng trắng làm dấu nghìn) — dùng cho dòng tổng kết.
    """
    out = []
    for m in (_MONEY_TOKEN_SPACED if spaced else _MONEY_TOKEN).finditer(line):
        v = parse_money(m.group(0))
        if v is not None and v > 0:
            out.append((m.start(), v))
    return out


# OCR hay viết "300. 000" / "55 .000" (chèn khoảng trắng quanh dấu nghìn) và nhầm O->0, l/I->1 trong số tiền.
_STRAY_SEP = re.compile(r"(?<![\d.,])(\d{1,3})\s*([.,])\s*(?=\d{3}(?!\d))")
_LETTER = "A-Za-zÀ-ỹ"
_DIGITISH = re.compile(rf"(?<![{_LETTER}\d])[\dOoIl|]{{1,3}}(?:[.,][\dOoIlCcDQ|]{{3}})+(?![{_LETTER}\d])")
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "C": "0", "c": "0", "D": "0", "Q": "0"})
_TRAILING_J = re.compile(rf"(?<=\d{{3}})[Jj](?![{_LETTER}\d])")    # '300000J' (viền bảng bị đọc thành J)
_SPACED_MILLIONS = re.compile(r"(?<![\d.,])([1-9]\d{0,2}) (\d{3}) (\d{3})(?![\d.,]| \d{3})")
_SPACED_THOUSANDS = re.compile(r"(?<![\d.,])([1-9]\d{1,2}) (000)(?![\d.,])")
_SPACED_SINGLE_K = re.compile(r"(?<![\d.,])([1-9]) (000)(?=\s+\d{1,3}[.,]\d{3})")


def normalize_numbers(line: str) -> str:
    """'300. 000' -> '300.000', '228.OOO' -> '228.000', '2 160 000' -> '2.160.000'. Chỉ đụng vào chuỗi trông như số tiền
    có dấu nghìn (có ít nhất một chữ số thật) nên không làm hỏng từ như 'No.100' hay 'Tp.HCM'."""
    line = _TRAILING_J.sub("", _STRAY_SEP.sub(r"\1\2", line))
    line = _SPACED_MILLIONS.sub(r"\1.\2.\3", line)
    line = _SPACED_THOUSANDS.sub(r"\1.\2", line)
    line = _SPACED_SINGLE_K.sub(r"\1.\2", line)

    def fix(m: re.Match) -> str:
        tok = m.group(0)
        return tok.translate(_DIGIT_FIX) if any(c.isdigit() for c in tok) else tok

    return _DIGITISH.sub(fix, line)


# ---------- phân loại dòng ----------

_SUMMARY_KEYS = [
    ("subtotal", ("tam tinh", "tong tien hang", "cong tien hang", "subtotal", "sub total", "sub-total")),
    ("tax", ("vat", "gtgt", "thue", "tax")),
    ("service", ("phi dich vu", "phi phuc vu", "phi pv", "service charge", "service fee", "service")),
    ("total", ("payment amount", "amount due", "tong cong", "tong thanh toan", "tong tien", "tong so tien",
               "can thanh toan", "phai thanh toan", "thanh toan", "grand total", "total", "tong")),
]
_SKIP_KEYS = ("khach dua", "tien thua", "tien thoi", "tien thi", "tra lai", "tien mat", "tienmat", "the ", "discount",
              "cash", "return amount", "change", "dt:", "d/c", "sdt", "tel", "hotline", "mst", "ma so thue",
              "dia chi", "address", "so hoa don", "hoa don so", "ban so", "thu ngan", "cashier", "so bill", "bill no")
_HEADER_WORDS = ("hoa don", "phieu", "bill", "receipt", "invoice", "dia chi", "dt", "tel",
                 "sdt", "mst", "hotline", "wifi", "website", "www", "http", "ten mon", "stt")


# Tesseract hay đọc "Tổng cộng" thành "Téng cộng" / "Tôäg cộng": sau khi bỏ dấu thành "teng cong" nên khớp
# chính xác thất bại và mất luôn tổng tiền. Khớp mờ chỉ áp cho phần nhãn đứng trước số của dòng có số.
_FUZZY_KEYS = (
    ("total", "tong cong"), ("total", "tong tien"), ("total", "thanh toan"), ("total", "payment amount"),
    ("subtotal", "tam tinh"), ("subtotal", "subtotal"), ("subtotal", "sub total"),
    ("service", "phi dich vu"), ("service", "phi phuc vu"),
)
FUZZY_RATIO = 0.75


def _fuzzy_summary(folded: str) -> str | None:
    if not any(c.isdigit() for c in folded):
        return None
    label = re.split(r"\d", folded, maxsplit=1)[0].strip(" :.-*|_=")
    if not 6 <= len(label) <= 20:
        return None
    for kind, key in _FUZZY_KEYS:
        if SequenceMatcher(None, label[: len(key) + 2], key).ratio() >= FUZZY_RATIO:
            return kind
    return None


def classify_summary(folded: str) -> str | None:
    """Từ khóa xuất hiện sớm nhất trong dòng thắng (ưu tiên theo thứ tự khi hòa); không khớp thì thử khớp mờ."""
    best: tuple[int, int, str] | None = None
    for prio, (kind, keys) in enumerate(_SUMMARY_KEYS):
        for k in keys:
            pos = folded.find(k)
            if pos != -1 and (best is None or (pos, prio) < best[:2]):
                best = (pos, prio, kind)
    return best[2] if best else _fuzzy_summary(folded)


def pick_amount(tokens: list[tuple[int, Decimal]]) -> Decimal | None:
    """Số tiền của dòng tổng kết: số cuối cùng, trừ khi đó chỉ là chữ số rác (< 1.000đ) đứng sau số tiền thật
    ('Tạm tính: 228.000 3' -> 228.000, không phải 3). Bỏ qua số < 100đ (tránh nhầm 'VAT 8' thành 8đ)."""
    real = [v for _, v in tokens if v >= MIN_LINE_TOTAL]
    if real:
        return real[-1]
    return tokens[-1][1] if tokens[-1][1] >= Decimal(100) else None


# năm 4 chữ số dạng 20xx được nhận kể cả khi dính liền giờ ("10/09/202210:54"); năm 2 chữ số thì phải đứng riêng
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(20\d{2}(?!\d{3})|\d{4}(?!\d)|\d{2}(?!\d))")
MIN_YEAR = 2000


def find_date(lines: list[str]) -> date | None:
    for line in lines:
        for m in _DATE_RE.finditer(line):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            if not MIN_YEAR <= y <= date.today().year + 1:   # '2926' / '1926' là đọc sai, không phải ngày hóa đơn
                continue
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
_BARE_INDEX_PREFIX = re.compile(rf"^\s*(?:[|\[]\s*)?\d{{1,2}}\s*[|]?\s+(?=[{_LETTER}])")
_QTY_SUFFIX = re.compile(r"\s+[xX*]?\s*(\d{1,2})\s*$")


def _clean_name(name: str) -> str:
    name = re.sub(r"[|_\[\]{}()¡¬]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -:.,*x")
    return name[:255]


def _tidy(d: Decimal) -> Decimal:
    return d.quantize(Decimal(1)) if d == d.to_integral_value() else d


def _close(q: Decimal, u: Decimal, t: Decimal) -> bool:
    return abs(q * u - t) <= max(Decimal(1), t * Decimal("0.005"))


def repair_item(q: Decimal, u: Decimal, t: Decimal) -> tuple[Decimal, Decimal, Decimal, str | None]:
    """Dòng món có SL × đơn giá ≠ thành tiền: thử các lỗi OCR hay gặp, chỉ nhận cách chỉnh nào làm 3 số KHỚP nhau.

    - mất 3 chữ số 0 ở cuối: '400.00' -> 400.000, '17,0' -> 17.000
    - mất dấu phẩy của SL cân: '28' -> 2,8 (kg)
    - đơn giá = thành tiền mà SL ≠ 1: SL bị đọc nhầm (vd '4' thay vì '1') -> SL = 1
    Không chỉnh được thì giữ nguyên. Dòng nào bị chỉnh đều kèm cảnh báo để người dùng đối chiếu (BR-10).
    """
    if t <= 0 or _close(q, u, t):
        return q, u, t, None
    qs = [(q, 0)] + ([(q / 10, 1)] if q == q.to_integral_value() and q >= 10 else [])
    us = [(u, 0)] + ([(u * 1000, 1)] if 0 < u < 1000 else [])
    ts = [(t, 0)] + ([(t * 1000, 1)] if 0 < t < 1000 else [])
    best = None
    for (q2, cq), (u2, cu), (t2, ct) in product(qs, us, ts):
        cost = cq + cu + ct
        if cost and _close(q2, u2, t2) and (best is None or cost < best[0]):
            best = (cost, q2, u2, t2)
    if best:
        return _tidy(best[1]), _tidy(best[2]), _tidy(best[3]), f"đã tự chỉnh cho khớp SL × đơn giá = thành tiền (đọc gốc {q} × {u} = {t})"
    if u == t and q != 1 and q == q.to_integral_value() and q <= 99:
        return Decimal(1), u, t, f"đơn giá bằng thành tiền nên đặt SL = 1 (đọc gốc SL = {q})"
    return q, u, t, None


_UNIT_WORDS = ("kg", "g", "gram", "dia", "đĩa", "dĩa", "cái", "cai", "chai", "con", "lon", "phần", "phan", "ly", "tô", "chén",
               "hộp", "hop", "gói", "goi", "lọ", "bát", "suất", "suat", "lít", "lit", "thùng", "cốc", "ổ", "bịch", "đvt")
_UNIT_TAIL = re.compile(r"\s+(?:" + "|".join(_UNIT_WORDS) + r")$", re.IGNORECASE)
# OCR hay dính liền ĐVT viết hoa vào chữ thường ngay trước: "chiếDia", "tayKg"
_UNIT_GLUED = re.compile(r"(?<=[a-zà-ỹ])(?:Dia|Dĩa|Đĩa|Kg|Chai|Cái|Con|Lon|Ly|Tô|Phần)$")


_CURRENCY = {"d", "đ", "vnd", "vnđ", "dong", "đồng"}


def _junk_after_amount(text: str, pos: int) -> bool:
    """Sau số tiền đầu tiên chỉ còn đúng một cụm chữ ngắn (2-4 chữ cái) không phải ký hiệu tiền tệ."""
    m = _MONEY_TOKEN.match(text, pos)
    rest = re.sub(r"[\s|!\]\[}{)(,.;:_-]+", " ", text[m.end():] if m else "").strip()
    return bool(re.fullmatch(r"[A-Za-zÀ-ỹ]{2,4}", rest)) and rest.lower() not in _CURRENCY


def parse_item_line(line: str) -> tuple[ParsedItem | None, str | None]:
    """Một dòng món -> (ParsedItem, warning). Không phải dòng món -> (None, None)."""
    text = _INDEX_PREFIX.sub("", line)   # bỏ số thứ tự "1. " đầu dòng
    if text == line:
        stripped = _BARE_INDEX_PREFIX.sub("", text)
        if stripped != text and len(money_tokens(stripped)) >= 2:
            text = stripped              # bảng có cột STT không dấu chấm: "1 Ốc Hương Kg 3,0 720.000 2.160.000"
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

    # SL nằm ngay trước các số tiền: "Cà phê 2 35.000 70.000" hoặc "Cá Song 7,2 650.000 4.680.000"
    qty: Decimal | None = prefix_qty
    if qty is None and len(values) >= 2 and Decimal("0.01") <= values[0] <= 99 \
            and not re.search(r"[.,]\d{3}", text[tokens[0][0]:tokens[0][0] + 6]):
        qty, values = values[0], values[1:]
    if qty is None:
        m2 = _QTY_SUFFIX.search(name)
        if m2 and len(name) > m2.end() - m2.start() + 1:
            qty, name = Decimal(m2.group(1)), _clean_name(name[: m2.start()])

    if qty is not None:   # có cột SL riêng -> chữ ngay trước đó là cột ĐVT ("Cá chim | Kg | 2 ...") chứ không phải tên món
        stripped = _UNIT_GLUED.sub("", _UNIT_TAIL.sub("", name))
        if sum(c.isalpha() for c in stripped) >= 2:
            name = stripped
    if sum(c.isalpha() for c in name) < 2:
        return None, None

    warning = None
    if len(values) >= 2:                       # ... đơn giá, thành tiền
        unit_price, line_total = values[-2], values[-1]
        if qty is None:
            qty = Decimal(1)
        if qty * unit_price != line_total:
            qty, unit_price, line_total, note = repair_item(qty, unit_price, line_total)
            warning = f"Dòng '{name}': {note}, cần kiểm tra" if note else (
                f"Dòng '{name}': {qty} × {unit_price} ≠ {line_total}, cần kiểm tra" if qty * unit_price != line_total else None)
    elif qty is not None and qty > 1 and _junk_after_amount(text, tokens[-1][0]):
        # bảng có cột T.Tiền nhưng ô đó bị đọc thành chữ rác -> số còn lại là đơn giá
        unit_price = values[0]
        line_total = qty * unit_price
        warning = f"Dòng '{name}': không đọc được thành tiền, tạm tính = {qty} × {unit_price}, cần kiểm tra"
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


_PAYMENT_ZONE_KEYS = (
    "diem tren", "tien mat", "tienmat", "tien thua", "tien thoi", "tien thi",
    "khach dua", "tra lai", "da bao gom", "da bao gdm", "da lam tron", "da lam tren",
    "lam tron", "chiet khau", "khuyen mai", "cash", "return amount",
)
_TOTAL_AFTER_DISCOUNT = ("da bao gom giam gia", "da bao gdm giam gia", "bao gom giam gia", "bao gdm giam gia")
_TOTAL_AFTER_DISCOUNT_RE = re.compile(r"bao\s+g[o0d]m\s+giam\s+gi[ad]")


def _is_total_after_discount(folded: str) -> bool:
    if any(k in folded for k in _TOTAL_AFTER_DISCOUNT) or _TOTAL_AFTER_DISCOUNT_RE.search(folded):
        return True
    if any(c.isdigit() for c in folded):
        label = re.split(r"\d", folded, maxsplit=1)[0].strip(" ()[]:.-*|_=")
        if 10 <= len(label) <= 28:
            return SequenceMatcher(None, label, "da bao gom giam gia").ratio() >= 0.78
    return False


def _numbers_only(line: str) -> bool:
    """Dòng chỉ gồm số/dấu (vd '1 17,000 17,000', '1.264 66,060 49,005') -> dòng chi tiết của món ở dòng trên."""
    return sum(c.isalpha() for c in line) == 0 and any(c.isdigit() for c in line)


def parse_qty_price_total(line: str, name: str) -> tuple[ParsedItem | None, str | None]:
    """'SL đơn_giá thành_tiền' (SL có thể thập phân như 0.49 / 1.264) -> ParsedItem với tên lấy từ dòng trên."""
    nums = re.findall(r"\d+(?:[.,]\d{3})+|\d+(?:[.,]\d{1,2})?", line)
    if len(nums) < 3:
        return None, None
    qty_s, price_s, total_s = nums[0], nums[-2], nums[-1]   # có thể có thêm cột giá gốc (gạch ngang) ở giữa
    qty = Decimal(qty_s.replace(",", "."))   # SL luôn là số thập phân kiểu 0.49 / 1.264 (kg), không phải hàng nghìn
    unit_price, line_total = parse_money(price_s), parse_money(total_s)
    if unit_price is None or line_total is None:
        return None, None
    note = None
    if abs(qty * unit_price - line_total) > max(Decimal(1), line_total * Decimal("0.02")):
        qty, unit_price, line_total, note = repair_item(qty, unit_price, line_total)
    if line_total < MIN_LINE_TOTAL:
        return None, None
    name = _clean_name(name)
    if sum(c.isalpha() for c in name) < 2:
        return None, None
    warning = f"Dòng '{name}': {note}, cần kiểm tra" if note else None
    if warning is None and abs(qty * unit_price - line_total) > max(Decimal(1), line_total * Decimal("0.02")):
        warning = f"Dòng '{name}': {qty} × {unit_price} ≠ {line_total}, cần kiểm tra"
    return ParsedItem(name, qty, unit_price, line_total), warning


# Các cặp chữ số OCR hay nhầm (Tesseract trên ảnh độ phân giải thấp)
_CONFUSABLE = {"1": "47", "4": "1", "7": "1", "0": "689", "6": "058", "8": "0369", "9": "08", "3": "8", "5": "6", "2": "7"}


def _repair_one_digit(result: ParsedReceipt) -> None:
    """Tổng các món lệch tổng tiền do ĐÚNG MỘT chữ số bị đọc nhầm ('413.000' thay vì '113.000').

    Chỉ sửa khi có duy nhất một (món, vị trí chữ số, chữ số thay) làm tổng khớp lại trong ngưỡng làm tròn;
    nhiều cách sửa cùng khớp thì không đoán. Luôn kèm cảnh báo để người dùng đối chiếu (BR-10).
    """
    if not result.items or result.total_amount is None:
        return
    target = result.subtotal if result.subtotal is not None else (
        result.total_amount - (result.tax_amount or 0) - (result.service_fee or 0))
    total = sum(i.line_total for i in result.items)
    if abs(target - total) <= ROUNDING_TOLERANCE or target <= 0:
        return
    found: list[tuple[ParsedItem, Decimal]] = []
    for item in result.items:
        if item.line_total != item.line_total.to_integral_value():
            continue
        digits = str(int(item.line_total))
        for pos, ch in enumerate(digits):
            for rep in _CONFUSABLE.get(ch, ""):
                if pos == 0 and rep == "0":
                    continue
                new = Decimal(digits[:pos] + rep + digits[pos + 1:])
                if abs(target - (total - item.line_total + new)) <= ROUNDING_TOLERANCE:
                    found.append((item, new))
    if len({id(i) for i, _ in found}) != 1 or len(found) != 1:
        return
    item, new = found[0]
    old = item.line_total
    item.line_total = new
    item.unit_price = _tidy(new / item.quantity) if item.quantity else new
    result.warnings = [w for w in result.warnings if item.item_name not in w]
    result.warnings.append(f"Dòng '{item.item_name}': thành tiền {old} đã tự sửa thành {new} cho khớp tổng hóa đơn, cần kiểm tra")


def parse_receipt(lines: list[str]) -> ParsedReceipt:
    """Entry point: danh sách dòng OCR (trên -> dưới) -> ParsedReceipt."""
    lines = [normalize_numbers(l.strip()) for l in lines if l and l.strip()]
    result = ParsedReceipt(merchant_name=find_merchant(lines), receipt_date=find_date(lines))

    in_items_zone = True  # sau khi gặp dòng tổng kết/thanh toán đầu tiên thì không nhận dòng món nữa
    totals_seen: dict[str, Decimal] = {}
    pending_name: str | None = None   # tên món ở dòng trên, số nằm ở dòng dưới (kiểu Bách Hóa Xanh)
    pending_summary: str | None = None   # nhãn "Tạm tính:" đứng riêng, số tiền nằm ở dòng ngay dưới
    last_item: ParsedItem | None = None   # món vừa nhận: dòng chữ thuần ngay sau nó có thể là phần tên bị xuống dòng
    for idx, line in enumerate(lines):
        f = fold(line)
        waiting, pending_summary = pending_summary, None   # chỉ hiệu lực cho đúng 1 dòng kế tiếp
        if waiting and _numbers_only(line) and not _DATE_RE.search(line):
            toks = [t for t in money_tokens(line, spaced=True) if re.search(r"[.,]\d{3}|\s\d{3}", line)]
            if toks:   # chỉ nhận số có dấu nghìn: tránh nhầm số điện thoại / mã số đứng sau nhãn
                amt = pick_amount(toks)
                if amt is not None:
                    totals_seen[waiting] = amt
                    in_items_zone = False
                continue
        # "(Đã bao gồm giảm giá) 242.841" = tổng phải trả, không phải dòng giảm giá
        if _is_total_after_discount(f):
            toks = money_tokens(line, spaced=True)
            if toks:
                amt = pick_amount(toks)
                if amt is not None:
                    totals_seen["total"] = amt
                    in_items_zone = False
            continue
        if any(k in f for k in _PAYMENT_ZONE_KEYS) and not _numbers_only(line):
            in_items_zone = False
            continue
        if re.fullmatch(r"\W*thanh toan\W*", f):   # tiêu đề "Thanh toán:" không số -> hết vùng món
            in_items_zone = False
            continue
        if any(k in f for k in _SKIP_KEYS) or _DATE_RE.search(line):
            continue
        kind = classify_summary(f)
        if kind:
            tokens = money_tokens(line, spaced=True)
            if tokens:  # dòng tiêu đề như "HÓA ĐƠN THANH TOÁN" không có số -> chưa hết vùng món
                amt = pick_amount(tokens)
                if amt is not None:
                    in_items_zone = False
                    totals_seen[kind] = amt
            else:
                pending_summary = kind
            continue
        if not in_items_zone:
            continue
        if _numbers_only(line):
            if pending_name:
                item, warning = parse_qty_price_total(line, pending_name)
                if item:
                    result.items.append(item)
                    if warning:
                        result.warnings.append(warning)
            pending_name = None
            continue
        item, warning = parse_item_line(line)
        if item:
            result.items.append(item)
            last_item = item
            if warning:
                result.warnings.append(warning)
            pending_name = None
        elif sum(c.isalpha() for c in line) >= 3:
            nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
            digits = any(c.isdigit() for c in line)
            if nxt and _numbers_only(nxt):
                pending_name = line      # dòng chữ thuần -> có thể là tên món của dòng số bên dưới
                last_item = None
            elif last_item is not None and not digits and len(line) <= 30 and classify_summary(f) is None:
                # tên món dài bị xuống dòng: "Mực cơm xào" / "hành cần" -> nối vào món ngay trước
                last_item.item_name = _clean_name(f"{last_item.item_name} {line}")
            else:
                pending_name = line
        # dòng rác (".", "_", "|"): giữ nguyên pending_name

    result.subtotal = totals_seen.get("subtotal")
    result.tax_amount = totals_seen.get("tax")
    result.service_fee = totals_seen.get("service")
    result.total_amount = totals_seen.get("total")

    _repair_one_digit(result)
    if result.subtotal is not None and result.items:
        s = sum(i.line_total for i in result.items)
        if s != result.subtotal:
            result.warnings.append(f"Tổng các dòng món ({s}) khác tạm tính ({result.subtotal})")
    if result.total_amount is not None and result.subtotal is None and result.items:
        s = sum(i.line_total for i in result.items) + (result.tax_amount or 0) + (result.service_fee or 0)
        if abs(s - result.total_amount) > ROUNDING_TOLERANCE:   # lệch < 1.000đ là làm tròn tiền, không phải lỗi đọc
            result.warnings.append(f"Tổng các dòng món + thuế + phí ({s}) khác tổng thanh toán ({result.total_amount}): có thể đọc thiếu/sai món")
    if result.total_amount is not None and result.subtotal is not None:
        expected = result.subtotal + (result.tax_amount or 0) + (result.service_fee or 0)
        if expected != result.total_amount:
            result.warnings.append(f"Tổng thanh toán ({result.total_amount}) khác tạm tính + VAT + phí ({expected})")
    return result