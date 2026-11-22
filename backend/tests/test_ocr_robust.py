"""Hồi quy cho các lỗi OCR đọc ảnh hóa đơn thật: số bị chèn khoảng trắng, năm vô lý, từ khóa tổng bị đọc sai
dấu, chữ số rác cuối dòng, ảnh nghiêng / có nền bàn / bị xoay."""
import shutil
from datetime import date
from decimal import Decimal

import cv2
import numpy as np
import pytest

from app.modules.ocr import preprocess as pp
from app.modules.ocr.engine import OcrBox, group_into_lines
from app.modules.ocr.parser import find_date, normalize_numbers, parse_receipt


@pytest.mark.parametrize("raw,fixed", [
    ("Tổng cộng: 300. 000", "Tổng cộng: 300.000"),
    ("Bún bò 2 55 .000 110 .000", "Bún bò 2 55.000 110.000"),
    ("Tạm tính: 228.OOO", "Tạm tính: 228.000"),
    ("No.100 Tp.HCM", "No.100 Tp.HCM"),          # không đụng vào chữ
    ("ĐT: 0909123456", "ĐT: 0909123456"),
])
def test_normalize_numbers(raw, fixed):
    assert normalize_numbers(raw) == fixed


def test_implausible_year_is_not_a_date():
    assert find_date(["Ngày: 05/11/2926"]) is None
    assert find_date(["Ngày 05 / 11 / 2026"]) == date(2026, 11, 5)


def test_garbled_total_keyword_still_found():
    r = parse_receipt(["Quán A", "Cơm 2 40.000 80.000", "Tạm tính: 80.000", "Téng cộng: 80.000"])
    assert r.total_amount == Decimal(80000)


def test_trailing_noise_digit_does_not_replace_amount():
    r = parse_receipt(["Quán A", "Cơm 2 40.000 80.000", "Tạm tính: 80.000 3", "Tổng cộng: 80.000"])
    assert r.subtotal == Decimal(80000)


def test_summary_label_alone_on_a_line():
    r = parse_receipt(["Quán A", "Cơm 2 40.000 80.000", "Tạm tính:", "80.000", "Tổng cộng:", "80.000"])
    assert (r.subtotal, r.total_amount) == (Decimal(80000), Decimal(80000))


def test_phone_number_after_label_is_not_money():
    r = parse_receipt(["Quán A", "HÓA ĐƠN THANH TOÁN", "0909123456", "Cơm 2 40.000 80.000"])
    assert r.total_amount is None


def test_tesseract_line_ids_keep_label_and_amount_together():
    # hai "dòng" Tesseract cùng baseline (nhãn và số cách nhau xa) phải gộp lại; dòng khác thì không
    boxes = [OcrBox("Tạm", 10, 100, 40, 20, 90, (1, 1, 1)), OcrBox("228.000", 400, 101, 80, 20, 90, (1, 1, 2)),
             OcrBox("VAT", 10, 140, 40, 20, 90, (1, 1, 3))]
    assert group_into_lines(boxes) == ["Tạm 228.000", "VAT"]


