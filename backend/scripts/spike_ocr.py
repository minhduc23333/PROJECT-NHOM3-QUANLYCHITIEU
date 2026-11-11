# File: backend/scripts/spike_ocr.py
import time
import cv2
import pytesseract
import easyocr

# Đường dẫn tới Tesseract trên máy bạn
pytesseract.pytesseract.tesseract_cmd = r'D:\Tesseract-OCR\tesseract.exe'

def test_tesseract(img_path):
    print("=== 1. Đang chạy Tesseract ===")
    start = time.time()
    img = cv2.imread(img_path)
    text = pytesseract.image_to_string(img, lang='vie')
    end = time.time()
    print(f"Thời gian: {end - start:.2f} giây")
    print(text.strip())
    print("-" * 40)

def test_easyocr(img_path):
    print("=== 2. Đang chạy EasyOCR ===")
    start = time.time()
    reader = easyocr.Reader(['vi', 'en'])
    result = reader.readtext(img_path, detail=0)
    end = time.time()
    print(f"Thời gian: {end - start:.2f} giây")
    print("\n".join(result))
    print("-" * 40)

if __name__ == "__main__":
    IMAGE_PATH = "scripts/test_images/1.jpg"
    
    print(f"BẮT ĐẦU TEST OCR CHO ẢNH: {IMAGE_PATH}\n")
    try:
        test_tesseract(IMAGE_PATH)
        test_easyocr(IMAGE_PATH)
    except Exception as e:
        print(f"Có lỗi xảy ra: {e}")