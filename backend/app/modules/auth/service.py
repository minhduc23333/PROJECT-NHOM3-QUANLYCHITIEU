from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unauthorized
from app.core.security import create_access_token, hash_password, verify_password
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