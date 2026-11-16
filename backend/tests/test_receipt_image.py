"""T05E176: API lấy ảnh gốc hóa đơn để hiển thị cạnh biểu mẫu kiểm tra OCR."""
import pytest

from tests.conftest import register

JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture()
def team(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    h = {n: register(client, f"{n.lower()}@x.vn", f"Người {n}") for n in "LMX"}
    gid = client.post("/api/groups", json={"name": "N"}, headers=h["L"]).json()["id"]
    client.post(f"/api/groups/{gid}/members", json={"email": "m@x.vn"}, headers=h["L"])
    rid = client.post(f"/api/groups/{gid}/receipts", headers=h["L"], files={"file": ("a.jpg", JPG, "image/jpeg")}).json()["id"]
    return {"h": h, "rid": rid, "dir": tmp_path}


def test_member_can_view_image(client, team):
    for who in "LM":
        r = client.get(f"/api/receipts/{team['rid']}/image", headers=team["h"][who])
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.content == JPG


def test_outsider_and_anonymous_cannot_view_image(client, team):
    assert client.get(f"/api/receipts/{team['rid']}/image", headers=team["h"]["X"]).status_code == 403
    assert client.get(f"/api/receipts/{team['rid']}/image").status_code == 401


def test_missing_receipt_or_file_gives_404(client, team):
    assert client.get("/api/receipts/9999/image", headers=team["h"]["L"]).status_code == 404
    for f in team["dir"].iterdir():
        f.unlink()
    r = client.get(f"/api/receipts/{team['rid']}/image", headers=team["h"]["L"])
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_personal_receipt_image_only_owner(client, team):
    rid = client.post("/api/receipts/personal", headers=team["h"]["M"], files={"file": ("a.jpg", JPG, "image/jpeg")}).json()["id"]
    assert client.get(f"/api/receipts/{rid}/image", headers=team["h"]["M"]).status_code == 200
    assert client.get(f"/api/receipts/{rid}/image", headers=team["h"]["L"]).status_code == 403
