from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100, examples=["An Nguyễn"])
    email: EmailStr = Field(examples=["an@demo.vn"])
    password: str = Field(min_length=6, max_length=72, examples=["123456"])


class LoginIn(BaseModel):
    email: EmailStr = Field(examples=["an@demo.vn"])
    password: str = Field(min_length=1, examples=["123456"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    created_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut