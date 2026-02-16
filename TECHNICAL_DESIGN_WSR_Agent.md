# Technical Design Document
## WSR Analysis Agent

## 1. Architecture

### 1.1 Ingestion Layer
- `extract_wsr_text_from_file(...)` routes by extension.
- Extractors:
  - PDF via `pypdf`
  - PPTX via `python-pptx`
  - DOCX via `python-docx`
  - TXT via plain file read

### 1.2 Processing Layer
- `clean_wsr_text(...)` removes noise and normalizes format.
- `sectionalize_text(...)` detects coarse sections.
- `chunk_text(...)` creates overlap chunks for retrieval quality.

### 1.3 Vector Layer
- `vectorize_text(...)` creates deterministic hashed vectors.
- `LocalVectorDB` persists chunk records in `.wsr_vector_db.json`.
- Query supports metadata filtering and cosine similarity ranking.

### 1.4 Analysis Layer
- `detect_signals(...)` extracts risks/dependencies from explicit sections or fallback keywords.
- `detect_reporting_gaps(...)` identifies missing owner/ETA/mitigation cues.
- `build_recommendations(...)` creates action suggestions with historical context grounding.

### 1.5 Assurance Layer
- `run_delivery_assurance(...)` compares current vs previous week outputs.
- Deterministic matching via token-overlap scoring.

## 2. Key Design Decisions
- Keep logic deterministic and transparent.
- Use local vector DB first for quick deployment.
- Preserve backward-compatible top-level wrappers.

## 3. Data Contracts
- `WSRMetadata`: `account`, `project_name`, `week_date`
- `ChunkRecord`: chunk text, vector, section, metadata
- Analysis output: risks, dependencies, observation gaps, recommendations, retrieved context

## 4. Operational Notes
- OCR is required for scanned documents.
- Local vector store can be replaced by managed vector DB later.
- Current design prioritizes readability and maintainability.
