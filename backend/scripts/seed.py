"""Chạy: python -m scripts.seed (từ thư mục backend). Chạy lại nhiều lần không bị trùng."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Group, GroupMember, User

DEMO_PASSWORD = "123456"


def main():
    with SessionLocal() as db:
        users = []
        for name, email in [("An Nguyễn", "an@demo.vn"), ("Bình Trần", "binh@demo.vn"), ("Chi Lê", "chi@demo.vn")]:
            u = db.scalar(select(User).where(User.email == email))
            if not u:
                u = User(full_name=name, email=email, password_hash=hash_password(DEMO_PASSWORD))
                db.add(u)
                db.flush()
            users.append(u)

        group = db.scalar(select(Group).where(Group.name == "Nhóm demo"))
        if not group:
            group = Group(name="Nhóm demo", created_by=users[0].id)
            db.add(group)
            db.flush()
            db.add(GroupMember(group_id=group.id, user_id=users[0].id, role="LEADER", status="ACTIVE"))
            for u in users[1:]:
                db.add(GroupMember(group_id=group.id, user_id=u.id, role="MEMBER", status="ACTIVE"))
        db.commit()
        print("Seed xong: 3 user (mật khẩu 123456) + 1 nhóm demo")


if __name__ == "__main__":
    main()