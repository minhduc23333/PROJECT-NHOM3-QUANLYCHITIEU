from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.receipts import service
from app.modules.receipts.schemas import ReceiptOut, ReceiptUpdate

router = APIRouter(tags=["receipts"], responses=COMMON_ERRORS)


@router.get("/groups/{group_id}/receipts", response_model=list[ReceiptOut], summary="Hóa đơn của một nhóm")
def list_receipts(group_id: int, db: DB, user: CurrentUser):
    return service.list_group_receipts(db, user, group_id)


@router.post(
    "/groups/{group_id}/receipts",
    response_model=ReceiptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tải ảnh hóa đơn",
)
async def upload_receipt(
    group_id: int,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
):
    image = await file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(image) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Ảnh không được vượt quá {settings.MAX_UPLOAD_MB} MB")
    return service.create_receipt(db, user, group_id, image)


@router.patch("/receipts/{receipt_id}", response_model=ReceiptOut, summary="Cập nhật dữ liệu hóa đơn")
def update_receipt(receipt_id: int, data: ReceiptUpdate, db: DB, user: CurrentUser):
    return service.update_receipt(db, user, receipt_id, data.model_dump(exclude_unset=True))


@router.post("/receipts/{receipt_id}/verify", response_model=ReceiptOut, summary="Xác nhận hóa đơn")
def verify_receipt(receipt_id: int, db: DB, user: CurrentUser):
    return service.verify_receipt(db, user, receipt_id)


@router.post("/receipts/{receipt_id}/settle", response_model=ReceiptOut, summary="Chốt hóa đơn")
def settle_receipt(receipt_id: int, db: DB, user: CurrentUser):
    return service.settle_receipt(db, user, receipt_id)
