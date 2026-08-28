"""Small, deterministic attachment policy for BX-03A.

The workflow service stores metadata and an opaque object-storage key.  It does
not inspect file contents; production can put malware scanning at that storage
boundary.  Similarity is deliberately a suggestion, never an authoritative
relationship.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CASE_FILES = 10
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
RELATION_METHODS = frozenset({"manual", "rule", "similarity_suggestion"})


class AttachmentError(ValueError):
    """A client supplied attachment that violates the published policy."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_metadata(filename, content_type, size_bytes, storage_key):
    """Validate metadata for an already-uploaded object.

    The object itself is intentionally outside this service.  ``size_bytes``
    is therefore supplied by the trusted storage adapter and checked again at
    the API boundary.
    """
    if not isinstance(filename, str) or not filename.strip() or len(filename) > 255:
        raise AttachmentError("FILENAME_INVALID", "filename is required and must be at most 255 characters")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise AttachmentError("FILENAME_INVALID", "filename must be a plain file name")
    extension = Path(filename).suffix.lower()
    expected = ALLOWED_EXTENSIONS.get(extension)
    if expected is None:
        raise AttachmentError("FILE_TYPE_NOT_ALLOWED", "file extension is not supported")
    if not isinstance(content_type, str) or content_type.lower() != expected:
        raise AttachmentError("MIME_EXTENSION_MISMATCH", "MIME type does not match the file extension")
    if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
        raise AttachmentError("FILE_SIZE_INVALID", "size_bytes must be a non-negative integer")
    if size_bytes > MAX_FILE_BYTES:
        raise AttachmentError("FILE_TOO_LARGE", "file must not exceed 10 MiB")
    if not isinstance(storage_key, str) or not storage_key.strip() or len(storage_key) > 512:
        raise AttachmentError("STORAGE_KEY_INVALID", "storage_key is required")
    if storage_key.startswith(("/", "\\")) or ".." in storage_key.split("/"):
        raise AttachmentError("STORAGE_KEY_INVALID", "storage_key must be an opaque object key")
    return {
        "filename": filename,
        "content_type": expected,
        "size_bytes": size_bytes,
        "storage_key": storage_key,
        "extension": extension,
    }


def load_required_rules(path=Path(__file__).with_name("attachment_rules.json")):
    """Load request-type-owned required attachment rules from local config."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schemaVersion") != "bx03a-attachment-rules-v1" or not isinstance(data.get("rules"), dict):
        raise ValueError("invalid attachment rules version")
    rules = {}
    for request_type, values in data["rules"].items():
        if not isinstance(request_type, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", request_type):
            raise ValueError("invalid request type in attachment rules")
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("invalid required attachment rule")
        rules[request_type] = tuple(dict.fromkeys(values))
    return rules


def missing_required_types(request_type, attachment_types, rules=None):
    rules = load_required_rules() if rules is None else rules
    required = tuple(rules.get(request_type, ()))
    present = set(attachment_types or ())
    return [item for item in required if item not in present]


def relation(method, source_attachment_id, target_attachment_id):
    """Build a relationship record and keep suggestions non-authoritative."""
    if method not in RELATION_METHODS:
        raise AttachmentError("RELATION_METHOD_INVALID", "unknown attachment relation method")
    if not isinstance(source_attachment_id, str) or not isinstance(target_attachment_id, str) or source_attachment_id == target_attachment_id:
        raise AttachmentError("RELATION_INVALID", "two distinct attachment IDs are required")
    return {
        "source_attachment_id": source_attachment_id,
        "target_attachment_id": target_attachment_id,
        "method": method,
        "authoritative": method != "similarity_suggestion",
    }


def similarity_suggestion(filename, candidates):
    """Return deterministic filename-token suggestions only.

    This is intentionally modest: it gives the UI a candidate and never adds a
    relation by itself.  A production embedding/model may replace this helper
    behind the same non-authoritative contract.
    """
    def tokens(value):
        return {part for part in re.split(r"[^a-z0-9çğıöşü]+", value.lower()) if len(part) >= 3}

    source = tokens(Path(filename).stem)
    if not source:
        return []
    suggestions = []
    for candidate in candidates or ():
        candidate_tokens = tokens(candidate.get("filename", ""))
        union = source | candidate_tokens
        score = len(source & candidate_tokens) / len(union) if union else 0.0
        if score > 0:
            suggestions.append({"attachment_id": candidate.get("attachment_id"), "score": round(score, 3), "method": "similarity_suggestion", "authoritative": False})
    return sorted(suggestions, key=lambda item: (-item["score"], item["attachment_id"] or ""))
