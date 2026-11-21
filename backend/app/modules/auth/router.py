from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.auth import service
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"], responses=COMMON_ERRORS)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED, summary="Đăng ký tài khoản")
def register(data: RegisterIn, db: DB):
    return service.register(db, data)


@router.post("/login", response_model=TokenOut, summary="Đăng nhập, nhận JWT")
def login(data: LoginIn, db: DB):
    return service.login(db, data)


@router.get("/me", response_model=UserOut, summary="Thông tin người dùng hiện tại")
def me(user: CurrentUser):
    return user