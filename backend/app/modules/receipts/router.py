from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.receipts import service
from app.modules.receipts.schemas import ReceiptOut

router = APIRouter(tags=["receipts"], responses=COMMON_ERRORS)


@router.get("/groups/{group_id}/receipts", response_model=list[ReceiptOut], summary="Hóa đơn của một nhóm")
def list_receipts(group_id: int, db: DB, user: CurrentUser):
    return service.list_group_receipts(db, user, group_id)