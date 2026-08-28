"""Pure F-06 case-state decisions used by the durable orchestrator worker."""

MAX_F04_START_ATTEMPTS = 4  # initial start plus the approved three retries

PRIORITY_RULES = (
    ("critical", 100, (("yangin", "Yangın riski"), ("gaz kacagi", "Gaz kaçağı riski"), ("patlama", "Patlama riski"), ("cokme", "Çökme riski"), ("can guvenligi", "Can güvenliği riski"), ("yarali", "Yaralı bildirimi"), ("acil mudahale", "Acil müdahale talebi"))),
    ("high", 70, (("su baskini", "Su baskını"), ("kanalizasyon", "Kanalizasyon etkisi"), ("zehirlenme", "Zehirlenme riski"), ("hijyen", "Hijyen riski"), ("salgin", "Salgın riski"))),
)


def _priority_text(value):
    return (value or "").lower().translate(str.maketrans("ığüşöç", "igusoc"))


def priority_for_text(value):
    """Return the first configured safety/service-impact rule, never model inference."""
    text = _priority_text(value)
    for level, score, rules in PRIORITY_RULES:
        for phrase, reason in rules:
            if phrase in text:
                return level, score, reason
    return "normal", 40, "Öncelik sinyali bulunmadı"


def next_start_action(classification_status, completion_status, generation_status, attempts):
    if classification_status != "classified" or completion_status != "complete":
        return "none"
    if generation_status is None:
        return "start" if attempts == 0 else "none"
    if generation_status == "failed":
        return "retry" if attempts < MAX_F04_START_ATTEMPTS else "terminal_failure"
    return "none"


def derive_case_state(classification_status, completion_status, generation_status, result_status, routing_status, notifications):
    if classification_status != "classified":
        return "needs_review"
    if completion_status is None:
        return "extracting"
    if completion_status in {"missing_information", "invalid_information"}:
        return "waiting_for_user"
    if generation_status == "failed":
        return "failed"
    if generation_status in {None, "queued", "processing"}:
        return "ready_for_processing"
    if result_status == "review_required":
        return "needs_review"
    if routing_status != "routed":
        return "draft_prepared"
    values = set((notifications or {}).values())
    if values == {"completed"} and len(notifications or {}) == 2:
        return "completed"
    return "notification_pending"


def project_case(role, source):
    if role not in {"USER", "ADMIN"}:
        raise ValueError("role must be USER or ADMIN")
    public = {key: source[key] for key in ("case_id", "state", "validation_status", "routing_status", "applicant_notifications") if key in source}
    if role == "ADMIN":
        public.update({key: source[key] for key in ("validated_fields", "target_notification") if key in source})
    return public
