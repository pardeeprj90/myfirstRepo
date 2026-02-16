"""Backward-compatible helpers for PDF-only calls.

New development should use ``src.wsr_assurance.workflow``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .workflow import analyze_wsr_file


@dataclass
class PDFAnalysisResult:
    file_name: str
    page_count: int
    cleaned_text: str
    extracted_risks: List[str]
    extracted_dependencies: List[str]
    summary: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "file_name": self.file_name,
            "page_count": self.page_count,
            "cleaned_text": self.cleaned_text,
            "extracted_risks": self.extracted_risks,
            "extracted_dependencies": self.extracted_dependencies,
            "summary": self.summary,
        }


def analyze_uploaded_pdf(file_path: str) -> Dict[str, object]:
    """Compatibility wrapper mapping old API to the new workflow."""
    return analyze_wsr_file(file_path=file_path, account="N/A", project_name="N/A", week_date="N/A")
