from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile, status

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS, ErrorResponse
from app.modules.receipts import service, uploads
from app.modules.receipts.schemas import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    ReceiptDetail,
    ReceiptOut,
    ReceiptUpdate,
    VerifyIn,
)

router = APIRouter(
    tags=["receipts"],
    responses={**COMMON_ERRORS, 409: {"model": ErrorResponse, "description": "Hóa đơn không còn ở trạng thái DRAFT"}},
)


@router.get("/groups/{group_id}/receipts", response_model=list[ReceiptOut], summary="Hóa đơn của một nhóm")
def list_receipts(group_id: int, db: DB, user: CurrentUser):
    return service.list_group_receipts(db, user, group_id)


@router.post(
    "/groups/{group_id}/receipts",
    response_model=ReceiptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tải ảnh hóa đơn (tạo bản nháp DRAFT, ocr_status=PENDING)",
    description=(
        "Chỉ nhận JPG/PNG ≤ `MAX_UPLOAD_MB` (mặc định 5 MB). Loại file kiểm tra bằng magic bytes, "
        "không tin content-type/tên file client gửi. Người tải lên phải là thành viên ACTIVE của nhóm. "
        "Hóa đơn DRAFT được tạo trước; OCR chạy riêng qua `POST /api/ocr/receipts/{id}`."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "File rỗng / không phải JPG, PNG hợp lệ"},
        413: {"model": ErrorResponse, "description": "Ảnh vượt giới hạn dung lượng"},
    },
)
async def upload_receipt(group_id: int, db: DB, user: CurrentUser, file: Annotated[UploadFile, File()]):
    service.require_upload_access(db, user, group_id)  # kiểm tra thành viên ACTIVE trước khi đọc file
    image = await uploads.read_limited(file)           # 413 nếu > MAX_UPLOAD_MB
    return service.create_receipt(db, user, group_id, image)


@router.post(
    "/receipts/personal",
    response_model=ReceiptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tải ảnh hóa đơn cá nhân (không cần nhóm, chỉ chủ tài khoản xem được)",
)
async def upload_personal_receipt(db: DB, user: CurrentUser, file: Annotated[UploadFile, File()]):
    image = await uploads.read_limited(file)
    return service.create_personal_receipt(db, user, image)


@router.get("/receipts/{receipt_id}", response_model=ReceiptDetail, summary="Xem hóa đơn + các dòng món (bản nháp)")
def get_receipt(receipt_id: int, db: DB, user: CurrentUser):
    return service.get_receipt(db, user, receipt_id)


@router.patch(
    "/receipts/{receipt_id}",
    response_model=ReceiptDetail,
    summary="Sửa thông tin hóa đơn / kết quả OCR (người tải lên)",
    description="Đổi tiền (subtotal/thuế/phí/tổng) khi đang VERIFIED → hóa đơn tự quay về DRAFT. SETTLED → 409.",
)
def update_receipt(receipt_id: int, data: ReceiptUpdate, db: DB, user: CurrentUser):
    return service.update_receipt(db, user, receipt_id, data)


@router.post(
    "/receipts/{receipt_id}/items",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm dòng món (người tải lên hoặc Leader)",
)
def add_item(receipt_id: int, data: ItemCreate, db: DB, user: CurrentUser):
    return service.add_item(db, user, receipt_id, data)


@router.patch("/receipts/{receipt_id}/items/{item_id}", response_model=ItemOut, summary="Sửa dòng món (người tải lên hoặc Leader)")
def update_item(receipt_id: int, item_id: int, data: ItemUpdate, db: DB, user: CurrentUser):
    return service.update_item(db, user, receipt_id, item_id, data)


@router.delete(
    "/receipts/{receipt_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa dòng món (người tải lên hoặc Leader)",
)
def delete_item(receipt_id: int, item_id: int, db: DB, user: CurrentUser):
    service.delete_item(db, user, receipt_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/receipts/{receipt_id}/verify",
    response_model=ReceiptDetail,
    summary="Xác nhận hóa đơn DRAFT → VERIFIED (chọn người trả, kiểm tra tổng tiền)",
)
def verify_receipt(receipt_id: int, data: VerifyIn, db: DB, user: CurrentUser):
    return service.verify_receipt(db, user, receipt_id, data)


@router.post(
    "/receipts/{receipt_id}/settle",
    response_model=ReceiptDetail,
    summary="Chốt hóa đơn VERIFIED → SETTLED (người tải lên hoặc Leader)",
)
def settle_receipt(receipt_id: int, db: DB, user: CurrentUser):
    return service.settle_receipt(db, user, receipt_id)
