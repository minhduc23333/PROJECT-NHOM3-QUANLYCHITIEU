from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import GroupMember, Receipt, ReceiptItem, User
from tests.conftest import register


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}


def test_frontend_routes_support_direct_navigation(client):
    paths = (
        "/login",
        "/register",
        "/groups",
        "/groups/1",
        "/receipts",
        "/debts",
        "/dev/ui",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert "<!doctype html>" in response.text.lower()


def test_register_login_me(client):
    h = register(client)
    assert client.get("/api/auth/me", headers=h).json()["email"] == "a@x.vn"
    r = client.post("/api/auth/login", json={"email": "A@X.vn", "password": "123456"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_duplicate_email_409(client):
    register(client)
    r = client.post("/api/auth/register", json={"full_name": "B b", "email": "a@x.vn", "password": "123456"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_401_format(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer sai"})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "a@x.vn", "password": "sai"})
    assert r.status_code == 401


def test_422_format(client):
    r = client.post("/api/auth/register", json={"full_name": "A", "email": "khong-phai-email", "password": "1"})
    body = r.json()["error"]
    assert r.status_code == 422 and body["code"] == "VALIDATION_ERROR"
    assert {d["field"] for d in body["details"]} == {"full_name", "email", "password"}


def test_403_and_404(client):
    ha = register(client, "a@x.vn")
    hb = register(client, "b@x.vn", "Người B")
    gid = client.post("/api/groups", json={"name": "Nhóm A"}, headers=ha).json()["id"]

    assert client.get(f"/api/groups/{gid}", headers=ha).status_code == 200
    r = client.get(f"/api/groups/{gid}", headers=hb)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    r = client.get("/api/groups/9999", headers=ha)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/khong-ton-tai")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_groups_and_dashboard(client):
    h = register(client)
    client.post("/api/groups", json={"name": "Nhóm 1"}, headers=h)
    groups = client.get("/api/groups", headers=h).json()
    assert groups[0]["my_role"] == "LEADER" and groups[0]["member_count"] == 1
    s = client.get("/api/dashboard/summary", headers=h).json()
    assert s["group_count"] == 1 and len(s["monthly"]) == 6


def test_leader_can_add_and_list_group_members(client):
    leader = register(client, "leader@x.vn")
    member = register(client, "member@x.vn", "Người B")
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=leader).json()["id"]

    added = client.post(
        f"/api/groups/{group_id}/members",
        json={"email": "MEMBER@x.vn"},
        headers=leader,
    )
    assert added.status_code == 201
    assert added.json() == {
        "user_id": 2,
        "full_name": "Người B",
        "email": "member@x.vn",
        "role": "MEMBER",
        "status": "ACTIVE",
    }

    members = client.get(f"/api/groups/{group_id}/members", headers=member).json()
    assert [entry["email"] for entry in members] == ["leader@x.vn", "member@x.vn"]


def test_adding_group_members_enforces_rbac_and_rejects_missing_or_duplicate(client):
    leader = register(client, "leader@x.vn")
    member = register(client, "member@x.vn", "Người B")
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=leader).json()["id"]

    denied = client.post(
        f"/api/groups/{group_id}/members",
        json={"email": "member@x.vn"},
        headers=member,
    )
    assert denied.status_code == 403

    missing = client.post(
        f"/api/groups/{group_id}/members",
        json={"email": "unknown@x.vn"},
        headers=leader,
    )
    assert missing.status_code == 404

    assert client.post(
        f"/api/groups/{group_id}/members",
        json={"email": "member@x.vn"},
        headers=leader,
    ).status_code == 201
    duplicate = client.post(
        f"/api/groups/{group_id}/members",
        json={"email": "MEMBER@x.vn"},
        headers=leader,
    )
    assert duplicate.status_code == 409


def test_swagger_has_bearer(client):
    spec = client.get("/openapi.json").json()
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    assert client.get("/docs").status_code == 200


def test_auth_routes_appear_once_under_api_prefix(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/auth/register" in paths
    assert "/api/auth/login" in paths
    assert "/auth/register" not in paths
    assert "/auth/login" not in paths


# ---------- Bản nháp hóa đơn, CRUD dòng món, xác nhận (Receipt tạo thẳng vào DB vì API upload làm riêng) ----------
def _user_id(email):
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def _make_receipt(group_id, uploader_id, **kw):
    with SessionLocal() as db:
        r = Receipt(group_id=group_id, uploaded_by=uploader_id, image_path="x.jpg", status="DRAFT", **kw)
        db.add(r)
        db.commit()
        return r.id


@pytest.fixture()
def setup(client):
    """leader (L), uploader (U, MEMBER), other (O, MEMBER), outsider (X, không thuộc nhóm)."""
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "LUOX"}
    gid = client.post("/api/groups", json={"name": "Nhóm"}, headers=h["L"]).json()["id"]
    for n in "UO":
        assert client.post(f"/api/groups/{gid}/members", json={"email": f"{n.lower()}@x.vn"}, headers=h["L"]).status_code == 201
    uid = {n: _user_id(f"{n.lower()}@x.vn") for n in "LUOX"}
    rid = _make_receipt(
        gid, uid["U"], merchant_name="Quán A",
        subtotal=Decimal("0"), tax_amount=Decimal("0"), service_fee=Decimal("0"), total_amount=Decimal("0"),
    )
    return {"h": h, "gid": gid, "uid": uid, "rid": rid}


def _item(client, s, who="U", **body):
    body = {"item_name": "Bún bò", "quantity": "2", "unit_price": "45000", **body}
    return client.post(f"/api/receipts/{s['rid']}/items", json=body, headers=s["h"][who])


def _fields(r):
    return {d["field"] for d in r.json()["error"]["details"]}


# ---------- Xem bản nháp ----------
def test_get_receipt_detail_with_items_and_permissions(client, setup):
    _item(client, setup)
    r = client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["O"])
    assert r.status_code == 200
    body = r.json()
    assert body["merchant_name"] == "Quán A" and body["status"] == "DRAFT"
    assert len(body["items"]) == 1 and Decimal(body["items"][0]["line_total"]) == Decimal("90000")
    assert Decimal(body["items_total"]) == Decimal("90000")
    assert body["can_edit_receipt"] is False and body["can_edit_items"] is False  # O không phải người tải/Leader
    mine = client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["U"]).json()
    assert mine["can_edit_receipt"] is True and mine["can_edit_items"] is True
    lead = client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["L"]).json()
    assert lead["can_edit_receipt"] is False and lead["can_edit_items"] is True


def test_get_receipt_404_403_401(client, setup):
    assert client.get("/api/receipts/9999", headers=setup["h"]["U"]).status_code == 404
    assert client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["X"]).status_code == 403
    assert client.get(f"/api/receipts/{setup['rid']}").status_code == 401


