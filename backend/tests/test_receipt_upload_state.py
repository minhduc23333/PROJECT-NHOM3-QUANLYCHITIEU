"""Test cho: (1) API tải ảnh + kiểm tra file, (2) máy trạng thái DRAFT → VERIFIED → SETTLED."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Debt, GroupMember, Receipt, SplitDetail
from tests.conftest import register

JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture()
def upload_dir(monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _upload(client, headers, gid, data=JPG, name="a.jpg", mime="image/jpeg"):
    return client.post(f"/api/groups/{gid}/receipts", headers=headers, files={"file": (name, data, mime)})


@pytest.fixture()
def team(client, upload_dir):
    """leader (L), member (M), outsider (X)."""
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "LMX"}
    gid = client.post("/api/groups", json={"name": "N"}, headers=h["L"]).json()["id"]
    assert client.post(f"/api/groups/{gid}/members", json={"email": "m@x.vn"}, headers=h["L"]).status_code == 201
    return {"h": h, "gid": gid, "dir": upload_dir}


# ---------------- Upload ----------------
def test_upload_accepts_jpg_and_png_by_magic_bytes(client, team):
    jpg = _upload(client, team["h"]["L"], team["gid"], JPG)
    png = _upload(client, team["h"]["L"], team["gid"], PNG, "x.jpg", "image/jpeg")  # đuôi/MIME nói dối
    assert jpg.status_code == png.status_code == 201
    assert sorted(p.suffix for p in team["dir"].iterdir()) == [".jpg", ".png"]


@pytest.mark.parametrize("data", [b"", b"GIF89a....", b"%PDF-1.4", b"<html>", b"\xff\xd8", b"\x89PNG"])
def test_upload_rejects_non_image_content_even_with_image_mime(client, team, data):
    r = _upload(client, team["h"]["L"], team["gid"], data, "a.jpg", "image/jpeg")
    assert r.status_code == 400
    assert list(team["dir"].iterdir()) == []


def test_upload_size_limit_boundary(client, team):
    exactly = JPG + b"x" * (5 * 1024 * 1024 - len(JPG))
    assert _upload(client, team["h"]["L"], team["gid"], exactly).status_code == 201
    assert _upload(client, team["h"]["L"], team["gid"], exactly + b"x").status_code == 413
    assert len(list(team["dir"].iterdir())) == 1  # ảnh quá cỡ không bị lưu


def test_upload_requires_active_member(client, team):
    assert _upload(client, team["h"]["X"], team["gid"]).status_code == 403        # người ngoài
    assert _upload(client, team["h"]["L"], 9999).status_code == 404               # nhóm không tồn tại
    assert client.post(f"/api/groups/{team['gid']}/receipts", files={"file": ("a.jpg", JPG)}).status_code == 401
    with SessionLocal() as db:  # thành viên đã bị gỡ (không còn ACTIVE)
        gm = db.scalar(select(GroupMember).where(GroupMember.group_id == team["gid"], GroupMember.user_id == 2))
        gm.status = "REMOVED"
        db.commit()
    assert _upload(client, team["h"]["M"], team["gid"]).status_code == 403
    assert list(team["dir"].iterdir()) == []


def test_upload_non_member_gets_403_before_size_check(client, team):
    too_big = JPG + b"x" * (5 * 1024 * 1024)
    assert _upload(client, team["h"]["X"], team["gid"], too_big).status_code == 403


def test_upload_creates_draft_pending_without_running_ocr(client, team, monkeypatch):
    from app.modules.ocr import service as ocr_service

    def boom(*a, **k):
        raise AssertionError("upload không được tự gọi OCR")

    monkeypatch.setattr(ocr_service, "extract", boom)
    r = _upload(client, team["h"]["M"], team["gid"]).json()
    assert (r["status"], r["ocr_status"], r["uploaded_by"], r["group_id"]) == ("DRAFT", "PENDING", 2, team["gid"])
    assert "image_path" not in r  # không lộ đường dẫn file trên server
    with SessionLocal() as db:
        assert db.get(Receipt, r["id"]).status == "DRAFT"


def test_upload_file_removed_when_db_write_fails(client, team, monkeypatch):
    from sqlalchemy.orm import Session

    def fail(self):
        raise RuntimeError("db down")

    monkeypatch.setattr(Session, "commit", fail)
    assert _upload(client, team["h"]["L"], team["gid"]).status_code == 500
    assert list(team["dir"].iterdir()) == []


# ---------------- Máy trạng thái ----------------
def _draft(client, team, who="L"):
    """Hóa đơn DRAFT hợp lệ sẵn sàng verify: 1 món 100.000, tổng 100.000."""
    r = _upload(client, team["h"][who], team["gid"]).json()
    url = f"/api/receipts/{r['id']}"
    assert client.post(f"{url}/items", headers=team["h"][who], json={"item_name": "A", "unit_price": "100000"}).status_code == 201
    assert client.patch(url, headers=team["h"][who], json={"subtotal": "100000", "total_amount": "100000"}).status_code == 200
    return r["id"], url, r["uploaded_by"]


def _status(client, team, url):
    return client.get(url, headers=team["h"]["L"]).json()["status"]


def test_cannot_skip_draft_to_settled_or_verify_twice(client, team):
    rid, url, lid = _draft(client, team)
    r = client.post(f"{url}/settle", headers=team["h"]["L"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert _status(client, team, url) == "DRAFT"
    assert client.post(f"{url}/verify", headers=team["h"]["L"], json={"payer_id": lid}).status_code == 200
    assert client.post(f"{url}/verify", headers=team["h"]["L"], json={"payer_id": lid}).status_code == 409


def test_verified_edits_only_reopen_when_split_inputs_change(client, team):
    rid, url, lid = _draft(client, team)
    L = team["h"]["L"]
    item_id = client.get(url, headers=L).json()["items"][0]["id"]
    verify = lambda: client.post(f"{url}/verify", headers=L, json={"payer_id": lid})  # noqa: E731

    assert verify().status_code == 200
    # không ảnh hưởng chia tiền → giữ VERIFIED
    assert client.patch(url, headers=L, json={"merchant_name": "Quán", "category": "Ăn uống"}).json()["status"] == "VERIFIED"
    assert client.patch(url, headers=L, json={"total_amount": "100000"}).json()["status"] == "VERIFIED"  # cùng giá trị
    assert client.patch(f"{url}/items/{item_id}", headers=L, json={"quantity": "1"}).json() is not None
    assert _status(client, team, url) == "VERIFIED"
    # đổi từng loại dữ liệu chia tiền → về DRAFT
    for field in ("subtotal", "tax_amount", "service_fee", "total_amount"):
        assert _status(client, team, url) == "VERIFIED"
        assert client.patch(url, headers=L, json={field: "1"}).json()["status"] == "DRAFT", field
        client.patch(url, headers=L, json={"subtotal": "100000", "total_amount": "100000", "tax_amount": None, "service_fee": None})
        assert verify().status_code == 200, field
    assert client.patch(f"{url}/items/{item_id}", headers=L, json={"unit_price": "50000"}).status_code == 200
    assert _status(client, team, url) == "DRAFT"


def test_reopen_clears_stale_split_and_open_debts(client, team):
    rid, url, lid = _draft(client, team)
    L = team["h"]["L"]
    assert client.post(f"{url}/verify", headers=L, json={"payer_id": lid}).status_code == 200
    with SessionLocal() as db:
        db.add(SplitDetail(receipt_id=rid, user_id=2, item_amount=Decimal(1), fee_amount=Decimal(0), final_amount=Decimal(1)))
        db.add(Debt(receipt_id=rid, debtor_id=2, creditor_id=1, amount=Decimal(1), status="OPEN"))
        db.commit()
    assert client.patch(url, headers=L, json={"total_amount": "1"}).json()["status"] == "DRAFT"
    with SessionLocal() as db:
        assert db.scalars(select(SplitDetail).where(SplitDetail.receipt_id == rid)).all() == []
        assert db.scalars(select(Debt).where(Debt.receipt_id == rid)).all() == []


def test_paid_debt_blocks_reopen_and_changes_are_rolled_back(client, team):
    rid, url, lid = _draft(client, team)
    L = team["h"]["L"]
    assert client.post(f"{url}/verify", headers=L, json={"payer_id": lid}).status_code == 200
    with SessionLocal() as db:
        db.add(Debt(receipt_id=rid, debtor_id=2, creditor_id=1, amount=Decimal(1), status="PAID"))
        db.commit()
    r = client.patch(url, headers=L, json={"total_amount": "1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_HAS_PAID_DEBT"
    body = client.get(url, headers=L).json()
    assert body["status"] == "VERIFIED" and Decimal(body["total_amount"]) == Decimal("100000")  # không bị ghi dở


def test_settled_is_fully_locked_and_flags(client, team):
    rid, url, lid = _draft(client, team)
    L, M = team["h"]["L"], team["h"]["M"]
    d = client.get(url, headers=L).json()
    assert (d["can_verify"], d["can_settle"], d["is_locked"]) == (True, False, False)
    assert client.get(url, headers=M).json()["can_verify"] is False  # M không phải người tải lên cũng không phải Leader
    d = client.post(f"{url}/verify", headers=L, json={"payer_id": lid}).json()
    assert (d["can_verify"], d["can_settle"], d["is_locked"]) == (False, True, False)
    item_id = d["items"][0]["id"]
    d = client.post(f"{url}/settle", headers=L).json()
    assert d["status"] == "SETTLED" and (d["can_verify"], d["can_settle"], d["is_locked"]) == (False, False, True)

    def locked(r):
        assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_SETTLED", r.text

    locked(client.patch(url, headers=L, json={"merchant_name": "Z"}))
    locked(client.patch(url, headers=L, json={"total_amount": "1"}))
    locked(client.post(f"{url}/items", headers=L, json={"item_name": "Z", "unit_price": "1"}))
    locked(client.patch(f"{url}/items/{item_id}", headers=L, json={"item_name": "Z"}))
    locked(client.delete(f"{url}/items/{item_id}", headers=L))
    locked(client.post(f"{url}/verify", headers=L, json={"payer_id": lid}))
    locked(client.post(f"{url}/settle", headers=L))
    assert _status(client, team, url) == "SETTLED"


def test_ocr_cannot_overwrite_verified_or_settled(client, team):
    rid, url, lid = _draft(client, team)
    L = team["h"]["L"]
    assert client.post(f"{url}/verify", headers=L, json={"payer_id": lid}).status_code == 200
    assert client.post(f"/api/ocr/receipts/{rid}", headers=L).status_code == 409
    assert client.post(f"{url}/settle", headers=L).status_code == 200
    assert client.post(f"/api/ocr/receipts/{rid}", headers=L).status_code == 409


def test_ocr_result_dropped_if_receipt_locked_during_ocr(client, team, monkeypatch):
    """OCR chạy lâu; nếu hóa đơn bị verify ở request khác giữa chừng → không ghi đè."""
    from app.modules.ocr import service as ocr_service
    from app.modules.ocr.parser import parse_receipt

    rid, url, lid = _draft(client, team)
    L = team["h"]["L"]
    with SessionLocal() as db:  # xóa dữ liệu để OCR "có gì đó để ghi"
        r = db.get(Receipt, rid)
        r.ocr_status = "PENDING"
        db.commit()

    def slow_extract(path):
        assert client.post(f"{url}/verify", headers=L, json={"payer_id": lid}).status_code == 200
        parsed = parse_receipt(["QUÁN X", "Phở 1 50.000 50.000", "Tổng cộng 50.000"])

        class Raw:
            text = ""

        return parsed, Raw()

    monkeypatch.setattr(ocr_service, "extract", slow_extract)
    assert client.post(f"/api/ocr/receipts/{rid}", headers=L).status_code == 409
    body = client.get(url, headers=L).json()
    assert body["status"] == "VERIFIED" and Decimal(body["total_amount"]) == Decimal("100000")
    assert [i["item_name"] for i in body["items"]] == ["A"]
