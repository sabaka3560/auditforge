"""AuditForge engine — public API.

Import everything you need from here. Don't import from submodules directly in main.py.
"""

from .comparator import compare
from .matcher import build_mapping
from .reader import read_actual, read_ideal
from .types import AuditRow, MappingResult
from .writer import build_report

__all__ = [
    "read_actual",
    "read_ideal",
    "build_mapping",
    "compare",
    "build_report",
    "AuditRow",
    "MappingResult",
]
