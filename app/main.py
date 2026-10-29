from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import engine
from app.exceptions import register_exception_handlers
from app.response import ApiResponse, success
from app.routers import auth, users

settings = get_settings()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 表结构统一由 Alembic 管理，启动前先执行 `alembic upgrade head`。
    yield
    await engine.dispose()

app = FastAPI(
    title="lxl-low-code-platform-backend",
    lifespan=lifespan,
    # 关闭默认的 /docs 和 /redoc：它们从 jsdelivr CDN 加载资源，国内网络下不可用
    docs_url=None,
    redoc_url=None,
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自托管的 Swagger UI，静态资源来自 /static，不走外部 CDN。"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="/static/swagger-ui/favicon-32x32.png",
    )


@app.get("/", response_model=ApiResponse[dict[str, str]])
async def root():
    return success({"message": "Hello from lxl-low-code-platform-backend", "docs": "/docs"})


@app.get("/health")
async def health():
    return {"status": "ok"}
