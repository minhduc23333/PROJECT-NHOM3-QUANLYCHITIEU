import os

# Test chạy trên SQLite tạm, không cần MySQL
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    Base.metadata.drop_all(engine)


def register(client, email="a@x.vn", name="Người A"):
    r = client.post("/api/auth/register", json={"full_name": name, "email": email, "password": "123456"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}