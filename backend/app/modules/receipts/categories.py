"""Phân loại danh mục chi tiêu (T05E17F, FR-14): chọn tay + quy tắc từ khóa đơn giản.

Danh mục cố định: Ăn uống, Di chuyển, Mua sắm, Khác. Không xác định được -> "Khác".
Thuần Python, không phụ thuộc DB/FastAPI để dễ test.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

DEFAULT = "Khác"
CATEGORIES: tuple[str, ...] = ("Ăn uống", "Di chuyển", "Mua sắm", DEFAULT)

# Tên cũ từng lưu từ giao diện trước đây -> danh mục chuẩn
_ALIASES = {"di lai": "Di chuyển"}


def _fold(s: str) -> str:
    """Chữ thường + bỏ dấu tiếng Việt; ký tự lạ thành khoảng trắng để so khớp theo từ."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " " + re.sub(r"[^a-z0-9&]+", " ", s).strip() + " "


_FOLDED = {_fold(c).strip(): c for c in CATEGORIES}


def normalize(value: str) -> str:
    """Chuẩn hóa giá trị người dùng/UI gửi lên thành một danh mục hợp lệ.

    Bỏ qua hoa/thường và dấu ("an uong" -> "Ăn uống"); để trống -> "Khác";
    không thuộc danh sách -> ValueError (API trả 422).
    """
    key = _fold(value).strip()
    if not key:
        return DEFAULT
    found = _FOLDED.get(key) or _ALIASES.get(key)
    if found is None:
        raise ValueError("Danh mục không hợp lệ, chọn một trong: " + ", ".join(CATEGORIES))
    return found


# Từ khóa đã bỏ dấu, so khớp nguyên từ/cụm từ. Cụm dài điểm cao hơn từ đơn (xem _score).
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Ăn uống": (
        "an uong", "nha hang", "quan an", "quan com", "quan nhau", "com tam", "com ga", "com suon", "com chien",
        "pho", "bun bo", "bun cha", "bun rieu", "hu tieu", "mi quang", "mi xao", "banh mi", "banh xeo", "banh cuon",
        "xoi", "chao", "lau", "nuong", "bbq", "buffet", "pizza", "burger", "ga ran", "tau hu", "che", "kem",
        "ca phe", "cafe", "coffee", "tra sua", "tra dao", "tra", "tea", "sinh to", "nuoc ep", "nuoc mia", "bia", "beer",
        "ruou", "bakery", "restaurant", "kitchen", "food", "kfc", "lotteria", "jollibee", "highlands", "starbucks",
        "phuc long", "the coffee house", "trung nguyen", "gong cha", "tocotoco", "koi", "pizza hut", "domino",
    ),
    "Di chuyển": (
        "di chuyen", "grab", "grabcar", "grabbike", "gojek", "xanh sm", "be bike", "be car", "taxi", "mai linh",
        "vinasun", "uber", "xe om", "xe bus", "xe buyt", "buyt", "bus", "ve xe", "ve tau", "tau", "ve may bay",
        "may bay", "vietjet", "vietnam airlines", "bamboo airways", "airlines", "xang", "xang dau", "petrolimex",
        "pvoil", "caltex", "gui xe", "bai do xe", "parking", "cau duong", "phi cau duong", "rua xe", "sua xe",
        "bao duong xe", "dau nhot",
    ),
    "Mua sắm": (
        "mua sam", "sieu thi", "tap hoa", "coopmart", "co opmart", "co op mart", "winmart", "vinmart", "bach hoa xanh",
        "lotte mart", "aeon", "big c", "mega market", "circle k", "family mart", "familymart", "ministop", "7 eleven",
        "gs25", "mart", "market", "shop", "store", "mall", "vincom", "tiki", "shopee", "lazada", "sendo",
        "the gioi di dong", "thegioididong", "dien may xanh", "fpt shop", "cellphones", "nguyen kim", "uniqlo", "zara",
        "h&m", "quan ao", "thoi trang", "ao", "giay", "dep", "tui", "balo", "my pham", "watsons", "guardian", "hasaki",
        "nha sach", "fahasa", "sach", "van phong pham", "dien thoai", "laptop", "do gia dung", "noi that", "ikea",
    ),
}
_PATTERNS = {
    cat: [(kw, re.compile(re.escape(_fold(kw))), len(kw.split())) for kw in kws]
    for cat, kws in _KEYWORDS.items()
}

MERCHANT_WEIGHT = 2   # khớp ở tên cửa hàng tin cậy hơn khớp ở tên món
ITEM_WEIGHT = 1


def _score(category: str, merchant: str, items: str) -> int:
    total = 0
    for _, pattern, words in _PATTERNS[category]:
        if pattern.search(merchant):
            total += words * MERCHANT_WEIGHT
        if pattern.search(items):
            total += words * ITEM_WEIGHT
    return total


def suggest(merchant_name: str | None, item_names: Iterable[str] = ()) -> str:
    """Gợi ý danh mục từ tên cửa hàng + tên các món. Không khớp từ khóa nào -> "Khác".

    Danh mục có điểm cao nhất thắng (cụm nhiều từ nặng hơn từ đơn); hòa thì theo thứ tự
    Ăn uống > Di chuyển > Mua sắm.
    """
    merchant = _fold(merchant_name or "")
    items = _fold(" ".join(item_names))
    best, best_score = DEFAULT, 0
    for category in _PATTERNS:  # dict giữ thứ tự khai báo
        s = _score(category, merchant, items)
        if s > best_score:
            best, best_score = category, s
    return best
