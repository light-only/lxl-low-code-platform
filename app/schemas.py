from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    name: str
    username: str
    phone: str
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    """创建用户 / 注册的请求体。"""

    password: str


class UserRead(UserBase):
    """返回给前端的用户信息，不含密码。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool
    created_at: datetime


class TokenRead(BaseModel):
    """登录成功后返回的令牌信息。"""

    access_token: str
    token_type: str = "bearer"
