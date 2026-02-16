# Functional Requirements Document (FRD)
## AI Delivery Assurance - Simplified PDF Analysis Flow

## 1. System Purpose
The system processes uploaded WSR PDFs and outputs deterministic risk/dependency analysis.

## 2. Inputs and Outputs
### 2.1 Inputs
- `file_path` (PDF)
- `account` (string)
- `project_name` (string)
- `week_date` (string)

### 2.2 Outputs (JSON)
- `file_name`
- `page_count`
- `cleaned_text`
- `extracted_risks[]`
- `extracted_dependencies[]`
- `summary[]`
- `metadata{account, project_name, week_date}`

## 3. Functional Modules
### 3.1 PDF Extraction Module
- Validate input is `.pdf`.
- Extract text from each page.
- Fail with clear error if no extractable text is found.

### 3.2 Cleaning Module
- Normalize line breaks and whitespace.
- Remove known noise lines (e.g., page counters, confidentiality stamps).

### 3.3 Signal Detection Module
- First try section-based extraction:
  - Risks/Issues section
  - Dependencies section
- If sections are unavailable, apply keyword scan fallback.
- Return capped list sizes for predictable output.

### 3.4 Summary Module
- Build deterministic summary bullets:
  - count of risk signals
  - count of dependency signals
  - top risk/dependency when available
  - analyzed line count

### 3.5 Workflow Module
- `analyze_wsr_file(...)` calls the PDF analysis module and appends metadata.
- CLI entrypoint supports manual execution.

## 4. Non-Functional Requirements
- Readability: clear functions, comments, and docstrings.
- Determinism: same input produces same output.
- Reliability: graceful errors for invalid file type and non-extractable PDFs.
- Maintainability: minimal module complexity and clean separation.

## 5. Explicit Exclusions
- No LLM calls.
- No vectorization or retrieval.
- No multi-format parsing beyond PDF.
- No recommendation generation beyond deterministic summary bullets.
