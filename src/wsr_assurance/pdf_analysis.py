"""Backward compatibility wrappers for older PDF-only function names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .workflow import clean_wsr_text, extract_wsr_text_from_file


@dataclass
class PDFAnalysisResult:
    """Legacy response shape retained for compatibility."""

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
    """Extract and clean PDF text for legacy callers.

    Full production analysis is available via workflow.analyze_wsr_file().
    """
    raw = extract_wsr_text_from_file(file_path)
    cleaned = clean_wsr_text(raw)
    return {
        "file_name": file_path,
        "cleaned_text": cleaned,
        "message": "Use analyze_wsr_file(current_file_path, previous_file_path, ...) for LangGraph + Pinecone analysis.",
    }
