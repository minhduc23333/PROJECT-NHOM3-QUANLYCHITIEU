"""Định dạng lỗi chung cho toàn bộ API:

    {"error": {"code": "NOT_FOUND", "message": "...", "details": null}}

Trong service/router chỉ cần raise:
    raise NotFound("Không tìm thấy nhóm")
    raise Forbidden("Bạn không thuộc nhóm này")
    raise BadRequest("...") / Conflict("...") / Unauthorized("...")
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")

STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
}

DEFAULT_MESSAGES = {
    401: "Bạn cần đăng nhập",
    403: "Bạn không có quyền thực hiện thao tác này",
    404: "Không tìm thấy dữ liệu",
    405: "Phương thức không được hỗ trợ",
}


# ---------- Exception dùng trong code ----------
class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str | None = None, details=None, code: str | None = None):
        self.message = message or DEFAULT_MESSAGES.get(self.status_code, "Yêu cầu không hợp lệ")
        self.details = details
        if code:
            self.code = code
        super().__init__(self.message)


class BadRequest(AppError):
    status_code, code = 400, "BAD_REQUEST"


class Unauthorized(AppError):
    status_code, code = 401, "UNAUTHORIZED"


class Forbidden(AppError):
    status_code, code = 403, "FORBIDDEN"


class NotFound(AppError):
    status_code, code = 404, "NOT_FOUND"


class Conflict(AppError):
    status_code, code = 409, "CONFLICT"


# ---------- Schema cho Swagger ----------
class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldError] | dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def _resp(desc: str) -> dict:
    return {"model": ErrorResponse, "description": desc}


# Gắn vào router: APIRouter(responses=COMMON_ERRORS)
COMMON_ERRORS = {
    401: _resp("Chưa đăng nhập / token hết hạn"),
    403: _resp("Không có quyền"),
    404: _resp("Không tìm thấy"),
    422: _resp("Dữ liệu không hợp lệ"),
}


# ---------- Handlers ----------
def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers)

    # Bắt cả lỗi của Starlette (404 route không tồn tại, 405...) chứ không chỉ fastapi.HTTPException
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(_: Request, exc: StarletteHTTPException):
        code = STATUS_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        detail = exc.detail
        if not isinstance(detail, str) or detail in ("Not Found", "Forbidden", "Not authenticated", "Method Not Allowed"):
            detail = DEFAULT_MESSAGES.get(exc.status_code, str(detail))
        return JSONResponse(_body(code, detail), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        details = []
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path", "header", "cookie")]
            details.append({"field": ".".join(loc), "message": e.get("msg", "Không hợp lệ")})
        return JSONResponse(_body("VALIDATION_ERROR", "Dữ liệu không hợp lệ", details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_exc(_: Request, exc: IntegrityError):
        log.warning("IntegrityError: %s", exc.orig)
        return JSONResponse(_body("CONFLICT", "Dữ liệu bị trùng hoặc vi phạm ràng buộc"), status_code=409)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse(_body("INTERNAL_ERROR", "Lỗi hệ thống, vui lòng thử lại"), status_code=500)