from app.main import app
from app.models.user import User
from app.security import pwd_context


async def test_login_returns_unified_envelope(client, session_factory):
    async with session_factory() as session:
        session.add(
            User(
                name="Alice",
                username="alice",
                phone="13800000000",
                hashed_password=pwd_context.hash("secret"),
            )
        )
        await session.commit()

    response = await client.post(
        "/auth/token", params={"username": "alice", "password": "secret"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["access_token"]


async def test_login_failure_uses_error_envelope(client):
    response = await client.post(
        "/auth/token", params={"username": "nobody", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "code": 401,
        "message": "账号或密码错误",
        "data": None,
    }


async def test_not_found_uses_error_envelope(client):
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["data"] is None


async def test_register_returns_created_user_envelope(client):
    response = await client.post(
        "/auth/register",
        json={
            "name": "Bob",
            "username": "bob",
            "phone": "13900000000",
            "password": "secret",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["username"] == "bob"
    assert "password" not in body["data"]
    assert "hashed_password" not in body["data"]


async def test_list_users_returns_paginated_envelope(client, session_factory):
    async with session_factory() as session:
        for index in range(3):
            session.add(
                User(
                    name=f"User {index}",
                    username=f"user{index}",
                    phone=f"1380000000{index}",
                    hashed_password=pwd_context.hash("secret"),
                )
            )
        await session.commit()

    response = await client.get("/users", params={"page": 1, "size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"] == {
        "items": body["data"]["items"],
        "total": 3,
        "page": 1,
        "size": 2,
    }
    assert len(body["data"]["items"]) == 2


async def test_create_user_returns_envelope(client):
    response = await client.post(
        "/users",
        json={
            "name": "Carol",
            "username": "carol",
            "phone": "13700000000",
            "password": "secret",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["username"] == "carol"


async def test_root_returns_envelope(client):
    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["docs"] == "/docs"


async def test_validation_error_uses_error_envelope(client):
    response = await client.post("/auth/register", json={"name": "Alice"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["message"] == "请求参数校验失败"
    assert body["data"]["errors"]


async def test_unhandled_error_uses_error_envelope(client, caplog):
    @app.get("/__boom")
    async def boom():
        raise RuntimeError("boom")

    try:
        response = await client.get("/__boom")
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "path", None) != "/__boom"
        ]

    assert response.status_code == 500
    assert response.json() == {
        "code": 500,
        "message": "服务器内部错误",
        "data": None,
    }
    assert "Unhandled error" in caplog.text
