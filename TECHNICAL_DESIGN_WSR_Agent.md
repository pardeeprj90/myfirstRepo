# Technical Design Document
## WSR PDF Upload Analysis (Current Implementation)

## 1. Design Intent
Deliver a clean production-oriented codebase focused on one flow:

**Upload PDF -> Extract -> Clean -> Detect Risks/Dependencies -> Return JSON**

## 2. Code Structure
```text
src/wsr_assurance/
├── pdf_analysis.py        # core pipeline logic
├── workflow.py            # API facade + CLI entrypoint
├── delivery_assurance.py  # compatibility facade
└── __init__.py            # package exports
```

Backward-compatible wrappers remain:
- `wsr_agent_workflow.py`
- `delivery_assurance_agent.py`

## 3. Component Design
### 3.1 `pdf_analysis.py`
Primary functions:
- `extract_pdf_text(file_path)`
- `clean_wsr_text(raw_text)`
- `extract_risks_and_dependencies(cleaned_text)`
- `build_summary(risks, dependencies, cleaned_text)`
- `analyze_uploaded_pdf(file_path)`

Data contract:
- `PDFAnalysisResult` dataclass with `to_dict()` for API output.

### 3.2 `workflow.py`
- `analyze_wsr_file(...)` is the primary API method.
- Attaches UI metadata to analysis output.
- Provides CLI `main()` for local usage.

### 3.3 `delivery_assurance.py`
- Compatibility adapter around the same PDF analysis flow.
- Returns current vs previous analysis side-by-side.

## 4. Error Handling
- Reject non-PDF input in extraction stage.
- Return clear error for scanned/image PDFs with no extractable text.

## 5. Runtime Dependencies
- `pypdf`

## 6. Operational Notes
- OCR should be handled before calling this service for scanned PDFs.
- This simplified version intentionally avoids orchestration layers and external stores.

## 7. Future Extension Points
- Add OCR preprocessing module.
- Add richer table extraction if needed.
- Add recommendation layer only after stable extraction quality baseline.
