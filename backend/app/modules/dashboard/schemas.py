from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class MonthTotal(BaseModel):
    month: str  # "2026-11"
    total: Decimal


class CategoryTotal(BaseModel):
    category: str  # hóa đơn chưa có category -> "Khác"
    total: Decimal


class RecentReceipt(BaseModel):
    id: int
    group_id: int | None = None       # None = hóa đơn cá nhân
    group_name: str | None = None
    merchant_name: str | None = None
    receipt_date: date | None = None
    category: str | None = None
    total_amount: Decimal | None = None   # tổng hóa đơn
    my_amount: Decimal                    # phần của tôi (final_amount); 0 nếu tôi không tham gia


class DashboardSummary(BaseModel):
    """Chỉ tính hóa đơn SETTLED trong phạm vi quyền của người dùng; không có dữ liệu thì trả 0 / danh sách rỗng."""

    group_count: int                  # nhóm tôi đang là thành viên ACTIVE
    receipt_count: int                # số hóa đơn SETTLED (nhóm của tôi + hóa đơn cá nhân)
    personal_spent: Decimal           # Σ final_amount của tôi (+ total_amount hóa đơn cá nhân)
    group_spent: Decimal              # Σ total_amount hóa đơn SETTLED thuộc các nhóm của tôi
    i_owe: Decimal                    # tôi đang nợ người khác (debts OPEN)
    owed_to_me: Decimal               # người khác đang nợ tôi (debts OPEN)
    monthly: list[MonthTotal]         # chi tiêu cá nhân 6 tháng gần nhất (biểu đồ cột)
    by_category: list[CategoryTotal]  # chi tiêu cá nhân theo danh mục, giảm dần (biểu đồ tròn)
    recent_receipts: list[RecentReceipt]  # 5 hóa đơn SETTLED gần nhất
