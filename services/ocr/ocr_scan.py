import logging
from typing import Dict, List, Optional

import numpy as np
import pytesseract
from PIL import Image, UnidentifiedImageError
import io

logger = logging.getLogger(__name__)

# PaddleOCR öncelikli motor — ağır (paddlepaddle + tespit/tanıma modelleri,
# ilk çağrıda indirilir) olduğu için modül seviyesinde LAZY ve TEK SEFER
# başlatılır (module-level singleton), her extract_scanned_text çağrısında
# değil. Kurulu değilse veya başlatılamazsa (paddlepaddle eksik, GPU/bellek
# sorunu vb.) None kalır ve aşağıdaki fallback zinciri Tesseract'a düşer —
# servis hiçbir zaman PaddleOCR yokluğu yüzünden çökmez.
_paddle_ocr = None
_paddle_import_failed = False


def _get_paddle_ocr():
    global _paddle_ocr, _paddle_import_failed
    if _paddle_ocr is not None or _paddle_import_failed:
        return _paddle_ocr
    try:
        from paddleocr import PaddleOCR

        # enable_mkldnn=False: PaddleOCR/PaddlePaddle 3.x'in CPU (oneDNN)
        # inference yolunda gerçek bir modelle doğrulanmış bug var —
        # "NotImplementedError: ConvertPirAttribute2RuntimeAttribute not
        # support [pir::ArrayAttribute<pir::DoubleAttribute>]" ile çöküyor.
        # mkldnn kapatılınca aynı model aynı görüntüde sorunsuz çalışıyor
        # (bkz. bu commit'in test çalıştırması). GPU'da (3090, CUDA ile)
        # mkldnn zaten devrede olmayan bir CPU-only optimizasyon backend'i
        # olduğu için bu flag GPU performansını etkilemiyor.
        _paddle_ocr = PaddleOCR(lang="tr", enable_mkldnn=False)
    except Exception as e:  # ImportError (kurulu değil) veya model indirme/başlatma hatası
        logger.warning(f"PaddleOCR başlatılamadı, Tesseract'a düşülüyor: {e}")
        _paddle_import_failed = True
        _paddle_ocr = None
    return _paddle_ocr


def _extract_with_paddle(image: Image.Image) -> Optional[Dict]:
    """PaddleOCR ile dener. Başarısız/boş sonuçta None döner — çağıran
    Tesseract'a düşer. pytesseract ile AYNI sözleşme (text/confidence/
    warnings) üretir ki extract_scanned_text'in dış davranışı ve
    contracts/schemas/ocr-result.schema.json ile uyumu değişmesin."""
    engine = _get_paddle_ocr()
    if engine is None:
        return None

    try:
        # .ocr() değil .predict() — PaddleOCR 3.x'te asıl API bu (.ocr()
        # eski/geriye-uyumluluk sarmalayıcısı, farklı ve daha kırılgan bir
        # sonuç şekli döndürüyor). .predict() bir sonuç nesnesi listesi
        # döner (tek görsel -> tek elemanlı liste), her biri dict-benzeri
        # ve "rec_texts"/"rec_scores" alanlarını içerir.
        results = engine.predict(np.array(image.convert("RGB")))
    except Exception as e:
        logger.warning(f"PaddleOCR işleme hatası, Tesseract'a düşülüyor: {e}")
        return None

    if not results:
        return None
    page = results[0]
    texts = [t.strip() for t in (page.get("rec_texts") or []) if t and t.strip()]
    scores = [float(s) for s in (page.get("rec_scores") or [])]

    if not texts:
        return None

    return {
        "text": " ".join(texts),
        "confidence": max(0.0, min(1.0, sum(scores) / len(scores))) if scores else 0.0,
        "warnings": [],
    }


def _extract_with_tesseract(image: Image.Image, lang: str) -> Dict:
    try:
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    except Exception as e:
        logger.error(f"OCR processing failed: {e}", exc_info=True)
        return {"text": "", "confidence": 0.0, "warnings": ["OCR_PROCESSING_FAILED"]}

    confidences = []
    for conf in data.get("conf", []):
        try:
            conf_val = float(conf)
            if conf_val >= 0:
                confidences.append(conf_val)
        except (TypeError, ValueError):
            continue

    if not confidences:
        return {"text": "", "confidence": 0.0, "warnings": ["NO_TEXT_FOUND"]}

    text = " ".join([word for word in data.get("text", []) if word.strip()])
    if not text.strip():
        return {"text": "", "confidence": 0.0, "warnings": ["NO_TEXT_FOUND"]}

    avg_confidence = sum(confidences) / len(confidences) / 100.0
    avg_confidence = max(0.0, min(1.0, avg_confidence))

    return {"text": text, "confidence": avg_confidence, "warnings": []}


def extract_scanned_text(image_bytes: bytes, lang: str = "tur") -> Dict:
    """PaddleOCR ÖNCELİKLİ, Tesseract YEDEK (eski sistem korunuyor, atılmadı).

    Sıra: önce PaddleOCR denenir (kurulu + başarılı + gerçek metin
    üretti ise doğrudan onun sonucu kullanılır — Tesseract hiç
    çalıştırılmaz, ekstra maliyet yok). PaddleOCR kurulu değilse, model
    başlatılamazsa, işlem sırasında hata verirse ya da hiç metin
    bulamazsa, aynı görsel Tesseract'a (services/workflow/pipeline.py ve
    services/ocr/main.py'nin bugüne kadar kullandığı yol) düşülür — imza
    ve dönüş sözleşmesi (text/confidence/warnings) değişmedi, bu iki
    çağıran hiç dokunulmadan çalışmaya devam eder.
    """
    warnings: List[str] = []

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as e:
        logger.error(f"OCR image open failed: {e}", exc_info=True)
        return {"text": "", "confidence": 0.0, "warnings": ["IMAGE_OPEN_FAILED"]}

    paddle_result = _extract_with_paddle(image)
    if paddle_result is not None:
        return paddle_result

    warnings.append("paddleocr_unavailable_or_empty_fell_back_to_tesseract")
    tesseract_result = _extract_with_tesseract(image, lang)
    tesseract_result["warnings"] = warnings + tesseract_result["warnings"]
    return tesseract_result
