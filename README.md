# WSR Analysis Agent

This project provides a **production-friendly WSR Analysis Agent** for Delivery Assurance teams.

It supports:
- Uploading WSR files in **PDF, PPTX, DOCX, and TXT**.
- Cleaning noisy content (header/footer-like repeats, page markers, extra spaces).
- Chunking content with section tags.
- Storing chunk vectors + metadata in a local vector DB.
- Running systematic analysis for:
  - Risks
  - Dependencies
  - Reporting gaps
  - Recommendations grounded in historical WSR context.

## Project Structure

```text
.
├── src/
│   └── wsr_assurance/
│       ├── workflow.py            # extraction, cleaning, chunking, vector DB, analysis
│       ├── delivery_assurance.py  # week-over-week comparison orchestration
│       ├── pdf_analysis.py        # backward-compatible PDF helper
│       └── __init__.py
├── wsr_agent_workflow.py          # backward-compatible wrapper
├── delivery_assurance_agent.py    # backward-compatible wrapper
├── BRD_WSR_Agent.md
├── FRD_AI_Delivery_Assurance_Agent.md
├── TECHNICAL_DESIGN_WSR_Agent.md
├── requirements.txt
└── README.md
```

## End-to-End Flow

1. User uploads WSR file with metadata (`account`, `project_name`, `week_date`).
2. System extracts text from file (PDF/PPTX/DOCX/TXT).
3. System cleans text and removes common noise.
4. System chunks text and stores vectors with metadata in `.wsr_vector_db.json`.
5. System detects risk/dependency signals (explicit sections first, keyword fallback).
6. System retrieves similar historical chunks (metadata-filtered vector similarity).
7. System outputs analysis + reporting gaps + recommendations.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage (Python)

```python
from src.wsr_assurance.workflow import analyze_wsr_file

report = analyze_wsr_file(
    file_path="/path/to/wsr_week_2026_02_16.pdf",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-16",
)
print(report)
```

## Week-over-Week Assurance

```python
from src.wsr_assurance.delivery_assurance import RunMetadata, run_delivery_assurance

result = run_delivery_assurance(
    current_wsr_path="/path/current_week.docx",
    previous_wsr_path="/path/previous_week.pptx",
    metadata=RunMetadata(project_id="Payments Modernization", week_date="2026-02-16", account="Retail Banking"),
)
print(result)
```

## Notes
- For image-only scanned PDFs, OCR is required before extraction.
- Local JSON vector DB is used for simplicity and easy adoption.
