"""Thời gian phản hồi API < 2 giây (T05E186) trên dữ liệu cỡ vừa: 60 hóa đơn đã chốt, mỗi hóa đơn 8 món, 3 người chia, có công nợ.

Chạy trên SQLite trong bộ nhớ nên chỉ bắt các lỗi truy vấn N+1 / vòng lặp chậm do code.
Muốn đo trên MySQL thật + server thật: python -m scripts.check_api_latency
"""
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Debt, Receipt, ReceiptItem, SplitDetail, User
from tests.conftest import register

LIMIT_SEC = 2.0
D = Decimal


@pytest.fixture()
def loaded(client):
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "ABC"}
    gid = client.post("/api/groups", json={"name": "Nhóm lớn"}, headers=h["A"]).json()["id"]
    for n in "BC":
        client.post(f"/api/groups/{gid}/members", json={"email": f"{n.lower()}@x.vn"}, headers=h["A"])
    with SessionLocal() as db:
        uid = {n: db.scalar(select(User.id).where(User.email == f"{n.lower()}@x.vn")) for n in "ABC"}
        first = None
        for k in range(60):
            r = Receipt(group_id=gid, uploaded_by=uid["A"], payer_id=uid["A"], image_path="x.jpg", status="SETTLED",
                        merchant_name=f"Quán {k}", category="Ăn uống", total_amount=D(240000), subtotal=D(240000),
                        receipt_date=date.today() - timedelta(days=k * 3))
            db.add(r)
            db.flush()
            first = first or r.id
            for i in range(8):
                db.add(ReceiptItem(receipt_id=r.id, item_name=f"Món {i}", quantity=D(1), unit_price=D(30000), line_total=D(30000)))
            for u in uid.values():
                db.add(SplitDetail(receipt_id=r.id, user_id=u, item_amount=D(80000), fee_amount=D(0), final_amount=D(80000)))
            db.add(Debt(receipt_id=r.id, debtor_id=uid["B"], creditor_id=uid["A"], amount=D(80000), status="OPEN"))
        db.commit()
    return {"h": h, "gid": gid, "rid": first}


def _timed(client, method, url, **kw):
    t0 = time.perf_counter()
    res = getattr(client, method)(url, **kw)
    return res, time.perf_counter() - t0


def test_main_endpoints_respond_under_2_seconds(client, loaded):
    h, gid, rid = loaded["h"]["A"], loaded["gid"], loaded["rid"]
    endpoints = [
        ("get", "/api/auth/me"),
        ("get", "/api/dashboard/summary"),
        ("get", "/api/groups"),
        ("get", f"/api/groups/{gid}"),
        ("get", f"/api/groups/{gid}/receipts"),
        ("get", f"/api/groups/{gid}/debts"),
        ("get", f"/api/receipts/{rid}"),
        ("get", f"/api/receipts/{rid}/selections"),
        ("get", f"/api/receipts/{rid}/debts"),
        ("get", "/api/receipts/category-suggestion?merchant_name=Highlands"),
    ]
    client.get("/api/auth/me", headers=h)  # khởi động nguội (import, kết nối) không tính vào số đo
    slow = []
    for method, url in endpoints:
        res, dt = _timed(client, method, url, headers=h)
        assert res.status_code == 200, f"{url}: {res.status_code} {res.text[:200]}"
        if dt >= LIMIT_SEC:
            slow.append(f"{url}: {dt:.2f}s")
    assert not slow, "API chậm hơn 2s: " + "; ".join(slow)


def test_login_under_2_seconds(client, loaded):
    res, dt = _timed(client, "post", "/api/auth/login", json={"email": "a@x.vn", "password": "123456"})
    assert res.status_code == 200 and dt < LIMIT_SEC, f"login {dt:.2f}s"
