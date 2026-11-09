from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_group_membership
from app.models import Receipt, User


def list_group_receipts(db: Session, user: User, group_id: int) -> list[Receipt]:
    get_group_membership(db, group_id, user.id)  # 404 / 403
    return list(
        db.scalars(select(Receipt).where(Receipt.group_id == group_id).order_by(Receipt.created_at.desc(), Receipt.id.desc()))
    )

# TODO: upload ảnh hóa đơn (lưu vào settings.UPLOAD_DIR, giới hạn settings.MAX_UPLOAD_MB),
#       sửa món / tổng tiền ở trạng thái DRAFT, chuyển DRAFT -> VERIFIED.