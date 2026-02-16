# myfirstRepo

Production-oriented LangChain + LangGraph workflow for Weekly Status Report (WSR) analysis.

## What this implementation now supports

- **WSR ingestion from uploaded files**: PDF and PPTX uploads.
- **Data extraction from rich formats**:
  - PDF: page text + table extraction (when tables are present).
  - PPTX: slide text + table cells + chart category/series values.
- **Metadata from UI inputs**: `account`, `project_name`, `week_date`.
- **Data cleaning**: removes noisy headers/footers, normalizes whitespace.
- **Section-aware chunking**: handles explicit and implicit risk/dependency structures.
- **Vectorization + persistence**: stores chunks in persistent FAISS index.
- **Metadata-aware retrieval**: filters chunks by account/project metadata and performs hybrid retrieval.
- **Context-size control**: bounded context sent to LLM for predictable token usage.
- **Preprocessing step before LangGraph**: clean WSR text and extract risks/dependencies immediately after file upload.
- **LangGraph pipeline** for analysis:
  1. retrieve similar historical chunks
  2. generate recommendations

## Project structure

```text
.
├── src/
│   └── wsr_assurance/
│       ├── __init__.py
│       ├── delivery_assurance.py
│       └── workflow.py
├── delivery_assurance_agent.py   # backward-compatible wrapper
├── wsr_agent_workflow.py         # backward-compatible wrapper
├── sample_past_wsr.json
└── requirements.txt
```

## Files

- `src/wsr_assurance/workflow.py` - File extraction, ingestion, vector retrieval, and recommendation workflow.
- `src/wsr_assurance/delivery_assurance.py` - Deterministic governance/audit analysis engine.
- `wsr_agent_workflow.py` - Backward-compatible import wrapper for workflow module.
- `delivery_assurance_agent.py` - Backward-compatible import wrapper for assurance module.
- `sample_past_wsr.json` - Seed dataset with account/project/week metadata.
- `requirements.txt` - Python dependencies.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="<your-key>"
```

## Seed historical WSR data (optional)

```bash
SEED_SAMPLE_DATA=true python wsr_agent_workflow.py
```

This writes chunked vectors to `.wsr_vector_db/`.

## Ingest uploaded WSR file from UI (PDF/PPTX)

```python
from wsr_agent_workflow import ingest_wsr_file_from_ui

chunks_added = ingest_wsr_file_from_ui(
    file_path="/path/to/wsr_week_2026_02_16.pdf",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-16",
)
```

## Analyze uploaded WSR file directly

```python
from wsr_agent_workflow import analyze_wsr_file

report = analyze_wsr_file(
    file_path="/path/to/wsr_week_2026_02_16.pptx",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-16",
)
print(report)
```

## Retrieval and accuracy strategy

For higher accuracy at scale (e.g., 200 WSRs/week), retrieval uses:

1. **MMR vector retrieval** for semantic recall.
2. **Metadata filtering** (`account`, `project_name`) for relevance isolation.
3. **BM25 lexical reranking** on filtered candidates.
4. **Keyword overlap tie-break** using extracted risk/dependency terms.
5. **Bounded context** to keep prompts manageable and avoid noisy long contexts.

## Important production note for scanned files

If a PDF is image/scanned and has no embedded text, OCR is required before ingestion. Current extraction expects text-based PDFs/PPTX.

## Scale notes

- For high ingestion volume, replace local FAISS files with a managed vector DB (pgvector, Pinecone, Weaviate) while keeping chunk metadata schema intact.
- Run ingestion asynchronously (queue/worker) to decouple upload latency from embedding generation.
- Add retention/archival policy and periodic index compaction.

## Architecture & Business Documentation

- `BRD_WSR_Agent.md` - Business requirements, pain points, ROI, and success criteria.
- `TECHNICAL_DESIGN_WSR_Agent.md` - End-to-end architecture, component design, and LangChain vs LangGraph decision rationale.


## Delivery Assurance (FRD-aligned) deterministic audit flow

New module: `delivery_assurance_agent.py`

- Ingests `PDF/DOCX/TXT` for **current** and **previous** WSR.
- Uses deterministic rule engines for auditing and quality checks.
- Uses LLM strictly as parser (fallback to rule parsing), with design target of **≤2 LLM calls per run**.
- Produces strict markdown sections and machine-readable JSON.

Example:

```python
from delivery_assurance_agent import RunMetadata, run_delivery_assurance

result = run_delivery_assurance(
    current_wsr_path="/path/current_wsr.pdf",
    previous_wsr_path="/path/previous_wsr.docx",
    metadata=RunMetadata(project_id="Payments Modernization", week_date="2026-02-16"),
)

print(result["markdown"])
```


### Strict Prompt Rule Coverage
- Excludes SLA and Appendix content from analysis.
- Excludes closed items and controlled items from active risk table.
- Uses explicit-section extraction when sections exist; otherwise one consolidated keyword-scan item.
- Enforces exact markdown section order for governance output.
