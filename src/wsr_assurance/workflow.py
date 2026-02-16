"""LangChain + LangGraph + Pinecone WSR analysis workflow.

This module implements a production-oriented agent flow for Weekly Status Reports:
- Multi-format extraction: PDF, PPTX, DOCX, TXT
- Data cleaning and chunking
- Metadata-rich vector upsert and retrieval in Pinecone
- Structured risk/dependency/gap/recommendation analysis
- Week-over-week progress comparison (current vs previous file)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from docx import Document as DocxDocument
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph
from pinecone import Pinecone, ServerlessSpec
from pypdf import PdfReader
from pptx import Presentation


NOISE_PATTERNS = [
    r"^page\s+\d+\s+of\s+\d+$",
    r"^confidential$",
    r"^internal use only$",
    r"^weekly status report$",
]

SECTION_HINTS = {
    "risks": ["risks", "risk", "issues", "concerns"],
    "dependencies": ["dependencies", "dependency", "external dependency"],
}


@dataclass
class WSRMetadata:
    """Metadata provided by the UI or upstream caller."""

    account: str
    project_name: str
    week_date: str

    def to_filter(self) -> Dict[str, Any]:
        """Metadata filter used for vector retrieval scope."""
        return {
            "account": self.account,
            "project_name": self.project_name,
        }


class WorkflowState(TypedDict, total=False):
    current_file_path: str
    previous_file_path: str
    metadata: Dict[str, str]
    current_raw_text: str
    previous_raw_text: str
    current_cleaned_text: str
    previous_cleaned_text: str
    current_chunks: List[Document]
    previous_chunks: List[Document]
    current_doc_id: str
    previous_doc_id: str
    retrieved_history: List[Document]
    current_analysis: Dict[str, Any]
    previous_analysis: Dict[str, Any]
    progress_comparison: List[Dict[str, str]]
    final_report: Dict[str, Any]


# -----------------------------
# Extraction and cleaning
# -----------------------------


def extract_wsr_text_from_file(file_path: str) -> str:
    """Extract text from PDF, PPTX, DOCX, or TXT."""
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
    reader = PdfReader(file_path)
    pages: List[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"[PAGE {idx}]\n{text}")
    if not pages:
        raise ValueError("No extractable text in PDF. OCR is required for scanned files.")
    return "\n\n".join(pages)


def _extract_pptx(file_path: str) -> str:
    prs = Presentation(file_path)
    lines: List[str] = []
    for slide_idx, slide in enumerate(prs.slides, start=1):
        lines.append(f"[SLIDE {slide_idx}]")
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                lines.append(shape.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
            if getattr(shape, "has_chart", False):
                chart = shape.chart
                series_dump: List[str] = []
                for series in chart.series:
                    values = [str(v) for v in series.values]
                    series_dump.append(f"{series.name}: {', '.join(values)}")
                if series_dump:
                    lines.append("Chart -> " + " ; ".join(series_dump))
    text = "\n".join([ln for ln in lines if ln.strip()])
    if not text:
        raise ValueError("No extractable text in PPTX.")
    return text


def _extract_docx(file_path: str) -> str:
    doc = DocxDocument(file_path)
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    text = "\n".join(lines)
    if not text:
        raise ValueError("No extractable text in DOCX.")
    return text


def clean_wsr_text(raw_text: str) -> str:
    """Remove header/footer-like noise and normalize whitespace."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in normalized.split("\n") if ln.strip()]

    line_counts = Counter(lines)
    repeat_threshold = max(2, int(len(lines) * 0.25))

    filtered: List[str] = []
    for line in lines:
        low = line.lower()
        if any(re.match(pattern, low) for pattern in NOISE_PATTERNS):
            continue
        if line_counts[line] >= repeat_threshold and len(line) < 90:
            continue
        filtered.append(line)

    return "\n".join(filtered).strip()


