from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings  # noqa: F401  (test monkeypatch service.settings.UPLOAD_DIR)
from app.core.deps import get_group_membership
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import GroupMember, Receipt, ReceiptItem, User
from app.modules.receipts import state, uploads
from app.modules.receipts.schemas import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    ReceiptDetail,
    ReceiptUpdate,
    VerifyIn,
)

# Quyền: xem = thành viên ACTIVE; sửa thông tin = người tải lên;
# thêm/sửa/xóa dòng món + xác nhận + chốt = người tải lên hoặc LEADER.
# Luồng trạng thái (xem state.py): DRAFT --verify--> VERIFIED --settle--> SETTLED.
#   - Sửa dữ liệu ảnh hưởng chia tiền khi VERIFIED -> tự quay về DRAFT.
#   - SETTLED: khóa mọi thao tác sửa (409, code RECEIPT_SETTLED).
# Upload ảnh -> tạo DRAFT (ocr_status=PENDING) -> OCR (module ocr) điền dữ liệu.

def list_group_receipts(db: Session, user: User, group_id: int) -> list[Receipt]:
    get_group_membership(db, group_id, user.id)  # 404 / 403
    return list(
        db.scalars(select(Receipt).where(Receipt.group_id == group_id).order_by(Receipt.created_at.desc(), Receipt.id.desc()))
    )


ZERO = Decimal("0")
CENT = Decimal("0.01")
MAX_MONEY = Decimal("10") ** 13  # DECIMAL(15,2) chứa được < 10^13


# ---------- Helper ----------
def _load(db: Session, user: User, receipt_id: int, *, lock: bool = False) -> tuple[Receipt, GroupMember | None]:
    """404 nếu không có hóa đơn; hóa đơn cá nhân chỉ chủ sở hữu truy cập được."""
    stmt = select(Receipt).where(Receipt.id == receipt_id)
    if lock:
        stmt = stmt.with_for_update()  # MySQL: khóa dòng, tránh 2 người xác nhận cùng lúc
    receipt = db.scalar(stmt)
    if receipt is None:
        raise NotFound("Không tìm thấy hóa đơn")
    if receipt.group_id is None:
        if receipt.uploaded_by != user.id:
            raise Forbidden("Bạn không có quyền truy cập hóa đơn cá nhân này")
        return receipt, None
    _, member = get_group_membership(db, receipt.group_id, user.id)
    return receipt, member


def _is_uploader(receipt: Receipt, member: GroupMember | None) -> bool:
    return member is None or member.user_id == receipt.uploaded_by


def _is_uploader_or_leader(receipt: Receipt, member: GroupMember | None) -> bool:
    return _is_uploader(receipt, member) or (member is not None and member.role == "LEADER")


def _require_draft(receipt: Receipt) -> None:
    """Chỉ DRAFT mới xác nhận được (VERIFIED: đã xác nhận rồi; SETTLED: đã chốt)."""
    state.require_not_settled(receipt)
    if receipt.status != state.DRAFT:
        raise Conflict("Hóa đơn đã được xác nhận", code=state.ERR_BAD_TRANSITION)


def _expected_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)


def _resolve_line_total(quantity: Decimal, unit_price: Decimal, line_total: Decimal | None) -> Decimal:
    """line_total = quantity × unit_price. Không gửi → tự tính; gửi mà lệch → 422."""
    expected = _expected_line_total(quantity, unit_price)
    if expected >= MAX_MONEY:
        raise Unprocessable(
            "Thành tiền quá lớn", details=[{"field": "unit_price", "message": "quantity × unit_price quá lớn"}]
        )
    if line_total is not None and line_total != expected:
        raise Unprocessable(
            "Thành tiền không khớp",
            details=[{"field": "line_total", "message": f"line_total phải bằng quantity × unit_price = {expected}"}],
        )
    return expected


def _items(db: Session, receipt_id: int) -> list[ReceiptItem]:
    return list(db.scalars(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id).order_by(ReceiptItem.id)))


def _detail(db: Session, receipt: Receipt, member: GroupMember | None) -> ReceiptDetail:
    items = _items(db, receipt.id)
    editable = not state.is_settled(receipt)
    return ReceiptDetail.model_validate(receipt).model_copy(
        update={
            "items": [ItemOut.model_validate(i) for i in items],
            "items_total": sum((i.line_total for i in items), ZERO),
            "is_locked": not editable,
            "can_verify": receipt.status == state.DRAFT and _is_uploader_or_leader(receipt, member),
            "can_settle": receipt.status == state.VERIFIED and _is_uploader_or_leader(receipt, member),
            "can_edit_receipt": editable and _is_uploader(receipt, member),
            "can_edit_items": editable and _is_uploader_or_leader(receipt, member),
        }
    )


