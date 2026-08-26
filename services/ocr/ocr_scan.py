import logging
from typing import Dict, List

import pytesseract
from PIL import Image, UnidentifiedImageError
import io

logger = logging.getLogger(__name__)

def extract_scanned_text(image_bytes: bytes, lang: str = "tur") -> Dict:
    warnings: List[str] = []
    
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as e:
        logger.error(f"OCR image open failed: {e}", exc_info=True)
        return {"text": "", "confidence": 0.0, "warnings": ["IMAGE_OPEN_FAILED"]}
    
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
    
    return {"text": text, "confidence": avg_confidence, "warnings": warnings}