def chunk_wsr_text(cleaned_text: str, metadata: WSRMetadata, doc_id: str) -> List[Document]:
    """Chunk cleaned text while attaching metadata for Pinecone filtering."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
    raw_chunks = splitter.split_text(cleaned_text)

    docs: List[Document] = []
    for idx, chunk in enumerate(raw_chunks):
        section = infer_section(chunk)
        docs.append(
            Document(
                page_content=chunk,
                metadata={
                    "doc_id": doc_id,
                    "chunk_id": f"{doc_id}-{idx}",
                    "chunk_index": idx,
                    "section": section,
                    "account": metadata.account,
                    "project_name": metadata.project_name,
                    "week_date": metadata.week_date,
                },
            )
        )
    return docs


def infer_section(text: str) -> str:
    """Infer a coarse section label for a chunk."""
    low = text.lower()
    for section, hints in SECTION_HINTS.items():
        if any(h in low for h in hints):
            return section
    return "general"


# -----------------------------
# Pinecone + LLM services
# -----------------------------


def _build_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model="text-embedding-3-small")


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def _get_vector_store(index_name: str | None = None) -> PineconeVectorStore:
    """Create Pinecone index if needed, then return LangChain vector store."""
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY is required.")

    index = index_name or os.environ.get("PINECONE_INDEX", "wsr-agent-index")
    cloud = os.environ.get("PINECONE_CLOUD", "aws")
    region = os.environ.get("PINECONE_REGION", "us-east-1")

    pc = Pinecone(api_key=pinecone_api_key)
    existing = [item.name for item in pc.list_indexes()]
    if index not in existing:
        pc.create_index(
            name=index,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )

    return PineconeVectorStore(index_name=index, embedding=_build_embeddings())


# -----------------------------
# Analysis helpers
# -----------------------------


def _extract_signal_lines(cleaned_text: str) -> Dict[str, List[Dict[str, str]]]:
    """Extract risk/dependency lines with explicit-section-first strategy."""
    lines = cleaned_text.splitlines()
    risks: List[Dict[str, str]] = []
    dependencies: List[Dict[str, str]] = []

    current_section = "general"
    for line in lines:
        normalized = line.lower().strip(" :")
        if normalized in SECTION_HINTS["risks"]:
            current_section = "risks"
            continue
        if normalized in SECTION_HINTS["dependencies"]:
            current_section = "dependencies"
            continue

        if current_section in {"risks", "dependencies"} and re.match(r"^[-*•]", line):
            item = {"description": re.sub(r"^[-*•]\s*", "", line).strip(), "source": "Explicit section"}
            if current_section == "risks":
                risks.append(item)
            else:
                dependencies.append(item)

    if risks or dependencies:
        return {"risks": risks[:20], "dependencies": dependencies[:20]}

    # Fallback for unstructured files.
    for line in lines:
        low = line.lower()
        if any(word in low for word in ["dependency", "pending", "awaiting", "vendor", "client"]):
            dependencies.append({"description": line, "source": "Keyword fallback"})
        elif any(word in low for word in ["risk", "issue", "blocked", "delay", "slippage", "defect"]):
            risks.append({"description": line, "source": "Keyword fallback"})

    return {"risks": risks[:20], "dependencies": dependencies[:20]}


def _detect_reporting_gaps(analysis: Dict[str, List[Dict[str, str]]]) -> List[str]:
    """Detect missing owner/date/mitigation cues in extracted items."""
    gaps: List[str] = []
    for label, items in [("risk", analysis["risks"]), ("dependency", analysis["dependencies"])]:
        for item in items:
            text = item["description"].lower()
            if "owner" not in text and "@" not in text:
                gaps.append(f"Missing owner in {label}: {item['description'][:100]}")
            if not re.search(r"\b\d{4}-\d{2}-\d{2}\b|\beta\b|\bdue\b|\btarget\b", text):
                gaps.append(f"Missing ETA/due date in {label}: {item['description'][:100]}")
            if not re.search(r"\bmitigation\b|\baction\b|\bplan\b", text):
                gaps.append(f"Missing mitigation/action in {label}: {item['description'][:100]}")

    unique: List[str] = []
    seen = set()
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            unique.append(gap)
    return unique[:12]


def _recommend_with_llm(
    current_analysis: Dict[str, List[Dict[str, str]]],
    retrieved_history: List[Document],
) -> List[Dict[str, str]]:
    """Generate recommendations grounded in extracted signals + retrieved history."""
    parser = JsonOutputParser()
    llm = _build_llm()

    history_text = "\n\n".join(
        f"- [{doc.metadata.get('week_date', 'N/A')}] {doc.page_content[:320]}"
        for doc in retrieved_history[:8]
    )

    messages = [
        SystemMessage(
            content=(
                "You are a delivery assurance analyst. Use only provided data. "
                "Return JSON array. Each item: for, signal, recommendation, rationale."
            )
        ),
        HumanMessage(
            content=(
                f"Current analysis:\n{json.dumps(current_analysis, indent=2)}\n\n"
                f"Historical context:\n{history_text}\n\n"
                "Create concise actionable recommendations."
            )
        ),
    ]

    output = llm.invoke(messages)
    parsed = parser.parse(output.content)

    if isinstance(parsed, list):
        return [
            {
                "for": str(item.get("for", "Risk")),
                "signal": str(item.get("signal", "N/A")),
                "recommendation": str(item.get("recommendation", "N/A")),
                "rationale": str(item.get("rationale", "N/A")),
            }
            for item in parsed
        ][:10]

    return []


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[a-zA-Z0-9_-]{3,}", text)}


def _compare_progress(
    current_analysis: Dict[str, Any],
    previous_analysis: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Track progress from previous week using deterministic token overlap."""
    current_items = [i["description"] for i in current_analysis["risks"] + current_analysis["dependencies"]]
    previous_items = [i["description"] for i in previous_analysis["risks"] + previous_analysis["dependencies"]]

    results: List[Dict[str, str]] = []
    matched_previous: set[str] = set()

    for current in current_items:
        cur_tokens = _tokenize(current)
        best_score = 0.0
        best_prev = ""
        for prev in previous_items:
            prev_tokens = _tokenize(prev)
            if not cur_tokens or not prev_tokens:
                continue
            score = len(cur_tokens & prev_tokens) / max(1, len(cur_tokens | prev_tokens))
            if score > best_score:
                best_score = score
                best_prev = prev

        if best_score >= 0.45:
            matched_previous.add(best_prev)
            status = "Existing (same signal)" if current == best_prev else "Existing (updated wording)"
            results.append({"current": current, "previous": best_prev, "status": status})
        else:
            results.append({"current": current, "previous": "N/A", "status": "New signal"})

    for prev in previous_items:
        if prev not in matched_previous:
            results.append({"current": "N/A", "previous": prev, "status": "No longer reported"})

    return results