# ---------- Sửa thông tin OCR ----------
def test_only_uploader_edits_receipt_header(client, setup):
    url = f"/api/receipts/{setup['rid']}"
    r = client.patch(url, json={"merchant_name": " Quán B ", "total_amount": "100000"}, headers=setup["h"]["U"])
    assert r.status_code == 200 and r.json()["merchant_name"] == "Quán B"
    assert Decimal(r.json()["total_amount"]) == Decimal("100000")
    assert Decimal(r.json()["subtotal"]) == 0  # trường không gửi giữ nguyên
    # Leader cũng không được sửa phần OCR
    assert client.patch(url, json={"merchant_name": "Z"}, headers=setup["h"]["L"]).status_code == 403
    assert client.patch(url, json={"merchant_name": "Z"}, headers=setup["h"]["X"]).status_code == 403
    assert client.patch(url, json={"total_amount": "-1"}, headers=setup["h"]["U"]).status_code == 422


# ---------- CRUD dòng món ----------
def test_add_item_auto_and_explicit_line_total(client, setup):
    r = _item(client, setup)
    assert r.status_code == 201 and Decimal(r.json()["line_total"]) == Decimal("90000")
    r = _item(client, setup, quantity="1.5", unit_price="10000", line_total="15000")
    assert r.status_code == 201 and Decimal(r.json()["line_total"]) == Decimal("15000")


def test_add_item_wrong_line_total_422(client, setup):
    r = _item(client, setup, line_total="1")
    assert r.status_code == 422 and _fields(r) == {"line_total"}
    r = _item(client, setup, quantity="0")
    assert r.status_code == 422
    r = _item(client, setup, item_name="  ")
    assert r.status_code == 422
    assert client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["U"]).json()["items"] == []


def test_item_permissions_uploader_or_leader(client, setup):
    assert _item(client, setup, "U").status_code == 201
    assert _item(client, setup, "L").status_code == 201
    assert _item(client, setup, "O").status_code == 403
    assert _item(client, setup, "X").status_code == 403


def test_update_item_recomputes_and_validates(client, setup):
    item = _item(client, setup).json()
    url = f"/api/receipts/{setup['rid']}/items/{item['id']}"
    r = client.patch(url, json={"quantity": "3"}, headers=setup["h"]["L"])
    assert r.status_code == 200 and Decimal(r.json()["line_total"]) == Decimal("135000")
    r = client.patch(url, json={"unit_price": "50000", "line_total": "150000"}, headers=setup["h"]["U"])
    assert r.status_code == 200 and Decimal(r.json()["line_total"]) == Decimal("150000")
    r = client.patch(url, json={"line_total": "5"}, headers=setup["h"]["U"])
    assert r.status_code == 422 and _fields(r) == {"line_total"}
    r = client.patch(url, json={"item_name": "Bún chả"}, headers=setup["h"]["U"])
    assert r.status_code == 200 and r.json()["item_name"] == "Bún chả"
    assert Decimal(r.json()["line_total"]) == Decimal("150000")  # chỉ đổi tên thì không đụng tiền
    assert client.patch(url, json={"item_name": "Z"}, headers=setup["h"]["O"]).status_code == 403
    assert client.patch(f"/api/receipts/{setup['rid']}/items/9999", json={"item_name": "Z"}, headers=setup["h"]["U"]).status_code == 404


