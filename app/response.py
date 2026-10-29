from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageData(BaseModel, Generic[T]):
    """分页数据，放在 ApiResponse.data 里。"""

    items: list[T]
    total: int
    page: int
    size: int


class ApiResponse(BaseModel, Generic[T]):
    """统一响应外壳：code=0 表示成功，失败时 code 等于 HTTP 状态码。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}
