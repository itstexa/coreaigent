import io

from pypdf import PdfReader


def extract_pdf_text(pdf_bytes: bytes) -> dict:
    warnings = []
    text_parts = []
    pages = 0

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return {"text": "", "pages": 0, "warnings": ["corrupt_pdf"]}

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return {"text": "", "pages": 0, "warnings": ["encrypted_pdf"]}

    if len(reader.pages) == 0:
        return {"text": "", "pages": 0, "warnings": ["empty_pdf"]}

    pages = len(reader.pages)

    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        text_parts.append(page_text)

    text = "\n\n".join(text_parts).strip()

    if not text:
        warnings.append("no_text_extracted")

    return {"text": text, "pages": pages, "warnings": warnings}
