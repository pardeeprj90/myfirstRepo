# WSR Analysis Agent (LangChain + LangGraph + Pinecone)

This repository implements a production-oriented Delivery Assurance agent that:
- Ingests **current and previous week** WSR files (`pdf`, `pptx`, `docx`, `txt`)
- Cleans messy data (header/footer-like repeats, extra spaces, page markers)
- Chunks and stores data in **Pinecone** with metadata
- Analyzes risks/dependencies from structured and unstructured reports
- Detects reporting gaps and generates recommendations
- Tracks progress from previous week

## Tech Stack
- **LangChain**: embeddings, LLM integration, document abstractions
- **LangGraph**: stateful orchestration of analysis nodes
- **Pinecone**: vector storage and metadata-filtered retrieval

## Project Structure

```text
src/wsr_assurance/
├── workflow.py            # main LangGraph workflow and core logic
├── delivery_assurance.py  # business entrypoint
├── pdf_analysis.py        # compatibility helpers
└── __init__.py
```

## User Upload Strategy (No user file path needed)

In production, users upload files via UI. Backend should:
1. Save the uploaded file to server/object storage.
2. Register that stored file using `upload_wsr_file(...)`.
3. Store returned `file_id` in DB.
4. Run analysis via `analyze_uploaded_wsr(file_id)`.

The agent auto-finds previous week file for same `account + project_name` by `week_date`.

- Week 1 upload: no previous found -> current-only analysis.
- Week 2 upload: week 1 auto-selected as previous -> progress comparison enabled.

## Workflow Stages
1. Extract current + previous file text (if previous exists)
2. Clean/normalize content
3. Chunk with metadata (`account`, `project_name`, `week_date`, `doc_id`)
4. Upsert chunks to Pinecone
5. Retrieve historical context with metadata filters
6. Analyze current and previous week signals
7. Compare week-over-week progress
8. Return final report

## Environment Variables
- `OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX` (optional, default: `wsr-agent-index`)
- `PINECONE_CLOUD` (optional, default: `aws`)
- `PINECONE_REGION` (optional, default: `us-east-1`)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage - Upload and Analyze by File ID

```python
from src.wsr_assurance.workflow import upload_wsr_file, analyze_uploaded_wsr

# Week 1
file_id_week1 = upload_wsr_file(
    file_path="/srv/uploads/wsr_2026_02_01.pdf",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-01",
)
report_week1 = analyze_uploaded_wsr(file_id_week1)

# Week 2
file_id_week2 = upload_wsr_file(
    file_path="/srv/uploads/wsr_2026_02_08.pdf",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-08",
)
report_week2 = analyze_uploaded_wsr(file_id_week2)
# report_week2 automatically compares against week1
```

## Notes
- For scanned image-only files, OCR is required before ingestion.
- `WSRFileRegistry` uses `.wsr_file_registry.json` in this repo for demo/reference implementation.
- Replace registry JSON with DB + object storage URI in production.
