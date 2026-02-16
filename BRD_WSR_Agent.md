# Business Requirements Document (BRD)
## AI Weekly Status Report Analysis Agent

## 1. Purpose
Build an AI-powered agent to automate Weekly Status Report (WSR) analysis so Delivery Assurance teams can quickly identify risks, dependencies, and governance gaps from uploaded project files.

## 2. Current Pain Areas
- Manual reading of weekly files (PDF/PPTX/DOCX) is time-consuming.
- Risk/dependency detection quality depends heavily on reviewer experience.
- Important signals are often hidden in messy or unstructured status content.
- Repeated weekly effort does not systematically reuse past learning.

## 3. Target Outcomes
- Reduce manual first-pass review effort.
- Increase consistency in identifying delivery risks and dependencies.
- Improve escalation readiness with structured observations and recommendations.

## 4. In Scope
- Multi-format WSR ingestion: PDF, PPTX, DOCX, TXT.
- Data cleaning: repetitive header/footer-like noise, whitespace normalization.
- Section-aware chunking.
- Metadata-enriched vector storage (`account`, `project_name`, `week_date`).
- Analysis outputs:
  - Risks
  - Dependencies
  - Observation/reporting gaps
  - Recommendations based on historical context.

## 5. Out of Scope (Current Phase)
- OCR engine for image-only scanned content.
- External ticketing tool automation.
- Fully autonomous decisioning without DA review.

## 6. Primary Users
- Delivery Assurance Analysts
- PMO teams
- Program and Delivery Managers

## 7. Success Criteria
- Reliable ingestion and analysis across supported file types.
- Structured analysis output with clear risk/dependency visibility.
- Historical context retrieval is metadata-scoped and relevant.
