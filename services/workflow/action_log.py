"""Validation and persistence helpers for workflow-owned case action events."""

import uuid


def _jsonb(value):
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:  # stdlib unit tests do not install DB driver
        return value
    return Jsonb(value)

ACTION_TYPES = frozenset(
    {
        "state_change",
        "assignment",
        "petition_edit",
        "attachment_change",
        "spam_decision",
        "view",
        "download",
    }
)


def build_action_event(case_id: str, action_type: str, actor: str) -> dict[str, str]:
    if isinstance(case_id, uuid.UUID):
        case_id = str(case_id)
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id is required")
    if action_type not in ACTION_TYPES:
        raise ValueError("unknown action_type")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor is required")
    return {"case_id": case_id, "action_type": action_type, "actor": actor}


def append_action_log(cur, case_id: str, action_type: str, actor: str, details=None, event_id=None):
    """Append one immutable event; duplicate event IDs are idempotent."""
    event = build_action_event(case_id, action_type, actor)
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise ValueError("details must be an object")
    event_id = event_id or uuid.uuid4()
    cur.execute(
        "INSERT INTO case_action_logs (event_id,case_id,action_type,actor,details) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING",
        (event_id, event["case_id"], event["action_type"], event["actor"], _jsonb(details)),
    )
    return event_id
