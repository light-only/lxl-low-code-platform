# 统一后端 API 返回结构 — 设计文档

- 日期：2026-10-28
- 状态：已实现（2026-10-28）
- 范围：`lxl-low-code-platform-backend`（FastAPI）

## 目标

所有业务接口的成功与失败响应使用同一外层结构，便于前端统一解包、统一错误提示。

## 响应结构

```jsonc
// 成功
{
  "code": 0,
  "message": "ok",
  "data": { }
}

// 失败
{
  "code": 409,
  "message": "账号已存在",
  "data": null
}
```

约定：

- `code = 0` 表示成功；失败时 `code` 等于 HTTP 状态码。
- HTTP 状态码保持语义（201/401/404/409/422/500 等），不统一改成 200。
- `message` 是可直接展示给用户的文案。
- `data` 承载业务数据；失败时为 `null`（参数校验失败时携带 `{"errors": [...]}`）。

## 模型定义

新增 `app/response.py`（响应模型与 `success` 辅助函数）：

```python
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}
```

`ApiResponse` / `PageData` 使用 `Generic`，接口通过 `response_model=ApiResponse[UserRead]` 等声明，
让 OpenAPI 文档同步反映统一外壳。

## 各接口返回

| 接口 | response_model | data |
|---|---|---|
| `POST /auth/token` | `ApiResponse[TokenRead]` | `{"access_token": "...", "token_type": "bearer"}` |
| `POST /auth/register` | `ApiResponse[UserRead]`（201） | 新建用户 |
| `GET /users` | `ApiResponse[PageData[UserRead]]` | `{items, total, page, size}` |
| `POST /users` | `ApiResponse[UserRead]`（201） | 新建用户 |
| `GET /` | `ApiResponse[dict[str, str]]` | `{"message": "...", "docs": "/docs"}` |

`GET /health` 保持原样 `{"status": "ok"}`，因为它是给探针/网管用的基础设施接口，包壳会要求改探针配置。

新增 `TokenRead` schema（`access_token: str`、`token_type: str = "bearer"`）。

## 列表分页

`GET /users` 增加 query 参数：

- `page`：默认 1，`ge=1`
- `size`：默认 10，`ge=1, le=100`

返回 `data = {items, total, page, size}`。`UserService` 增加 `list_page(page, size)`，
使用 `SELECT count(*)` 与 `offset/limit` 查询。

## 错误处理

新增 `app/exceptions.py`，提供 `register_exception_handlers(app)`，在 `main.py` 中调用。处理器：

1. `starlette.exceptions.HTTPException`（含 FastAPI `HTTPException`）
   - `code = exc.status_code`
   - `message = exc.detail`（非字符串时 JSON 序列化为字符串）
   - 透传 `exc.headers`
2. `fastapi.exceptions.RequestValidationError`
   - 422
   - `message = "请求参数校验失败"`
   - `data = {"errors": jsonable_encoder(exc.errors())}`
3. `Exception`（兜底）
   - 记录 `logger.exception`
   - 500，`message = "服务器内部错误"`，不泄露堆栈
4. 404 / 405 由第 1 条覆盖（Starlette 的 `HTTPException`）。

## 顺带修复

- `POST /auth/register` 当前实现 `UserCreate(db).create(payload)` 把 Pydantic 模型当 Service 使用，
  必然 500；改为 `UserService(db).create(payload)`。
- `app/routers/users.py` 中重复的创建逻辑改为调用 `UserService`。
- `GET /users` 的 `page` / `size` 参数落地，避免前端传了被忽略。

## 测试

- 保留 `test_health`。
- 新增测试：登录成功/失败、注册、分页列表、422 参数校验、404 的响应结构断言。
- 测试通过 `app.dependency_overrides[get_db]` 注入内存 SQLite 会话；不依赖真实 MySQL。
- 兜底 500 处理器测试使用 `TestClient(app, raise_server_exceptions=False)`。

## 不在本次范围

- 前端 `src/utils/request.ts` 的解包改造（另一个仓库，待后端定稿后单独处理）。
- 登录接口参数形式：目前 `username` / `password` 是 query 参数，与前端 POST JSON 不匹配；
  建议后续改为请求体，本次不动。
- 自定义业务错误码表（当前 `code` 直接用 HTTP 状态码）。
