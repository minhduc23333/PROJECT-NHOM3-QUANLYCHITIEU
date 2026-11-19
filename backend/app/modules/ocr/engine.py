"""Engine OCR đóng gói độc lập (task T05E16E): ảnh -> text/box thô.

Không import FastAPI/SQLAlchemy. Hàm chính: `run_ocr(image_path)` (một lượt) và `recognize(img, psm)`
(ảnh đã tiền xử lý -> OcrResult). Việc thử nhiều biến thể ảnh + chọn kết quả tốt nhất nằm ở `pipeline.py`.
Cấu hình trong .env: OCR_ENGINE (tesseract | easyocr), OCR_LANG, OCR_TIMEOUT_SEC, TESSERACT_CMD.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import numpy as np

from app.core.config import settings
from app.modules.ocr.preprocess import iter_variants, load_image

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
    line_id: tuple[int, int, int] | None = None  # (block, paragraph, line) do Tesseract báo; None nếu engine không có


@dataclass
class OcrResult:
    boxes: list[OcrBox] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)   # text đã gom theo dòng, từ trên xuống

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def mean_conf(self) -> float:
        """Độ tin cậy trung bình 0..100 (trọng số theo độ dài từ); 0 nếu engine không báo / không có chữ."""
        good = [b for b in self.boxes if b.conf >= 0 and len(b.text) >= 2]
        total = sum(len(b.text) for b in good)
        return sum(b.conf * len(b.text) for b in good) / total if total else 0.0


def _group_by_geometry(boxes: list[OcrBox]) -> list[list[OcrBox]]:
    """Gom box thành dòng theo toạ độ: cùng dòng nếu tâm dọc lệch < 0.6 chiều cao dòng (ảnh đã thẳng)."""
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
    return rows


def _row_geom(row: list[OcrBox]) -> tuple[float, float, float, float]:
    """(tâm dọc, chiều cao trung vị, x trái, x phải) của một dòng."""
    hs = sorted(b.h for b in row)
    cy = sum(b.y + b.h / 2 for b in row) / len(row)
    return cy, hs[len(hs) // 2], min(b.x for b in row), max(b.x + b.w for b in row)


def _merge_same_row(rows: list[list[OcrBox]]) -> list[list[OcrBox]]:
    """Tesseract đôi khi tách 'Tạm tính:' và '228.000' (cách nhau một khoảng trắng rộng) thành 2 dòng
    cùng baseline. Gộp lại nếu cùng tâm dọc và không chồng nhau theo chiều ngang."""
    rows = sorted(rows, key=lambda r: _row_geom(r)[0])
    merged: list[list[OcrBox]] = []
    for row in rows:
        if merged:
            cy1, h1, l1, r1 = _row_geom(merged[-1])
            cy2, h2, l2, r2 = _row_geom(row)
            if abs(cy1 - cy2) <= 0.45 * min(h1, h2) and (l2 > r1 or l1 > r2):
                merged[-1] = merged[-1] + row
                continue
        merged.append(row)
    return merged


def group_into_lines(boxes: list[OcrBox]) -> list[str]:
    """Box -> các dòng text, từ trên xuống.

    Có line_id (Tesseract) thì dùng cấu trúc dòng của chính nó — nó bám theo baseline nên đúng cả khi
    chữ còn hơi nghiêng; gom bằng toạ độ như trước dễ xé 'nhãn' và 'số tiền' của cùng một dòng.
    Không có line_id (EasyOCR) thì gom theo toạ độ.
    """
    if not boxes:
        return []
    if all(b.line_id is not None for b in boxes):
        by_id: dict[tuple[int, int, int], list[OcrBox]] = {}
        for b in boxes:
            by_id.setdefault(b.line_id, []).append(b)
        rows = _merge_same_row(list(by_id.values()))
    else:
        rows = _group_by_geometry(boxes)
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
    except pytesseract.TesseractNotFoundError:  # để image_to_data báo lỗi Tesseract rõ ràng hơn
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


def _tesseract(img: np.ndarray, psm: int = 6) -> list[OcrBox]:
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover
        raise OcrError("Chưa cài pytesseract (pip install pytesseract)") from exc
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        d = pytesseract.image_to_data(
            img,
            lang=_resolve_tess_lang(pytesseract),
            # oem 1 = LSTM; dpi 300 để Tesseract khỏi đoán (ảnh từ mảng numpy không có DPI)
            config=f"--oem 1 --psm {psm} --dpi 300",
            output_type=pytesseract.Output.DICT,
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
        boxes.append(
            OcrBox(
                txt, d["left"][i], d["top"][i], d["width"][i], d["height"][i], float(d["conf"][i]),
                line_id=(d["block_num"][i], d["par_num"][i], d["line_num"][i]),
            )
        )
    return boxes


def detect_rotation(img: np.ndarray) -> int | None:
    """Số lần xoay 90° NGƯỢC chiều kim đồng hồ (1..3) để chữ thẳng đứng theo Tesseract OSD; 0 = đã thẳng;
    None nếu không xác định được (ảnh quá ít chữ, thiếu osd.traineddata, engine khác Tesseract...)."""
    if settings.OCR_ENGINE != "tesseract":
        return None
    try:
        import pytesseract

        if settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        osd = pytesseract.image_to_osd(img, config="--psm 0", output_type=pytesseract.Output.DICT)
        if float(osd.get("orientation_conf", 0)) < 1.0:
            return None
        return (4 - int(osd.get("rotate", 0)) // 90) % 4    # OSD báo độ xoay THUẬN chiều kim đồng hồ cần để sửa
    except Exception as exc:  # noqa: BLE001  OSD hay lỗi với hóa đơn ít chữ; chỉ là gợi ý nên nuốt lỗi
        log.debug("OSD không xác định được hướng: %s", exc)
        return None


_easy_reader = None


def _easyocr(img: np.ndarray, psm: int = 6) -> list[OcrBox]:  # noqa: ARG001  (psm chỉ dùng cho Tesseract)
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


def recognize(img: np.ndarray, psm: int = 6) -> OcrResult:
    """Ảnh ĐÃ tiền xử lý -> OcrResult (box + dòng). Chạy đồng bộ, không timeout."""
    try:
        fn = _ENGINES[settings.OCR_ENGINE]
    except KeyError as exc:
        raise OcrError(f"OCR_ENGINE không hợp lệ: {settings.OCR_ENGINE}") from exc
    boxes = fn(img, psm=psm)
    return OcrResult(boxes=boxes, lines=group_into_lines(boxes))


def _recognize(path: str) -> OcrResult:
    """Một lượt đơn giản: ảnh -> biến thể tiền xử lý đầu tiên -> OCR."""
    _, img = next(iter_variants(load_image(path)))
    return recognize(img)


_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")


def _run_with_timeout(fn, arg, timeout: float | None):
    """Chạy fn(arg) trong thread riêng với timeout. Thread quá hạn không bị kill (Python không cho);
    ta chỉ bỏ kết quả của nó."""
    timeout = settings.OCR_TIMEOUT_SEC if timeout is None else timeout
    future = _pool.submit(fn, arg)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        log.warning("OCR timeout sau %.0fs: %s", timeout, arg)
        raise OcrTimeout(f"OCR quá {timeout:.0f}s") from exc


def run_ocr(image_path: str, timeout: float | None = None) -> OcrResult:
    """Một lượt OCR có timeout. Ném OcrTimeout / OcrError / ImageError khi thất bại.
    (Luồng chính dùng pipeline.read_receipt: nhiều lượt + chọn kết quả tốt nhất.)"""
    return _run_with_timeout(_recognize, image_path, timeout)
