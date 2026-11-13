from decimal import Decimal

import numpy as np
import pytest

from app.modules.ocr import preprocess as pp
from app.modules.ocr.engine import OcrBox, OcrError, group_into_lines
from app.modules.ocr.parser import find_date, parse_money, parse_receipt

SAMPLE = """NHÀ HÀNG BÚN BÒ HUẾ
Đ/c: 12 Lê Lợi, Q1
ĐT: 0909123456
HÓA ĐƠN THANH TOÁN
Ngày: 05/11/2026 19:30
Bàn số 5
Tên món SL Đơn giá Thành tiền
Bún bò đặc biệt 2 55.000 110.000
Nem rán 1 45,000 45,000
3. Trà đá 3 5.000 15.000
Tạm tính: 170.000
Phí dịch vụ 5%: 8.500
VAT 10%: 17.850
Tổng cộng: 196.350
Tiền khách đưa: 300.000""".split("\n")


# ---------- parser ----------

@pytest.mark.parametrize("raw,expected", [
    ("1.250.000", 1250000), ("125,000", 125000), ("35000", 35000),
    ("35.000đ", 35000), ("12.50", Decimal("12.50")), ("abc", None), ("12345678901", None),
])
def test_parse_money(raw, expected):
    assert parse_money(raw) == (Decimal(expected) if expected is not None else None)


def test_parse_full_receipt():
    r = parse_receipt(SAMPLE)
    assert r.merchant_name == "NHÀ HÀNG BÚN BÒ HUẾ"
    assert str(r.receipt_date) == "2026-11-05"
    assert [(i.item_name, i.quantity, i.unit_price, i.line_total) for i in r.items] == [
        ("Bún bò đặc biệt", Decimal(2), Decimal(55000), Decimal(110000)),
        ("Nem rán", Decimal(1), Decimal(45000), Decimal(45000)),
        ("Trà đá", Decimal(3), Decimal(5000), Decimal(15000)),
    ]
    assert (r.subtotal, r.tax_amount, r.service_fee, r.total_amount) == (
        Decimal(170000), Decimal(17850), Decimal(8500), Decimal(196350))
    assert r.ocr_status == "DONE" and r.warnings == [] and r.missing == []


def test_unrecognized_fields_stay_empty_not_invented():
    r = parse_receipt(["Cà phê sữa 35.000", "Tổng cộng 35.000"])
    assert r.subtotal is None and r.tax_amount is None and r.service_fee is None
    assert r.receipt_date is None
    assert "subtotal" in r.missing and "receipt_date" in r.missing


def test_garbage_is_failed():
    r = parse_receipt(["@@##", "lorem ipsum", ""])
    assert r.ocr_status == "FAILED" and r.items == [] and r.total_amount is None


def test_total_mismatch_gives_warning():
    r = parse_receipt(["Bún bò 2 55.000 110.000", "Tạm tính: 110.000", "VAT: 11.000", "Tổng cộng: 999.000"])
    assert any("khác tạm tính + VAT" in w for w in r.warnings)


def test_inconsistent_line_warns_but_keeps_values():
    r = parse_receipt(["Nem rán 2 45.000 50.000"])
    assert r.items[0].line_total == Decimal(50000)
    assert r.warnings


def test_find_date_rejects_invalid():
    assert find_date(["31/02/2026"]) is None
    assert str(find_date(["ngày 1-2-26"])) == "2026-02-01"


# ---------- preprocess / engine helpers ----------

def test_resize_and_gray_and_threshold():
    small = np.full((100, 200, 3), 255, np.uint8)
    out = pp.preprocess(small)
    assert out.ndim == 2 and out.shape[1] == pp.MIN_WIDTH
    big = np.full((3000, 4000, 3), 255, np.uint8)
    assert pp.preprocess(big).shape[1] == pp.MAX_WIDTH
    assert set(np.unique(out)) <= {0, 255}


def test_load_image_rejects_corrupt_file(tmp_path):
    bad = tmp_path / "x.jpg"
    bad.write_bytes(b"\xff\xd8\xffnot really an image")
    with pytest.raises(pp.ImageError):
        pp.load_image(str(bad))
    with pytest.raises(pp.ImageError):
        pp.load_image(str(tmp_path / "missing.jpg"))


def test_group_into_lines():
    boxes = [OcrBox("55.000", 300, 52, 80, 20, 90), OcrBox("Bún", 10, 50, 40, 20, 90),
             OcrBox("Nem", 10, 100, 40, 20, 90)]
    assert group_into_lines(boxes) == ["Bún 55.000", "Nem"]


# ---------- API (cần DB test như các test khác) ----------

def _make_receipt(client, monkeypatch, tmp_path, headers):
    from app.modules.receipts import service as receipts_service

    monkeypatch.setattr(receipts_service.settings, "UPLOAD_DIR", str(tmp_path))
    gid = client.post("/api/groups", json={"name": "Nhóm A"}, headers=headers).json()["id"]
    r = client.post(f"/api/groups/{gid}/receipts", headers=headers,
                    files={"file": ("r.png", b"\x89PNG\r\n\x1a\nvalid", "image/png")})
    return r.json()["id"]


