from dataclasses import dataclass
from typing import Optional


@dataclass
class MappingResult:
    """One ideal config name resolved (or not) to an actual column header."""

    ideal_name: str
    ideal_value: str
    matched_header: Optional[str]
    match_method: str  # Exact | Normalized | Manual Alias | Fuzzy | Unmatched
    similarity_score: float
    status: str  # Matched | Unmatched
    remarks: str
    options: str = ""  # Valid choices from the ideal file Options column


@dataclass
class AuditRow:
    """One BU × config comparison result written to an output sheet."""

    bu_name: str
    config_name: str
    actual_value: str
    ideal_value: str
    comment: str  # Controls in place | Controls gaps | Actual config captured
    options: str = ""  # Populated only for control gaps
