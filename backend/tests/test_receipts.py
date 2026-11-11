from tests.conftest import register


def test_upload_receipt_validates_membership_and_image_signature(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client, "owner@x.vn")
    outsider = register(client, "outsider@x.vn")
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=owner).json()["id"]

    denied = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=outsider,
        files={"file": ("receipt.jpg", b"\xff\xd8\xffvalid", "image/jpeg")},
    )
    assert denied.status_code == 403

    invalid = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=owner,
        files={"file": ("receipt.jpg", b"not an image", "image/jpeg")},
    )
    assert invalid.status_code == 400

    uploaded = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=owner,
        files={"file": ("misleading.png", b"\xff\xd8\xffvalid", "image/png")},
    )
    assert uploaded.status_code == 201
    receipt = uploaded.json()
    assert receipt["status"] == "DRAFT"
    assert receipt["ocr_status"] == "PENDING"
    assert receipt["uploaded_by"] == 1
    stored_files = list(tmp_path.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].suffix == ".jpg"


def test_upload_receipt_rejects_images_over_configured_limit(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client)
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=owner).json()["id"]
    too_large = b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024)

    response = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=owner,
        files={"file": ("receipt.jpg", too_large, "image/jpeg")},
    )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_receipt_state_transitions_and_settled_lock(client):
    owner = register(client)
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=owner).json()["id"]
    uploaded = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=owner,
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nvalid", "application/octet-stream")},
    )
    receipt_id = uploaded.json()["id"]

    updated = client.patch(
        f"/api/receipts/{receipt_id}",
        headers=owner,
        json={"total_amount": "120.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "DRAFT"

    verified = client.post(f"/api/receipts/{receipt_id}/verify", headers=owner)
    assert verified.status_code == 200
    assert verified.json()["status"] == "VERIFIED"

    edited = client.patch(
        f"/api/receipts/{receipt_id}",
        headers=owner,
        json={"total_amount": "125.00"},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "DRAFT"
    assert edited.json()["total_amount"] == "125.00"

    assert client.post(f"/api/receipts/{receipt_id}/settle", headers=owner).status_code == 409
    assert client.post(f"/api/receipts/{receipt_id}/verify", headers=owner).json()["status"] == "VERIFIED"
    assert client.post(f"/api/receipts/{receipt_id}/settle", headers=owner).json()["status"] == "SETTLED"
    assert client.patch(
        f"/api/receipts/{receipt_id}",
        headers=owner,
        json={"total_amount": "130.00"},
    ).status_code == 409
