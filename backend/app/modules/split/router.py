from typing import Literal

from fastapi import APIRouter, Query

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS, ErrorResponse
from app.modules.split import service
from app.modules.split.schemas import DebtList, DebtOut, SelectionSummary, SplitResult

router = APIRouter(tags=["split"], responses=COMMON_ERRORS)

_SETTLED_409 = {409: {"model": ErrorResponse, "description": "Hóa đơn đã SETTLED (RECEIPT_SETTLED) hoặc sai trạng thái"}}


# ---------- Chọn / bỏ chọn món ----------
@router.get(
    "/receipts/{receipt_id}/selections",
    response_model=SelectionSummary,
    summary="Ai chọn món nào: tổng tạm tính từng người + món chưa ai chọn",
    description="Thành viên ACTIVE của nhóm. Hóa đơn cá nhân → 400 `PERSONAL_RECEIPT`.",
)
def get_selections(receipt_id: int, db: DB, user: CurrentUser):
    return service.selection_summary(db, user, receipt_id)


@router.put(
    "/receipts/{receipt_id}/items/{item_id}/selection",
    response_model=SelectionSummary,
    summary="Chọn món cho mình hoặc thành viên khác (chỉ LEADER)",
    description=(
        "Mặc định chọn cho chính mình. LEADER có thể truyền `user_id` để chọn thay thành viên ACTIVE. "
        "Idempotent. Nhiều người có thể cùng chọn 1 món → chia đều. Dùng được khi hóa đơn DRAFT hoặc VERIFIED; "
        "SETTLED → 409. Trả lại bảng tổng tạm tính mới."
    ),
    responses=_SETTLED_409,
)
def select_item(
    receipt_id: int, item_id: int, db: DB, user: CurrentUser, user_id: int | None = Query(None, gt=0)
):
    return service.select_item(db, user, receipt_id, item_id, user_id)


@router.delete(
    "/receipts/{receipt_id}/items/{item_id}/selection",
    response_model=SelectionSummary,
    summary="Bỏ chọn món của mình hoặc thành viên khác (chỉ LEADER)",
    description="Mặc định bỏ chọn cho chính mình. LEADER có thể truyền `user_id` để bỏ chọn thay thành viên ACTIVE. Idempotent.",
    responses=_SETTLED_409,
)
def deselect_item(
    receipt_id: int, item_id: int, db: DB, user: CurrentUser, user_id: int | None = Query(None, gt=0)
):
    return service.deselect_item(db, user, receipt_id, item_id, user_id)


# ---------- Chốt + chia tiền + công nợ ----------
@router.post(
    "/receipts/{receipt_id}/split",
    response_model=SplitResult,
    summary="Chốt hóa đơn: tính chia, ghi split_details + debts, chuyển SETTLED (chỉ LEADER)",
    description=(
        "Hóa đơn phải `VERIFIED`. Chặn (422) nếu còn món chưa ai chọn hoặc tổng tiền không khớp. "
        "Tạo nợ cho mọi người ≠ người trả có số tiền > 0. Thuế/phí chia theo tỉ lệ; phần lẻ đồng dồn cho người trả. "
        "Toàn bộ trong 1 transaction."
    ),
    responses={**_SETTLED_409, 422: {"model": ErrorResponse, "description": "Chưa đủ điều kiện chốt (details liệt kê lỗi)"}},
)
def finalize_receipt(receipt_id: int, db: DB, user: CurrentUser):
    return service.finalize_receipt(db, user, receipt_id)


# ---------- Công nợ ----------
@router.get(
    "/receipts/{receipt_id}/debts",
    response_model=DebtList,
    summary="Công nợ của một hóa đơn",
    description="`debtor` = người phải trả, `creditor` = người nhận (người đã trả hóa đơn).",
)
def receipt_debts(
    receipt_id: int,
    db: DB,
    user: CurrentUser,
    status: Literal["OPEN", "PAID"] | None = Query(None, description="Lọc theo trạng thái"),
    mine: bool = Query(False, description="Chỉ các khoản liên quan tới tôi"),
):
    return service.receipt_debts(db, user, receipt_id, status=status, mine=mine)


@router.get(
    "/groups/{group_id}/debts",
    response_model=DebtList,
    summary="Công nợ của cả nhóm (mọi hóa đơn)",
    description="Chỉ thành viên ACTIVE của nhóm. Người ngoài nhóm → 403, nhóm không tồn tại → 404.",
)
def group_debts(
    group_id: int,
    db: DB,
    user: CurrentUser,
    status: Literal["OPEN", "PAID"] | None = Query(None, description="Lọc theo trạng thái"),
    mine: bool = Query(False, description="Chỉ các khoản liên quan tới tôi"),
):
    return service.group_debts(db, user, group_id, status=status, mine=mine)


@router.patch(
    "/debts/{debt_id}/pay",
    response_model=DebtOut,
    summary="Xác nhận khoản nợ đã được thanh toán",
    description="Chỉ chủ nợ hoặc LEADER ACTIVE của nhóm được xác nhận. Khoản đã PAID trả 409 `DEBT_ALREADY_PAID`.",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def pay_debt(debt_id: int, db: DB, user: CurrentUser):
    return service.pay_debt(db, user, debt_id)
