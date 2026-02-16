from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langgraph.graph import END, StateGraph


class WorkflowState(TypedDict, total=False):
    current_wsr: str
    metadata: Dict[str, str]
    cleaned_wsr: str
    extracted_risks: List[str]
    extracted_dependencies: List[str]
    retrieved_chunks: List[Dict[str, Any]]
    recommendations: List[Dict[str, str]]
    final_report: Dict[str, Any]


@dataclass
class WSRMetadata:
    account: str
    project_name: str
    week_date: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "account": self.account.strip(),
            "project_name": self.project_name.strip(),
            "week_date": self.week_date.strip(),
        }


def extract_wsr_text_from_file(file_path: str) -> str:
    """
    Extract text from uploaded WSR file.

    Supported:
    - PDF: page text + table text (if pdfplumber available)
    - PPTX: slide text + tables + chart series/categories
    """

    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return _extract_from_pdf(file_path)
    if suffix == ".pptx":
        return _extract_from_pptx(file_path)

    raise ValueError(f"Unsupported file type: {suffix}. Expected .pdf or .pptx")


def _extract_from_pdf(file_path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF extraction. Install dependencies.") from exc

    blocks: List[str] = []
    reader = PdfReader(file_path)

    for idx, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            blocks.append(f"[PDF_PAGE_{idx}]\n{page_text.strip()}")

    # Optional table extraction for better risk/dependency recovery from tabular WSRs.
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(file_path) as pdf:
            for p_idx, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                for t_idx, table in enumerate(tables, start=1):
                    table_lines: List[str] = []
                    for row in table or []:
                        cells = [str(c).strip() if c is not None else "" for c in row]
                        if any(cells):
                            table_lines.append(" | ".join(cells))
                    if table_lines:
                        blocks.append(
                            f"[PDF_TABLE_{p_idx}_{t_idx}]\n" + "\n".join(table_lines)
                        )
    except ImportError:
        # Graceful fallback when pdfplumber is unavailable.
        pass

    extracted = "\n\n".join(blocks).strip()
    if not extracted:
        raise ValueError("No extractable text found in PDF. If scan-based, run OCR before ingestion.")

    return extracted


def _extract_from_pptx(file_path: str) -> str:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise RuntimeError("python-pptx is required for PPTX extraction. Install dependencies.") from exc

    prs = Presentation(file_path)
    blocks: List[str] = []

    for s_idx, slide in enumerate(prs.slides, start=1):
        slide_blocks: List[str] = []

        for shape in slide.shapes:
            # Text boxes/placeholders
            if hasattr(shape, "has_text_frame") and shape.has_text_frame and shape.text:
                txt = shape.text.strip()
                if txt:
                    slide_blocks.append(txt)

            # Tables
            if hasattr(shape, "has_table") and shape.has_table:
                rows: List[str] = []
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    slide_blocks.append("[TABLE]\n" + "\n".join(rows))

            # Charts (series + categories)
            if hasattr(shape, "has_chart") and shape.has_chart:
                chart = shape.chart
                chart_lines: List[str] = []

                categories = []
                if chart.plots and chart.plots[0].categories:
                    categories = [str(c.label) for c in chart.plots[0].categories]
                    chart_lines.append("Categories: " + ", ".join(categories))

                for series in chart.series:
                    points = []
                    for pt in series.values:
                        try:
                            points.append(str(pt))
                        except Exception:
                            points.append("")
                    chart_lines.append(f"Series {series.name}: " + ", ".join(points))

                if chart_lines:
                    slide_blocks.append("[CHART]\n" + "\n".join(chart_lines))

        if slide_blocks:
            blocks.append(f"[SLIDE_{s_idx}]\n" + "\n".join(slide_blocks))

    extracted = "\n\n".join(blocks).strip()
    if not extracted:
        raise ValueError("No extractable text found in PPTX.")

    return extracted


@dataclass
class WSRVectorStoreManager:
    """Persistent vector store for WSR chunks with metadata-aware retrieval."""

    index_path: str = ".wsr_vector_db"
    embedding_model: str = "text-embedding-3-small"

    def __post_init__(self) -> None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required.")

        self.embeddings = OpenAIEmbeddings(model=self.embedding_model)
        self.index_dir = Path(self.index_path)

        if self.index_dir.exists() and (self.index_dir / "index.faiss").exists():
            self.vector_store = FAISS.load_local(
                self.index_path,
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
            self.vector_store = FAISS.from_texts(
                ["bootstrap"],
                self.embeddings,
                metadatas=[
                    {
                        "doc_type": "bootstrap",
                        "account": "system",
                        "project_name": "system",
                        "week_date": "1970-01-01",
                        "chunk_id": "bootstrap-0",
                    }
                ],
            )
            self._save()

    def _save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store.save_local(self.index_path)

    @staticmethod
    def clean_wsr_text(raw_text: str) -> str:
        """Removes noisy headers/footers/extra spaces for higher-quality chunking and retrieval."""

        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.strip() for ln in text.split("\n")]

        cleaned: List[str] = []
        for line in lines:
            if not line:
                cleaned.append("")
                continue
            if re.match(r"^page\s+\d+\s+of\s+\d+$", line, flags=re.IGNORECASE):
                continue
            if re.match(r"^(confidential|internal use only)$", line, flags=re.IGNORECASE):
                continue
            if re.match(r"^generated on\s*:\s*", line, flags=re.IGNORECASE):
                continue
            if re.match(r"^\[pdf_page_\d+\]$", line, flags=re.IGNORECASE):
                continue
            cleaned.append(re.sub(r"\s+", " ", line))

        result = "\n".join(cleaned)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    @staticmethod
    def _sectionalize_wsr(clean_text: str) -> List[Dict[str, str]]:
        """Keeps semantic chunks around key sections before text splitting."""

        section_patterns = [
            ("risks", r"\brisks?\b|\bissues?\b|\bconcerns?\b"),
            ("dependencies", r"\bdependenc(?:y|ies)\b|\bexternal blockers?\b|\bassumptions?\b"),
            ("highlights", r"\b(highlights?|achievements?|accomplishments?)\b"),
            ("blockers", r"\bblockers?\b"),
            ("tables", r"\[table\]|\bmatrix\b|\bstatus table\b"),
            ("charts", r"\[chart\]|\btrend\b|\bburn\s*down\b"),
        ]

        lines = clean_text.splitlines()
        sections: List[Dict[str, str]] = []
        current_name = "general"
        current_lines: List[str] = []

        for line in lines:
            lower = line.lower().strip(" :-")
            matched = None
            for name, pattern in section_patterns:
                if re.search(pattern, lower):
                    matched = name
                    break

            if matched and (line.endswith(":") or len(line.split()) <= 5 or line.startswith("[")):
                if current_lines:
                    sections.append({"section": current_name, "text": "\n".join(current_lines).strip()})
                current_name = matched
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sections.append({"section": current_name, "text": "\n".join(current_lines).strip()})

        return [s for s in sections if s["text"]]

    def _build_documents(self, wsr_text: str, metadata: WSRMetadata) -> List[Document]:
        cleaned = self.clean_wsr_text(wsr_text)
        sections = self._sectionalize_wsr(cleaned)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=700,
            chunk_overlap=120,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        docs: List[Document] = []
        chunk_counter = 0

        for section in sections:
            split_docs = splitter.create_documents([section["text"]])
            for sd in split_docs:
                chunk_counter += 1
                doc_meta = {
                    **metadata.to_dict(),
                    "section": section["section"],
                    "chunk_id": f"{metadata.account}-{metadata.project_name}-{metadata.week_date}-{chunk_counter}",
                    "ingested_at": datetime.utcnow().isoformat(),
                    "doc_type": "wsr",
                }
                docs.append(Document(page_content=sd.page_content, metadata=doc_meta))

        return docs

    def ingest_wsr(self, wsr_text: str, metadata: WSRMetadata) -> int:
        docs = self._build_documents(wsr_text, metadata)
        if docs:
            self.vector_store.add_documents(docs)
            self._save()
        return len(docs)

    def load_seed_json(self, path: str = "sample_past_wsr.json") -> int:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        total = 0
        for rec in records:
            meta = WSRMetadata(
                account=rec["account"],
                project_name=rec["project_name"],
                week_date=rec["week_date"],
            )
            total += self.ingest_wsr(rec["wsr_text"], meta)
        return total

    def _all_wsr_documents(self) -> List[Document]:
        docs = []
        for item in self.vector_store.docstore._dict.values():  # noqa: SLF001
            if isinstance(item, Document) and item.metadata.get("doc_type") == "wsr":
                docs.append(item)
        return docs

    def _matches_filter(self, doc: Document, metadata_filter: Dict[str, str]) -> bool:
        for key, expected in metadata_filter.items():
            if expected and str(doc.metadata.get(key, "")).lower() != expected.lower():
                return False
        return True

    @staticmethod
    def _overlap_score(doc_text: str, terms: List[str]) -> int:
        doc_lower = doc_text.lower()
        return sum(1 for t in terms if t and t.lower() in doc_lower)

    def retrieve_relevant_chunks(
        self,
        query: str,
        metadata_filter: Dict[str, str],
        terms: List[str],
        k: int = 12,
        fetch_k: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval approach:
        1) vector MMR for semantic recall
        2) metadata filtering (account/project/week)
        3) BM25 lexical ranking on filtered candidates
        4) overlap tie-break for risk/dependency precision
        """

        mmr_docs = self.vector_store.max_marginal_relevance_search(
            query,
            k=max(k, 20),
            fetch_k=fetch_k,
            lambda_mult=0.35,
        )

        filtered = [d for d in mmr_docs if self._matches_filter(d, metadata_filter)]

        if not filtered:
            filtered = [
                d
                for d in self._all_wsr_documents()
                if self._matches_filter(d, metadata_filter)
            ]

        if not filtered:
            return []

        bm25 = BM25Retriever.from_documents(filtered)
        bm25.k = min(k * 2, len(filtered))
        bm25_docs = bm25.invoke(query)

        ranked = sorted(
            bm25_docs,
            key=lambda d: self._overlap_score(d.page_content, terms),
            reverse=True,
        )

        selected = ranked[:k]
        return [
            {
                "chunk_id": d.metadata.get("chunk_id"),
                "account": d.metadata.get("account"),
                "project_name": d.metadata.get("project_name"),
                "week_date": d.metadata.get("week_date"),
                "section": d.metadata.get("section"),
                "content": d.page_content,
            }
            for d in selected
        ]


def build_llm(model: str = "gpt-4o-mini", temperature: float = 0.1) -> ChatOpenAI:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run this workflow.")
    return ChatOpenAI(model=model, temperature=temperature)


def regex_list_extract(text: str, section_header: str) -> List[str]:
    lines = text.splitlines()
    target = section_header.lower()

    found: List[str] = []
    active = False
    for raw in lines:
        line = raw.strip()
        lower = line.lower().strip(" :")

        if lower.startswith(target):
            active = True
            continue

        if active and re.match(r"^(highlights?|progress|blockers?|dependencies?|risks?|issues?|concerns?)\b", lower):
            break

        if active and (line.startswith("-") or line.startswith("•") or re.match(r"^\d+\.", line)):
            found.append(line.lstrip("-•0123456789. ").strip())

    return [f for f in found if f]


def preprocess_current_wsr(current_wsr: str) -> Dict[str, List[str] | str]:
    """Pre-step executed immediately after file/text ingestion, before graph execution."""

    cleaned = WSRVectorStoreManager.clean_wsr_text(current_wsr)
    llm = build_llm()
    parser = JsonOutputParser()

    prompt = [
        SystemMessage(
            content=(
                "Extract risks and dependencies with very high precision from WSR content. "
                "WSR may be unstructured and may come from text extracted from PDF/PPTX including table/chart labels. "
                "Return strict JSON with keys: risks (array), dependencies (array). "
                "Do not hallucinate; only use explicit or strongly implied statements."
            )
        ),
        HumanMessage(content=cleaned),
    ]

    risks: List[str] = []
    deps: List[str] = []

    response = llm.invoke(prompt)
    try:
        parsed = parser.parse(response.content)
        risks = parsed.get("risks", [])
        deps = parsed.get("dependencies", [])
    except Exception:
        risks = regex_list_extract(cleaned, "risks")
        deps = regex_list_extract(cleaned, "dependencies")

    return {
        "cleaned_wsr": cleaned,
        "extracted_risks": risks,
        "extracted_dependencies": deps,
    }


def retrieve_context(state: WorkflowState) -> WorkflowState:
    metadata_filter = {
        "account": state["metadata"].get("account", ""),
        "project_name": state["metadata"].get("project_name", ""),
    }

    terms = state.get("extracted_risks", []) + state.get("extracted_dependencies", [])
    query = " | ".join(terms) if terms else state["cleaned_wsr"][:350]

    store = WSRVectorStoreManager()
    chunks = store.retrieve_relevant_chunks(
        query=query,
        metadata_filter=metadata_filter,
        terms=terms,
        k=12,
        fetch_k=80,
    )

    return {**state, "retrieved_chunks": chunks}


def _build_bounded_context(chunks: List[Dict[str, Any]], max_chars: int = 6500) -> str:
    payload: List[str] = []
    used = 0

    for c in chunks:
        block = (
            f"Chunk: {c.get('chunk_id')}\n"
            f"Week: {c.get('week_date')}\n"
            f"Section: {c.get('section')}\n"
            f"Content:\n{c.get('content')}\n"
        )
        if used + len(block) > max_chars:
            break
        payload.append(block)
        used += len(block)

    return "\n---\n".join(payload)


def recommend_actions(state: WorkflowState) -> WorkflowState:
    llm = build_llm(temperature=0.05)
    parser = JsonOutputParser()

    bounded_context = _build_bounded_context(state.get("retrieved_chunks", []), max_chars=6500)

    prompt = [
        SystemMessage(
            content=(
                "You are a PMO delivery analyst. Generate top-quality recommendations based on:\n"
                "1) current WSR risks/dependencies\n"
                "2) retrieved historical chunks from similar WSRs.\n"
                "Return strict JSON: recommendations[] where each item has:\n"
                "title, risk_or_dependency, rationale, owner, next_step, confidence(0-1)."
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "metadata": state["metadata"],
                    "current_risks": state.get("extracted_risks", []),
                    "current_dependencies": state.get("extracted_dependencies", []),
                    "historical_context": bounded_context,
                },
                indent=2,
            )
        ),
    ]

    response = llm.invoke(prompt)
    recommendations: List[Dict[str, str]] = []

    try:
        parsed = parser.parse(response.content)
        recommendations = parsed.get("recommendations", [])
    except Exception:
        recommendations = [
            {
                "title": "Run immediate risk/dependency triage",
                "risk_or_dependency": "General",
                "rationale": "Early alignment and ownership reduce schedule slippage.",
                "owner": "Project Manager",
                "next_step": "Host a focused 30-minute triage and assign DRIs for each item.",
                "confidence": "0.55",
            }
        ]

    report = {
        "metadata": state["metadata"],
        "risks": state.get("extracted_risks", []),
        "dependencies": state.get("extracted_dependencies", []),
        "retrieved_context_count": len(state.get("retrieved_chunks", [])),
        "recommendations": recommendations,
    }

    return {**state, "recommendations": recommendations, "final_report": report}


def build_workflow():
    graph = StateGraph(WorkflowState)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("recommend", recommend_actions)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "recommend")
    graph.add_edge("recommend", END)

    return graph.compile()


def analyze_wsr(
    current_wsr_text: str,
    account: str,
    project_name: str,
    week_date: str,
) -> Dict[str, Any]:
    preprocessed = preprocess_current_wsr(current_wsr_text)
    app = build_workflow()
    result = app.invoke(
        {
            "current_wsr": current_wsr_text,
            "metadata": {
                "account": account,
                "project_name": project_name,
                "week_date": week_date,
            },
            "cleaned_wsr": preprocessed["cleaned_wsr"],
            "extracted_risks": preprocessed["extracted_risks"],
            "extracted_dependencies": preprocessed["extracted_dependencies"],
        }
    )
    return result["final_report"]


def analyze_wsr_file(
    file_path: str,
    account: str,
    project_name: str,
    week_date: str,
) -> Dict[str, Any]:
    extracted_text = extract_wsr_text_from_file(file_path)
    return analyze_wsr(
        current_wsr_text=extracted_text,
        account=account,
        project_name=project_name,
        week_date=week_date,
    )


def ingest_wsr_from_ui(current_wsr_text: str, account: str, project_name: str, week_date: str) -> int:
    metadata = WSRMetadata(account=account, project_name=project_name, week_date=week_date)
    store = WSRVectorStoreManager()
    return store.ingest_wsr(current_wsr_text, metadata)


def ingest_wsr_file_from_ui(file_path: str, account: str, project_name: str, week_date: str) -> int:
    extracted_text = extract_wsr_text_from_file(file_path)
    return ingest_wsr_from_ui(extracted_text, account, project_name, week_date)


def main() -> None:
    """Run a local demo for manual verification."""
    # One-time seed load for demo. In production, call ingest_wsr_file_from_ui() per uploaded WSR file.
    if os.environ.get("SEED_SAMPLE_DATA", "false").lower() == "true":
        store = WSRVectorStoreManager()
        seeded = store.load_seed_json("sample_past_wsr.json")
        print(f"Seeded chunks: {seeded}")

    sample_wsr = """
    Weekly Status Report
    Generated On: 2026-02-16
    Confidential

    Risks:
    - UAT environment unstable due to DB refresh failures.
    - Vendor API throttling delaying nightly reconciliation.

    Dependencies:
    - Security signoff pending for SSO rollout.
    - Data provider schema update still pending.
    """

    output = analyze_wsr(
        current_wsr_text=sample_wsr,
        account="Retail Banking",
        project_name="Payments Modernization",
        week_date="2026-02-16",
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
