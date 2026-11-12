"""Engine OCR đóng gói độc lập (task T05E16E): ảnh -> text/box thô.

Không import FastAPI/SQLAlchemy. Hàm chính: `run_ocr(image_path)`.
Cấu hình trong .env: OCR_ENGINE (tesseract | easyocr), OCR_LANG, OCR_TIMEOUT_SEC, TESSERACT_CMD.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import numpy as np

from app.core.config import settings
from app.modules.ocr.preprocess import load_image, preprocess

log = logging.getLogger(__name__)



class OcrError(RuntimeError):
    """OCR lỗi (engine thiếu, ảnh hỏng...)."""


class OcrTimeout(OcrError):
    """OCR chạy quá OCR_TIMEOUT_SEC."""


@dataclass
class OcrBox:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: float  # 0..100, -1 nếu engine không báo


@dataclass
class OcrResult:
    boxes: list[OcrBox] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)   # text đã gom theo dòng, từ trên xuống

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def group_into_lines(boxes: list[OcrBox]) -> list[str]:
    """Gom các box thành dòng: cùng dòng nếu tâm dọc lệch < nửa chiều cao dòng."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: (b.y + b.h / 2, b.x))
    rows: list[list[OcrBox]] = []
    for b in ordered:
        cy = b.y + b.h / 2
        if rows:
            last = rows[-1]
            ref_cy = sum(x.y + x.h / 2 for x in last) / len(last)
            ref_h = sum(x.h for x in last) / len(last)
            if abs(cy - ref_cy) <= max(ref_h, b.h) * 0.6:
                last.append(b)
                continue
        rows.append([b])
    return [" ".join(x.text for x in sorted(r, key=lambda b: b.x)) for r in rows]


_tess_langs: str | None = None


def _resolve_tess_lang(pytesseract) -> str:
    """Lọc OCR_LANG theo gói ngôn ngữ thực sự đã cài (vd chưa có 'vie' thì chỉ dùng 'eng').

    Không lọc thì Tesseract ném lỗi khi thiếu tessdata -> API 500 thay vì rơi về nhập tay.
    """
    global _tess_langs
    if _tess_langs is not None:
        return _tess_langs
    wanted = [x for x in settings.OCR_LANG.split("+") if x]
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:  # không liệt kê được -> cứ dùng nguyên cấu hình
        return settings.OCR_LANG
    usable = [x for x in wanted if x in installed]
    if not usable:
        raise OcrError(f"Tesseract chưa cài ngôn ngữ nào trong OCR_LANG={settings.OCR_LANG}")
    if usable != wanted:
        missing = "+".join(x for x in wanted if x not in installed)
        log.warning("Tesseract thiếu tessdata '%s' -> chỉ dùng '%s' (độ chính xác tiếng Việt sẽ kém hơn)",
                    missing, "+".join(usable))
    _tess_langs = "+".join(usable)
    return _tess_langs


def _tesseract(img: np.ndarray) -> list[OcrBox]:
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover
        raise OcrError("Chưa cài pytesseract (pip install pytesseract)") from exc
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        d = pytesseract.image_to_data(
            img, lang=_resolve_tess_lang(pytesseract), config="--psm 6", output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrError("Không tìm thấy Tesseract; đặt TESSERACT_CMD trong .env") from exc
    except pytesseract.TesseractError as exc:
        raise OcrError(f"Tesseract lỗi: {exc}") from exc
    boxes = []
    for i, txt in enumerate(d["text"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        boxes.append(OcrBox(txt, d["left"][i], d["top"][i], d["width"][i], d["height"][i], float(d["conf"][i])))
    return boxes


_easy_reader = None


def _easyocr(img: np.ndarray) -> list[OcrBox]:
    global _easy_reader
    try:
        import easyocr
    except ImportError as exc:  # pragma: no cover
        raise OcrError("Chưa cài easyocr (pip install easyocr)") from exc
    if _easy_reader is None:  # nạp model rất chậm -> chỉ nạp 1 lần
        _easy_reader = easyocr.Reader(["vi", "en"], gpu=False)
    boxes = []
    for pts, txt, conf in _easy_reader.readtext(img):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x, y = int(min(xs)), int(min(ys))
        boxes.append(OcrBox(txt.strip(), x, y, int(max(xs)) - x, int(max(ys)) - y, float(conf) * 100))
    return [b for b in boxes if b.text]


_ENGINES = {"tesseract": _tesseract, "easyocr": _easyocr}


def _recognize(path: str) -> OcrResult:
    img = preprocess(load_image(path))
    try:
        fn = _ENGINES[settings.OCR_ENGINE]
    except KeyError as exc:
        raise OcrError(f"OCR_ENGINE không hợp lệ: {settings.OCR_ENGINE}") from exc
    boxes = fn(img)
    return OcrResult(boxes=boxes, lines=group_into_lines(boxes))


_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")


def run_ocr(image_path: str, timeout: float | None = None) -> OcrResult:
    """Chạy OCR có timeout. Ném OcrTimeout / OcrError / ImageError khi thất bại.

    Lưu ý: thread quá hạn không bị kill (Python không cho); ta bỏ kết quả của nó.
    """
    timeout = settings.OCR_TIMEOUT_SEC if timeout is None else timeout
    future = _pool.submit(_recognize, image_path)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        log.warning("OCR timeout sau %.0fs: %s", timeout, image_path)
        raise OcrTimeout(f"OCR quá {timeout:.0f}s") from exc
