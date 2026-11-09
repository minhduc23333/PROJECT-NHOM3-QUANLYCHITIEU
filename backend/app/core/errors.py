import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("smartsplit")


def _body(code: str, message: str, details=None):
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exc(_: Request, exc: HTTPException):
        return JSONResponse(_body(f"HTTP_{exc.status_code}", str(exc.detail)),
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "Dữ liệu không hợp lệ", details), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Lỗi không xử lý: %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(_body("INTERNAL_ERROR", "Lỗi hệ thống, vui lòng thử lại"), status_code=500)
