from datetime import date, datetime
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
    created_at: datetime | None = None
    category: str | None = None
    status: str
    total_amount: Decimal | None = None   # tổng hóa đơn
    my_amount: Decimal                    # phần của tôi (final_amount); 0 nếu tôi không tham gia


class DashboardSummary(BaseModel):
    """Chi tiêu gồm hóa đơn nhóm SETTLED và hóa đơn cá nhân VERIFIED/SETTLED; danh sách gần đây gồm mọi hóa đơn được xem."""

    group_count: int                  # nhóm tôi đang là thành viên ACTIVE
    receipt_count: int                # số hóa đơn SETTLED (nhóm của tôi + hóa đơn cá nhân)
    total_receipt_count: int           # mọi hóa đơn trong nhóm đang tham gia + hóa đơn cá nhân của tôi
    personal_spent: Decimal           # Σ final_amount nhóm đã chốt + total_amount hóa đơn cá nhân đã xác nhận
    group_spent: Decimal              # Σ total_amount hóa đơn SETTLED thuộc các nhóm của tôi
    i_owe: Decimal                    # tôi đang nợ người khác (debts OPEN)
    owed_to_me: Decimal               # người khác đang nợ tôi (debts OPEN)
    monthly: list[MonthTotal]         # chi tiêu cá nhân 6 tháng gần nhất (biểu đồ cột)
    by_category: list[CategoryTotal]  # chi tiêu cá nhân theo danh mục, giảm dần (biểu đồ tròn)
    recent_receipts: list[RecentReceipt]  # 5 hóa đơn gần đây nhất trong phạm vi quyền


# ---------- Báo cáo chi tiêu theo thời gian / danh mục (T05E180) ----------
class ReportPeriod(BaseModel):
    key: str                            # "2026-11", "2026-W46", "2026-11-16"
    label: str                          # nhãn ngắn để vẽ trục: "11/2026", "16/11", ...
    start: date
    end: date
    total: Decimal
    by_category: dict[str, Decimal]     # dùng cho biểu đồ cột chồng theo danh mục


class ReportCategory(BaseModel):
    category: str
    total: Decimal
    receipt_count: int
    percent: float                      # % trên tổng, làm tròn 1 chữ số


class ReportMerchant(BaseModel):
    merchant: str
    total: Decimal
    receipt_count: int


class SpendingReport(BaseModel):
    """Nhóm tính SETTLED; phần của tôi còn tính hóa đơn cá nhân VERIFIED/SETTLED."""

    date_from: date
    date_to: date
    granularity: str                    # day | week | month
    scope: str                          # me: phần của tôi | group: tổng hóa đơn của nhóm
    group_id: int | None = None
    total: Decimal
    receipt_count: int
    average_per_period: Decimal
    periods: list[ReportPeriod]         # đủ mọi kỳ trong khoảng, kỳ không có chi tiêu = 0
    by_category: list[ReportCategory]   # giảm dần theo số tiền
    top_merchants: list[ReportMerchant] # tối đa 5