# ---------- Xem + sửa bản nháp ----------
def get_receipt(db: Session, user: User, receipt_id: int) -> ReceiptDetail:
    receipt, member = _load(db, user, receipt_id)
    return _detail(db, receipt, member)


def update_receipt(db: Session, user: User, receipt_id: int, data: ReceiptUpdate) -> ReceiptDetail:
    receipt, member = _load(db, user, receipt_id, lock=True)
    if not _is_uploader(receipt, member):
        raise Forbidden("Chỉ người tải hóa đơn lên mới được sửa thông tin hóa đơn")
    state.require_not_settled(receipt)
    changes = data.model_dump(exclude_unset=True)
    split_inputs_changed = any(
        field in state.SPLIT_FIELDS and getattr(receipt, field) != value
        for field, value in changes.items()
    )
    for field, value in changes.items():
        setattr(receipt, field, value)
    state.reopen_if_split_inputs_changed(db, receipt, split_inputs_changed)
    db.commit()
    return _detail(db, receipt, member)


# ---------- CRUD dòng món ----------
def _load_for_item_edit(db: Session, user: User, receipt_id: int) -> Receipt:
    receipt, member = _load(db, user, receipt_id, lock=True)
    if not _is_uploader_or_leader(receipt, member):
        raise Forbidden("Chỉ người tải lên hoặc trưởng nhóm mới được sửa dòng món")
    state.require_not_settled(receipt)
    return receipt


def _get_item(db: Session, receipt_id: int, item_id: int) -> ReceiptItem:
    item = db.scalar(select(ReceiptItem).where(ReceiptItem.id == item_id, ReceiptItem.receipt_id == receipt_id))
    if item is None:
        raise NotFound("Không tìm thấy dòng món")
    return item


def add_item(db: Session, user: User, receipt_id: int, data: ItemCreate) -> ItemOut:
    receipt = _load_for_item_edit(db, user, receipt_id)
    item = ReceiptItem(
        receipt_id=receipt.id,
        item_name=data.item_name,
        quantity=data.quantity,
        unit_price=data.unit_price,
        line_total=_resolve_line_total(data.quantity, data.unit_price, data.line_total),
    )
    db.add(item)
    state.reopen_if_split_inputs_changed(db, receipt, True)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


