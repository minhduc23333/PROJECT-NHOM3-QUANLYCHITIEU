import time
from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, BadRequest, Conflict, Unauthorized
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    hash_password,
    password_fingerprint,
    read_password_reset_token,
    verify_password,
)
from app.models import User
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut


def _token_for(user: User) -> TokenOut:
    token, expires_in = create_access_token(user.id)
    return TokenOut(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


def register(db: Session, data: RegisterIn) -> TokenOut:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise Conflict("Email đã được sử dụng", details=[{"field": "email", "message": "Email đã được sử dụng"}])
    user = User(full_name=data.full_name.strip(), email=email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_for(user)


def login(db: Session, data: LoginIn) -> TokenOut:
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise Unauthorized("Email hoặc mật khẩu không đúng")
    return _token_for(user)


# ---------- Quên mật khẩu ----------
FORGOT_MESSAGE = "Nếu email này đã đăng ký, chúng tôi đã gửi liên kết đặt lại mật khẩu. Hãy kiểm tra hộp thư (cả mục Spam)."
RESET_OK_MESSAGE = "Đã đặt lại mật khẩu. Bạn có thể đăng nhập bằng mật khẩu mới."
RESET_INVALID_MESSAGE = "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Hãy yêu cầu liên kết mới."

# Chống spam: tối đa 5 yêu cầu / email / 15 phút (bộ nhớ trong tiến trình, đủ cho 1 server)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SEC = 15 * 60
_attempts: dict[str, deque[float]] = defaultdict(deque)


class TooManyRequests(AppError):
    status_code, code = 429, "TOO_MANY_REQUESTS"


def reset_rate_limit() -> None:
    """Dùng trong test."""
    _attempts.clear()


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    q = _attempts[key]
    while q and now - q[0] > RATE_LIMIT_WINDOW_SEC:
        q.popleft()
    if len(q) >= RATE_LIMIT_MAX:
        raise TooManyRequests("Bạn thử quá nhiều lần, vui lòng đợi ít phút rồi thử lại.")
    q.append(now)


def request_password_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Tạo liên kết đặt lại mật khẩu. Email không tồn tại -> None (API vẫn trả cùng một thông báo để không lộ email nào đã đăng ký)."""
    email = email.lower()
    _check_rate_limit(email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    token, _ = create_password_reset_token(user.id, user.password_hash)
    link = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/#/reset-password/{token}"
    return user, link


def reset_password(db: Session, token: str, new_password: str) -> None:
    parsed = read_password_reset_token(token)
    if parsed is None:
        raise BadRequest(RESET_INVALID_MESSAGE, code="RESET_TOKEN_INVALID")
    user_id, fingerprint = parsed
    user = db.get(User, user_id)
    # Dấu vân tay không khớp = mật khẩu đã được đổi sau khi cấp token -> token đã dùng rồi
    if user is None or password_fingerprint(user.password_hash) != fingerprint:
        raise BadRequest(RESET_INVALID_MESSAGE, code="RESET_TOKEN_INVALID")
    user.password_hash = hash_password(new_password)
    db.commit()
