import hashlib
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> tuple[str, int]:
    """Trả về (token, số giây còn hiệu lực)."""
    expires_in = settings.JWT_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> int | None:
    """Trả về user_id, hoặc None nếu token sai/hết hạn."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------- Quên mật khẩu ----------
# Token đặt lại mật khẩu KHÔNG lưu DB (stateless) nhưng:
#  - ký bằng khóa riêng (JWT_SECRET + hậu tố) và dùng claim "uid" thay vì "sub" -> không thể dùng làm token đăng nhập;
#  - chứa dấu vân tay của mật khẩu hiện tại -> dùng xong (đổi mật khẩu) là token cũ tự vô hiệu, chỉ dùng được 1 lần.
RESET_TOKEN_TYPE = "pwd-reset"


def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def _reset_key() -> str:
    return settings.JWT_SECRET + ":password-reset"


def create_password_reset_token(user_id: int, password_hash: str) -> tuple[str, int]:
    """Trả về (token, số giây còn hiệu lực)."""
    expires_in = settings.PASSWORD_RESET_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    payload = {
        "uid": str(user_id),
        "typ": RESET_TOKEN_TYPE,
        "fp": password_fingerprint(password_hash),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, _reset_key(), algorithm=settings.JWT_ALGORITHM), expires_in


def read_password_reset_token(token: str) -> tuple[int, str] | None:
    """Trả về (user_id, fingerprint) hoặc None nếu token sai/hết hạn/không phải token đặt lại mật khẩu."""
    try:
        payload = jwt.decode(token, _reset_key(), algorithms=[settings.JWT_ALGORITHM])
        if payload.get("typ") != RESET_TOKEN_TYPE:
            return None
        return int(payload["uid"]), str(payload["fp"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
