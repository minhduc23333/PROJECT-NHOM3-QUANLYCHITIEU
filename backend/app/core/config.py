from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env nằm ở backend/ — dùng đường dẫn tuyệt đối để chạy uvicorn/pytest từ thư mục nào cũng đọc đúng
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Đọc cấu hình từ biến môi trường / file backend/.env (xem .env.example)."""

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SmartSplit AI API"
    APP_ENV: str = "dev"  # dev | prod
    API_PREFIX: str = "/api"

    DATABASE_URL: str = "mysql+pymysql://smartsplit:smartsplit@127.0.0.1:3306/smartsplit"
    DB_ECHO: bool = False
    AUTO_MIGRATE: bool = True  # dev: tự chạy `alembic upgrade head` khi khởi động nếu DB (MySQL) còn trống

    JWT_SECRET: str = "change-me-in-.env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 5

    # OCR (module app/modules/ocr)
    OCR_ENGINE: str = "auto"             # auto | tesseract | easyocr | gemini  (auto: có GEMINI_API_KEY thì dùng Gemini trước)
    OCR_LANG: str = "vie+eng"            # chỉ dùng cho tesseract (cần tessdata 'vie')
    OCR_TIMEOUT_SEC: float = 60.0
    TESSERACT_CMD: str = ""              # vd Windows: D:/Tesseract-OCR/tesseract.exe

    CORS_ORIGINS: str = "http://localhost:8000"

    GEMINI_API_KEY: str = ""
    # Model đọc hóa đơn: ưu tiên độ chính xác hơn tốc độ. Thử lần lượt GEMINI_MODEL rồi GEMINI_FALLBACK_MODELS
    # (model nào key không có quyền / chưa tồn tại sẽ tự bị bỏ qua).
    GEMINI_MODEL: str = "gemini-4-argon"
    GEMINI_FALLBACK_MODELS: str = "gemini-3.1-pro-preview,gemini-3.8-flash,gemini-3.5-flash"
    GEMINI_THINKING_LEVEL: str = "high"   # low | medium | high (suy nghĩ kỹ hơn = đọc số chuẩn hơn, chậm hơn)
    GEMINI_CALL_TIMEOUT_SEC: float = 150.0    # tối đa cho 1 lượt gọi model
    GEMINI_TOTAL_BUDGET_SEC: float = 280.0    # tối đa cho toàn bộ 1 lần đọc (gồm các lượt tự kiểm toán)

    # Quên mật khẩu: liên kết đặt lại gửi qua email. Chưa có SMTP_HOST thì chỉ ghi liên kết vào log của backend (dev).
    PUBLIC_BASE_URL: str = "http://localhost:8000"  # địa chỉ người dùng mở web (dùng để tạo liên kết trong email)
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""  # vd: "SmartSplit AI <no-reply@gmail.com>"; để trống thì dùng SMTP_USER
    SMTP_STARTTLS: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

if settings.APP_ENV == "prod" and len(settings.JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET quá ngắn cho môi trường prod (cần >= 32 ký tự).")