def _paper_on_dark_table(angle=0.0):
    img = np.full((1600, 1200, 3), 40, np.uint8)
    paper = np.full((900, 560, 3), 245, np.uint8)
    for y in range(80, 820, 60):
        cv2.putText(paper, "Bun bo 2 55.000 110.000", (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    img[350:1250, 320:880] = paper
    m = cv2.getRotationMatrix2D((600, 800), angle, 1)
    return cv2.warpAffine(img, m, (1200, 1600), borderValue=(40, 40, 40))


def test_crop_receipt_removes_table_and_keeps_paper():
    out = pp.crop_receipt(_paper_on_dark_table(5))
    assert out.shape[0] < 1300 and out.shape[1] < 800        # đã bỏ phần mặt bàn
    assert out.mean() > 150                                   # còn lại chủ yếu là giấy sáng


def test_crop_skips_full_page_scan():
    page = np.full((800, 600, 3), 250, np.uint8)
    assert pp.crop_receipt(page) is page


def test_deskew_leaves_straight_paper_alone():
    straight = pp.to_gray(_paper_on_dark_table(0)[350:1250, 320:880])
    assert abs(pp.estimate_skew_angle(straight)) < 0.5       # ảnh thẳng thì không bị "chỉnh" bậy


def test_text_scale_targets_readable_height():
    gray = np.full((2000, 1400), 255, np.uint8)
    for y in range(100, 1900, 70):
        cv2.putText(gray, "Bun bo 55.000", (30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
    h = pp.estimate_text_height(pp.normalize_text_scale(gray))
    assert h is not None and 20 <= h <= 40


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="cần Tesseract")
def test_pipeline_reads_tilted_photo_on_table(tmp_path):
    from app.modules.ocr.pipeline import read_receipt

    paper = np.full((620, 520, 3), 245, np.uint8)
    rows = ["QUAN COM TAM", "Com tam 2 40.000 80.000", "Tra da 1 5.000 5.000",
            "Tam tinh: 85.000", "Tong cong: 85.000"]
    for i, t in enumerate(rows):
        cv2.putText(paper, t, (15, 60 + i * 80), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (15, 15, 15), 2, cv2.LINE_AA)
    img = np.full((1800, 1400, 3), 45, np.uint8)
    img[500:1120, 440:960] = paper
    img = cv2.warpAffine(img, cv2.getRotationMatrix2D((700, 900), 5, 1), (1400, 1800), borderValue=(45, 45, 45))
    path = tmp_path / "r.jpg"
    cv2.imwrite(str(path), img)
    parsed, _ = read_receipt(str(path), timeout=90)
    assert parsed.total_amount == Decimal(85000)
    assert len(parsed.items) == 2


# ---------- dòng OCR thô lấy từ hóa đơn thật (Bách Hóa Xanh, nhà hàng Let's Go) ----------

BHX_RAW = [
    "BÁCH HÓA XANH", "PHIẾU THANH TOÁN", "Số CT: 22091052190069816", "Ngay CT: 10/09/202210:54 <.",
    "Nhân viên: Tống Trương Tu Hao `.", "mẽ... Vu Thành tiền",
    "HẠT É GÓI 100G", "1 17,0 17,000",
    "DAU AN COOKING TUON CHAI 2L.", "4 413,000 413,000",
    "MANG NHÔM BHX 30CMX7M", "1 30,000 30,000",
    "TAU HO TRANG ICHI-SAKUARA 240G (CB)", "1 8,500 8,500",
    "CAI THIA (KG)", "0.49 24,900 12,199",
    "TAO GALA MINI NHAP KHAU", "1.264 60,000 49,005 61,943",
    "(Đã bao gdm giảm giá) 242,641", "Thanh toán:", "(Đã làm trên) 242,000", "Tiền mặt. __ 802,000",
]

NHA_HANG_RAW = [
    "Nhà Hàng Let's Go |", "PHIẾU TAM TINH", "Số HD :HD.4008 10:11 07/05/2018", "Giờ vào: 19:04", "06/05/2018",
    "Món |ÐVT|[SL| Đ.Giá | T.Tiên |",
    "Cáchm |Kg |2 | 300000J 600000)", "Sườn ram mã Dia |2 300.000} 600.000.",
    "Mực cơm xào| Dia |2 | 300.000! 600.000!", "hành cần ¬",
    "Bò xào hành | Dia |2 | 250.000| 500.000,", "n",
    "Khoai tây chiếDia |2 | 150.000 son", "Mi xào hải si Dia |1 | 250.000] 250.000",
    "Chả giò Dia |1 | 340.000} 340.000", "Cơm chiên hả Dia |2 | 250.000! 500.000| |", "sản",
    "Rau muống |Dia |4 | 100.000| 400.00", "Khăn Lạnh | Cái |20| 3000| 60000",
    "RượuNgũ |Chai |1 | 200.000. 200.000", "Lượng Tửu", "nhỏ",
    "Nghéu Kg |3 | 150000 450.000", "Tômhủm |Con |2 | 165.000} 330.000", "trung - ;",
    "Tém si | Kg_|3 | 250.000} 750000", "Ốc ngón tay | Kg |3 | 250.000| 750.000", "ỐcHương | Kg |4 | 300.000] 1.200.000",
    "| Hàu Kg |28| 100.000) 280.000", "¡ Bia Sài gồn |Chai |48 15.000| 720.000", "chai ¬ | _ -",
    "Nước Sanna |Chai | 4 10.000 40.00C", "Tiger Lon |7 20.000 140.00C",
    "Tổng công 115,8 9.010.000",
]


def test_real_bhx_receipt():
    r = parse_receipt(BHX_RAW)
    assert r.receipt_date == date(2022, 9, 10)                    # "10/09/202210:54" dính giờ
    got = [(i.quantity, i.unit_price, i.line_total) for i in r.items]
    assert got == [
        (Decimal(1), Decimal(17000), Decimal(17000)),             # '17,0' mất 3 chữ số 0
        (Decimal(1), Decimal(113000), Decimal(113000)),           # '413,000' -> 113.000 nhờ khớp tổng hóa đơn
        (Decimal(1), Decimal(30000), Decimal(30000)),
        (Decimal(1), Decimal(8500), Decimal(8500)),
        (Decimal("0.49"), Decimal(24900), Decimal(12199)),
        (Decimal("1.264"), Decimal(49005), Decimal(61943)),       # bỏ cột giá gốc gạch ngang 50.000
    ]
    assert r.subtotal == Decimal(242641)
    assert r.discount_amount == Decimal(641)
    assert r.total_amount == Decimal(242000)
    assert any("tự sửa" in w for w in r.warnings)                 # số bị sửa phải có cảnh báo


def test_real_restaurant_receipt_all_20_items_and_total():
    r = parse_receipt(NHA_HANG_RAW)
    assert len(r.items) == 20
    assert sum(i.line_total for i in r.items) == Decimal(9010000) == r.total_amount
    by = {i.item_name.split()[0]: i for i in r.items}
    assert by["Hàu"].quantity == Decimal("2.8") and by["Hàu"].line_total == Decimal(280000)   # '28' -> 2,8 kg
    assert by["Khoai"].line_total == Decimal(300000)              # ô T.Tiền bị đọc thành chữ rác -> SL × đơn giá
    assert by["Rau"].line_total == Decimal(400000)                # '400.00' mất số 0
    assert by["Tiger"].line_total == Decimal(140000)              # '140.00C'
    assert not any(i.item_name.split()[-1] in ("Kg", "Dia", "Chai", "Cái") or i.item_name.endswith("Dia") for i in r.items)  # đã bỏ cột ĐVT
    assert next(i.item_name for i in r.items if i.item_name.startswith("Bia")).endswith("chai")   # 'chai' xuống dòng là tên, giữ lại
    assert "hành cần" in next(i.item_name for i in r.items if i.item_name.startswith("Mực"))      # tên món xuống dòng


def test_numbers_not_glued_together():
    assert normalize_numbers("200.000. 200.000") == "200.000. 200.000"
