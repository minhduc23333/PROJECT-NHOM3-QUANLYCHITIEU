from fastapi import APIRouter

from app.core.errors import COMMON_ERRORS

router = APIRouter(prefix="/ocr", tags=["ocr"], responses=COMMON_ERRORS)

# TODO: POST /ocr/receipts/{receipt_id}  -> chạy OCR cho hóa đơn đã upload