"""Simple schema definitions for rule engine outputs."""
from typing import TypedDict, List


class RuleEngineResult(TypedDict):
    document_type: str
    document_type_score: float
    purpose: str
    recommended_department: str
    department_score: float
    missing_fields: List[str]
    legislation_suggestions: List[str]
    draft_type: str
    draft: str
    notes: str
