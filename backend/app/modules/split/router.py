from fastapi import APIRouter

from app.core.errors import COMMON_ERRORS

router = APIRouter(tags=["split"], responses=COMMON_ERRORS)

# TODO: POST /receipts/{receipt_id}/selections   -> chọn món
#       POST /receipts/{receipt_id}/split        -> tính chia tiền
#       GET  /groups/{group_id}/debts            -> công nợ