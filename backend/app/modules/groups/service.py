from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_group_membership, require_leader
from app.core.errors import Conflict, NotFound
from app.models import Group, GroupMember, User
from app.modules.groups.schemas import (
    GroupCreate,
    GroupDetail,
    GroupOut,
    MemberAdd,
    MemberOut,
)


def list_my_groups(db: Session, user: User) -> list[GroupOut]:
    count_sq = (
        select(GroupMember.group_id, func.count().label("n"))
        .where(GroupMember.status == "ACTIVE")
        .group_by(GroupMember.group_id)
        .subquery()
    )
    rows = db.execute(
        select(Group, GroupMember.role, count_sq.c.n)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .join(count_sq, count_sq.c.group_id == Group.id)
        .where(GroupMember.user_id == user.id, GroupMember.status == "ACTIVE")
        .order_by(Group.created_at.desc(), Group.id.desc())
    ).all()
    return [
        GroupOut.model_validate(g).model_copy(update={"my_role": role, "member_count": n}) for g, role, n in rows
    ]


def create_group(db: Session, user: User, data: GroupCreate) -> GroupOut:
    group = Group(name=data.name.strip(), created_by=user.id)
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id, role="LEADER", status="ACTIVE"))
    db.commit()
    db.refresh(group)
    return GroupOut.model_validate(group).model_copy(update={"my_role": "LEADER", "member_count": 1})


def get_group(db: Session, user: User, group_id: int) -> GroupDetail:
    group, me = get_group_membership(db, group_id, user.id)  # 404 / 403
    members = _list_members(db, group_id)
    active = sum(1 for member in members if member.status == "ACTIVE")
    return GroupDetail.model_validate(group).model_copy(
        update={"my_role": me.role, "member_count": active, "members": members}
    )


def list_group_members(db: Session, user: User, group_id: int) -> list[MemberOut]:
    get_group_membership(db, group_id, user.id)
    return _list_members(db, group_id)


def add_group_member(db: Session, user: User, group_id: int, data: MemberAdd) -> MemberOut:
    _, requester = get_group_membership(db, group_id, user.id)
    require_leader(requester)

    email = str(data.email).lower()
    invited_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if invited_user is None:
        raise NotFound("Không tìm thấy tài khoản với email này")

    membership = db.get(GroupMember, (group_id, invited_user.id))
    if membership is not None:
        if membership.status == "ACTIVE":
            raise Conflict("Thành viên đã có trong nhóm")
        membership.status = "ACTIVE"
        membership.role = "MEMBER"
    else:
        membership = GroupMember(group_id=group_id, user_id=invited_user.id, role="MEMBER", status="ACTIVE")
        db.add(membership)

    db.commit()
    return MemberOut(
        user_id=invited_user.id,
        full_name=invited_user.full_name,
        email=invited_user.email,
        role=membership.role,
        status=membership.status,
    )


def _list_members(db: Session, group_id: int) -> list[MemberOut]:
    rows = db.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.role, User.full_name)
    ).all()
    return [
        MemberOut(user_id=u.id, full_name=u.full_name, email=u.email, role=m.role, status=m.status) for m, u in rows
    ]
