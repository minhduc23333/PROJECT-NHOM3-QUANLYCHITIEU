from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "mysql+pymysql://smartsplit:smartsplit@localhost:3306/smartsplit"
    # Không có giá trị mặc định: bắt buộc đặt trong .env / biến môi trường
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 5
    CORS_ORIGINS: str = "http://localhost:8000"

    @field_validator("JWT_SECRET")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET phải dài ít nhất 32 ký tự")
        return v


settings = Settings()
