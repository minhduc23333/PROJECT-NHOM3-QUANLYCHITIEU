"""Test 3 API: chọn/bỏ chọn món + tạm tính, chốt chia tiền + tạo công nợ, xem công nợ."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Debt, GroupMember, ItemSelection, Receipt, SplitDetail, User
from app.modules.split import calc
from tests.conftest import register

D = Decimal
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture()
def upload_dir(monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def team(client, upload_dir):
    """L = leader, A, B = thành viên, X = người ngoài nhóm."""
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "LABX"}
    gid = client.post("/api/groups", json={"name": "N"}, headers=h["L"]).json()["id"]
    for n in "AB":
        assert client.post(f"/api/groups/{gid}/members", json={"email": f"{n.lower()}@x.vn"}, headers=h["L"]).status_code == 201
    with SessionLocal() as db:
        uid = {n: db.scalar(select(User.id).where(User.email == f"{n.lower()}@x.vn")) for n in "LABX"}
    return {"h": h, "gid": gid, "uid": uid}


def make_receipt(client, team, items, *, tax="0", fee="0", payer="L", verify=True):
    """items = [(tên, đơn giá, số lượng)] → hóa đơn nhóm (VERIFIED nếu verify). Trả (receipt_id, [item_id])."""
    H = team["h"]["L"]
    rid = client.post(
        f"/api/groups/{team['gid']}/receipts", headers=H, files={"file": ("a.jpg", JPG, "image/jpeg")}
    ).json()["id"]
    ids = []
    for name, price, qty in items:
        r = client.post(
            f"/api/receipts/{rid}/items", headers=H, json={"item_name": name, "unit_price": str(price), "quantity": str(qty)}
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    sub = sum(D(p) * D(q) for _, p, q in items)
    r = client.patch(
        f"/api/receipts/{rid}",
        headers=H,
        json={"subtotal": str(sub), "tax_amount": tax, "service_fee": fee, "total_amount": str(sub + D(tax) + D(fee))},
    )
    assert r.status_code == 200, r.text
    if verify:
        r = client.post(f"/api/receipts/{rid}/verify", headers=H, json={"payer_id": team["uid"][payer]})
        assert r.status_code == 200, r.text
    return rid, ids


def pick(client, team, who, rid, *item_ids):
    for i in item_ids:
        r = client.put(f"/api/receipts/{rid}/items/{i}/selection", headers=team["h"][who])
        assert r.status_code == 200, r.text


def finalize(client, team, rid, who="L"):
    return client.post(f"/api/receipts/{rid}/split", headers=team["h"][who])


# =============== thuật toán thuần ===============
def test_calc_splits_shared_item_equally_and_fee_proportionally():
    shares = calc.compute_shares({1: D(100000), 2: D(50000)}, {1: [10, 11], 2: [10]}, D(15000))
    assert (shares[10].item_amount, shares[10].fee_amount) == (D(100000), D(10000))
    assert (shares[11].item_amount, shares[11].fee_amount) == (D(50000), D(5000))


def test_calc_remainder_goes_to_payer_and_sum_equals_total():
    # 100.000 chia 3 người: 33.333 mỗi người, dư 1 đồng → người trả
    shares = calc.compute_shares({1: D(100000)}, {1: [1, 2, 3]}, D(0))
    assert {s.final_amount for s in shares.values()} == {D(33333)}
    final = calc.assign_remainder(shares, 2, D(100000))
    assert sum(s.final_amount for s in final.values()) == D(100000)
    assert final[2].final_amount == D(33334) and final[1].final_amount == D(33333)


def test_calc_payer_without_items_still_gets_remainder_row():
    shares = calc.compute_shares({1: D(100000)}, {1: [1, 2, 3]}, D(0))
    final = calc.assign_remainder(shares, 99, D(100000))
    assert final[99].item_amount == 0 and final[99].final_amount == D(1)


# =============== API 1: chọn / bỏ chọn ===============
def test_select_deselect_and_provisional_totals(client, team):
    rid, (bun, com) = make_receipt(client, team, [("Bún", 60000, 1), ("Cơm", 40000, 1)], tax="10000")
    H = team["h"]

    s = client.get(f"/api/receipts/{rid}/selections", headers=H["A"]).json()
    assert [m["full_name"] for m in s["members"]] == ["Người A", "Người B", "Người L"]
    assert {u["id"] for u in s["unselected_items"]} == {bun, com}
    assert D(s["items_total"]) == 100000 and D(s["fee_total"]) == 10000 and s["my_selected_item_ids"] == []

    pick(client, team, "A", rid, bun)
    s = client.put(f"/api/receipts/{rid}/items/{com}/selection", headers=H["B"]).json()
    by = {m["user_id"]: m for m in s["members"]}
    a, b = by[team["uid"]["A"]], by[team["uid"]["B"]]
    assert (D(a["item_amount"]), D(a["fee_amount"]), D(a["total"])) == (60000, 6000, 66000)
    assert (D(b["item_amount"]), D(b["fee_amount"]), D(b["total"])) == (40000, 4000, 44000)
    assert s["unselected_items"] == [] and s["my_selected_item_ids"] == [com]

    # bỏ chọn → món quay lại danh sách chưa ai chọn, tạm tính A về 0
    s = client.delete(f"/api/receipts/{rid}/items/{bun}/selection", headers=H["A"]).json()
    assert [u["id"] for u in s["unselected_items"]] == [bun]
    assert D({m["user_id"]: m for m in s["members"]}[team["uid"]["A"]]["total"]) == 0


def test_shared_item_is_split_equally_between_selectors(client, team):
    rid, (pizza,) = make_receipt(client, team, [("Pizza", 90000, 1)])
    pick(client, team, "A", rid, pizza)
    s = client.put(f"/api/receipts/{rid}/items/{pizza}/selection", headers=team["h"]["B"]).json()
    totals = {m["user_id"]: D(m["total"]) for m in s["members"]}
    assert totals[team["uid"]["A"]] == totals[team["uid"]["B"]] == 45000 and totals[team["uid"]["L"]] == 0


def test_select_is_idempotent_and_only_for_self(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "A", rid, i, i)  # chọn 2 lần không lỗi
    pick(client, team, "A", rid, i)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ItemSelection)) == 1
    assert client.delete(f"/api/receipts/{rid}/items/{i}/selection", headers=team["h"]["B"]).status_code == 200  # B chưa chọn: OK, A vẫn giữ
    s = client.get(f"/api/receipts/{rid}/selections", headers=team["h"]["A"]).json()
    assert s["my_selected_item_ids"] == [i]  # B không thể bỏ chọn hộ A


def test_selection_permissions_and_errors(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    url = f"/api/receipts/{rid}/items/{i}/selection"
    assert client.put(url).status_code == 401
    assert client.put(url, headers=team["h"]["X"]).status_code == 403                 # người ngoài nhóm
    assert client.get(f"/api/receipts/{rid}/selections", headers=team["h"]["X"]).status_code == 403
    assert client.put(f"/api/receipts/9999/items/{i}/selection", headers=team["h"]["A"]).status_code == 404
    assert client.put(f"/api/receipts/{rid}/items/9999/selection", headers=team["h"]["A"]).status_code == 404
    _other, (j,) = make_receipt(client, team, [("B", 5000, 1)])
    assert client.put(f"/api/receipts/{rid}/items/{j}/selection", headers=team["h"]["A"]).status_code == 404  # món của HĐ khác
    with SessionLocal() as db:  # thành viên bị gỡ không chọn được nữa
        db.scalar(select(GroupMember).where(GroupMember.user_id == team["uid"]["B"])).status = "REMOVED"
        db.commit()
    assert client.put(url, headers=team["h"]["B"]).status_code == 403


def test_personal_receipt_has_no_selection(client, team):
    r = client.post("/api/receipts/personal", headers=team["h"]["A"], files={"file": ("a.jpg", JPG, "image/jpeg")}).json()
    r2 = client.get(f"/api/receipts/{r['id']}/selections", headers=team["h"]["A"])
    assert r2.status_code == 400 and r2.json()["error"]["code"] == "PERSONAL_RECEIPT"
    assert client.get(f"/api/receipts/{r['id']}/selections", headers=team["h"]["B"]).status_code == 403


def test_settled_receipt_locks_selection(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "A", rid, i)
    assert finalize(client, team, rid).status_code == 200
    r = client.delete(f"/api/receipts/{rid}/items/{i}/selection", headers=team["h"]["A"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_SETTLED"
    assert client.put(f"/api/receipts/{rid}/items/{i}/selection", headers=team["h"]["B"]).status_code == 409
    assert client.get(f"/api/receipts/{rid}/selections", headers=team["h"]["A"]).json()["can_select"] is False


def test_removed_member_selection_is_ignored(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "B", rid, i)
    with SessionLocal() as db:
        db.scalar(select(GroupMember).where(GroupMember.user_id == team["uid"]["B"])).status = "REMOVED"
        db.commit()
    s = client.get(f"/api/receipts/{rid}/selections", headers=team["h"]["A"]).json()
    assert [u["id"] for u in s["unselected_items"]] == [i]
    assert finalize(client, team, rid).status_code == 422


# =============== API 2: chốt + chia + công nợ ===============
def test_finalize_creates_splits_debts_and_settles(client, team):
    # Bún 60k (A), Cơm 40k (B + L), thuế 10k, phí 5k, L trả tiền
    rid, (bun, com) = make_receipt(client, team, [("Bún", 60000, 1), ("Cơm", 40000, 1)], tax="10000", fee="5000")
    pick(client, team, "A", rid, bun)
    pick(client, team, "B", rid, com)
    pick(client, team, "L", rid, com)
    r = finalize(client, team, rid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "SETTLED" and body["payer_id"] == team["uid"]["L"] and D(body["total_amount"]) == 115000

    splits = {s["user_id"]: s for s in body["splits"]}
    uid = team["uid"]
    assert D(splits[uid["A"]]["final_amount"]) == 60000 + 9000   # 15.000 × 60/100
    assert D(splits[uid["B"]]["final_amount"]) == 20000 + 3000   # 15.000 × 20/100
    assert D(splits[uid["L"]]["final_amount"]) == 20000 + 3000
    assert sum(D(s["final_amount"]) for s in body["splits"]) == 115000  # khớp tổng hóa đơn

    # nợ chỉ cho người ≠ người trả; creditor = người trả
    debts = {d["debtor_id"]: d for d in body["debts"]}
    assert set(debts) == {uid["A"], uid["B"]}
    assert all(d["creditor_id"] == uid["L"] and d["status"] == "OPEN" for d in body["debts"])
    assert (D(debts[uid["A"]]["amount"]), D(debts[uid["B"]]["amount"])) == (69000, 23000)
    assert debts[uid["A"]]["debtor_name"] == "Người A" and debts[uid["A"]]["creditor_name"] == "Người L"

    with SessionLocal() as db:
        assert db.get(Receipt, rid).status == "SETTLED"
        assert db.scalar(select(func.sum(SplitDetail.final_amount)).where(SplitDetail.receipt_id == rid)) == 115000
        assert db.scalar(select(func.count()).select_from(Debt).where(Debt.receipt_id == rid)) == 2


def test_finalize_rounding_remainder_goes_to_payer(client, team):
    rid, (i,) = make_receipt(client, team, [("Lẩu", 100000, 1)], payer="B")
    pick(client, team, "L", rid, i)
    pick(client, team, "A", rid, i)
    pick(client, team, "B", rid, i)
    body = finalize(client, team, rid).json()
    final = {s["user_id"]: D(s["final_amount"]) for s in body["splits"]}
    assert final[team["uid"]["L"]] == final[team["uid"]["A"]] == 33333
    assert final[team["uid"]["B"]] == 33334  # người trả nhận phần dư 1đ
    assert sum(final.values()) == 100000
    assert {d["debtor_id"] for d in body["debts"]} == {team["uid"]["L"], team["uid"]["A"]}  # không nợ chính mình


def test_finalize_payer_who_chose_nothing_gets_no_debt_but_others_do(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)], payer="L")
    pick(client, team, "A", rid, i)
    body = finalize(client, team, rid).json()
    assert [d["debtor_id"] for d in body["debts"]] == [team["uid"]["A"]] and D(body["debts"][0]["amount"]) == 100000
    assert [s["user_id"] for s in body["splits"]] == [team["uid"]["A"]]  # người trả không chọn gì → không có dòng chia


def test_finalize_blocked_when_items_unselected(client, team):
    rid, (a, b) = make_receipt(client, team, [("A", 60000, 1), ("B", 40000, 1)])
    pick(client, team, "A", rid, a)
    r = finalize(client, team, rid)
    assert r.status_code == 422
    assert any("chưa có ai chọn" in d["message"] and f"id {b}" in d["message"] for d in r.json()["error"]["details"])
    with SessionLocal() as db:  # không ghi gì nửa vời
        assert db.get(Receipt, rid).status == "VERIFIED"
        assert db.scalar(select(func.count()).select_from(SplitDetail)) == 0
        assert db.scalar(select(func.count()).select_from(Debt)) == 0


def test_finalize_blocked_when_total_mismatch(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "A", rid, i)
    with SessionLocal() as db:  # dữ liệu bị sửa ngoài luồng làm lệch tổng
        db.get(Receipt, rid).total_amount = D(999)
        db.commit()
    r = finalize(client, team, rid)
    assert r.status_code == 422 and any(d["field"] == "total_amount" for d in r.json()["error"]["details"])


def test_finalize_permissions_and_state(client, team):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "A", rid, i)
    assert client.post(f"/api/receipts/{rid}/split").status_code == 401
    assert finalize(client, team, rid, "A").status_code == 403       # thành viên thường không chốt được
    assert finalize(client, team, rid, "X").status_code == 403       # người ngoài nhóm
    assert finalize(client, team, 9999).status_code == 404
    assert finalize(client, team, rid).status_code == 200
    again = finalize(client, team, rid)
    assert again.status_code == 409 and again.json()["error"]["code"] == "RECEIPT_SETTLED"  # không chốt 2 lần
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Debt)) == 1  # không nhân đôi nợ

    draft, (j,) = make_receipt(client, team, [("B", 1000, 1)], verify=False)
    pick(client, team, "A", draft, j)
    r = finalize(client, team, draft)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"  # DRAFT chưa VERIFIED


def test_finalize_personal_receipt_rejected(client, team):
    r = client.post("/api/receipts/personal", headers=team["h"]["L"], files={"file": ("a.jpg", JPG, "image/jpeg")}).json()
    resp = client.post(f"/api/receipts/{r['id']}/split", headers=team["h"]["L"])
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "PERSONAL_RECEIPT"


def test_finalize_is_one_transaction_rollback_on_failure(client, team, monkeypatch):
    rid, (i,) = make_receipt(client, team, [("A", 100000, 1)])
    pick(client, team, "A", rid, i)

    from app.modules.split import service

    def boom(*a, **k):
        raise RuntimeError("lỗi giữa chừng sau khi đã add split_details/debts")

    monkeypatch.setattr(service.state, "transition", boom)  # nổ SAU khi đã db.add(...) → phải rollback sạch
    assert finalize(client, team, rid).status_code == 500
    monkeypatch.undo()
    with SessionLocal() as db:
        assert db.get(Receipt, rid).status == "VERIFIED"
        assert db.scalar(select(func.count()).select_from(SplitDetail)) == 0  # split_details đã add nhưng rollback
        assert db.scalar(select(func.count()).select_from(Debt)) == 0
    assert finalize(client, team, rid).status_code == 200  # sau lỗi vẫn chốt lại được


def test_edit_after_verify_reopens_and_finalize_recomputes(client, team):
    rid, (a, b) = make_receipt(client, team, [("A", 60000, 1), ("B", 40000, 1)])
    pick(client, team, "A", rid, a, b)
    # sửa giá khi VERIFIED → về DRAFT; xác nhận lại rồi chốt phải theo số mới
    assert client.patch(f"/api/receipts/{rid}/items/{b}", headers=team["h"]["L"], json={"unit_price": "50000"}).status_code == 200
    assert client.patch(
        f"/api/receipts/{rid}", headers=team["h"]["L"], json={"subtotal": "110000", "total_amount": "110000"}
    ).status_code == 200
    assert client.post(f"/api/receipts/{rid}/verify", headers=team["h"]["L"], json={"payer_id": team["uid"]["L"]}).status_code == 200
    body = finalize(client, team, rid).json()
    assert D(body["debts"][0]["amount"]) == 110000


# =============== API 3: xem công nợ ===============
@pytest.fixture()
def settled(client, team):
    """2 hóa đơn đã chốt: HĐ1 (L trả; A nợ 60k, B nợ 40k), HĐ2 (A trả; B nợ 30k)."""
    r1, (x, y) = make_receipt(client, team, [("X", 60000, 1), ("Y", 40000, 1)], payer="L")
    pick(client, team, "A", r1, x)
    pick(client, team, "B", r1, y)
    assert finalize(client, team, r1).status_code == 200
    r2, (z,) = make_receipt(client, team, [("Z", 30000, 1)], payer="A")
    pick(client, team, "B", r2, z)
    assert finalize(client, team, r2).status_code == 200
    return r1, r2


def test_receipt_debts_listing(client, team, settled):
    r1, r2 = settled
    d = client.get(f"/api/receipts/{r1}/debts", headers=team["h"]["B"]).json()  # thành viên thấy cả nợ của người khác
    assert {(x["debtor_name"], x["creditor_name"], D(x["amount"])) for x in d["items"]} == {
        ("Người A", "Người L", D(60000)),
        ("Người B", "Người L", D(40000)),
    }
    assert D(d["total_open"]) == 100000 and D(d["total_paid"]) == 0
    assert all(x["receipt_id"] == r1 and x["group_id"] == team["gid"] for x in d["items"])
    assert len(client.get(f"/api/receipts/{r2}/debts", headers=team["h"]["L"]).json()["items"]) == 1


def test_group_debts_listing_and_filters(client, team, settled):
    r1, r2 = settled
    url = f"/api/groups/{team['gid']}/debts"
    d = client.get(url, headers=team["h"]["L"]).json()
    assert len(d["items"]) == 3 and D(d["total_open"]) == 130000
    assert [x["receipt_id"] for x in d["items"]] == [r2, r1, r1]  # hóa đơn mới trước

    mine = client.get(url, params={"mine": "true"}, headers=team["h"]["A"]).json()
    assert {(x["debtor_name"], x["creditor_name"]) for x in mine["items"]} == {("Người A", "Người L"), ("Người B", "Người A")}
    assert client.get(url, params={"mine": "true"}, headers=team["h"]["L"]).json()["items"].__len__() == 2

    with SessionLocal() as db:  # đánh dấu 1 khoản đã trả
        debt = db.scalar(select(Debt).where(Debt.receipt_id == r2))
        debt.status = "PAID"
        db.commit()
    paid = client.get(url, params={"status": "PAID"}, headers=team["h"]["L"]).json()
    assert len(paid["items"]) == 1 and D(paid["total_paid"]) == 30000 and D(paid["total_open"]) == 0
    assert D(client.get(url, params={"status": "OPEN"}, headers=team["h"]["L"]).json()["total_open"]) == 100000
    assert client.get(url, params={"status": "WRONG"}, headers=team["h"]["L"]).status_code == 422


def test_debts_only_within_permission_scope(client, team, settled):
    r1, _ = settled
    gurl = f"/api/groups/{team['gid']}/debts"
    assert client.get(gurl).status_code == 401
    assert client.get(gurl, headers=team["h"]["X"]).status_code == 403                    # người ngoài nhóm
    assert client.get(f"/api/receipts/{r1}/debts", headers=team["h"]["X"]).status_code == 403
    assert client.get("/api/groups/9999/debts", headers=team["h"]["L"]).status_code == 404
    assert client.get("/api/receipts/9999/debts", headers=team["h"]["L"]).status_code == 404

    # nhóm khác không lẫn vào
    other = client.post("/api/groups", json={"name": "Khác"}, headers=team["h"]["X"]).json()["id"]
    assert client.get(f"/api/groups/{other}/debts", headers=team["h"]["X"]).json()["items"] == []
    assert client.get(f"/api/groups/{other}/debts", headers=team["h"]["L"]).status_code == 403

    with SessionLocal() as db:  # bị gỡ khỏi nhóm → không xem được nữa
        db.scalar(select(GroupMember).where(GroupMember.user_id == team["uid"]["B"])).status = "REMOVED"
        db.commit()
    assert client.get(gurl, headers=team["h"]["B"]).status_code == 403
    assert client.get(f"/api/receipts/{r1}/debts", headers=team["h"]["B"]).status_code == 403


def test_personal_receipt_debts_empty_and_private(client, team):
    r = client.post("/api/receipts/personal", headers=team["h"]["A"], files={"file": ("a.jpg", JPG, "image/jpeg")}).json()
    assert client.get(f"/api/receipts/{r['id']}/debts", headers=team["h"]["A"]).json()["items"] == []
    assert client.get(f"/api/receipts/{r['id']}/debts", headers=team["h"]["L"]).status_code == 403


def test_discount_amount_verify_and_proportional_split(client, team):
    """Hóa đơn Bách Hóa Xanh: tổng món 242.642đ, giảm/làm tròn 642đ -> thực trả 242.000đ."""
    H = team["h"]["L"]
    rid = client.post(
        f"/api/groups/{team['gid']}/receipts", headers=H, files={"file": ("a.jpg", JPG, "image/jpeg")}
    ).json()["id"]
    a_item = client.post(f"/api/receipts/{rid}/items", headers=H, json={"item_name": "Hạt é", "unit_price": "17000"}).json()["id"]
    b_item = client.post(f"/api/receipts/{rid}/items", headers=H, json={"item_name": "Các món khác", "unit_price": "225642"}).json()["id"]
    r = client.patch(
        f"/api/receipts/{rid}",
        headers=H,
        json={"subtotal": "242642", "discount_amount": "642", "total_amount": "242000"},
    )
    assert r.status_code == 200 and D(r.json()["discount_amount"]) == 642
    assert client.post(f"/api/receipts/{rid}/verify", headers=H, json={"payer_id": team["uid"]["L"]}).status_code == 200

    pick(client, team, "A", rid, a_item)
    pick(client, team, "L", rid, b_item)
    body = finalize(client, team, rid).json()
    assert body["status"] == "SETTLED" and D(body["total_amount"]) == 242000
    assert sum(D(s["final_amount"]) for s in body["splits"]) == 242000
    assert all(D(s["item_amount"]) >= 0 and D(s["fee_amount"]) >= 0 for s in body["splits"])
    by = {s["user_id"]: D(s["final_amount"]) for s in body["splits"]}
    assert by[team["uid"]["A"]] == 16955 and by[team["uid"]["L"]] == 225045


def test_dashboard_reflects_new_debts(client, team, settled):
    s = client.get("/api/dashboard/summary", headers=team["h"]["B"]).json()
    assert D(s["i_owe"]) == 70000                       # 40k (HĐ1) + 30k (HĐ2)
    assert D(client.get("/api/dashboard/summary", headers=team["h"]["L"]).json()["owed_to_me"]) == 100000
