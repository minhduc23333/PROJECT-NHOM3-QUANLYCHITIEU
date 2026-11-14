from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardSummary

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
