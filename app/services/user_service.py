from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.models.user import User
from app.schemas import UserCreate
from app.security import pwd_context
from app.services.base import BaseService


class UserService(BaseService):
    """Example service. Move CRUD / business rules here."""

    async def list_page(self, page: int, size: int) -> dict:
        total = await self.db.scalar(select(func.count()).select_from(User)) or 0
        result = await self.db.execute(
            select(User).order_by(User.id).offset((page - 1) * size).limit(size)
        )
        return {
            "items": list(result.scalars().all()),
            "total": total,
            "page": page,
            "size": size,
        }

    async def list_all(self) -> list[User]:
        result = await self.db.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

    async def create(self,payload:UserCreate) -> User:
        if await self.db.scalar(select(User).where(User.username == payload.username)):
               raise HTTPException(status.HTTP_409_CONFLICT, "账号已存在")

        user = User(
            name=payload.name,
            username=payload.username,
            phone=payload.phone,
            email=payload.email,
            hashed_password=pwd_context.hash(payload.password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user