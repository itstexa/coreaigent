"""Deterministic, editable citizen-document drafts (BX-07)."""
import json
from pathlib import Path

CONFIG = json.loads((Path(__file__).parent / "draft_templates.json").read_text(encoding="utf-8"))


def validate_draft(document_type, fields=None, text=""):
    if not isinstance(document_type, str) or document_type not in CONFIG["templates"]:
        raise ValueError("unsupported_document_type")
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("invalid_text")
    values = fields if isinstance(fields, dict) else {}
    missing = [name for name in CONFIG["templates"][document_type]["required"]
               if not isinstance(values.get(name), str) or not values[name].strip()]
    return missing


def make_draft(document_type, fields=None, text=""):
    missing = validate_draft(document_type, fields, text)
    values = fields if isinstance(fields, dict) else {}
    body = values.get("body", text)
    rendered = "KONU: {0}\n\n{1}".format(values.get("subject", ""), body)
    return {"draft_id": "draft-local", "document_type": document_type,
            "template_version": CONFIG["version"], "fields": values,
            "text": rendered, "missing_fields": missing,
            "temporary": True, "editable": True, "legal_finality": False}
