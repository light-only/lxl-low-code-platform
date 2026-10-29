from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "lxl-low-code-platform-backend"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    backend_cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    db_type: Literal["mysql", "sqlite"] = "mysql"
    mysql_user: str = "app"
    mysql_password: str = "app"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_db: str = "lxl_low_code"

    # 保留 SQLite 仅用于单元测试（内存库），生产/开发都走 MySQL
    sqlite_path: str = "./lxl-low-code-platform-backend.db"

    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"

    @property
    def database_url(self) -> str:
        if self.db_type == "mysql":
            user = quote_plus(self.mysql_user)
            password = quote_plus(self.mysql_password)
            return (
                f"mysql+asyncmy://{user}:{password}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
                "?charset=utf8mb4"
            )
        return f"sqlite+aiosqlite:///{self.sqlite_path}"

    @property
    def cors_origins(self) -> list[str]:
        return self.backend_cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
