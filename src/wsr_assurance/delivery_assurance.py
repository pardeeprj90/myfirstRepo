"""Delivery Assurance API layer.

This module exposes a simple business-facing entrypoint while delegating
execution to the LangGraph workflow in ``workflow.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .workflow import analyze_uploaded_wsr, analyze_wsr_file


@dataclass
class RunMetadata:
    """Run metadata provided by UI/service layer."""

    project_id: str
    week_date: str
    account: str


def run_delivery_assurance(current_wsr_path: str, previous_wsr_path: str, metadata: RunMetadata) -> Dict[str, Any]:
    """Run current-week analysis and compare with previous-week WSR."""
    return analyze_wsr_file(
        current_file_path=current_wsr_path,
        previous_file_path=previous_wsr_path,
        account=metadata.account,
        project_name=metadata.project_id,
        week_date=metadata.week_date,
    )


def run_delivery_assurance_for_uploaded_file(current_file_id: str) -> Dict[str, Any]:
    """Run assurance flow using uploaded file id (auto resolves previous week file)."""
    return analyze_uploaded_wsr(current_file_id)
