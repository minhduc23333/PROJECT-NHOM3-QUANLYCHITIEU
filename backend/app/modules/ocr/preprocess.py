"""Tiền xử lý ảnh hóa đơn trước khi OCR (task T05E16E).

Ảnh chụp bằng điện thoại thường: hóa đơn nhỏ giữa khung hình, nền bàn tối, hơi nghiêng/méo phối cảnh,
ánh sáng không đều, chữ in nhiệt nhạt. Pipeline mới xử lý đúng các vấn đề đó:

    đọc ảnh -> cắt đúng tờ hóa đơn + nắn phối cảnh -> xám -> san phẳng ánh sáng
            -> chuẩn hóa cỡ chữ (~28px) -> chỉnh nghiêng -> (tùy chọn) nhị phân Otsu

`preprocess()` giữ nguyên hành vi cũ (resize + deskew + adaptive threshold) để code/test cũ vẫn chạy;
engine dùng `iter_variants()` rồi chọn kết quả tốt nhất.
Chỉ phụ thuộc OpenCV + NumPy, không đụng DB hay FastAPI để dễ test.
"""
from __future__ import annotations

import cv2
import numpy as np

MIN_WIDTH = 1000       # (preprocess cũ) ảnh nhỏ hơn: phóng to
MAX_WIDTH = 2000       # (preprocess cũ) ảnh lớn hơn: thu nhỏ
MAX_DESKEW_DEG = 15.0  # chỉ chỉnh nghiêng nhẹ; lớn hơn thường là phát hiện sai

TARGET_TEXT_HEIGHT = 28   # chiều cao ký tự trung vị (px) mà Tesseract đọc tốt nhất
MIN_SCALE, MAX_SCALE = 0.35, 3.0
MAX_SIDE = 3600           # cạnh dài tối đa sau chuẩn hóa (giữ OCR không quá chậm)
CROP_MARGIN = 0.012       # co vào 1.2% mỗi cạnh để loại viền bàn còn sót


class ImageError(ValueError):
    """Ảnh không đọc được / hỏng."""


def load_image(path: str) -> np.ndarray:
    # imdecode + fromfile: đọc được cả đường dẫn có dấu tiếng Việt trên Windows
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError as exc:
        raise ImageError(f"Không mở được file ảnh: {path}") from exc
    # IMREAD_COLOR bỏ qua kênh alpha; OpenCV >= 3.1 tự áp EXIF orientation
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ImageError("Không giải mã được ảnh (file hỏng hoặc không phải JPG/PNG)")
    return img


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def resize_for_ocr(img: np.ndarray, min_width: int = MIN_WIDTH, max_width: int = MAX_WIDTH) -> np.ndarray:
    h, w = img.shape[:2]
    if w < min_width:
        scale, interp = min_width / w, cv2.INTER_CUBIC
    elif w > max_width:
        scale, interp = max_width / w, cv2.INTER_AREA
    else:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=interp)


# ---------------------------------------------------------------- chỉnh nghiêng

