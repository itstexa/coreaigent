import base64
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pdf_extract import extract_pdf_text
from ocr_scan import extract_scanned_text

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger("ocr")


class DocumentInput(BaseModel):
    schemaVersion: str
    requestId: str
    documentId: str
    scenarioId: str
    contentType: str
    content: Optional[str] = None
    fileName: Optional[str] = None
    source: str


class OCRResult(BaseModel):
    schemaVersion: str = "1.0"
    requestId: str
    documentId: str
    workflowId: str
    text: str
    language: str = "tr"
    confidence: float
    pages: Optional[int] = None
    warnings: List[str] = Field(default_factory=list)


app = FastAPI(title="OCR Service")


def _log(request_id: str, document_id: str, workflow_id: str = None, error: str = None):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ocr",
        "requestId": request_id,
        "documentId": document_id,
    }
    if workflow_id:
        log_entry["workflowId"] = workflow_id
    if error:
        log_entry["error"] = error
    logger.info(json.dumps(log_entry, ensure_ascii=False))


@app.post("/v1/ocr")
async def ocr_endpoint(request: DocumentInput):
    workflow_id = request.requestId
    warnings = []
    confidence = 1.0
    pages = None
    text = ""

    try:
        if request.contentType == "application/pdf":
            if not request.content:
                raise ValueError("content is required for PDF")
            pdf_bytes = base64.b64decode(request.content)
            result = extract_pdf_text(pdf_bytes)
            text = result.get("text", "")
            pages = result.get("pages")
            warnings = result.get("warnings", [])
            if warnings:
                confidence *= 0.5

        elif request.contentType in ("image/png", "image/jpeg"):
            if not request.content:
                raise ValueError("content is required for image")
            image_bytes = base64.b64decode(request.content)
            result = extract_scanned_text(image_bytes)
            text = result.get("text", "")
            pages = result.get("pages")
            warnings = result.get("warnings", [])
            confidence = result.get("confidence", 1.0)

        elif request.contentType == "text/plain":
            text = request.content or ""
            confidence = 1.0
            pages = None

        else:
            raise ValueError(f"Unsupported contentType: {request.contentType}")

        language = "tr" if text else "unknown"
        _log(request.requestId, request.documentId, workflow_id)

        return OCRResult(
            requestId=request.requestId,
            documentId=request.documentId,
            workflowId=workflow_id,
            text=text,
            language=language,
            confidence=confidence,
            pages=pages,
            warnings=warnings
        )

    except Exception as e:
        _log(request.requestId, request.documentId, workflow_id, error=f"processing_error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    try:
        import pypdf
        import pytesseract
        return {"status": "ready"}
    except ImportError as e:
        _log("", "", error=f"dependency_error: {str(e)}")
        raise HTTPException(status_code=503, detail="Dependencies not available")
