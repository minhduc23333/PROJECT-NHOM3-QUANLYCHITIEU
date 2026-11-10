from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Đi Đà Lạt"])


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    created_by: int
    created_at: datetime | None = None
    my_role: str | None = None
    member_count: int | None = None


class MemberOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str
    status: str


class GroupDetail(GroupOut):
    members: list[MemberOut] = []