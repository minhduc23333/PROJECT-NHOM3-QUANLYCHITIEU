"""Tiền xử lý ảnh hóa đơn trước khi OCR (task T05E16E).

Thứ tự: đọc ảnh -> xoay thẳng (EXIF + deskew) -> resize -> grayscale -> threshold.
Chỉ phụ thuộc OpenCV + NumPy, không đụng DB hay FastAPI để dễ test.
"""
from __future__ import annotations

import cv2
import numpy as np

MIN_WIDTH = 1000      # ảnh nhỏ hơn: phóng to cho OCR đọc được chữ nhỏ
MAX_WIDTH = 2000      # ảnh lớn hơn: thu nhỏ để OCR không chậm
MAX_DESKEW_DEG = 15.0  # chỉ chỉnh nghiêng nhẹ; lớn hơn thường là phát hiện sai


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


def estimate_skew_angle(gray: np.ndarray) -> float:
    """Góc nghiêng (độ) của các dòng chữ, dựa trên minAreaRect của vùng chữ."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(bw)
    if coords is None or len(coords) < 50:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    # chuẩn hóa về (-45, 45]
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return float(angle)


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def deskew(gray: np.ndarray) -> np.ndarray:
    angle = estimate_skew_angle(gray)
    if abs(angle) < 0.5 or abs(angle) > MAX_DESKEW_DEG:
        return gray
    return rotate(gray, angle)


def threshold(gray: np.ndarray) -> np.ndarray:
    """Adaptive threshold: chịu được ảnh chụp bị bóng/đèn không đều."""
    blur = cv2.medianBlur(gray, 3)
    return cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )


def preprocess(img: np.ndarray, *, binarize: bool = True) -> np.ndarray:
    """Pipeline đầy đủ. Trả ảnh xám (đã nhị phân hóa nếu binarize=True)."""
    gray = to_gray(img)
    gray = resize_for_ocr(gray)
    gray = deskew(gray)
    return threshold(gray) if binarize else gray
