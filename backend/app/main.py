import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.groups.router import router as groups_router
from app.modules.ocr.router import router as ocr_router
from app.modules.receipts.router import router as receipts_router
from app.modules.split.router import router as split_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TAGS = [
    {"name": "system", "description": "Kiểm tra tình trạng server / DB"},
    {"name": "auth", "description": "Đăng ký, đăng nhập (JWT), thông tin tài khoản"},
    {"name": "groups", "description": "Nhóm chi tiêu và thành viên"},
    {"name": "receipts", "description": "Hóa đơn"},
    {"name": "ocr", "description": "Đọc hóa đơn từ ảnh"},
    {"name": "split", "description": "Chọn món, chia tiền, công nợ (chưa triển khai)"},
    {"name": "dashboard", "description": "Số liệu tổng quan"},
]

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "API cho SmartSplit AI.\n\n"
        "**Cách thử:** gọi `POST /api/auth/login` (tài khoản seed: `an@demo.vn` / `123456`), "
        "copy `access_token`, bấm **Authorize** rồi dán token.\n\n"
        "Mọi lỗi trả về dạng `{\"error\": {\"code\", \"message\", \"details\"}}`."
    ),
    openapi_tags=TAGS,
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

api = APIRouter(prefix=settings.API_PREFIX)


@app.get("/health", tags=["system"], summary="Server + DB còn sống")
@api.get("/health", tags=["system"], summary="Server + DB còn sống")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


for r in (auth_router, groups_router, receipts_router, ocr_router, split_router, dashboard_router):
    api.include_router(r)
app.include_router(api)

# Phục vụ frontend (HTML/JS thuần) ở "/". Phải đặt CUỐI CÙNG, sau mọi route API.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def frontend_page():
    return FileResponse(FRONTEND_DIR / "index.html")


def frontend_group_page(group_id: str):
    return frontend_page()


if FRONTEND_DIR.exists():
    for path in (
        "/login",
        "/register",
        "/groups",
        "/receipts",
        "/debts",
        "/dev/ui",
    ):
        app.add_api_route(path, frontend_page, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        "/groups/{group_id}",
        frontend_group_page,
        methods=["GET"],
        include_in_schema=False,
    )

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")