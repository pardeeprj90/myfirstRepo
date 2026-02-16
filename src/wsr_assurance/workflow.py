"""Workflow facade for simple PDF upload analysis.

This module keeps API names easy for existing callers while implementing
one clear flow: upload PDF -> analyze PDF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from .pdf_analysis import PDFAnalysisResult, analyze_uploaded_pdf


@dataclass
class WSRMetadata:
    """Metadata accepted for compatibility with earlier APIs."""

    account: str
    project_name: str
    week_date: str


def analyze_wsr_file(file_path: str, account: str, project_name: str, week_date: str) -> Dict[str, Any]:
    """Analyze an uploaded WSR PDF and return structured output.

    Metadata is accepted for compatibility and traceability.
    """
    result = analyze_uploaded_pdf(file_path)
    payload = result.to_dict()
    payload["metadata"] = {
        "account": account,
        "project_name": project_name,
        "week_date": week_date,
    }
    return payload


def analyze_wsr(current_wsr_text: str, account: str, project_name: str, week_date: str) -> Dict[str, Any]:
    """Legacy method kept for backward compatibility.

    In this simplified requirement, only file uploads are supported, so this
    method returns a clear message for callers to switch to file-based flow.
    """
    return {
        "metadata": {
            "account": account,
            "project_name": project_name,
            "week_date": week_date,
        },
        "message": "Please use analyze_wsr_file(file_path, ...) for PDF upload analysis.",
    }


def ingest_wsr_from_ui(current_wsr_text: str, account: str, project_name: str, week_date: str) -> int:
    """Legacy compatibility method.

    Vector ingestion is intentionally not part of the simplified PDF-only scope.
    """
    _ = (current_wsr_text, account, project_name, week_date)
    return 0


def ingest_wsr_file_from_ui(file_path: str, account: str, project_name: str, week_date: str) -> int:
    """Compatibility method that validates file readability and returns success marker."""
    _ = analyze_wsr_file(file_path, account, project_name, week_date)
    return 1


def main() -> None:
    """CLI helper for local manual testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze uploaded WSR PDF")
    parser.add_argument("file_path", help="Path to uploaded WSR PDF file")
    parser.add_argument("--account", default="N/A")
    parser.add_argument("--project-name", default="N/A")
    parser.add_argument("--week-date", default="N/A")
    args = parser.parse_args()

    result: PDFAnalysisResult | Dict[str, Any]
    result = analyze_wsr_file(args.file_path, args.account, args.project_name, args.week_date)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
