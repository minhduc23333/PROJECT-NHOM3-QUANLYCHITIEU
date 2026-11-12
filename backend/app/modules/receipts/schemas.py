from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int | None = None
    uploaded_by: int
    payer_id: int | None = None
    merchant_name: str | None = None
    receipt_date: date | None = None
    total_amount: Decimal | None = None
    category: str | None = None
    status: str
    ocr_status: str | None = None
    created_at: datetime | None = None


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Money = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


# ---------- Dòng món ----------
class ItemCreate(BaseModel):
    item_name: Name = Field(examples=["Bún bò"])
    quantity: Quantity = Decimal("1")
    unit_price: Money = Field(examples=["45000"])
    line_total: Money | None = Field(
        default=None,
        description="Bỏ trống để server tự tính = quantity × unit_price. Nếu gửi lên mà không khớp → 422.",
    )


class ItemUpdate(BaseModel):
    """Chỉ gửi các trường cần đổi. Đổi quantity/unit_price mà không gửi line_total → server tự tính lại."""

    item_name: Name | None = None
    quantity: Quantity | None = None
    unit_price: Money | None = None
    line_total: Money | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


# ---------- Hóa đơn nháp ----------
class ReceiptUpdate(BaseModel):
    """Sửa thông tin đầu hóa đơn (chỉ người tải lên, không sửa được sau khi SETTLED)."""

    merchant_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    receipt_date: date | None = None
    subtotal: Money | None = None
    tax_amount: Money | None = None
    service_fee: Money | None = None
    total_amount: Money | None = None
    category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None


class ReceiptDetail(ReceiptOut):
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    service_fee: Decimal | None = None
    items: list[ItemOut] = []
    items_total: Decimal = Decimal("0")       # SUM(line_total) thực tế, để UI so với subtotal
    can_edit_receipt: bool = False            # người tải lên, trừ khi SETTLED
    can_edit_items: bool = False              # người tải lên hoặc Leader, trừ khi SETTLED


class VerifyIn(BaseModel):
    payer_id: int = Field(description="Người đã trả tiền hóa đơn, phải là thành viên ACTIVE của nhóm")
