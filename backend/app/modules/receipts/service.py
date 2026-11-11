from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_group_membership
from app.core.errors import BadRequest, Conflict, NotFound
from app.models import GroupMember, Receipt, User


def list_group_receipts(db: Session, user: User, group_id: int) -> list[Receipt]:
    get_group_membership(db, group_id, user.id)  # 404 / 403
    return list(
        db.scalars(select(Receipt).where(Receipt.group_id == group_id).order_by(Receipt.created_at.desc(), Receipt.id.desc()))
    )


def create_receipt(
    db: Session,
    user: User,
    group_id: int,
    image: bytes,
) -> Receipt:
    get_group_membership(db, group_id, user.id)
    if not image:
        raise BadRequest("Ảnh hóa đơn không được để trống")
    if image.startswith(b"\xff\xd8\xff"):
        extension = ".jpg"
    elif image.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = ".png"
    else:
        raise BadRequest("Chỉ chấp nhận ảnh JPG hoặc PNG hợp lệ")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = upload_dir / f"{uuid4().hex}{extension}"
    try:
        image_path.write_bytes(image)
    except OSError:
        image_path.unlink(missing_ok=True)
        raise

    receipt = Receipt(
        group_id=group_id,
        uploaded_by=user.id,
        image_path=str(image_path),
        status="DRAFT",
        ocr_status="PENDING",
    )
    try:
        db.add(receipt)
        db.commit()
    except Exception:
        db.rollback()
        image_path.unlink(missing_ok=True)
        raise
    db.refresh(receipt)
    return receipt


def update_receipt(db: Session, user: User, receipt_id: int, changes: dict) -> Receipt:
    receipt = _get_receipt_for_member(db, user, receipt_id)
    if receipt.status == "SETTLED":
        raise Conflict("Hóa đơn đã chốt, không thể chỉnh sửa")
    if not changes:
        raise BadRequest("Cần cung cấp ít nhất một trường để cập nhật")

    payer_id = changes.get("payer_id")
    if payer_id is not None:
        payer_membership = db.get(GroupMember, (receipt.group_id, payer_id))
        if payer_membership is None or payer_membership.status != "ACTIVE":
            raise BadRequest("Người trả tiền phải là thành viên ACTIVE trong nhóm")

    for field, value in changes.items():
        setattr(receipt, field, value)
    if receipt.status == "VERIFIED":
        receipt.status = "DRAFT"
    db.commit()
    db.refresh(receipt)
    return receipt


def verify_receipt(db: Session, user: User, receipt_id: int) -> Receipt:
    receipt = _get_receipt_for_member(db, user, receipt_id)
    if receipt.status != "DRAFT":
        raise Conflict("Chỉ hóa đơn DRAFT mới có thể xác nhận")
    receipt.status = "VERIFIED"
    db.commit()
    db.refresh(receipt)
    return receipt


def settle_receipt(db: Session, user: User, receipt_id: int) -> Receipt:
    receipt = _get_receipt_for_member(db, user, receipt_id)
    if receipt.status != "VERIFIED":
        raise Conflict("Chỉ hóa đơn VERIFIED mới có thể chốt")
    receipt.status = "SETTLED"
    db.commit()
    db.refresh(receipt)
    return receipt


def _get_receipt_for_member(db: Session, user: User, receipt_id: int) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise NotFound("Không tìm thấy hóa đơn")
    get_group_membership(db, receipt.group_id, user.id)
    return receipt
