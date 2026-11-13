from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.modules.receipts.schemas import ReceiptOut


class OcrItemOut(BaseModel):
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class OcrProcessOut(BaseModel):
    """Kết quả chạy OCR cho một hóa đơn nháp."""

    receipt: ReceiptOut
    items: list[OcrItemOut]
    missing: list[str]       # trường chưa nhận ra, UI đánh dấu cho người dùng nhập
    warnings: list[str]      # vd: tổng dòng món lệch tạm tính
    raw_text: str | None = None  # text thô để debug / hiển thị khi FAILED
