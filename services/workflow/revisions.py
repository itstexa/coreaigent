"""Pure BX-05 edit validation and revision policy."""
import uuid

EDITABLE = {"text", "structured_fields", "attachment_ids"}
def validate_edit(payload):
    if not isinstance(payload, dict) or not payload or "classification" in payload:
        raise ValueError("classification is not editable" if isinstance(payload, dict) and "classification" in payload else "edit must contain content")
    if set(payload) - EDITABLE:
        raise ValueError("unknown edit field")
    if "text" in payload and (not isinstance(payload["text"], str) or not payload["text"].strip()): raise ValueError("text must be non-empty")
    if "structured_fields" in payload and not isinstance(payload["structured_fields"], dict): raise ValueError("structured_fields must be an object")
    if "attachment_ids" in payload and (not isinstance(payload["attachment_ids"], list) or any(_bad_uuid(x) for x in payload["attachment_ids"])): raise ValueError("attachment_ids must contain UUIDs")
    return payload
def _bad_uuid(value):
    try: uuid.UUID(str(value)); return False
    except (ValueError, TypeError, AttributeError): return True
def edit_decision(state, resolved=False):
    if resolved or state in {"completed", "closed"}: return "terminal"
    if state in {"draft", "draft_prepared", "waiting_for_information", "waiting_for_user", "review", "needs_review", "routed"}: return "accepted"
    return "terminal"
def next_revision(current):
    if current is None: return 1
    if not isinstance(current, int) or current < 1: raise ValueError("revision must be positive")
    return current + 1
