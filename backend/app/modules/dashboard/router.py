from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"], responses=COMMON_ERRORS)


@router.get("/summary", response_model=DashboardSummary, summary="Số liệu tổng quan + chi tiêu 6 tháng")
def get_summary(db: DB, user: CurrentUser):
    return service.summary(db, user)