from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "mysql+pymysql://smartsplit:smartsplit@localhost:3306/smartsplit"
    JWT_SECRET: str = "abcd"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 5
    CORS_ORIGINS: str = "http://localhost:8000"


settings = Settings()