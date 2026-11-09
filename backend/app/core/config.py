from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Đọc cấu hình từ biến môi trường / file backend/.env (xem .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SmartSplit AI API"
    APP_ENV: str = "dev"  # dev | prod
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "mysql+pymysql://smartsplit:smartsplit@localhost:3306/smartsplit"
    DB_ECHO: bool = False

    JWT_SECRET: str = "change-me-in-.env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 5

    CORS_ORIGINS: str = "http://localhost:8000"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

if settings.APP_ENV == "prod" and len(settings.JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET quá ngắn cho môi trường prod (cần >= 32 ký tự).")