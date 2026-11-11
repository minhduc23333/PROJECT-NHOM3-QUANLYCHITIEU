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