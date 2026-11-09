from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

# Hash giả để vẫn tốn thời gian bcrypt khi email không tồn tại (tránh dò email qua thời gian phản hồi)
_DUMMY_HASH = hash_password("dummy-password")


def _token_for(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


def register(db: Session, data: RegisterIn) -> TokenOut:
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")

    user = User(full_name=data.full_name, email=data.email, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:   # hai request đăng ký cùng email cùng lúc
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")
    return _token_for(user)


def login(db: Session, data: LoginIn) -> TokenOut:
    user = db.scalar(select(User).where(User.email == data.email))
    ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    return _token_for(user)
