# WSR PDF Analysis

This project supports one simple use case:

**User uploads a WSR PDF -> system extracts content -> system returns risk/dependency analysis.**

## Project Structure

```text
.
├── src/
│   └── wsr_assurance/
│       ├── pdf_analysis.py        # core PDF extraction + analysis logic
│       ├── workflow.py            # API/CLI-facing orchestration
│       ├── delivery_assurance.py  # compatibility facade
│       └── __init__.py
├── wsr_agent_workflow.py          # backward-compatible wrapper
├── delivery_assurance_agent.py    # backward-compatible wrapper
├── BRD_WSR_Agent.md
├── FRD_AI_Delivery_Assurance_Agent.md
├── TECHNICAL_DESIGN_WSR_Agent.md
├── requirements.txt
└── README.md
```

## Processing Flow
1. Extract text from all PDF pages.
2. Clean whitespace and remove noise lines.
3. Detect risks and dependencies (section-first, keyword fallback).
4. Return deterministic JSON output.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage (Python)

```python
from src.wsr_assurance.workflow import analyze_wsr_file

result = analyze_wsr_file(
    file_path="/path/to/wsr.pdf",
    account="Retail Banking",
    project_name="Payments Modernization",
    week_date="2026-02-16",
)
print(result)
```

## Usage (CLI)

```bash
python wsr_agent_workflow.py /path/to/wsr.pdf --account "Retail Banking" --project-name "Payments Modernization" --week-date "2026-02-16"
```

## Notes
- This version is intentionally simple and readable.
- For image-only scanned PDFs, run OCR before analysis.
