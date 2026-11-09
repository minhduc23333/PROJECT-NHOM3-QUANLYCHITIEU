"""Dependency dùng chung cho các router."""
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.security import decode_access_token
from app.models import Group, GroupMember, User

# auto_error=False để tự trả lỗi 401 đúng định dạng chung
bearer = HTTPBearer(auto_error=False, description="Dán access_token lấy từ /api/auth/login")

DB = Annotated[Session, Depends(get_db)]


def get_current_user(db: DB, cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if cred is None:
        raise Unauthorized("Bạn cần đăng nhập")
    user_id = decode_access_token(cred.credentials)
    if user_id is None:
        raise Unauthorized("Phiên đăng nhập không hợp lệ hoặc đã hết hạn")
    user = db.get(User, user_id)
    if user is None:
        raise Unauthorized("Tài khoản không tồn tại")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_group_membership(db: Session, group_id: int, user_id: int) -> tuple[Group, GroupMember]:
    """404 nếu nhóm không tồn tại, 403 nếu user không phải thành viên ACTIVE."""
    group = db.get(Group, group_id)
    if group is None:
        raise NotFound("Không tìm thấy nhóm")
    member = db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
            GroupMember.status == "ACTIVE",
        )
    )
    if member is None:
        raise Forbidden("Bạn không phải thành viên của nhóm này")
    return group, member


def require_leader(member: GroupMember) -> None:
    if member.role != "LEADER":
        raise Forbidden("Chỉ trưởng nhóm mới được thực hiện thao tác này")