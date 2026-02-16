# Functional Requirements Document (FRD)
## AI Delivery Assurance Agent

## 1. System Purpose
The agent ingests weekly status files, cleans and structures content, stores vectors with metadata, and returns systematic delivery analysis.

## 2. Inputs
- `file_path` (PDF/PPTX/DOCX/TXT)
- `account`
- `project_name`
- `week_date`

## 3. Outputs
- Structured JSON report containing:
  - `metadata`
  - `analysis.risks[]`
  - `analysis.dependencies[]`
  - `analysis.observation_gaps[]`
  - `analysis.recommendations[]`
  - `retrieved_context[]`

## 4. Functional Modules

### 4.1 File Extraction
- Parse text from PDF/PPTX/DOCX/TXT.
- Extract PPTX text/table/chart content where available.
- Return clear error when no extractable content is found.

### 4.2 Data Cleaning
- Normalize whitespace and line breaks.
- Remove repeated/noisy lines (header/footer style repetition).
- Remove known non-content markers (page counters/confidential markers).

### 4.3 Sectioning and Chunking
- Detect heading-like sections where present.
- Produce overlapping chunks for robust context capture.
- Preserve section label in each chunk.

### 4.4 Vectorization and Storage
- Convert each chunk into deterministic vectors.
- Store vectors + metadata in local vector DB (`.wsr_vector_db.json`).
- Enable metadata-based filtering by account/project during retrieval.

### 4.5 Signal Analysis
- Prefer explicit section extraction for risks/dependencies.
- If explicit sections are absent, use keyword fallback for messy content.
- Detect reporting gaps (owner, ETA/due date, mitigation/action cues).

### 4.6 Recommendations
- Generate deterministic, actionable recommendations per signal.
- Ground recommendations with retrieved historical chunks.

### 4.7 Week-over-Week Comparison
- Compare current and previous WSR analyses using deterministic token overlap.
- Classify as existing/new/no-longer-reported signals.

## 5. Non-Functional Requirements
- Readable code with clear comments/docstrings.
- Deterministic analysis behavior.
- Extensible architecture for future OCR/LLM upgrades.
- Basic production readiness with metadata-aware retrieval.
