VALID = {"full_name": "An Nguyễn", "email": "An@Demo.vn", "password": "matkhau123"}


def test_register_ok_returns_token_and_normalized_email(client):
    r = client.post("/auth/register", json=VALID)
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"] and body["token_type"] == "bearer"
    assert body["user"]["email"] == "an@demo.vn"
    assert "password" not in body["user"] and "password_hash" not in body["user"]


def test_register_duplicate_email_case_insensitive(client):
    assert client.post("/auth/register", json=VALID).status_code == 201
    r = client.post("/auth/register", json={**VALID, "email": "an@demo.vn"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "HTTP_409"


def test_register_validation_errors(client):
    r = client.post("/auth/register", json={"full_name": "A", "email": "khong-phai-email", "password": "123"})
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert fields == {"full_name", "email", "password"}


def test_register_password_too_long_in_bytes(client):
    r = client.post("/auth/register", json={**VALID, "password": "ế" * 30})  # 90 byte
    assert r.status_code == 422


def test_login_and_me(client):
    client.post("/auth/register", json=VALID)
    r = client.post("/auth/login", json={"email": "an@demo.vn", "password": VALID["password"]})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["full_name"] == "An Nguyễn"


def test_login_wrong_password_and_unknown_email_same_message(client):
    client.post("/auth/register", json=VALID)
    a = client.post("/auth/login", json={"email": "an@demo.vn", "password": "sai-mat-khau"})
    b = client.post("/auth/login", json={"email": "khong@co.vn", "password": "sai-mat-khau"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer rac"}).status_code == 401
