from fastapi import APIRouter, status

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.groups import service
from app.modules.groups.schemas import (
    GroupCreate,
    GroupDetail,
    GroupOut,
    MemberAdd,
    MemberOut,
)

router = APIRouter(prefix="/groups", tags=["groups"], responses=COMMON_ERRORS)


@router.get("", response_model=list[GroupOut], summary="Danh sách nhóm của tôi")
def list_groups(db: DB, user: CurrentUser):
    return service.list_my_groups(db, user)


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="Tạo nhóm (người tạo là LEADER)")
def create_group(data: GroupCreate, db: DB, user: CurrentUser):
    return service.create_group(db, user, data)


@router.get("/{group_id}", response_model=GroupDetail, summary="Chi tiết nhóm + thành viên")
def get_group(group_id: int, db: DB, user: CurrentUser):
    return service.get_group(db, user, group_id)


@router.get("/{group_id}/members", response_model=list[MemberOut], summary="Danh sách thành viên nhóm")
def list_group_members(group_id: int, db: DB, user: CurrentUser):
    return service.list_group_members(db, user, group_id)


@router.post(
    "/{group_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm thành viên bằng email (chỉ LEADER)",
)
def add_group_member(group_id: int, data: MemberAdd, db: DB, user: CurrentUser):
    return service.add_group_member(db, user, group_id, data)
