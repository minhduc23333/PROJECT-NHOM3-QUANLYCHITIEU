"""Test API Dashboard (T05E17D): chỉ tính SETTLED, đúng phạm vi quyền, trả 0 khi trống."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Debt, GroupMember, Receipt, SplitDetail, User
from tests.conftest import register

D = Decimal


def _uid(email):
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.email == email))


def _receipt(group_id, uploader, status="SETTLED", total="300000", splits=None, **kw):
    """Tạo thẳng vào DB. splits = {user_id: final_amount}."""
    with SessionLocal() as db:
        r = Receipt(
            group_id=group_id, uploaded_by=uploader, image_path="x.jpg", status=status,
            total_amount=D(total), subtotal=D(total), receipt_date=kw.pop("receipt_date", date.today()), **kw,
        )
        db.add(r)
        db.flush()
        for uid, amount in (splits or {}).items():
            db.add(SplitDetail(receipt_id=r.id, user_id=uid, item_amount=D(amount), fee_amount=D(0), final_amount=D(amount)))
        db.commit()
        return r.id


def _summary(client, headers):
    r = client.get("/api/dashboard/summary", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def team(client):
    """Nhóm gồm A (leader), B, C; X là người ngoài nhóm."""
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "ABCX"}
    gid = client.post("/api/groups", json={"name": "Nhóm"}, headers=h["A"]).json()["id"]
    for n in "BC":
        assert client.post(f"/api/groups/{gid}/members", json={"email": f"{n.lower()}@x.vn"}, headers=h["A"]).status_code == 201
    return {"h": h, "gid": gid, "uid": {n: _uid(f"{n.lower()}@x.vn") for n in "ABCX"}}


def test_requires_login(client):
    assert client.get("/api/dashboard/summary").status_code == 401


def test_empty_returns_zero(client):
    h = register(client)
    s = _summary(client, h)
    for key in ("personal_spent", "group_spent", "i_owe", "owed_to_me"):
        assert D(s[key]) == 0, key
    assert s["group_count"] == 0 and s["receipt_count"] == 0
    assert len(s["monthly"]) == 6 and all(D(m["total"]) == 0 for m in s["monthly"])
    assert s["by_category"] == [] and s["recent_receipts"] == []


def test_only_settled_receipts_are_counted(client, team):
    u = team["uid"]
    split = {u["A"]: "100000", u["B"]: "100000", u["C"]: "100000"}
    _receipt(team["gid"], u["A"], "SETTLED", "300000", split)
    _receipt(team["gid"], u["A"], "VERIFIED", "999999", split)
    _receipt(team["gid"], u["A"], "DRAFT", "888888")

    a = _summary(client, team["h"]["A"])
    assert a["group_count"] == 1 and a["receipt_count"] == 1
    assert D(a["group_spent"]) == 300000          # Σ total_amount, chỉ SETTLED
    assert D(a["personal_spent"]) == 100000       # Σ final_amount của riêng A
    assert len(a["recent_receipts"]) == 1
    assert D(a["recent_receipts"][0]["my_amount"]) == 100000
    assert a["recent_receipts"][0]["group_name"] == "Nhóm"
    # thành viên khác: chung chi tiêu nhóm nhưng phần cá nhân của mình
    b = _summary(client, team["h"]["B"])
    assert D(b["group_spent"]) == 300000 and D(b["personal_spent"]) == 100000


def test_unequal_split_gives_each_member_own_amount(client, team):
    u = team["uid"]
    _receipt(team["gid"], u["A"], total="300000", splits={u["A"]: "150000", u["B"]: "100000", u["C"]: "50000"})
    assert D(_summary(client, team["h"]["B"])["personal_spent"]) == 100000
    assert D(_summary(client, team["h"]["C"])["personal_spent"]) == 50000


def test_member_who_did_not_join_split_sees_zero_personal(client, team):
    u = team["uid"]
    _receipt(team["gid"], u["A"], total="200000", splits={u["A"]: "100000", u["B"]: "100000"})
    c = _summary(client, team["h"]["C"])
    assert D(c["personal_spent"]) == 0 and D(c["group_spent"]) == 200000
    assert D(c["recent_receipts"][0]["my_amount"]) == 0


def test_outsider_sees_nothing_from_other_groups(client, team):
    u = team["uid"]
    _receipt(team["gid"], u["A"], total="300000", splits={u["A"]: "300000"})
    x = _summary(client, team["h"]["X"])
    assert x["group_count"] == 0 and x["receipt_count"] == 0
    assert D(x["group_spent"]) == 0 and D(x["personal_spent"]) == 0 and x["recent_receipts"] == []


def test_removed_member_loses_access_to_group_numbers(client, team):
    u = team["uid"]
    _receipt(team["gid"], u["A"], total="300000", splits={u["A"]: "150000", u["C"]: "150000"})
    with SessionLocal() as db:
        db.get(GroupMember, (team["gid"], u["C"])).status = "REMOVED"
        db.commit()
    c = _summary(client, team["h"]["C"])
    assert c["group_count"] == 0 and c["receipt_count"] == 0
    assert D(c["group_spent"]) == 0 and D(c["personal_spent"]) == 0 and c["recent_receipts"] == []


def test_personal_receipt_counts_only_for_owner_and_only_when_settled(client, team):
    u = team["uid"]
    _receipt(None, u["A"], "SETTLED", "50000", category="Ăn uống")
    _receipt(None, u["A"], "DRAFT", "70000")
    a = _summary(client, team["h"]["A"])
    assert a["receipt_count"] == 1 and D(a["personal_spent"]) == 50000
    assert D(a["group_spent"]) == 0                     # hóa đơn cá nhân không thuộc chi tiêu nhóm
    assert a["recent_receipts"][0]["group_id"] is None
    b = _summary(client, team["h"]["B"])                # người khác không thấy hóa đơn cá nhân của A
    assert b["receipt_count"] == 0 and D(b["personal_spent"]) == 0


def test_chart_data_by_month_and_category(client, team):
    u = team["uid"]
    today = date.today()
    _receipt(None, u["A"], total="60000", category="Ăn uống")
    _receipt(None, u["A"], total="40000", category="Ăn uống")
    _receipt(None, u["A"], total="30000")                          # chưa có danh mục -> "Khác"
    _receipt(None, u["A"], total="10000", category="Di chuyển")
    a = _summary(client, team["h"]["A"])
    assert [(c["category"], D(c["total"])) for c in a["by_category"]] == [
        ("Ăn uống", D(100000)), ("Khác", D(30000)), ("Di chuyển", D(10000)),
    ]
    this_month = f"{today.year:04d}-{today.month:02d}"
    assert a["monthly"][-1]["month"] == this_month and D(a["monthly"][-1]["total"]) == 140000
    assert D(a["personal_spent"]) == 140000


def test_receipt_older_than_six_months_in_total_but_not_in_chart(client, team):
    u = team["uid"]
    _receipt(None, u["A"], total="80000", receipt_date=date(2020, 1, 15))
    a = _summary(client, team["h"]["A"])
    assert D(a["personal_spent"]) == 80000
    assert all(D(m["total"]) == 0 for m in a["monthly"])


def test_open_debts_only(client, team):
    u = team["uid"]
    rid = _receipt(team["gid"], u["A"], total="300000", splits={u["A"]: "100000", u["B"]: "200000"})
    with SessionLocal() as db:
        db.add(Debt(receipt_id=rid, debtor_id=u["B"], creditor_id=u["A"], amount=D(200000), status="OPEN"))
        db.add(Debt(receipt_id=rid, debtor_id=u["C"], creditor_id=u["A"], amount=D(50000), status="PAID"))
        db.commit()
    assert D(_summary(client, team["h"]["B"])["i_owe"]) == 200000
    a = _summary(client, team["h"]["A"])
    assert D(a["owed_to_me"]) == 200000 and D(a["i_owe"]) == 0
