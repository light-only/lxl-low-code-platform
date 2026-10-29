from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.response import ApiResponse, PageData, success
from app.schemas import UserCreate, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=ApiResponse[PageData[UserRead]])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return success(await UserService(db).list_page(page, size))


@router.post("", response_model=ApiResponse[UserRead], status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await UserService(db).create(payload)
    return success(user)
