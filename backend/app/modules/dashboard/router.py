from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.dashboard import report, service
from app.modules.dashboard.schemas import DashboardSummary, SpendingReport

router = APIRouter(prefix="/dashboard", tags=["dashboard"], responses=COMMON_ERRORS)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Số liệu tổng quan (chỉ hóa đơn SETTLED) + dữ liệu biểu đồ",
)
def get_summary(db: DB, user: CurrentUser):
    """Chi tiêu cá nhân (Σ final_amount), chi tiêu nhóm (Σ total_amount), số nhóm, số hóa đơn,
    5 hóa đơn gần nhất, chi tiêu theo tháng/danh mục. Không có dữ liệu thì trả 0 / danh sách rỗng."""
    return service.summary(db, user)


@router.get(
    "/report",
    response_model=SpendingReport,
    summary="Báo cáo chi tiêu theo thời gian và danh mục (chỉ hóa đơn SETTLED)",
)
def get_report(
    db: DB,
    user: CurrentUser,
    date_from: date | None = Query(None, description="Từ ngày (mặc định: đầu tháng cách đây 5 tháng)"),
    date_to: date | None = Query(None, description="Đến ngày (mặc định: hôm nay)"),
    granularity: Literal["auto", "day", "week", "month"] = Query("auto", description="Gom theo ngày/tuần/tháng; auto tự chọn theo độ dài khoảng"),
    scope: Literal["me", "group"] = Query("me", description="me: phần chi tiêu của tôi; group: tổng hóa đơn của nhóm"),
    group_id: int | None = Query(None, description="Chỉ một nhóm (phải là thành viên)"),
):
    """T05E180. Trả về tổng, số hóa đơn, trung bình mỗi kỳ, chuỗi theo kỳ (kèm chia theo danh mục),
    tổng theo danh mục (kèm %) và 5 cửa hàng chi nhiều nhất. Khoảng thời gian tối đa 2 năm (422)."""
    return report.spending_report(
        db, user, date_from=date_from, date_to=date_to, granularity=granularity, scope=scope, group_id=group_id
    )
