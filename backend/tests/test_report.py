"""T05E180: báo cáo chi tiêu theo thời gian / danh mục (chỉ hóa đơn SETTLED)."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.core.db import SessionLocal
from app.models import Receipt, SplitDetail
from app.modules.dashboard.report import default_range, pick_granularity
from tests.conftest import register


def _receipt(db, *, group_id, uploader, total, when, category=None, merchant=None, status="SETTLED", shares=None):
    r = Receipt(group_id=group_id, uploaded_by=uploader, payer_id=uploader if group_id else None, image_path="x.jpg",
                merchant_name=merchant, receipt_date=when, category=category, subtotal=D(total), total_amount=D(total),
                status=status, ocr_status="DONE")
    db.add(r)
    db.flush()
    for uid, amt in (shares or {}).items():
        db.add(SplitDetail(receipt_id=r.id, user_id=uid, item_amount=D(amt), fee_amount=D(0), final_amount=D(amt)))
    return r


@pytest.fixture()
def data(client):
    ha, hb, hx = (register(client, f"{n}@x.vn", f"Người {n}") for n in "abx")
    me_a = client.get("/api/auth/me", headers=ha).json()["id"]
    me_b = client.get("/api/auth/me", headers=hb).json()["id"]
    gid = client.post("/api/groups", json={"name": "Nhóm"}, headers=ha).json()["id"]
    client.post(f"/api/groups/{gid}/members", json={"email": "b@x.vn"}, headers=ha)
    with SessionLocal() as db:
        _receipt(db, group_id=gid, uploader=me_a, total=100000, when=date(2026, 9, 5), category="Ăn uống",
                 merchant="Phở Hòa", shares={me_a: 60000, me_b: 40000})
        _receipt(db, group_id=gid, uploader=me_a, total=200000, when=date(2026, 10, 20), category="Đi lại",
                 merchant="Grab", shares={me_a: 50000, me_b: 150000})
        _receipt(db, group_id=gid, uploader=me_a, total=999000, when=date(2026, 10, 21), category="Ăn uống",
                 status="VERIFIED")  # chưa chốt -> không tính
        _receipt(db, group_id=None, uploader=me_a, total=30000, when=date(2026, 10, 2), merchant="Phở Hòa")  # cá nhân, không danh mục
        _receipt(db, group_id=None, uploader=me_b, total=77000, when=date(2026, 10, 2))  # cá nhân của B
        db.commit()
    return {"ha": ha, "hb": hb, "hx": hx, "gid": gid}


def q(client, h, **params):
    return client.get("/api/dashboard/report", headers=h, params={"date_from": "2026-09-01", "date_to": "2026-10-31", **params})


def test_me_scope_counts_my_share_and_personal_only_settled(client, data):
    r = q(client, data["ha"], granularity="month").json()
    assert r["granularity"] == "month" and r["scope"] == "me"
    assert [(p["key"], int(float(p["total"]))) for p in r["periods"]] == [("2026-09", 60000), ("2026-10", 80000)]
    assert int(float(r["total"])) == 140000 and r["receipt_count"] == 3
    cats = {c["category"]: (int(float(c["total"])), c["percent"]) for c in r["by_category"]}
    assert cats == {"Ăn uống": (60000, 42.9), "Đi lại": (50000, 35.7), "Khác": (30000, 21.4)}
    assert r["top_merchants"][0]["merchant"] == "Phở Hòa" and int(float(r["top_merchants"][0]["total"])) == 90000


def test_group_scope_uses_receipt_totals_without_personal(client, data):
    r = q(client, data["ha"], scope="group", granularity="month").json()
    assert int(float(r["total"])) == 300000 and r["receipt_count"] == 2
    oct_ = r["periods"][1]
    assert {k: int(float(v)) for k, v in oct_["by_category"].items()} == {"Đi lại": 200000}


def test_group_filter_excludes_personal_and_checks_membership(client, data):
    r = q(client, data["hb"], group_id=data["gid"]).json()
    assert int(float(r["total"])) == 190000  # 40k + 150k, không có hóa đơn cá nhân 77k
    assert q(client, data["hx"], group_id=data["gid"]).status_code == 403
    assert q(client, data["ha"], group_id=9999).status_code == 404


def test_periods_cover_whole_range_with_zeros(client, data):
    r = client.get("/api/dashboard/report", headers=data["ha"],
                   params={"date_from": "2026-10-01", "date_to": "2026-10-07", "granularity": "auto"}).json()
    assert r["granularity"] == "day" and len(r["periods"]) == 7
    assert [int(float(p["total"])) for p in r["periods"]][1] == 30000  # 02/10: hóa đơn cá nhân
    assert sum(int(float(p["total"])) for p in r["periods"]) == 30000


def test_week_buckets_start_monday_and_clip_to_range(client, data):
    r = q(client, data["ha"], granularity="week").json()
    first = r["periods"][0]
    assert first["start"] == "2026-09-01" and first["end"] == "2026-09-06"  # 01/09/2026 là thứ Ba
    assert r["periods"][-1]["end"] == "2026-10-31"


def test_invalid_range_422_and_auth(client, data):
    r = client.get("/api/dashboard/report", headers=data["ha"], params={"date_from": "2026-10-10", "date_to": "2026-10-01"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "date_from"
    r = client.get("/api/dashboard/report", headers=data["ha"], params={"date_from": "2023-01-01", "date_to": "2026-10-01"})
    assert r.status_code == 422
    assert client.get("/api/dashboard/report").status_code == 401


def test_empty_report_and_defaults(client):
    h = register(client, "new@x.vn", "Người mới")
    r = client.get("/api/dashboard/report", headers=h).json()
    assert int(float(r["total"])) == 0 and r["by_category"] == [] and r["top_merchants"] == []
    assert len(r["periods"]) >= 6 and all(int(float(p["total"])) == 0 for p in r["periods"])


def test_helpers():
    assert default_range(date(2026, 3, 15)) == (date(2025, 10, 1), date(2026, 3, 15))
    assert pick_granularity(date(2026, 1, 1), date(2026, 1, 31), "auto") == "day"
    assert pick_granularity(date(2026, 1, 1), date(2026, 3, 31), "auto") == "week"
    assert pick_granularity(date(2026, 1, 1), date(2026, 12, 31), "auto") == "month"
    assert pick_granularity(date(2026, 1, 1), date(2026, 12, 31), "day") == "day"
