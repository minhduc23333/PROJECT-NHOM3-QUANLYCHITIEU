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


def test_upload_personal_receipt_needs_no_group_and_is_private(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client, "personal@x.vn")
    other_user = register(client, "other@x.vn")

    response = client.post(
        "/api/receipts/personal",
        headers=owner,
        files={"file": ("receipt.jpg", b"\xff\xd8\xffvalid", "image/jpeg")},
    )

    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt["group_id"] is None
    assert receipt["uploaded_by"] == 1
    assert receipt["status"] == "DRAFT"
    assert receipt["ocr_status"] == "PENDING"
    assert client.get(f"/api/receipts/{receipt['id']}", headers=owner).status_code == 200
    assert client.get(f"/api/receipts/{receipt['id']}", headers=other_user).status_code == 403
    assert len(list(tmp_path.iterdir())) == 1


def test_upload_personal_receipt_rejects_images_over_configured_limit(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client)
    too_large = b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024)

    response = client.post(
        "/api/receipts/personal",
        headers=owner,
        files={"file": ("receipt.jpg", too_large, "image/jpeg")},
    )

    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_receipt_full_lifecycle_upload_edit_verify_settle(client, monkeypatch, tmp_path):
    """Upload -> thêm món -> nhập tiền -> verify (chọn người trả) -> settle; mỗi bước sai đều bị chặn."""
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    owner = register(client)
    group_id = client.post("/api/groups", json={"name": "Nhóm A"}, headers=owner).json()["id"]
    uploaded = client.post(
        f"/api/groups/{group_id}/receipts",
        headers=owner,
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nvalid", "application/octet-stream")},
    )
    receipt_id = uploaded.json()["id"]
    owner_id = uploaded.json()["uploaded_by"]
    url = f"/api/receipts/{receipt_id}"

    # Chưa có món/tiền -> không verify được, vẫn DRAFT
    assert client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id}).status_code == 422
    # Chưa VERIFIED -> không chốt được
    assert client.post(f"{url}/settle", headers=owner).status_code == 409

    item = client.post(
        f"{url}/items",
        headers=owner,
        json={"item_name": "Bún bò", "quantity": "2", "unit_price": "60000"},
    )
    assert item.status_code == 201
    item_id = item.json()["id"]
    updated = client.patch(url, headers=owner, json={"subtotal": "120000", "total_amount": "120000"})
    assert updated.status_code == 200 and updated.json()["status"] == "DRAFT"

    verified = client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id})
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED" and verified.json()["payer_id"] == owner_id
    assert verified.json()["can_edit_receipt"] and verified.json()["can_edit_items"]

    # Sửa thông tin không ảnh hưởng chia tiền giữ VERIFIED; sửa tiền sẽ mở lại DRAFT.
    metadata = client.patch(url, headers=owner, json={"merchant_name": "Quán mới"})
    assert metadata.status_code == 200 and metadata.json()["status"] == "VERIFIED"
    reopened = client.patch(url, headers=owner, json={"total_amount": "125000"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "DRAFT"
    assert client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id}).status_code == 422
    assert client.patch(url, headers=owner, json={"total_amount": "120000"}).status_code == 200
    # Verify lại sau khi hiệu chỉnh, rồi sửa dòng món để tự quay lại DRAFT.
    verified = client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id})
    assert verified.status_code == 200
    changed_item = client.patch(
        f"{url}/items/{item_id}",
        headers=owner,
        json={"quantity": "3", "unit_price": "60000"},
    )
    assert changed_item.status_code == 200
    assert client.get(url, headers=owner).json()["status"] == "DRAFT"
    assert client.patch(
        f"{url}/items/{item_id}",
        headers=owner,
        json={"quantity": "2"},
    ).status_code == 200
    assert client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id}).status_code == 200

    added_item = client.post(
        f"{url}/items",
        headers=owner,
        json={"item_name": "Trà đá", "unit_price": "1000"},
    )
    assert added_item.status_code == 201
    assert client.get(url, headers=owner).json()["status"] == "DRAFT"
    assert client.patch(url, headers=owner, json={"subtotal": "121000", "total_amount": "121000"}).status_code == 200
    assert client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id}).status_code == 200
    assert client.delete(f"{url}/items/{added_item.json()['id']}", headers=owner).status_code == 204
    assert client.get(url, headers=owner).json()["status"] == "DRAFT"
    assert client.patch(url, headers=owner, json={"subtotal": "120000", "total_amount": "120000"}).status_code == 200
    assert client.post(f"{url}/verify", headers=owner, json={"payer_id": owner_id}).status_code == 200

    settled = client.post(f"{url}/settle", headers=owner)
    assert settled.status_code == 200 and settled.json()["status"] == "SETTLED"
    assert not settled.json()["can_edit_receipt"] and not settled.json()["can_edit_items"]
    assert client.post(f"{url}/settle", headers=owner).status_code == 409
    assert client.patch(url, headers=owner, json={"merchant_name": "Không sửa"}).status_code == 409
    assert client.patch(url, headers=owner, json={"total_amount": "130000"}).status_code == 409
    assert client.post(f"{url}/items", headers=owner, json={"item_name": "Z", "unit_price": "1000"}).status_code == 409
    assert client.patch(f"{url}/items/{item_id}", headers=owner, json={"item_name": "Không sửa"}).status_code == 409
    assert client.delete(f"{url}/items/{item_id}", headers=owner).status_code == 409


def test_settle_permission_only_uploader_or_leader(client, monkeypatch, tmp_path):
    from app.modules.receipts import service

    monkeypatch.setattr(service.settings, "UPLOAD_DIR", str(tmp_path))
    leader, member = register(client, "l@x.vn", "Leader"), register(client, "m@x.vn", "Member")
    gid = client.post("/api/groups", json={"name": "N"}, headers=leader).json()["id"]
    assert client.post(f"/api/groups/{gid}/members", json={"email": "m@x.vn"}, headers=leader).status_code == 201
    r = client.post(f"/api/groups/{gid}/receipts", headers=leader,
                    files={"file": ("a.jpg", b"\xff\xd8\xffvalid", "image/jpeg")}).json()
    lid = r["uploaded_by"]
    url = f"/api/receipts/{r['id']}"
    client.post(f"{url}/items", headers=leader, json={"item_name": "A", "unit_price": "10000"})
    client.patch(url, headers=leader, json={"subtotal": "10000", "total_amount": "10000"})
    assert client.post(f"{url}/verify", headers=leader, json={"payer_id": lid}).status_code == 200
    assert client.post(f"{url}/settle", headers=member).status_code == 403
    assert client.post(f"{url}/settle", headers=leader).status_code == 200
