"""Schema cho module split: chọn món, chốt chia tiền, công nợ."""
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------- Chọn / bỏ chọn món ----------
class MemberShare(BaseModel):
    user_id: int
    full_name: str
    selected_item_ids: list[int] = []
    item_amount: Decimal = Field(description="Tiền món của người này (đã chia đều nếu món có nhiều người chọn)")
    fee_amount: Decimal = Field(description="Phần thuế + phí dịch vụ chia theo tỉ lệ")
    total: Decimal = Field(description="Tạm tính = item_amount + fee_amount (làm tròn xuống tới đồng)")


class UnselectedItem(BaseModel):
    id: int
    item_name: str
    quantity: Decimal
    line_total: Decimal


class SelectionSummary(BaseModel):
    receipt_id: int
    receipt_status: str
    can_select: bool = Field(description="False khi hóa đơn đã SETTLED")
    items_total: Decimal = Field(description="Tổng tiền các dòng món")
    fee_total: Decimal = Field(description="Thuế + phí dịch vụ")
    my_selected_item_ids: list[int] = []
    members: list[MemberShare] = Field(description="Mọi thành viên ACTIVE của nhóm, kể cả người chưa chọn món")
    unselected_items: list[UnselectedItem] = Field(description="Món chưa có thành viên ACTIVE nào chọn")


# ---------- Công nợ ----------
class DebtOut(BaseModel):
    id: int
    receipt_id: int
    group_id: int | None = None
    merchant_name: str | None = None
    debtor_id: int = Field(description="Người phải trả tiền")
    debtor_name: str
    creditor_id: int = Field(description="Người nhận tiền (người đã trả hóa đơn)")
    creditor_name: str
    amount: Decimal
    status: str = Field(description="OPEN | PAID")


class DebtList(BaseModel):
    items: list[DebtOut]
    total_open: Decimal = Field(description="Tổng các khoản còn nợ (OPEN) trong danh sách này")
    total_paid: Decimal = Field(description="Tổng các khoản đã trả (PAID) trong danh sách này")


# ---------- Chốt hóa đơn + chia tiền ----------
class SplitLine(BaseModel):
    user_id: int
    full_name: str
    item_amount: Decimal
    fee_amount: Decimal
    final_amount: Decimal


class SplitResult(BaseModel):
    receipt_id: int
    status: str
    payer_id: int
    total_amount: Decimal
    splits: list[SplitLine]
    debts: list[DebtOut]
