from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReceiptUpdate(BaseModel):
    payer_id: int | None = None
    merchant_name: str | None = Field(default=None, max_length=255)
    receipt_date: date | None = None
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    service_fee: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=50)


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    uploaded_by: int
    payer_id: int | None = None
    merchant_name: str | None = None
    receipt_date: date | None = None
    total_amount: Decimal | None = None
    category: str | None = None
    status: str
    ocr_status: str | None = None
    created_at: datetime | None = None