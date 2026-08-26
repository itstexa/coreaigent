import base64
import logging
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVICES_DIR = os.path.dirname(_HERE)
for _svc in ("ocr", "classification", "validation", "llm"):
    _path = os.path.join(_SERVICES_DIR, _svc)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from pdf_extract import extract_pdf_text
from ocr_scan import extract_scanned_text
from classify import classify_document
from validate import validate_document
from router import route_document
from draft import generate_draft, summarize
import rag_connector

logger = logging.getLogger("workflow.pipeline")

DRAFT_ELIGIBLE_TYPES = {"petition", "application", "complaint", "information_request", "official_letter"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(correlation_id: str, step: str, message: str, level: str = "info"):
    payload = {
        "timestamp": _now(),
        "service": "workflow",
        "correlationId": correlation_id,
        "step": step,
        "message": message,
    }
    getattr(logger, level)(payload)


def run_pipeline(document_input: dict, workflow_id: str, model, tokenizer) -> dict:
    request_id = document_input["requestId"]
    document_id = document_input["documentId"]
    content_type = document_input["contentType"]
    content = document_input.get("content")

    steps = []
    error = None

    def record(service: str, status: str):
        steps.append({"service": service, "status": status, "timestamp": _now()})

    # --- OCR ---
    text = ""
    ocr_warnings = []
    try:
        if content_type == "text/plain":
            text = content or ""
        elif content_type == "application/pdf":
            if not content:
                raise ValueError("PDF içeriği boş")
            pdf_bytes = base64.b64decode(content)
            result = extract_pdf_text(pdf_bytes)
            text = result.get("text", "")
            ocr_warnings = result.get("warnings", [])
        elif content_type in ("image/png", "image/jpeg"):
            if not content:
                raise ValueError("Görsel içeriği boş")
            image_bytes = base64.b64decode(content)
            result = extract_scanned_text(image_bytes)
            text = result.get("text", "")
            ocr_warnings = result.get("warnings", [])
        else:
            raise ValueError(f"Desteklenmeyen contentType: {content_type}")
        record("ocr", "completed")
        _log(workflow_id, "ocr", f"metin uzunluğu={len(text)}, warnings={ocr_warnings}")
    except Exception as exc:
        record("ocr", "failed")
        _log(workflow_id, "ocr", f"kritik hata: {exc}", level="error")
        return {
            "schemaVersion": "1.0",
            "requestId": request_id,
            "documentId": document_id,
            "workflowId": workflow_id,
            "status": "rejected",
            "documentType": "unsupported",
            "department": "manual_review",
            "draft": "",
            "steps": steps,
            "error": {"step": "ocr", "message": str(exc)},
        }

    if not text or not text.strip():
        record("classification", "skipped")
        record("validation", "skipped")
        record("rag", "skipped")
        record("llm", "skipped")
        _log(workflow_id, "workflow", "OCR metin üretmedi, evrak reddedildi", level="error")
        return {
            "schemaVersion": "1.0",
            "requestId": request_id,
            "documentId": document_id,
            "workflowId": workflow_id,
            "status": "rejected",
            "documentType": "unsupported",
            "department": "manual_review",
            "draft": "",
            "steps": steps,
            "error": {"step": "ocr", "message": "Metin çıkarılamadı (okunamayan/boş belge)"},
        }

    # --- Classification ---
    document_type = "unsupported"
    classification_decision = "manual_review"
    try:
        cls_result = classify_document(text, model, tokenizer)
        document_type = cls_result["documentType"]
        classification_decision = cls_result["classification"]
        record("classification", "completed")
        _log(workflow_id, "classification", f"documentType={document_type}, classification={classification_decision}")
    except Exception as exc:
        record("classification", "failed")
        _log(workflow_id, "classification", f"hata: {exc}", level="error")

    # --- Validation ---
    missing_fields = []
    conflicts = []
    try:
        val_result = validate_document(document_type, text, model, tokenizer)
        missing_fields = val_result.get("missingFields", [])
        conflicts = val_result.get("conflicts", [])
        record("validation", "completed")
        _log(workflow_id, "validation", f"missingFields={missing_fields}, conflicts={conflicts}")
    except Exception as exc:
        record("validation", "failed")
        _log(workflow_id, "validation", f"hata (kritik değil, devam ediliyor): {exc}", level="error")

    # --- RAG (best-effort) ---
    context_snippets = []
    if document_type in DRAFT_ELIGIBLE_TYPES:
        try:
            rag_result = rag_connector.get_rag_context(text[:500])
            context_snippets = rag_result.get("context_snippets", [])
            record("rag", "completed" if context_snippets else "skipped")
            _log(workflow_id, "rag", f"{len(context_snippets)} kaynak bulundu")
        except Exception as exc:
            record("rag", "failed")
            _log(workflow_id, "rag", f"hata (kritik değil, boş bağlamla devam): {exc}", level="error")
    else:
        record("rag", "skipped")

    # --- LLM: routing + draft ---
    department = "manual_review"
    confidence = 0.0
    draft_text = ""
    try:
        routing = route_document(text, model, tokenizer)
        department = routing["department"]
        confidence = routing["confidence"]

        if document_type in DRAFT_ELIGIBLE_TYPES and classification_decision != "unsupported":
            draft_text = generate_draft(text, context_snippets, model, tokenizer)
        else:
            draft_text = summarize(text, model, tokenizer)

        record("llm", "completed")
        _log(workflow_id, "llm", f"department={department}, confidence={confidence}")
    except Exception as exc:
        record("llm", "failed")
        _log(workflow_id, "llm", f"hata: {exc}", level="error")
        error = {"step": "llm", "message": str(exc)}

    # --- Nihai durum ---
    if document_type == "unsupported":
        status = "manual_review"
    elif missing_fields:
        status = "needs_information"
    elif classification_decision == "manual_review" or department == "manual_review":
        status = "manual_review"
    elif error:
        status = "manual_review"
    else:
        status = "completed"

    record("workflow", "completed")

    return {
        "schemaVersion": "1.0",
        "requestId": request_id,
        "documentId": document_id,
        "workflowId": workflow_id,
        "status": status,
        "documentType": document_type,
        "department": department,
        "draft": draft_text,
        "steps": steps,
        "error": error,
    }
