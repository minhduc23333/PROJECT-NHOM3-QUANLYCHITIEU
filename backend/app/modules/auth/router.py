from fastapi import APIRouter, BackgroundTasks, status

from app.core.deps import DB, CurrentUser
from app.core import mailer
from app.core.config import settings
from app.core.errors import COMMON_ERRORS
from app.modules.auth import service
from app.modules.auth.schemas import (
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
)

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


def _send_reset_email(to: str, full_name: str, link: str) -> None:
    mailer.send_email(
        to,
        "Đặt lại mật khẩu SmartSplit AI",
        f"Xin chào {full_name},\n\n"
        "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản SmartSplit AI của bạn.\n"
        f"Bấm vào liên kết sau để đặt mật khẩu mới (có hiệu lực {settings.PASSWORD_RESET_EXPIRE_MINUTES} phút, dùng được 1 lần):\n\n"
        f"{link}\n\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này, mật khẩu của bạn vẫn giữ nguyên.\n\n"
        "SmartSplit AI",
    )


@router.post(
    "/forgot-password",
    response_model=MessageOut,
    summary="Quên mật khẩu: gửi liên kết đặt lại qua email",
    description=(
        "Luôn trả cùng một thông báo dù email có tồn tại hay không (không lộ email nào đã đăng ký). "
        "Tối đa 5 yêu cầu / email / 15 phút (429)."
    ),
)
def forgot_password(data: ForgotPasswordIn, db: DB, background: BackgroundTasks):
    found = service.request_password_reset(db, data.email)
    dev_link = None
    if found is not None:
        user, link = found
        background.add_task(_send_reset_email, user.email, user.full_name, link)  # gửi nền, không làm chậm response
        if settings.APP_ENV == "dev" and not mailer.smtp_configured():
            dev_link = link  # dev chưa có SMTP: trả liên kết để thử luôn trên giao diện
    return MessageOut(message=service.FORGOT_MESSAGE, dev_reset_link=dev_link)


@router.post(
    "/reset-password",
    response_model=MessageOut,
    summary="Đặt mật khẩu mới bằng token trong liên kết email",
    description="Token sai / hết hạn / đã dùng rồi: 400 (code `RESET_TOKEN_INVALID`).",
)
def reset_password(data: ResetPasswordIn, db: DB):
    service.reset_password(db, data.token, data.new_password)
    return MessageOut(message=service.RESET_OK_MESSAGE)
