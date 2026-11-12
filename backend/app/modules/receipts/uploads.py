"""Kiểm tra & lưu file ảnh hóa đơn tải lên.

- Loại file xác định bằng chữ ký (magic bytes), KHÔNG tin content-type / tên file do client gửi.
- Tên file lưu trên đĩa do server tự sinh (uuid) nên không có path traversal.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.core.errors import BadRequest

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
CHUNK = 64 * 1024


def max_upload_bytes() -> int:
    return settings.MAX_UPLOAD_MB * 1024 * 1024


def detect_image_extension(data: bytes) -> str | None:
    """'.jpg' / '.png' theo magic bytes; None nếu không phải JPG/PNG."""
    if data.startswith(JPEG_MAGIC):
        return ".jpg"
    if data.startswith(PNG_MAGIC):
        return ".png"
    return None


async def read_limited(file: UploadFile) -> bytes:
    """Đọc từng khúc và dừng ngay khi vượt giới hạn (413), không nạp cả file khổng lồ vào RAM."""
    limit = max_upload_bytes()
    buf = bytearray()
    while chunk := await file.read(CHUNK):
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(status_code=413, detail=f"Ảnh không được vượt quá {settings.MAX_UPLOAD_MB} MB")
    return bytes(buf)


def validate_image(data: bytes) -> str:
    """Trả phần mở rộng hợp lệ hoặc ném 400."""
    if not data:
        raise BadRequest("Ảnh hóa đơn không được để trống")
    extension = detect_image_extension(data)
    if extension is None:
        raise BadRequest("Chỉ chấp nhận ảnh JPG hoặc PNG hợp lệ")
    return extension


def save_image(data: bytes, extension: str) -> Path:
    """Ghi file vào UPLOAD_DIR; lỗi giữa chừng thì xóa file dở dang."""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid4().hex}{extension}"
    try:
        path.write_bytes(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path
