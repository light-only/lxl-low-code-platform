from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.response import ApiResponse, success
from app.schemas import TokenRead, UserCreate, UserRead
from app.security import pwd_context
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"exp": expire, "sub": subject}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


@router.post("/token", response_model=ApiResponse[TokenRead])
async def login(
    username: str,
    password: str,
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.username == username))
    if user is None or not pwd_context.verify(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.username)
    return success({"access_token": token, "token_type": "bearer"})


@router.post("/register", response_model=ApiResponse[UserRead], status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await UserService(db).create(payload)
    return success(user)