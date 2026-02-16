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

## Workflow Stages
1. Extract current + previous file text
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

## Usage

```python
from src.wsr_assurance.delivery_assurance import RunMetadata, run_delivery_assurance

report = run_delivery_assurance(
    current_wsr_path="/path/current_week.pdf",
    previous_wsr_path="/path/previous_week.pptx",
    metadata=RunMetadata(
        project_id="Payments Modernization",
        week_date="2026-02-16",
        account="Retail Banking",
    ),
)
```

## Notes
- For scanned image-only files, OCR is required before ingestion.
- The workflow uses deterministic parsing logic for signal extraction and progress tracking.
