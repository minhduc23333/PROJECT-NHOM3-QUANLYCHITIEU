from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import COMMON_ERRORS
from app.modules.ocr import service
from app.modules.ocr.schemas import OcrItemOut, OcrProcessOut

router = APIRouter(prefix="/ocr", tags=["ocr"], responses=COMMON_ERRORS)


@router.post(
    "/receipts/{receipt_id}",
    response_model=OcrProcessOut,
    summary="Chạy OCR cho hóa đơn đã tải lên",
)
def run_receipt_ocr(receipt_id: int, db: DB, user: CurrentUser):
    """OCR thất bại vẫn trả 200 với `receipt.ocr_status = "FAILED"` để UI chuyển sang nhập tay."""
    receipt, parsed, raw_text = service.process_receipt(db, user, receipt_id)
    items = [OcrItemOut.model_validate(i, from_attributes=True) for i in parsed.items] if parsed else []
    return OcrProcessOut(
        receipt=receipt,
        items=items,
        missing=parsed.missing if parsed else ["merchant_name", "receipt_date", "items", "subtotal", "total_amount"],
        warnings=parsed.warnings if parsed else ["OCR thất bại, vui lòng nhập tay"],
        raw_text=raw_text,
    )