def _text_mask(gray: np.ndarray) -> np.ndarray:
    """Nhị phân chữ = 255 (Otsu). Nếu 'chữ' chiếm > 50% ảnh thì Otsu chọn nhầm nền -> đảo lại."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if cv2.countNonZero(bw) > 0.5 * bw.size:
        bw = 255 - bw
    return bw


def estimate_skew_angle(gray: np.ndarray, max_deg: float = MAX_DESKEW_DEG) -> float:
    """Góc nghiêng (độ) của các dòng chữ bằng projection profile.

    Xoay thử nhiều góc, góc nào làm các dòng chữ 'sắc' nhất (tổng ô vuông chênh lệch giữa các hàng
    liền kề lớn nhất) là góc đúng. Khác cách cũ (minAreaRect trên mọi điểm tối) — cách cũ lấy cả
    mặt bàn tối làm 'chữ' nên ảnh chụp thật hầu như không bao giờ được chỉnh.
    """
    h, w = gray.shape[:2]
    s = min(1.0, 700 / max(h, w))
    small = cv2.resize(gray, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else gray
    bw = _text_mask(small)
    if cv2.countNonZero(bw) < 50:
        return 0.0
    sh, sw = bw.shape
    center = (sw / 2, sh / 2)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        r = cv2.warpAffine(bw, m, (sw, sh), flags=cv2.INTER_NEAREST)
        prof = r.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(prof) ** 2))

    base = score(0.0)
    coarse = np.arange(-max_deg, max_deg + 0.01, 1.0)
    best = max(coarse, key=score)
    fine = np.arange(best - 1.0, best + 1.01, 0.2)
    best = max(fine, key=score)
    if score(best) <= base * 1.03:     # không cải thiện rõ rệt -> coi như thẳng
        return 0.0
    return float(best)


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def deskew(gray: np.ndarray) -> np.ndarray:
    angle = estimate_skew_angle(gray)
    if abs(angle) < 0.3 or abs(angle) > MAX_DESKEW_DEG:
        return gray
    return rotate(gray, angle)


def rotate90(img: np.ndarray, quarter_turns: int) -> np.ndarray:
    """Xoay ngược chiều kim đồng hồ quarter_turns * 90 độ (0..3)."""
    return np.ascontiguousarray(np.rot90(img, quarter_turns % 4))


# ---------------------------------------------------------------- cắt hóa đơn + nắn phối cảnh

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Sắp 4 điểm theo thứ tự: trên-trái, trên-phải, dưới-phải, dưới-trái."""
    rect = np.zeros((4, 2), np.float32)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    rect[0], rect[2] = pts[np.argmin(s)], pts[np.argmax(s)]
    rect[1], rect[3] = pts[np.argmin(d)], pts[np.argmax(d)]
    return rect


def _four_point_warp(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = _order_points(quad)
    width = int(round(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))))
    height = int(round(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], np.float32), dst)
    return cv2.warpPerspective(img, m, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def crop_receipt(img: np.ndarray) -> np.ndarray:
    """Tìm tờ hóa đơn (vùng giấy sáng nhất, liền khối) và nắn thẳng. Không chắc -> trả ảnh gốc.

    Không cắt khi ảnh gần như toàn giấy (ảnh scan), khi vùng giấy quá nhỏ (<3%) hoặc quá lớn (>92%).
    """
    h, w = img.shape[:2]
    s = min(1.0, 800 / max(h, w))
    small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
    gray = cv2.GaussianBlur(to_gray(small), (9, 9), 0)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(mask) > 0.85 * mask.size:
        return img
    # chữ trên giấy tạo lỗ hổng trong mask -> đóng lại rồi lấp đầy
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img
    biggest = max(contours, key=cv2.contourArea)
    area_frac = cv2.contourArea(biggest) / mask.size
    if not 0.03 <= area_frac <= 0.92:
        return img
    hull = cv2.convexHull(biggest)
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)
    quad = quad / s
    center = quad.mean(axis=0)
    quad = center + (quad - center) * (1 - 2 * CROP_MARGIN)   # co vào, bỏ viền bàn
    out = _four_point_warp(img, quad)
    return out if min(out.shape[:2]) >= 150 else img


# ---------------------------------------------------------------- chuẩn hóa độ sáng / cỡ chữ

def normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """San phẳng ánh sáng: chia ảnh cho 'nền' ước lượng (đóng hình thái + làm mờ). Bóng đổ biến mất,
    giấy ~255, chữ giữ nguyên độ đậm tương đối. Sau đó kéo giãn tương phản để chữ in nhiệt nhạt rõ lên."""
    h, w = gray.shape[:2]
    s = 0.25 if max(h, w) > 1200 else 1.0
    small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s != 1.0 else gray
    k = max(9, int(round(min(small.shape[:2]) / 12))) | 1
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 3)
    if s != 1.0:
        bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    norm = cv2.divide(gray, np.maximum(bg, 1), scale=255)
    lo = float(np.percentile(norm, 0.5))
    if lo < 200:   # kéo giãn: điểm tối nhất -> 0, giấy -> 255
        norm = np.clip((norm.astype(np.float32) - lo) * (255.0 / (255.0 - lo)), 0, 255).astype(np.uint8)
    return norm