# -----------------------------
# LangGraph nodes
# -----------------------------


def _preprocess_current(state: WorkflowState) -> WorkflowState:
    metadata = WSRMetadata(**state["metadata"])
    raw_text = extract_wsr_text_from_file(state["current_file_path"])
    cleaned = clean_wsr_text(raw_text)
    doc_id = f"current:{metadata.week_date}:{uuid.uuid4().hex[:8]}"
    chunks = chunk_wsr_text(cleaned, metadata, doc_id)

    state["current_raw_text"] = raw_text
    state["current_cleaned_text"] = cleaned
    state["current_chunks"] = chunks
    state["current_doc_id"] = doc_id
    return state


def _preprocess_previous(state: WorkflowState) -> WorkflowState:
    metadata = WSRMetadata(**state["metadata"])
    raw_text = extract_wsr_text_from_file(state["previous_file_path"])
    cleaned = clean_wsr_text(raw_text)
    doc_id = f"previous:{metadata.week_date}:{uuid.uuid4().hex[:8]}"
    chunks = chunk_wsr_text(cleaned, metadata, doc_id)

    state["previous_raw_text"] = raw_text
    state["previous_cleaned_text"] = cleaned
    state["previous_chunks"] = chunks
    state["previous_doc_id"] = doc_id
    return state


def _upsert_documents(state: WorkflowState) -> WorkflowState:
    store = _get_vector_store()
    store.add_documents(state["current_chunks"])
    store.add_documents(state["previous_chunks"])
    return state


def _retrieve_history(state: WorkflowState) -> WorkflowState:
    store = _get_vector_store()
    metadata = WSRMetadata(**state["metadata"])

    current_signals = _extract_signal_lines(state["current_cleaned_text"])
    query_text = "\n".join([i["description"] for i in current_signals["risks"] + current_signals["dependencies"]])
    if not query_text.strip():
        query_text = state["current_cleaned_text"][:1200]

    docs = store.similarity_search(
        query=query_text,
        k=8,
        filter=metadata.to_filter(),
    )

    # Remove chunks from current/previous doc ids to focus on older history.
    excluded = {state["current_doc_id"], state["previous_doc_id"]}
    state["retrieved_history"] = [d for d in docs if d.metadata.get("doc_id") not in excluded]
    return state


def _analyze_current(state: WorkflowState) -> WorkflowState:
    analysis = _extract_signal_lines(state["current_cleaned_text"])
    analysis["observation_gaps"] = _detect_reporting_gaps(analysis)
    analysis["recommendations"] = _recommend_with_llm(analysis, state.get("retrieved_history", []))
    state["current_analysis"] = analysis
    return state


def _analyze_previous(state: WorkflowState) -> WorkflowState:
    state["previous_analysis"] = _extract_signal_lines(state["previous_cleaned_text"])
    return state