def update_item(db: Session, user: User, receipt_id: int, item_id: int, data: ItemUpdate) -> ItemOut:
    receipt = _load_for_item_edit(db, user, receipt_id)
    item = _get_item(db, receipt.id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "item_name" in changes and changes["item_name"] is None:
        raise Unprocessable("Tên món không được để trống", details=[{"field": "item_name", "message": "Bắt buộc"}])

    split_inputs_changed = False
    if {"quantity", "unit_price", "line_total"} & changes.keys():
        quantity = changes.get("quantity") or item.quantity
        unit_price = changes["unit_price"] if changes.get("unit_price") is not None else item.unit_price
        line_total = _resolve_line_total(quantity, unit_price, changes.get("line_total"))
        split_inputs_changed = (quantity, unit_price, line_total) != (item.quantity, item.unit_price, item.line_total)
        item.line_total = line_total
        item.quantity, item.unit_price = quantity, unit_price
    if "item_name" in changes:
        split_inputs_changed = split_inputs_changed or changes["item_name"] != item.item_name
        item.item_name = changes["item_name"]
    state.reopen_if_split_inputs_changed(db, receipt, split_inputs_changed)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


def delete_item(db: Session, user: User, receipt_id: int, item_id: int) -> None:
    receipt = _load_for_item_edit(db, user, receipt_id)
    item = _get_item(db, receipt.id, item_id)
    state.reopen_if_split_inputs_changed(db, receipt, True)
    db.delete(item)
    db.commit()


# ---------- Xác nhận DRAFT -> VERIFIED ----------
def verify_receipt(db: Session, user: User, receipt_id: int, data: VerifyIn) -> ReceiptDetail:
    receipt, member = _load(db, user, receipt_id, lock=True)
    if not _is_uploader_or_leader(receipt, member):
        raise Forbidden("Chỉ người tải lên hoặc trưởng nhóm mới được xác nhận hóa đơn")
    _require_draft(receipt)

    errors: list[dict] = []

    if receipt.group_id is None:
        if data.payer_id != user.id:
            errors.append({"field": "payer_id", "message": "Hóa đơn cá nhân chỉ có thể chọn chủ tài khoản làm người trả tiền"})
    else:
        payer = db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == receipt.group_id,
                GroupMember.user_id == data.payer_id,
                GroupMember.status == "ACTIVE",
            )
        )
        if payer is None:
            errors.append({"field": "payer_id", "message": "Người trả tiền phải là thành viên đang hoạt động của nhóm"})

    items = _items(db, receipt.id)
    if not items:
        errors.append({"field": "items", "message": "Hóa đơn chưa có dòng món nào"})
    bad_lines = [i.id for i in items if i.line_total != _expected_line_total(i.quantity, i.unit_price)]
    if bad_lines:
        errors.append({"field": "items", "message": f"Dòng món {bad_lines} có line_total ≠ quantity × unit_price"})

    items_sum = sum((i.line_total for i in items), ZERO)
    if receipt.subtotal is None:
        errors.append({"field": "subtotal", "message": "Chưa có tạm tính (subtotal)"})
    elif receipt.subtotal != items_sum:
        errors.append({"field": "subtotal", "message": f"subtotal ({receipt.subtotal}) ≠ tổng các dòng món ({items_sum})"})

    if receipt.total_amount is None:
        errors.append({"field": "total_amount", "message": "Chưa có tổng tiền (total_amount)"})
    elif receipt.subtotal is not None:
        expected_total = receipt.subtotal + (receipt.tax_amount or ZERO) + (receipt.service_fee or ZERO)
        if receipt.total_amount != expected_total:
            errors.append(
                {
                    "field": "total_amount",
                    "message": f"total_amount ({receipt.total_amount}) ≠ subtotal + thuế + phí dịch vụ ({expected_total})",
                }
            )

    if errors:
        db.rollback()  # nhả khóa dòng; chưa ghi gì nên hóa đơn vẫn DRAFT
        raise Unprocessable("Hóa đơn chưa hợp lệ để xác nhận", details=errors)

    # Ghi payer + trạng thái trong cùng 1 transaction (1 commit); lỗi → rollback, vẫn DRAFT
    try:
        receipt.payer_id = data.payer_id
        state.transition(receipt, state.VERIFIED)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _detail(db, receipt, member)



# ---------- Tải ảnh hóa đơn (tạo bản nháp, chờ OCR) ----------
def require_upload_access(db: Session, user: User, group_id: int) -> None:
    """Người tải lên phải là thành viên ACTIVE của nhóm (404 nhóm không tồn tại / 403)."""
    get_group_membership(db, group_id, user.id)


def _create_receipt(db: Session, user: User, image: bytes, group_id: int | None) -> Receipt:
    extension = uploads.validate_image(image)  # 400 nếu rỗng / sai magic bytes
    image_path = uploads.save_image(image, extension)

    # Tạo DRAFT + ocr_status=PENDING TRƯỚC; OCR chạy sau qua POST /api/ocr/receipts/{id}
    receipt = Receipt(
        group_id=group_id,
        uploaded_by=user.id,
        image_path=str(image_path),
        status=state.DRAFT,
        ocr_status="PENDING",
    )
    try:
        db.add(receipt)
        db.commit()
    except Exception:
        db.rollback()
        image_path.unlink(missing_ok=True)  # không để lại file mồ côi nếu ghi DB lỗi
        raise
    db.refresh(receipt)
    return receipt


def create_receipt(db: Session, user: User, group_id: int, image: bytes) -> Receipt:
    require_upload_access(db, user, group_id)
    return _create_receipt(db, user, image, group_id)


def create_personal_receipt(db: Session, user: User, image: bytes) -> Receipt:
    return _create_receipt(db, user, image, None)


# ---------- Chốt VERIFIED -> SETTLED ----------
def settle_receipt(db: Session, user: User, receipt_id: int) -> ReceiptDetail:
    receipt, member = _load(db, user, receipt_id, lock=True)
    if not _is_uploader_or_leader(receipt, member):
        raise Forbidden("Chỉ người tải lên hoặc trưởng nhóm mới được chốt hóa đơn")
    if receipt.status != state.VERIFIED:
        db.rollback()
        if state.is_settled(receipt):
            raise Conflict("Hóa đơn đã được chốt", code=state.ERR_SETTLED)
        raise Conflict("Chỉ hóa đơn VERIFIED mới có thể chốt", code=state.ERR_BAD_TRANSITION)
    state.transition(receipt, state.SETTLED)
    db.commit()
    return _detail(db, receipt, member)
