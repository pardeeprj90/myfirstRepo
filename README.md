# WSR PDF Analysis

This project is now simplified to one clear use case:

**User uploads a WSR PDF → system extracts content → system returns risk/dependency analysis.**

## Clean project structure

```text
.
├── src/
│   └── wsr_assurance/
│       ├── pdf_analysis.py        # core PDF extraction + analysis logic
│       ├── workflow.py            # API/CLI-facing orchestration
│       ├── delivery_assurance.py  # compatibility entrypoint
│       └── __init__.py
├── wsr_agent_workflow.py          # backward-compatible wrapper
├── delivery_assurance_agent.py    # backward-compatible wrapper
├── requirements.txt
└── README.md
```

## What happens on PDF upload

1. Extract text from all PDF pages.
2. Clean whitespace and remove noise lines.
3. Detect risks and dependencies (section-first, keyword fallback).
4. Return deterministic JSON output with summary bullets.

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

## Note

- This version is intentionally simple and readable.
- If PDF is scanned/image-only, OCR is required before analysis.