def test_ocr_endpoint_fills_receipt(client, monkeypatch, tmp_path):
    from tests.conftest import register
    from app.modules.ocr import service

    h = register(client)
    rid = _make_receipt(client, monkeypatch, tmp_path, h)
    parsed = parse_receipt(SAMPLE)
    raw = type("R", (), {"text": "\n".join(SAMPLE)})()
    monkeypatch.setattr(service, "extract", lambda path: (parsed, raw))

    res = client.post(f"/api/ocr/receipts/{rid}", headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["receipt"]["ocr_status"] == "DONE"
    assert body["receipt"]["merchant_name"] == "NHÀ HÀNG BÚN BÒ HUẾ"
    assert len(body["items"]) == 3
    # đã DONE -> không chạy lại đè dữ liệu
    assert client.post(f"/api/ocr/receipts/{rid}", headers=h).status_code == 409


def test_ocr_failure_marks_failed_for_manual_entry(client, monkeypatch, tmp_path):
    from tests.conftest import register
    from app.modules.ocr import service

    h = register(client)
    rid = _make_receipt(client, monkeypatch, tmp_path, h)

    def boom(path):
        raise OcrError("hỏng")

    monkeypatch.setattr(service, "extract", boom)
    res = client.post(f"/api/ocr/receipts/{rid}", headers=h)
    assert res.status_code == 200
    assert res.json()["receipt"]["ocr_status"] == "FAILED"
    assert res.json()["items"] == []


def test_ocr_endpoint_requires_membership(client, monkeypatch, tmp_path):
    from tests.conftest import register

    owner = register(client, "o@x.vn")
    outsider = register(client, "z@x.vn")
    rid = _make_receipt(client, monkeypatch, tmp_path, owner)
    assert client.post(f"/api/ocr/receipts/{rid}", headers=outsider).status_code == 403
    assert client.post("/api/ocr/receipts/9999", headers=owner).status_code == 404


def test_ocr_personal_receipt_is_available_only_to_owner(client, monkeypatch, tmp_path):
    from app.modules.ocr import service
    from app.modules.receipts import service as receipts_service
    from tests.conftest import register

    monkeypatch.setattr(receipts_service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client, "personal@x.vn")
    other_user = register(client, "other@x.vn")
    response = client.post(
        "/api/receipts/personal",
        headers=owner,
        files={"file": ("r.png", b"\x89PNG\r\n\x1a\nvalid", "image/png")},
    )
    receipt_id = response.json()["id"]

    def fail_ocr(path):
        raise OcrError("OCR test failure")

    monkeypatch.setattr(service, "extract", fail_ocr)
    assert client.post(f"/api/ocr/receipts/{receipt_id}", headers=other_user).status_code == 403
    processed = client.post(f"/api/ocr/receipts/{receipt_id}", headers=owner)
    assert processed.status_code == 200, processed.text
    assert processed.json()["receipt"]["ocr_status"] == "FAILED"


# ---------- hóa đơn viết số kiểu "50 662 000" (khoảng trắng làm dấu nghìn) ----------

def test_summary_line_with_space_thousands_separator():
    r = parse_receipt(["Quán Cơm Tấm", "Cơm tấm 2 40.000 80.000", "Tạm tính: 1 250 000", "Tiền thanh toán: 50 662 000"])
    assert r.subtotal == Decimal(1250000)
    assert r.total_amount == Decimal(50662000)


def test_zero_noise_is_not_a_total():
    r = parse_receipt(["Quán A", "Tổng cộng: 000"])
    assert r.total_amount is None


def test_item_name_strips_table_border_noise():
    r = parse_receipt(["Quán A", "[ Khăn lạnh | 31 2.000 62.000", "Tổng cộng 62.000"])
    assert [i.item_name for i in r.items] == ["Khăn lạnh"]


def test_tesseract_lang_falls_back_to_installed(monkeypatch):
    """Thiếu tessdata 'vie' thì chỉ dùng 'eng' thay vì ném lỗi Tesseract -> API 500."""
    from app.modules.ocr import engine

    class FakeTess:
        @staticmethod
        def get_languages(config=""):
            return ["eng", "osd"]

    monkeypatch.setattr(engine, "_tess_langs", None)
    monkeypatch.setattr(engine.settings, "OCR_LANG", "vie+eng")
    assert engine._resolve_tess_lang(FakeTess) == "eng"
    monkeypatch.setattr(engine, "_tess_langs", None)
    monkeypatch.setattr(engine.settings, "OCR_LANG", "vie")
    with pytest.raises(OcrError):
        engine._resolve_tess_lang(FakeTess)
    monkeypatch.setattr(engine, "_tess_langs", None)
