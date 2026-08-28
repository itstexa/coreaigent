"""Local-only PDF/DOCX conversion for the OCR boundary."""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SUPPORTED = {".pdf": PDF, ".docx": DOCX}
DET_MODEL_DIR = Path(os.environ.get("PADDLE_DET_MODEL_DIR", "/var/cache/paddleocr/hub/models--PaddlePaddle--PP-OCRv5_mobile_det/snapshots/0d63e78e2b680928f6b1747d76a08db6e645efb7"))
REC_MODEL_DIR = Path(os.environ.get("PADDLE_REC_MODEL_DIR", "/var/cache/paddleocr/hub/models--PaddlePaddle--latin_PP-OCRv5_mobile_rec/snapshots/ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57"))
_OCR = None
_OCR_LOCK = threading.Lock()
_OCR_SEMAPHORE = threading.BoundedSemaphore(1)


class ExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_upload(filename: str | None, content_type: str | None, content: bytes) -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower()
    if not filename or len(filename) > 255 or SUPPORTED.get(suffix) != content_type:
        raise ExtractionError("FILE_TYPE_INVALID", "Only matching PDF and DOCX uploads are accepted")
    if not content:
        raise ExtractionError("FILE_EMPTY", "The source file must not be empty")
    if len(content) > MAX_FILE_BYTES:
        raise ExtractionError("FILE_TOO_LARGE", "The source file exceeds 10 MiB")
    return filename, content_type


def _native_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception as exc:
        raise ExtractionError("PDF_UNREADABLE", "The PDF cannot be read") from exc


def _docx_text(content: bytes) -> str:
    try:
        from docx import Document

        document = Document(io.BytesIO(content))
    except Exception as exc:
        raise ExtractionError("DOCX_UNREADABLE", "The DOCX cannot be read") from exc
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _ocr_model():
    global _OCR
    if _OCR is not None:
        return _OCR
    if not DET_MODEL_DIR.is_dir() or not REC_MODEL_DIR.is_dir():
        raise ExtractionError("OCR_MODEL_UNAVAILABLE", "Pinned local OCR artifacts are unavailable")
    with _OCR_LOCK:
        if _OCR is None:
            from paddleocr import PaddleOCR

            _OCR = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_detection_model_dir=str(DET_MODEL_DIR),
                text_recognition_model_name="latin_PP-OCRv5_mobile_rec",
                text_recognition_model_dir=str(REC_MODEL_DIR),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
            )
    return _OCR


def _ocr_pdf_text(content: bytes) -> str:
    if not _OCR_SEMAPHORE.acquire(blocking=False):
        raise ExtractionError("OCR_BUSY", "OCR is busy; retry the request")
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
            source.write(content)
            source.flush()
            texts = []
            for result in _ocr_model().predict(source.name):
                raw = getattr(result, "json", result)
                payload = json.loads(raw) if isinstance(raw, str) else raw
                values = payload.get("res", {}).get("rec_texts", []) if isinstance(payload, dict) else []
                texts.extend(value for value in values if isinstance(value, str))
            return "\n".join(texts)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("PDF_OCR_FAILED", "OCR could not extract text from the PDF") from exc
    finally:
        _OCR_SEMAPHORE.release()


def extract_text(filename: str, content_type: str, content: bytes) -> str:
    """Extract local text, using pinned OCR only when a PDF has no text layer."""
    validate_upload(filename, content_type, content)
    text = _docx_text(content) if content_type == DOCX else _native_pdf_text(content)
    return text or (_ocr_pdf_text(content) if content_type == PDF else "")
