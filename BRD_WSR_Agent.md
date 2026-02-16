# Business Requirements Document (BRD)
## WSR PDF Upload Analysis

## 1. Purpose
Build a simple and reliable service where a user uploads a Weekly Status Report (WSR) PDF and immediately receives analysis of delivery risks and dependencies.

## 2. Current Pain Areas
- WSR review is manual and slow.
- Different report formats cause inconsistent analysis quality.
- Key risk/dependency signals are often buried in long narrative text.

## 3. Business Goal
Reduce the time needed for first-pass WSR review by automating PDF extraction and deterministic risk/dependency signal detection.

## 4. Scope
### In Scope
- PDF upload-based analysis.
- Text extraction from PDF pages.
- Text cleaning (noise removal, whitespace normalization).
- Risk/dependency signal extraction.
- Deterministic JSON response for API/UI.

### Out of Scope
- PPTX/DOCX ingestion.
- Vector database, retrieval orchestration, and recommendation ranking.
- OCR processing for image-only scanned PDFs.

## 5. Users
- PMO analysts
- Delivery managers
- Program leads

## 6. Success Criteria
- User can upload PDF and receive analysis response consistently.
- Response includes extracted risks, dependencies, and concise summary.
- Code is easy to understand and maintain.

## 7. KPI Targets
- Reduce manual first-pass review effort.
- Improve consistency of weekly risk/dependency signal reporting.
- Keep onboarding and maintenance effort low through clean code structure.

## 8. Constraints and Assumptions
- PDFs are text-extractable.
- OCR is handled outside this service when needed.
- API/UI provides metadata (`account`, `project_name`, `week_date`) for traceability.
