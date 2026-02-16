"""WSR assurance package.

This package separates concerns into production-oriented modules while
preserving legacy top-level entrypoints.
"""

from .delivery_assurance import RunMetadata, run_delivery_assurance
from .workflow import (
    WSRMetadata,
    analyze_wsr,
    analyze_wsr_file,
    ingest_wsr_file_from_ui,
    ingest_wsr_from_ui,
)

__all__ = [
    "RunMetadata",
    "WSRMetadata",
    "run_delivery_assurance",
    "analyze_wsr",
    "analyze_wsr_file",
    "ingest_wsr_from_ui",
    "ingest_wsr_file_from_ui",
]
