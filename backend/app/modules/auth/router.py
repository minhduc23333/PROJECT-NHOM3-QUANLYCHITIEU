from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.modules.auth import service
from app.modules.auth.deps import get_current_user
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    return service.register(db, data)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    return service.login(db, data)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
