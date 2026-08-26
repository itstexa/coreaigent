import logging
from datetime import datetime, timezone
from typing import Dict, List

from required_fields import REQUIRED_FIELDS
from rule_checks import regex_field_present
from llm_checks import check_missing_semantic_fields, check_contradictions

logger = logging.getLogger(__name__)


def validate_document(document_type: str, source_text: str, model, tokenizer) -> dict:
    request_id = "validation-internal"
    document_id = "unknown"
    workflow_id = "unknown"

    log_context = {
        "requestId": request_id,
        "documentId": document_id,
        "workflowId": workflow_id,
        "service": "validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if document_type == "unsupported" or document_type not in REQUIRED_FIELDS:
        logger.info("Unsupported or unknown document type", extra=log_context)
        return {"missingFields": [], "conflicts": []}

    required_fields = REQUIRED_FIELDS[document_type]

    if len(source_text) < 10:
        missing_fields = [field_name for field_name, _ in required_fields]
        logger.info("Source text too short, all fields missing", extra=log_context)
        return {"missingFields": missing_fields, "conflicts": []}

    missing_fields: List[str] = []
    llm_fields: List[str] = []

    for field_name, method in required_fields:
        if method == "regex":
            if not regex_field_present(field_name, source_text):
                missing_fields.append(field_name)
        elif method == "llm":
            llm_fields.append(field_name)

    if llm_fields:
        try:
            semantic_missing = check_missing_semantic_fields(
                source_text, llm_fields, model, tokenizer
            )
            missing_fields.extend(semantic_missing)
        except Exception as e:
            logger.error(
                "Semantic field check failed",
                extra={**log_context, "error": "semantic_check_error", "detail": str(e)},
            )
            raise

    ordered_missing = []
    for field_name, _ in required_fields:
        if field_name in missing_fields and field_name not in ordered_missing:
            ordered_missing.append(field_name)

    try:
        conflicts = check_contradictions(source_text, model, tokenizer)
    except Exception as e:
        logger.error(
            "Contradiction check failed",
            extra={**log_context, "error": "contradiction_check_error", "detail": str(e)},
        )
        raise

    return {"missingFields": ordered_missing, "conflicts": conflicts}
