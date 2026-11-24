"""Gemini OCR: thứ tự model, tự bỏ model không có quyền, lượt tự kiểm toán, lỗi rõ ràng (không gọi mạng thật)."""
import sys
import types
from decimal import Decimal

import pytest

from app.core.config import settings
from app.modules.ocr import gemini_ocr as g
from app.modules.ocr.engine import OcrError


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    g._UNHEALTHY_UNTIL.clear()
    monkeypatch.setattr(g, "_LAST_GOOD_MODEL", None)
    monkeypatch.setattr(g, "_CACHED_FALLBACKS", [])
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-4-argon")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODELS", "gemini-3.1-pro-preview,gemini-3.8-flash")
    yield
    g._UNHEALTHY_UNTIL.clear()


def _receipt(total):
    return g._GeminiReceipt(
        merchant_name="Quán A",
        receipt_date="2019-03-29",
        items=[g._GeminiItem(item_name="Coca", quantity=9, unit_price=25000, line_total=225000)],
        subtotal=225000,
        total_amount=total,
    )


def _fake_google(monkeypatch):
    genai = types.ModuleType("google.genai")
    genai.Client = lambda **kw: types.SimpleNamespace(models=types.SimpleNamespace(list=lambda: []))
    gtypes = types.ModuleType("google.genai.types")
    gtypes.HttpOptions = lambda **kw: kw
    genai.types = gtypes
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", gtypes)


def test_model_khong_co_quyen_tu_chuyen_sang_model_ke_tiep(monkeypatch, tmp_path):
    _fake_google(monkeypatch)
    img = tmp_path / "r.jpg"
    img.write_bytes(b"x")
    calls = []

    def fake_call(client, types_, model, img_bytes, mime, prompt, timeout=None):
        calls.append(model)
        if model == "gemini-4-argon":
            raise RuntimeError("403 PERMISSION_DENIED")
        if model == "gemini-3.1-pro-preview":
            raise RuntimeError("404 NOT_FOUND")
        return _receipt(225000)

    monkeypatch.setattr(g, "_call_model", fake_call)
    monkeypatch.setattr(g, "_prepare_image_bytes", lambda p: (b"x", "image/jpeg"))
    parsed, _ = g.read_receipt_gemini(str(img))
    assert calls[:3] == ["gemini-4-argon", "gemini-3.1-pro-preview", "gemini-3.8-flash"]
    assert parsed.total_amount == Decimal(225000)
    assert parsed.ocr_status == "DONE"


def test_tu_kiem_toan_lai_khi_lech_tien_va_chon_ket_qua_khop(monkeypatch, tmp_path):
    _fake_google(monkeypatch)
    img = tmp_path / "r.jpg"
    img.write_bytes(b"x")
    prompts = []

    def fake_call(client, types_, model, img_bytes, mime, prompt, timeout=None):
        prompts.append(prompt)
        return _receipt(325000 if len(prompts) == 1 else 225000)   # lượt 1 sai tổng, lượt kiểm toán đúng

    monkeypatch.setattr(g, "_call_model", fake_call)
    monkeypatch.setattr(g, "_prepare_image_bytes", lambda p: (b"x", "image/jpeg"))
    parsed, _ = g.read_receipt_gemini(str(img))
    assert len(prompts) == 2 and "KIỂM TOÁN" in prompts[1]
    assert parsed.total_amount == Decimal(225000)


def test_tat_ca_model_loi_bao_loi_ro_rang(monkeypatch, tmp_path):
    _fake_google(monkeypatch)
    img = tmp_path / "r.jpg"
    img.write_bytes(b"x")

    def boom(*a, **k):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(g, "_call_model", boom)
    monkeypatch.setattr(g, "_prepare_image_bytes", lambda p: (b"x", "image/jpeg"))
    with pytest.raises(OcrError) as ei:
        g.read_receipt_gemini(str(img))
    assert "GEMINI_API_KEY" in str(ei.value)


def test_timeout_va_model_mac_dinh_uu_tien_do_chinh_xac():
    assert g._per_call_timeout() >= 60
    assert g._total_budget() >= g._per_call_timeout()
    assert settings.GEMINI_MODEL
<<<<<<< HEAD


def test_chuan_hoa_model_id_trong_env():
    assert g._normalize_model_name(" gemini 3.5-flash-lite ") == "gemini-3.5-flash-lite"
    assert g._normalize_model_name("models/gemini-2.5-flash") == "gemini-2.5-flash"
=======
>>>>>>> 183f54fae0693e6e492861efe8028d57c217a3a6
