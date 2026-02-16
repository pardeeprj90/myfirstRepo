"""Delivery assurance facade on top of the simple PDF analysis service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .workflow import analyze_wsr_file


@dataclass
class RunMetadata:
    """Run-level metadata used by the delivery assurance entrypoint."""

    project_id: str
    week_date: str


def run_delivery_assurance(current_wsr_path: str, previous_wsr_path: str, metadata: RunMetadata) -> Dict[str, Any]:
    """Analyze current WSR PDF and provide a minimal week-over-week note.

    The simplified requirement is PDF upload analysis. Previous WSR is accepted
    for compatibility, and this function returns both analyses side-by-side.
    """
    current = analyze_wsr_file(
        file_path=current_wsr_path,
        account="N/A",
        project_name=metadata.project_id,
        week_date=metadata.week_date,
    )
    previous = analyze_wsr_file(
        file_path=previous_wsr_path,
        account="N/A",
        project_name=metadata.project_id,
        week_date=metadata.week_date,
    )

    return {
        "project_id": metadata.project_id,
        "week_date": metadata.week_date,
        "current_week_analysis": current,
        "previous_week_analysis": previous,
        "note": "Simplified flow: PDF extraction and deterministic signal analysis.",
    }
