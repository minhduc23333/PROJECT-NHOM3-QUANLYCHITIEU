"""Test phân loại danh mục chi tiêu (T05E17F): chọn tay + quy tắc từ khóa, mặc định Khác."""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.receipts import categories
from app.modules.receipts.categories import CATEGORIES, DEFAULT, normalize, suggest

# ---------- quy tắc từ khóa (hàm thuần) ----------


@pytest.mark.parametrize("merchant,items,expected", [
    ("NHÀ HÀNG BÚN BÒ HUẾ", ["Bún bò đặc biệt", "Trà đá"], "Ăn uống"),
    ("Highlands Coffee", [], "Ăn uống"),
    ("Quán Cơm Tấm Ba Ghiền", [], "Ăn uống"),
    ("Tàu Hũ Cô Ba", [], "Ăn uống"),               # "tau hu" (2 từ) thắng "tau" (Di chuyển)
    ("Grab", ["GrabCar"], "Di chuyển"),
    ("Petrolimex", ["Xăng A95"], "Di chuyển"),
    ("Vinasun Taxi", [], "Di chuyển"),
    ("WinMart", ["Sữa", "Trứng"], "Mua sắm"),
    ("Co.opmart Cống Quỳnh", [], "Mua sắm"),
    ("Cửa hàng quần áo Hoa", ["Quần jean"], "Mua sắm"),
    ("Phòng khám ABC", ["Khám bệnh"], DEFAULT),
    ("Quận 1 Spa", [], DEFAULT),                   # "Quận" không bị nhầm với "quán"
    ("cua hang xyz.com", [], DEFAULT),
    (None, [], DEFAULT),
    ("", [], DEFAULT),
])
def test_suggest_by_keywords(merchant, items, expected):
    assert suggest(merchant, items) == expected


def test_merchant_match_outweighs_item_match():
    # Tên cửa hàng là siêu thị (Mua sắm) nên thắng món "Bia" (Ăn uống)
    assert suggest("Circle K", ["Bia Tiger"]) == "Mua sắm"


def test_suggest_is_accent_and_case_insensitive():
    assert suggest("HIGHLANDS COFFEE") == suggest("highlands coffee") == "Ăn uống"
    assert suggest("ca phe so 1") == "Ăn uống"


@pytest.mark.parametrize("raw,expected", [
    ("Ăn uống", "Ăn uống"), ("an uong", "Ăn uống"), ("  ĂN UỐNG ", "Ăn uống"),
    ("Di chuyển", "Di chuyển"), ("Đi lại", "Di chuyển"),   # tên cũ từ giao diện trước
    ("Khác", "Khác"), ("", "Khác"), ("   ", "Khác"),
])
def test_normalize_valid(raw, expected):
    assert normalize(raw) == expected


def test_normalize_rejects_unknown():
    with pytest.raises(ValueError):
        normalize("Nhà ở")


def test_four_fixed_categories_default_is_khac():
    assert CATEGORIES == ("Ăn uống", "Di chuyển", "Mua sắm", "Khác") and DEFAULT == "Khác"


# ---------- API ----------


def _upload(client, headers, monkeypatch, tmp_path):
    from app.modules.receipts import service as receipts_service

    monkeypatch.setattr(receipts_service.settings, "UPLOAD_DIR", str(tmp_path))
    gid = client.post("/api/groups", json={"name": "Nhóm"}, headers=headers).json()["id"]
    r = client.post(f"/api/groups/{gid}/receipts", headers=headers,
                    files={"file": ("r.png", b"\x89PNG\r\n\x1a\nvalid", "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch(client, headers, rid, category):
    return client.patch(f"/api/receipts/{rid}", json={"category": category}, headers=headers)


def test_patch_category_accepts_list_and_normalizes(client, monkeypatch, tmp_path):
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)
    assert _patch(client, h, rid, "Mua sắm").json()["category"] == "Mua sắm"
    assert _patch(client, h, rid, "di chuyen").json()["category"] == "Di chuyển"
    assert _patch(client, h, rid, "").json()["category"] == "Khác"       # để trống -> mặc định Khác
    assert client.get(f"/api/receipts/{rid}", headers=h).json()["category"] == "Khác"


def test_patch_category_rejects_unknown_value(client, monkeypatch, tmp_path):
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)
    assert _patch(client, h, rid, "Nhà ở").status_code == 422
    assert _patch(client, h, rid, "x" * 51).status_code == 422


def test_category_suggestion_endpoint(client):
    from tests.conftest import register

    assert client.get("/api/receipts/category-suggestion?merchant_name=Grab").status_code == 401
    h = register(client)
    url = "/api/receipts/category-suggestion"
    assert client.get(url, params={"merchant_name": "Highlands Coffee"}, headers=h).json() == {"category": "Ăn uống"}
    assert client.get(url, params={"merchant_name": "Grab"}, headers=h).json() == {"category": "Di chuyển"}
    assert client.get(url, params={"merchant_name": "Công ty ABC"}, headers=h).json() == {"category": "Khác"}
    assert client.get(url, headers=h).json() == {"category": "Khác"}     # không có tên cửa hàng -> Khác


def _fake_ocr(monkeypatch, merchant, item_names):
    from app.modules.ocr import service
    from app.modules.ocr.parser import ParsedItem, ParsedReceipt

    items = [ParsedItem(n, Decimal(1), Decimal(50000), Decimal(50000)) for n in item_names]
    parsed = ParsedReceipt(merchant_name=merchant, receipt_date=date(2026, 11, 5), items=items,
                           subtotal=Decimal(50000) * len(items), total_amount=Decimal(50000) * len(items))
    monkeypatch.setattr(service, "extract", lambda path: (parsed, type("R", (), {"text": "x"})()))


def test_ocr_suggests_category_from_keywords(client, monkeypatch, tmp_path):
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)
    _fake_ocr(monkeypatch, "Quán Cơm Tấm Ba Ghiền", ["Cơm tấm sườn"])
    res = client.post(f"/api/ocr/receipts/{rid}", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["receipt"]["category"] == "Ăn uống"


def test_ocr_unknown_merchant_defaults_to_khac(client, monkeypatch, tmp_path):
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)
    _fake_ocr(monkeypatch, "Công ty TNHH ABC", ["Dịch vụ tư vấn"])
    assert client.post(f"/api/ocr/receipts/{rid}", headers=h).json()["receipt"]["category"] == "Khác"


def test_ocr_never_overrides_manual_category(client, monkeypatch, tmp_path):
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)
    _patch(client, h, rid, "Mua sắm")                       # người dùng chọn tay trước khi OCR
    _fake_ocr(monkeypatch, "Quán Cơm Tấm Ba Ghiền", ["Cơm tấm sườn"])
    assert client.post(f"/api/ocr/receipts/{rid}", headers=h).json()["receipt"]["category"] == "Mua sắm"


def test_ocr_failure_leaves_category_empty(client, monkeypatch, tmp_path):
    from app.modules.ocr import service
    from app.modules.ocr.engine import OcrError
    from tests.conftest import register

    h = register(client)
    rid = _upload(client, h, monkeypatch, tmp_path)

    def boom(path):
        raise OcrError("hỏng")

    monkeypatch.setattr(service, "extract", boom)
    assert client.post(f"/api/ocr/receipts/{rid}", headers=h).json()["receipt"]["category"] is None
