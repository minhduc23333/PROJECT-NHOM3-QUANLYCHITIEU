"""Test quên mật khẩu: không lộ email, token 1 lần dùng / hết hạn, không dùng chéo với token đăng nhập, chống spam."""
import pytest

from app.core.config import settings
from app.modules.auth import service

USER = {"full_name": "An Nguyễn", "email": "an@demo.vn", "password": "matkhaucu123"}
NEW = "matkhaumoi456"


@pytest.fixture(autouse=True)
def _clean_limiter():
    service.reset_rate_limit()
    yield
    service.reset_rate_limit()


def _forgot(client, email=USER["email"]):
    return client.post("/api/auth/forgot-password", json={"email": email})


def _token_from(res):
    link = res.json()["dev_reset_link"]
    assert "/#/reset-password/" in link
    return link.split("/#/reset-password/")[1]


def _reset(client, token, pw=NEW):
    return client.post("/api/auth/reset-password", json={"token": token, "new_password": pw})


def _login(client, pw):
    return client.post("/api/auth/login", json={"email": USER["email"], "password": pw})


def test_forgot_does_not_reveal_whether_email_exists(client):
    client.post("/api/auth/register", json=USER)
    known, unknown = _forgot(client), _forgot(client, "khong-co@demo.vn")
    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]
    assert unknown.json()["dev_reset_link"] is None


def test_forgot_rejects_bad_email_format(client):
    assert _forgot(client, "khong-phai-email").status_code == 422


def test_full_flow_new_password_works_old_one_does_not(client):
    client.post("/api/auth/register", json=USER)
    token = _token_from(_forgot(client))
    r = _reset(client, token)
    assert r.status_code == 200, r.text
    assert _login(client, NEW).status_code == 200
    assert _login(client, USER["password"]).status_code == 401


def test_reset_token_is_single_use(client):
    client.post("/api/auth/register", json=USER)
    token = _token_from(_forgot(client))
    assert _reset(client, token).status_code == 200
    again = _reset(client, token, "mot-mat-khau-khac-789")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "RESET_TOKEN_INVALID"
    assert _login(client, NEW).status_code == 200  # mật khẩu không bị đổi lần 2


def test_garbage_and_tampered_tokens_rejected(client):
    client.post("/api/auth/register", json=USER)
    token = _token_from(_forgot(client))
    for bad in ["khong-phai-token-gi-ca", token[:-3] + "abc", token + "x"]:
        r = _reset(client, bad)
        assert r.status_code == 400 and r.json()["error"]["code"] == "RESET_TOKEN_INVALID"
    assert _login(client, USER["password"]).status_code == 200  # mật khẩu cũ còn nguyên


def test_expired_token_rejected(client, monkeypatch):
    client.post("/api/auth/register", json=USER)
    monkeypatch.setattr(settings, "PASSWORD_RESET_EXPIRE_MINUTES", -1)  # token sinh ra đã hết hạn
    token = _token_from(_forgot(client))
    assert _reset(client, token).status_code == 400


def test_access_token_cannot_be_used_as_reset_token_and_vice_versa(client):
    client.post("/api/auth/register", json=USER)
    access = _login(client, USER["password"]).json()["access_token"]
    assert _reset(client, access).status_code == 400            # token đăng nhập không đặt lại được mật khẩu
    reset_token = _token_from(_forgot(client))
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {reset_token}"})
    assert me.status_code == 401                                 # token đặt lại không đăng nhập được


def test_reset_password_validation(client):
    client.post("/api/auth/register", json=USER)
    token = _token_from(_forgot(client))
    assert _reset(client, token, "123").status_code == 422             # quá ngắn
    assert _reset(client, token, "ế" * 30).status_code == 422          # 90 byte > 72
    assert _login(client, USER["password"]).status_code == 200          # token vẫn dùng được sau khi bị 422
    assert _reset(client, token).status_code == 200


def test_rate_limit_per_email(client):
    client.post("/api/auth/register", json=USER)
    codes = [_forgot(client).status_code for _ in range(service.RATE_LIMIT_MAX + 1)]
    assert codes[:-1] == [200] * service.RATE_LIMIT_MAX and codes[-1] == 429
    assert _forgot(client, "nguoi-khac@demo.vn").status_code == 200   # email khác không bị ảnh hưởng


def test_email_sent_in_background_and_dev_link_hidden_when_smtp_configured(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.core.mailer.send_email", lambda to, subject, body: sent.append((to, subject, body)) or True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")   # giống production: có SMTP
    client.post("/api/auth/register", json=USER)
    res = _forgot(client)
    assert res.status_code == 200 and res.json()["dev_reset_link"] is None   # không lộ liên kết qua API
    assert len(sent) == 1 and sent[0][0] == USER["email"]
    assert "/#/reset-password/" in sent[0][2] and "An Nguyễn" in sent[0][2]
    _forgot(client, "khong-co@demo.vn")
    assert len(sent) == 1                                              # email lạ: không gửi gì
    token = sent[0][2].split("/#/reset-password/")[1].split()[0]
    assert _reset(client, token).status_code == 200
