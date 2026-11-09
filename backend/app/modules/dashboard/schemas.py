from decimal import Decimal

from pydantic import BaseModel


class MonthTotal(BaseModel):
    month: str  # "2026-11"
    total: Decimal


class DashboardSummary(BaseModel):
    group_count: int
    receipt_count: int
    total_spent: Decimal          # tổng tiền các hóa đơn tôi là người trả
    i_owe: Decimal                # tôi đang nợ người khác (debts OPEN)
    owed_to_me: Decimal           # người khác đang nợ tôi (debts OPEN)
    monthly: list[MonthTotal]     # 6 tháng gần nhất, dùng vẽ biểu đồ