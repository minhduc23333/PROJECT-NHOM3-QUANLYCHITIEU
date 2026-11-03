from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        CheckConstraint("role IN ('LEADER','MEMBER')", name="ck_gm_role"),
        CheckConstraint("status IN ('ACTIVE','REMOVED')", name="ck_gm_status"),
    )

    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="MEMBER")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())