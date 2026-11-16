import sys

import cv2

from app.modules.ocr.engine import _tesseract, group_into_lines
from app.modules.ocr.preprocess import deskew, load_image, resize_for_ocr, to_gray


def remove_shadow(gray):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, k)
    bg = cv2.medianBlur(bg, 21)
    return cv2.divide(gray, bg, scale=255)


def show(name, img):
    print(f"\n===== {name} =====")
    print("\n".join(group_into_lines(_tesseract(img))))


path = sys.argv[1]
gray = deskew(resize_for_ocr(to_gray(load_image(path))))
flat = remove_shadow(gray)
show("B: xoa bong", flat)
_, otsu = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
show("C: xoa bong + Otsu", otsu)