def _compare_weeks(state: WorkflowState) -> WorkflowState:
    state["progress_comparison"] = _compare_progress(
        current_analysis=state["current_analysis"],
        previous_analysis=state["previous_analysis"],
    )
    return state


def _build_report(state: WorkflowState) -> WorkflowState:
    state["final_report"] = {
        "metadata": state["metadata"],
        "current_week_analysis": state["current_analysis"],
        "previous_week_analysis": state["previous_analysis"],
        "progress_comparison": state["progress_comparison"],
        "retrieved_history_count": len(state.get("retrieved_history", [])),
    }
    return state


# -----------------------------
# Public workflow entrypoints
# -----------------------------


def build_workflow():
    """Build LangGraph workflow for current-vs-previous WSR analysis."""
    graph = StateGraph(WorkflowState)
    graph.add_node("preprocess_current", _preprocess_current)
    graph.add_node("preprocess_previous", _preprocess_previous)
    graph.add_node("upsert_documents", _upsert_documents)
    graph.add_node("retrieve_history", _retrieve_history)
    graph.add_node("analyze_current", _analyze_current)
    graph.add_node("analyze_previous", _analyze_previous)
    graph.add_node("compare_weeks", _compare_weeks)
    graph.add_node("build_report", _build_report)

    graph.set_entry_point("preprocess_current")
    graph.add_edge("preprocess_current", "preprocess_previous")
    graph.add_edge("preprocess_previous", "upsert_documents")
    graph.add_edge("upsert_documents", "retrieve_history")
    graph.add_edge("retrieve_history", "analyze_current")
    graph.add_edge("analyze_current", "analyze_previous")
    graph.add_edge("analyze_previous", "compare_weeks")
    graph.add_edge("compare_weeks", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()


def analyze_wsr_file(
    current_file_path: str,
    previous_file_path: str,
    account: str,
    project_name: str,
    week_date: str,
) -> Dict[str, Any]:
    """Analyze current WSR and track progress from previous week file."""
    app = build_workflow()
    result = app.invoke(
        {
            "current_file_path": current_file_path,
            "previous_file_path": previous_file_path,
            "metadata": {
                "account": account,
                "project_name": project_name,
                "week_date": week_date,
            },
        }
    )
    return result["final_report"]


def ingest_wsr_file_from_ui(file_path: str, account: str, project_name: str, week_date: str) -> int:
    """Ingest one WSR file into Pinecone with metadata."""
    metadata = WSRMetadata(account=account, project_name=project_name, week_date=week_date)
    raw_text = extract_wsr_text_from_file(file_path)
    cleaned = clean_wsr_text(raw_text)
    doc_id = f"ingest:{week_date}:{uuid.uuid4().hex[:8]}"
    chunks = chunk_wsr_text(cleaned, metadata, doc_id)
    store = _get_vector_store()
    store.add_documents(chunks)
    return len(chunks)


def analyze_wsr(current_wsr_text: str, account: str, project_name: str, week_date: str) -> Dict[str, Any]:
    """Compatibility API. Prefer file-based analyze_wsr_file for production use."""
    metadata = {
        "account": account,
        "project_name": project_name,
        "week_date": week_date,
    }
    basic = _extract_signal_lines(clean_wsr_text(current_wsr_text))
    basic["observation_gaps"] = _detect_reporting_gaps(basic)
    return {"metadata": metadata, "current_week_analysis": basic, "message": "Use analyze_wsr_file for full LangGraph flow."}


def ingest_wsr_from_ui(current_wsr_text: str, account: str, project_name: str, week_date: str) -> int:
    """Compatibility API for text ingestion path."""
    metadata = WSRMetadata(account=account, project_name=project_name, week_date=week_date)
    doc_id = f"ingest-text:{week_date}:{uuid.uuid4().hex[:8]}"
    chunks = chunk_wsr_text(clean_wsr_text(current_wsr_text), metadata, doc_id)
    store = _get_vector_store()
    store.add_documents(chunks)
    return len(chunks)


def main() -> None:
    """CLI helper for manual run."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze current WSR and compare with previous week")
    parser.add_argument("current_file_path")
    parser.add_argument("previous_file_path")
    parser.add_argument("--account", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--week-date", required=True)
    args = parser.parse_args()

    report = analyze_wsr_file(
        current_file_path=args.current_file_path,
        previous_file_path=args.previous_file_path,
        account=args.account,
        project_name=args.project_name,
        week_date=args.week_date,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
