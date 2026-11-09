from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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