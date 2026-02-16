"""Production-oriented WSR analysis workflow.

This module implements the main flow requested for Delivery Assurance:
1. Accept uploaded WSR files (PDF/PPTX/DOCX/TXT).
2. Extract and clean messy content.
3. Chunk and vectorize with metadata.
4. Persist to a local vector database.
5. Analyze risks, dependencies, reporting gaps, and recommendations.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple



# -----------------------------
# Data contracts
# -----------------------------


@dataclass
class WSRMetadata:
    """Metadata provided by UI or ingestion APIs."""

    account: str
    project_name: str
    week_date: str


@dataclass
class ChunkRecord:
    """Persisted vector store record for one text chunk."""

    id: str
    doc_id: str
    chunk_index: int
    text: str
    section: str
    vector: List[float]
    metadata: Dict[str, str]


@dataclass
class SignalItem:
    """Detected risk/dependency item from current WSR."""

    item_type: str
    description: str
    source: str


RISK_KEYWORDS = {
    "risk",
    "issue",
    "blocked",
    "delay",
    "slippage",
    "escalation",
    "defect",
    "quality",
    "rework",
}

DEPENDENCY_KEYWORDS = {
    "dependency",
    "dependent",
    "pending",
    "awaiting",
    "approval",
    "sign-off",
    "external",
    "vendor",
    "client",
}

HEADING_MAP = {
    "risks": "risks",
    "risk": "risks",
    "issues": "risks",
    "dependencies": "dependencies",
    "dependency": "dependencies",
    "summary": "summary",
    "highlights": "summary",
    "milestones": "milestones",
    "progress": "milestones",
    "actions": "actions",
}

NOISE_PATTERNS = [
    r"^page\s+\d+\s+of\s+\d+$",
    r"^confidential$",
    r"^internal use only$",
    r"^weekly status report$",
]

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")


# -----------------------------
# Extraction
# -----------------------------


def extract_wsr_text_from_file(file_path: str) -> str:
    """Extract text from supported file types: PDF, PPTX, DOCX, TXT."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    if suffix == ".pptx":
        return _extract_pptx(file_path)
    if suffix == ".docx":
        return _extract_docx(file_path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError("Unsupported file type. Allowed: .pdf, .pptx, .docx, .txt")


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages: List[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"[PAGE {index}]\n{text}")
    if not pages:
        raise ValueError("No extractable text found in PDF. OCR is required for scanned files.")
    return "\n\n".join(pages)


def _extract_pptx(file_path: str) -> str:
    from pptx import Presentation

    prs = Presentation(file_path)
    lines: List[str] = []
    for slide_num, slide in enumerate(prs.slides, start=1):
        lines.append(f"[SLIDE {slide_num}]")
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                lines.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
            if getattr(shape, "has_chart", False):
                chart = shape.chart
                try:
                    series_dump: List[str] = []
                    for series in chart.series:
                        points = [str(v) for v in series.values]
                        series_dump.append(f"{series.name}: {', '.join(points)}")
                    if series_dump:
                        lines.append("Chart -> " + " ; ".join(series_dump))
                except Exception:
                    # Chart extraction support varies by deck/chart type.
                    pass
    text = "\n".join([ln for ln in lines if ln.strip()])
    if not text.strip():
        raise ValueError("No extractable text found in PPTX.")
    return text


def _extract_docx(file_path: str) -> str:
    from docx import Document

    doc = Document(file_path)
    lines: List[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            row_values = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_values:
                lines.append(" | ".join(row_values))
    text = "\n".join(lines)
    if not text.strip():
        raise ValueError("No extractable text found in DOCX.")
    return text


# -----------------------------
# Cleaning and chunking
# -----------------------------


def clean_wsr_text(raw_text: str) -> str:
    """Normalize whitespace and remove common header/footer noise."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n") if ln.strip()]

    # Drop repetitive header/footer lines by frequency.
    line_counts = Counter(lines)
    threshold = max(2, int(len(lines) * 0.25))

    cleaned: List[str] = []
    for line in lines:
        lower = line.lower()
        if any(re.match(p, lower) for p in NOISE_PATTERNS):
            continue
        if line_counts[line] >= threshold and len(line) < 80:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def sectionalize_text(cleaned_text: str) -> List[Tuple[str, str]]:
    """Split document into coarse sections based on heading-like lines."""
    current_section = "general"
    sections: List[Tuple[str, List[str]]] = [(current_section, [])]

    for line in cleaned_text.splitlines():
        canonical = line.lower().strip(" :")
        if canonical in HEADING_MAP:
            current_section = HEADING_MAP[canonical]
            sections.append((current_section, []))
            continue
        sections[-1][1].append(line)

    return [(name, "\n".join(lines).strip()) for name, lines in sections if "\n".join(lines).strip()]


def chunk_text(cleaned_text: str, chunk_size: int = 900, overlap: int = 120) -> List[Dict[str, str]]:
    """Create metadata-friendly chunks using section boundaries + char windows."""
    chunks: List[Dict[str, str]] = []
    for section, section_text in sectionalize_text(cleaned_text):
        start = 0
        while start < len(section_text):
            end = min(len(section_text), start + chunk_size)
            chunk_value = section_text[start:end].strip()
            if chunk_value:
                chunks.append({"section": section, "text": chunk_value})
            if end == len(section_text):
                break
            start = max(0, end - overlap)
    return chunks


# -----------------------------
# Vector storage
# -----------------------------


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def vectorize_text(text: str, dim: int = 256) -> List[float]:
    """Convert text into a deterministic hashed vector for similarity search."""
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        index = hash(token) % dim
        vec[index] += 1.0

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class LocalVectorDB:
    """Lightweight JSON-backed vector database for WSR chunks.

    This keeps setup simple while preserving production-friendly metadata filters.
    """

    def __init__(self, path: str = ".wsr_vector_db.json"):
        self.path = Path(path)
        self.records: List[ChunkRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.records = []
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.records = [ChunkRecord(**item) for item in data]

    def _save(self) -> None:
        data = [asdict(record) for record in self.records]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_document(self, doc_id: str, chunks: List[Dict[str, str]], metadata: WSRMetadata) -> int:
        base_meta = {
            "account": metadata.account,
            "project_name": metadata.project_name,
            "week_date": metadata.week_date,
            "ingested_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        for index, chunk in enumerate(chunks):
            text = chunk["text"]
            record = ChunkRecord(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                chunk_index=index,
                text=text,
                section=chunk["section"],
                vector=vectorize_text(text),
                metadata=base_meta,
            )
            self.records.append(record)
        self._save()
        return len(chunks)

    def query(
        self,
        query_text: str,
        metadata: WSRMetadata,
        exclude_doc_id: str,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        query_vec = vectorize_text(query_text)
        candidates: List[Tuple[float, ChunkRecord]] = []
        for record in self.records:
            if record.doc_id == exclude_doc_id:
                continue
            if record.metadata.get("account") != metadata.account:
                continue
            if record.metadata.get("project_name") != metadata.project_name:
                continue
            score = cosine_similarity(query_vec, record.vector)
            if score > 0:
                candidates.append((score, record))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "score": round(score, 4),
                "chunk_text": rec.text,
                "section": rec.section,
                "week_date": rec.metadata.get("week_date", ""),
                "doc_id": rec.doc_id,
            }
            for score, rec in candidates[:top_k]
        ]


# -----------------------------
# Analysis logic
# -----------------------------


def _extract_bullets(text: str) -> List[str]:
    bullets: List[str] = []
    for line in text.splitlines():
        if re.match(r"^[-*•]\s+", line):
            bullets.append(re.sub(r"^[-*•]\s+", "", line).strip())
    return bullets


def detect_signals(cleaned_text: str) -> List[SignalItem]:
    """Detect risks/dependencies from explicit sections or keyword signals."""
    sections = dict(sectionalize_text(cleaned_text))
    items: List[SignalItem] = []

    risk_text = sections.get("risks", "")
    dep_text = sections.get("dependencies", "")

    if risk_text or dep_text:
        for line in _extract_bullets(risk_text):
            items.append(SignalItem(item_type="Risk", description=line, source="Explicit section"))
        for line in _extract_bullets(dep_text):
            items.append(SignalItem(item_type="Dependency", description=line, source="Explicit section"))

    if not items:
        for line in cleaned_text.splitlines():
            lower = line.lower()
            has_risk = any(word in lower for word in RISK_KEYWORDS)
            has_dep = any(word in lower for word in DEPENDENCY_KEYWORDS)
            if has_risk or has_dep:
                item_type = "Dependency" if has_dep and not has_risk else "Risk"
                items.append(SignalItem(item_type=item_type, description=line, source="Keyword fallback"))

    return items[:20]


def detect_reporting_gaps(items: List[SignalItem]) -> List[str]:
    """Identify common WSR reporting quality gaps from extracted signal lines."""
    gaps: List[str] = []
    for item in items:
        text = item.description.lower()
        if not re.search(r"\bowner\b|\b@[a-zA-Z0-9_.-]+\b", text):
            gaps.append(f"Missing owner in {item.item_type.lower()}: {item.description[:120]}")
        if not re.search(r"\b\d{4}-\d{2}-\d{2}\b|\beta\b|\bdue\b|\btarget\b", text):
            gaps.append(f"Missing due date/ETA in {item.item_type.lower()}: {item.description[:120]}")
        if not re.search(r"\bmitigation\b|\baction\b|\bplan\b", text):
            gaps.append(f"Missing mitigation/action in {item.item_type.lower()}: {item.description[:120]}")

    # Keep response concise and deterministic.
    unique_gaps = []
    seen = set()
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            unique_gaps.append(gap)
    return unique_gaps[:10]


def build_recommendations(items: List[SignalItem], context_chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Generate deterministic recommendations using current signals + historical context."""
    recommendations: List[Dict[str, str]] = []
    context_preview = " ".join(ch["chunk_text"][:120] for ch in context_chunks[:3]).lower()

    for item in items[:8]:
        desc = item.description
        if item.item_type == "Dependency":
            action = "Create a dependency tracker with owner, ETA, and escalation path."
        else:
            action = "Define mitigation owner, due date, and weekly control checkpoint."

        if "vendor" in desc.lower() or "vendor" in context_preview:
            action = "Escalate vendor dependency in governance call and lock recovery milestones."
        if "uat" in desc.lower() or "test" in desc.lower():
            action = "Introduce daily test environment health checks and defect triage."

        recommendations.append(
            {
                "for": item.item_type,
                "signal": desc,
                "recommendation": action,
                "basis": item.source,
            }
        )

    return recommendations


def _format_signal_rows(items: List[SignalItem]) -> List[Dict[str, str]]:
    return [{"type": i.item_type, "description": i.description, "source": i.source} for i in items]


# -----------------------------
# Public APIs
# -----------------------------


def ingest_wsr_file_from_ui(file_path: str, account: str, project_name: str, week_date: str) -> int:
    """Ingest uploaded WSR into local vector DB with chunk metadata."""
    metadata = WSRMetadata(account=account.strip(), project_name=project_name.strip(), week_date=week_date.strip())
    raw_text = extract_wsr_text_from_file(file_path)
    cleaned_text = clean_wsr_text(raw_text)
    chunks = chunk_text(cleaned_text)

    vector_db = LocalVectorDB()
    doc_id = f"{Path(file_path).name}:{week_date}:{uuid.uuid4().hex[:8]}"
    return vector_db.add_document(doc_id=doc_id, chunks=chunks, metadata=metadata)


def ingest_wsr_from_ui(current_wsr_text: str, account: str, project_name: str, week_date: str) -> int:
    """Backward-compatible text ingestion path using same chunk/vector pipeline."""
    metadata = WSRMetadata(account=account.strip(), project_name=project_name.strip(), week_date=week_date.strip())
    cleaned_text = clean_wsr_text(current_wsr_text)
    chunks = chunk_text(cleaned_text)

    vector_db = LocalVectorDB()
    doc_id = f"text:{week_date}:{uuid.uuid4().hex[:8]}"
    return vector_db.add_document(doc_id=doc_id, chunks=chunks, metadata=metadata)


def analyze_wsr_file(file_path: str, account: str, project_name: str, week_date: str) -> Dict[str, Any]:
    """Analyze uploaded WSR file and return systematic DA report."""
    metadata = WSRMetadata(account=account.strip(), project_name=project_name.strip(), week_date=week_date.strip())

    raw_text = extract_wsr_text_from_file(file_path)
    cleaned_text = clean_wsr_text(raw_text)
    chunks = chunk_text(cleaned_text)

    vector_db = LocalVectorDB()
    doc_id = f"{Path(file_path).name}:{week_date}:{uuid.uuid4().hex[:8]}"
    ingested_chunks = vector_db.add_document(doc_id=doc_id, chunks=chunks, metadata=metadata)

    signal_items = detect_signals(cleaned_text)
    query_text = "\n".join(item.description for item in signal_items) if signal_items else cleaned_text[:1500]
    context = vector_db.query(query_text=query_text, metadata=metadata, exclude_doc_id=doc_id, top_k=8)

    risks = [item for item in signal_items if item.item_type == "Risk"]
    dependencies = [item for item in signal_items if item.item_type == "Dependency"]
    gaps = detect_reporting_gaps(signal_items)
    recommendations = build_recommendations(signal_items, context)

    return {
        "metadata": asdict(metadata),
        "file_name": Path(file_path).name,
        "doc_id": doc_id,
        "ingested_chunks": ingested_chunks,
        "analysis": {
            "risks": _format_signal_rows(risks),
            "dependencies": _format_signal_rows(dependencies),
            "observation_gaps": gaps,
            "recommendations": recommendations,
        },
        "retrieved_context": context,
    }


def analyze_wsr(current_wsr_text: str, account: str, project_name: str, week_date: str) -> Dict[str, Any]:
    """Analyze raw WSR text with same pipeline used for uploaded files."""
    metadata = WSRMetadata(account=account.strip(), project_name=project_name.strip(), week_date=week_date.strip())

    cleaned_text = clean_wsr_text(current_wsr_text)
    chunks = chunk_text(cleaned_text)

    vector_db = LocalVectorDB()
    doc_id = f"text:{week_date}:{uuid.uuid4().hex[:8]}"
    ingested_chunks = vector_db.add_document(doc_id=doc_id, chunks=chunks, metadata=metadata)

    signal_items = detect_signals(cleaned_text)
    query_text = "\n".join(item.description for item in signal_items) if signal_items else cleaned_text[:1500]
    context = vector_db.query(query_text=query_text, metadata=metadata, exclude_doc_id=doc_id, top_k=8)

    risks = [item for item in signal_items if item.item_type == "Risk"]
    dependencies = [item for item in signal_items if item.item_type == "Dependency"]

    return {
        "metadata": asdict(metadata),
        "doc_id": doc_id,
        "ingested_chunks": ingested_chunks,
        "analysis": {
            "risks": _format_signal_rows(risks),
            "dependencies": _format_signal_rows(dependencies),
            "observation_gaps": detect_reporting_gaps(signal_items),
            "recommendations": build_recommendations(signal_items, context),
        },
        "retrieved_context": context,
    }


def main() -> None:
    """CLI entrypoint for manual testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze uploaded WSR file (.pdf/.pptx/.docx/.txt)")
    parser.add_argument("file_path", help="Path to uploaded WSR file")
    parser.add_argument("--account", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--week-date", required=True)
    args = parser.parse_args()

    result = analyze_wsr_file(
        file_path=args.file_path,
        account=args.account,
        project_name=args.project_name,
        week_date=args.week_date,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
