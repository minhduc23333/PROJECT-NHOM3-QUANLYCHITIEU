# API xử lý tạo nhóm

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_group_membership
from app.models import Group, GroupMember, User
from app.modules.groups.schemas import GroupCreate, GroupDetail, GroupOut, MemberOut


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
    rows = db.execute(
        select(GroupMember, User)
        .join(User, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.role, User.full_name)
    ).all()
    members = [
        MemberOut(user_id=u.id, full_name=u.full_name, email=u.email, role=m.role, status=m.status) for m, u in rows
    ]
    active = sum(1 for m in members if m.status == "ACTIVE")
    return GroupDetail.model_validate(group).model_copy(
        update={"my_role": me.role, "member_count": active, "members": members}
    )