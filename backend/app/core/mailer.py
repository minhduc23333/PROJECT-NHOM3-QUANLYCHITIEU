"""Gửi email đơn giản qua SMTP (thư viện chuẩn smtplib, không cần cài thêm).

Chưa cấu hình SMTP_HOST -> không gửi, chỉ ghi nội dung vào log để dev copy liên kết.
Lỗi gửi mail không bao giờ làm hỏng request: chỉ ghi log và trả False.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("smartsplit.mail")


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST)


def send_email(to: str, subject: str, body: str) -> bool:
    if not smtp_configured():
        log.warning("SMTP chưa cấu hình, KHÔNG gửi email tới %s.\nTiêu đề: %s\n%s", to, subject, body)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception:  # noqa: BLE001  không để lỗi mạng/SMTP làm hỏng API
        log.exception("Gửi email tới %s thất bại", to)
        return False
