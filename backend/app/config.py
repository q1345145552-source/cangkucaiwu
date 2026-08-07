import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/warehouse_finance"
    SECRET_KEY: str = "change-me-random-secret-key-2026"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    LINE_CHANNEL_SECRET: str = ""
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    UPLOAD_DIR: str = "/app/uploads"
    class Config:
        env_file = ".env"
        case_sensitive = True

_INSECURE_SECRETS = {"change-me-random-secret-key-2026", "warehouse-finance-secret-key-2026", ""}

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    if s.SECRET_KEY in _INSECURE_SECRETS or len(s.SECRET_KEY) < 32:
        import logging
        logging.getLogger("uvicorn.error").warning(
            "⚠️ SECRET_KEY 使用了不安全的默认值或过短。生产环境必须在 .env 设置长随机 SECRET_KEY，"
            "否则任何人都可伪造登录令牌！"
        )
    return s