def estimate_text_height(gray: np.ndarray) -> float | None:
    """Chiều cao trung vị của các ký tự (thành phần liên thông cỡ chữ). None nếu quá ít để ước lượng."""
    bw = _text_mask(gray)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    if n <= 1:
        return None
    hs, ws = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH]
    keep = (hs >= 6) & (hs <= gray.shape[0] * 0.15) & (ws <= hs * 4)
    if int(keep.sum()) < 20:
        return None
    return float(np.median(hs[keep]))


def normalize_text_scale(gray: np.ndarray) -> np.ndarray:
    """Phóng/thu để ký tự cao ~TARGET_TEXT_HEIGHT px — mấu chốt khi hóa đơn chỉ chiếm một góc ảnh 12MP
    (cách cũ thu cả ảnh về 2000px nên chữ chỉ còn ~10px và Tesseract đọc ra rác)."""
    h, w = gray.shape[:2]
    th = estimate_text_height(gray)
    scale = TARGET_TEXT_HEIGHT / th if th else (1400 / w)
    scale = float(np.clip(scale, MIN_SCALE, MAX_SCALE))
    scale = min(scale, MAX_SIDE / max(h, w))
    if abs(scale - 1.0) < 0.05:
        return gray
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=interp)


def binarize(gray: np.ndarray) -> np.ndarray:
    """Otsu trên ảnh đã san phẳng sáng (không cần adaptive threshold với tham số C dễ làm mất chữ nhạt)."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def _pad(img: np.ndarray, px: int = 24) -> np.ndarray:
    return cv2.copyMakeBorder(img, px, px, px, px, cv2.BORDER_CONSTANT, value=255)


def prepare(img: np.ndarray, *, crop: bool = True, binary: bool = False) -> np.ndarray:
    """Pipeline mới cho một ảnh (BGR hoặc xám) -> ảnh xám (hoặc nhị phân) sẵn sàng cho Tesseract."""
    if crop and img.ndim == 3:
        img = crop_receipt(img)
    gray = normalize_illumination(to_gray(img))
    gray = normalize_text_scale(gray)
    gray = deskew(gray)
    if binary:
        gray = binarize(gray)
    return _pad(gray)


def iter_variants(img: np.ndarray):
    """Generator (tên, ảnh). Biến thể 'crop' trước; 'full' chỉ khi việc cắt thật sự đổi ảnh."""
    cropped = crop_receipt(img)
    was_cropped = cropped is not img
    gray = deskew(normalize_text_scale(normalize_illumination(to_gray(cropped))))
    yield "crop-gray" if was_cropped else "full-gray", _pad(gray)
    yield "crop-bin" if was_cropped else "full-bin", _pad(binarize(gray))
    if was_cropped:
        full = deskew(normalize_text_scale(normalize_illumination(to_gray(img))))
        yield "full-gray", _pad(full)


def preprocess(img: np.ndarray, *, binarize: bool = True) -> np.ndarray:
    """Pipeline đơn giản cũ, giữ để tương thích. Trả ảnh xám (đã nhị phân hóa nếu binarize=True)."""
    gray = to_gray(img)
    gray = resize_for_ocr(gray)
    gray = deskew(gray)
    return _threshold(gray) if binarize else gray


def _threshold(gray: np.ndarray) -> np.ndarray:
    """Adaptive threshold (cũ): chịu được bóng đổ nhưng tham số C=15 dễ xóa chữ nhạt."""
    blur = cv2.medianBlur(gray, 3)
    return cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


# tương thích tên cũ
threshold = _threshold
