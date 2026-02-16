"""Simple, production-ready PDF analysis pipeline for Weekly Status Reports (WSR).

This module intentionally keeps the workflow small and readable:
1. Read uploaded PDF.
2. Clean and normalize extracted text.
3. Detect risk/dependency signals from content.
4. Generate a concise analysis response.

Use this module when the user journey is: "upload PDF -> get analysis".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from pypdf import PdfReader


RISK_KEYWORDS = (
    "risk",
    "issue",
    "blocked",
    "delay",
    "dependency",
    "pending",
    "slippage",
    "escalation",
)


@dataclass
class PDFAnalysisResult:
    """Structured response returned by the PDF analysis service."""

    file_name: str
    page_count: int
    cleaned_text: str
    extracted_risks: List[str]
    extracted_dependencies: List[str]
    summary: List[str]

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "file_name": self.file_name,
            "page_count": self.page_count,
            "cleaned_text": self.cleaned_text,
            "extracted_risks": self.extracted_risks,
            "extracted_dependencies": self.extracted_dependencies,
            "summary": self.summary,
        }


def extract_pdf_text(file_path: str) -> str:
    """Extract text from each PDF page.

    Raises:
        ValueError: if file is not a PDF or contains no extractable text.
    """
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported in this simplified flow.")

    reader = PdfReader(str(path))
    pages: List[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            pages.append(f"[PAGE {page_number}]\n{page_text}")

    if not pages:
        raise ValueError("No extractable text found in PDF. OCR is required for scanned files.")

    return "\n\n".join(pages)


def clean_wsr_text(raw_text: str) -> str:
    """Normalize whitespace and remove obvious non-content noise lines."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in normalized.split("\n"):
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue
        if re.match(r"^(page\s+\d+\s+of\s+\d+)$", compact, flags=re.IGNORECASE):
            continue
        if re.match(r"^(confidential|internal use only)$", compact, flags=re.IGNORECASE):
            continue
        lines.append(compact)
    return "\n".join(lines)


def _extract_bullets(section_text: str) -> List[str]:
    """Extract bullet-like lines from a text section."""
    bullets = []
    for line in section_text.splitlines():
        if re.match(r"^[-*•]\s+", line):
            bullets.append(re.sub(r"^[-*•]\s+", "", line).strip())
    return bullets


def _get_section(text: str, heading_names: List[str]) -> str:
    """Return section content for a given heading list.

    The section ends at the next heading-style line.
    """
    lines = text.splitlines()
    start_index = -1
    for i, line in enumerate(lines):
        low = line.lower().strip(" :")
        if low in heading_names:
            start_index = i + 1
            break

    if start_index == -1:
        return ""

    section_lines: List[str] = []
    for line in lines[start_index:]:
        if re.match(r"^[A-Za-z][A-Za-z\s/&-]{1,40}:?$", line):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip()


def extract_risks_and_dependencies(cleaned_text: str) -> tuple[List[str], List[str]]:
    """Extract risk/dependency lines using section-first logic with keyword fallback."""
    risk_section = _get_section(cleaned_text, ["risks", "issues", "risk & issues"])
    dep_section = _get_section(cleaned_text, ["dependencies", "external dependencies"])

    risks = _extract_bullets(risk_section)
    dependencies = _extract_bullets(dep_section)

    # Fallback: no explicit sections found, so scan content lines for signal keywords.
    if not risks and not dependencies:
        for line in cleaned_text.splitlines():
            low = line.lower()
            if any(k in low for k in RISK_KEYWORDS):
                if "depend" in low:
                    dependencies.append(line)
                else:
                    risks.append(line)

    return risks[:10], dependencies[:10]


def build_summary(risks: List[str], dependencies: List[str], cleaned_text: str) -> List[str]:
    """Build a small deterministic summary for UI display."""
    summary: List[str] = []
    summary.append(f"Detected {len(risks)} risk signal(s) in the uploaded WSR.")
    summary.append(f"Detected {len(dependencies)} dependency signal(s) in the uploaded WSR.")

    if risks:
        summary.append(f"Top risk: {risks[0]}")
    if dependencies:
        summary.append(f"Top dependency: {dependencies[0]}")

    summary.append(f"Analyzed {len(cleaned_text.splitlines())} cleaned line(s) from the PDF content.")
    return summary


def analyze_uploaded_pdf(file_path: str) -> PDFAnalysisResult:
    """End-to-end function used by API/UI after user uploads a PDF."""
    raw_text = extract_pdf_text(file_path)
    cleaned_text = clean_wsr_text(raw_text)
    risks, dependencies = extract_risks_and_dependencies(cleaned_text)
    summary = build_summary(risks, dependencies, cleaned_text)

    reader = PdfReader(file_path)
    return PDFAnalysisResult(
        file_name=Path(file_path).name,
        page_count=len(reader.pages),
        cleaned_text=cleaned_text,
        extracted_risks=risks,
        extracted_dependencies=dependencies,
        summary=summary,
    )