def test_delete_item(client, setup):
    item = _item(client, setup).json()
    url = f"/api/receipts/{setup['rid']}/items/{item['id']}"
    assert client.delete(url, headers=setup["h"]["O"]).status_code == 403
    assert client.delete(url, headers=setup["h"]["L"]).status_code == 204
    assert client.delete(url, headers=setup["h"]["L"]).status_code == 404


def test_item_of_other_receipt_is_404(client, setup):
    other_rid = _make_receipt(setup["gid"], setup["uid"]["U"])
    item = _item(client, setup).json()
    r = client.patch(f"/api/receipts/{other_rid}/items/{item['id']}", json={"item_name": "Z"}, headers=setup["h"]["U"])
    assert r.status_code == 404


# ---------- Xác nhận ----------
def _ready(client, setup, tax="10000", fee="5000", total="105000"):
    """1 món 90.000 + thêm món 0 -> subtotal 90.000"""
    assert _item(client, setup).status_code == 201
    client.patch(
        f"/api/receipts/{setup['rid']}",
        json={"subtotal": "90000", "tax_amount": tax, "service_fee": fee, "total_amount": total},
        headers=setup["h"]["U"],
    )


def _verify(client, setup, payer="U", who="U"):
    return client.post(
        f"/api/receipts/{setup['rid']}/verify", json={"payer_id": setup["uid"][payer]}, headers=setup["h"][who]
    )


def test_verify_ok_sets_payer_and_status(client, setup):
    _ready(client, setup)
    r = _verify(client, setup, payer="O", who="L")  # Leader xác nhận, O là người trả
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "VERIFIED" and r.json()["payer_id"] == setup["uid"]["O"]
    assert r.json()["can_edit_items"] is True  # VERIFIED vẫn sửa được (sẽ quay về DRAFT nếu ảnh hưởng chia tiền)
    # Đã VERIFIED thì không xác nhận lại được
    assert _verify(client, setup).status_code == 409
    # Dashboard bắt đầu có số liệu cho người trả
    s = client.get("/api/dashboard/summary", headers=setup["h"]["O"]).json()
    assert Decimal(s["total_spent"]) == Decimal("105000")
    # Sửa thông tin không ảnh hưởng chia tiền: vẫn VERIFIED; thêm món: quay về DRAFT
    url = f"/api/receipts/{setup['rid']}"
    assert client.patch(url, json={"merchant_name": "Z"}, headers=setup["h"]["U"]).json()["status"] == "VERIFIED"
    assert _item(client, setup).status_code == 201
    assert client.get(url, headers=setup["h"]["U"]).json()["status"] == "DRAFT"


def test_verify_wrong_total_422_stays_draft(client, setup):
    _ready(client, setup, total="999")
    r = _verify(client, setup)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _fields(r) == {"total_amount"}
    d = client.get(f"/api/receipts/{setup['rid']}", headers=setup["h"]["U"]).json()
    assert d["status"] == "DRAFT" and d["payer_id"] is None


def test_verify_wrong_subtotal_and_missing_fields(client, setup):
    assert _item(client, setup).status_code == 201
    client.patch(f"/api/receipts/{setup['rid']}", json={"subtotal": "1", "total_amount": "1"}, headers=setup["h"]["U"])
    assert _fields(_verify(client, setup)) == {"subtotal"}  # total = 1 + 0 + 0 khớp, chỉ subtotal sai


def test_verify_requires_items_and_collects_all_errors(client, setup):
    r = _verify(client, setup, payer="X")  # chưa có món + payer ngoài nhóm
    assert r.status_code == 422 and {"payer_id", "items"} <= _fields(r)


def test_verify_null_tax_and_fee_count_as_zero(client, setup):
    assert _item(client, setup).status_code == 201
    with SessionLocal() as db:
        rc = db.get(Receipt, setup["rid"])
        rc.subtotal, rc.tax_amount, rc.service_fee, rc.total_amount = Decimal("90000"), None, None, Decimal("90000")
        db.commit()
    assert _verify(client, setup).status_code == 200


def test_verify_payer_must_be_active_member(client, setup):
    _ready(client, setup)
    assert _verify(client, setup, payer="X").status_code == 422
    with SessionLocal() as db:
        gm = db.get(GroupMember, (setup["gid"], setup["uid"]["O"]))
        gm.status = "REMOVED"
        db.commit()
    assert _verify(client, setup, payer="O").status_code == 422


def test_verify_permissions_and_flags_bad_line(client, setup):
    _ready(client, setup)
    assert _verify(client, setup, who="O").status_code == 403
    assert _verify(client, setup, who="X").status_code == 403
    with SessionLocal() as db:  # dòng món sai do OCR đưa vào
        db.add(ReceiptItem(receipt_id=setup["rid"], item_name="Lỗi", quantity=Decimal("1"),
                           unit_price=Decimal("10"), line_total=Decimal("99")))
        db.commit()
    r = _verify(client, setup)
    assert r.status_code == 422 and "items" in _fields(r)
