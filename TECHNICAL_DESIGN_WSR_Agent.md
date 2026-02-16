# Technical Design Document
## AI Agent for Weekly Status Report (WSR) Analysis

## 1. Purpose
Design a production-grade AI system that ingests WSR files (PDF/PPTX), extracts project health signals (risks/dependencies), retrieves similar historical cases, and generates high-quality recommendations.

## 2. Architecture Overview

### 2.1 Logical Layers
1. **Ingestion Layer**
   - Accepts file upload + metadata (`account`, `project_name`, `week_date`).
   - Extracts file text from PDF/PPTX (including table/chart-derived text where possible).

2. **Processing Layer**
   - Cleans and normalizes content.
   - Performs section-aware + recursive chunking.
   - Attaches metadata to each chunk.

3. **Knowledge Layer**
   - Embeds chunks and stores in vector index.
   - Preserves document-level and chunk-level metadata for filtered retrieval.

4. **Reasoning Layer (Agent)**
   - Extracts current risks/dependencies.
   - Retrieves historical analog chunks.
   - Produces recommendations with owner + next steps + confidence.

5. **Delivery Layer**
   - Returns structured report JSON.
   - (Optional future) Pushes to PMO dashboards and alerting channels.

## 3. Component Design

### 3.1 File Extraction Component
- **Input:** `file_path`, file type.
- **PDF path:** `pypdf` for text + optional `pdfplumber` for tables.
- **PPTX path:** `python-pptx` for slide text, table cells, chart categories/series.
- **Output:** unified extracted text stream with source markers.

### 3.2 Cleaning & Normalization Component
- Removes repetitive noise (headers/footers/confidential stamps/page counters).
- Collapses whitespace and normalizes line breaks.
- Retains semantic markers for tables/charts to preserve context.

### 3.3 Chunking & Metadata Component
- Sectional segmentation for explicit and implicit risk/dependency content.
- Recursive chunk splitting (`chunk_size`, `overlap`) to preserve context continuity.
- Metadata fields:
  - `account`, `project_name`, `week_date`
  - `section`, `chunk_id`, `ingested_at`, `doc_type`

### 3.4 Vectorization & Storage Component
- Embedding model transforms chunks to vectors.
- Persistent vector index stores vectors + metadata.
- Current local FAISS suitable for dev/pilot.
- Production recommendation: managed vector backend (pgvector/Pinecone/Weaviate) with partitioning.

### 3.5 Retrieval Component (Hybrid)
1. Semantic retrieval (MMR) for broad recall.
2. Metadata filter (account/project; optionally week constraints).
3. BM25 reranking on filtered candidates.
4. Term overlap scoring using extracted risk/dependency terms.
5. Top-k selection with bounded context size.

### 3.6 Reasoning Component
- LLM-based extraction for risks/dependencies from potentially unstructured content.
- LLM-based recommendation generation grounded in retrieved context.
- Deterministic fallback extraction heuristics if parser/LLM JSON parsing fails.

## 4. LangChain vs LangGraph Decision

## 4.1 Can LangChain alone work?
**Yes, for simple linear pipelines**, where steps are fixed and no conditional or resumable orchestration is needed.

Use only LangChain when:
- Single pass extract -> retrieve -> summarize is enough.
- No branching, retries, or stateful multi-step control is needed.
- Prototype speed is the main goal.

## 4.2 Why LangGraph is recommended here
**LangGraph is preferred for production-grade agent orchestration** because this use case requires explicit workflow state and future extensibility.

Benefits in this use case:
- Stateful nodes (`clean_extract`, `retrieve`, `recommend`) with typed state.
- Easy insertion of guardrails (validation, confidence checks, HITL nodes).
- Supports branching/retry policies and future asynchronous fan-out.
- Better observability and deterministic flow control than ad-hoc chains.

## 4.3 Recommendation
- Keep **LangChain** for model/retriever abstractions.
- Use **LangGraph** as orchestration backbone in production.

## 5. Data Model

### 5.1 Ingestion Input
```json
{
  "file_path": "...",
  "account": "Retail Banking",
  "project_name": "Payments Modernization",
  "week_date": "2026-02-16"
}
```

### 5.2 Chunk Metadata
```json
{
  "account": "Retail Banking",
  "project_name": "Payments Modernization",
  "week_date": "2026-02-16",
  "section": "risks",
  "chunk_id": "...",
  "ingested_at": "...",
  "doc_type": "wsr"
}
```

### 5.3 Analysis Output
```json
{
  "metadata": {...},
  "risks": [...],
  "dependencies": [...],
  "retrieved_context_count": 12,
  "recommendations": [
    {
      "title": "...",
      "risk_or_dependency": "...",
      "rationale": "...",
      "owner": "...",
      "next_step": "...",
      "confidence": 0.82
    }
  ]
}
```

## 6. Accuracy Strategy
- Retrieval-grounded generation only (no free-form recommendations without context).
- Context bounding to reduce noise and prompt drift.
- Explicit “no hallucination” extraction instruction.
- Add confidence scoring and low-confidence review workflow.
- Evaluation set with manually labeled WSRs for precision/recall tracking.

## 7. Scalability & Reliability
- Queue-based asynchronous ingestion workers.
- Partition index by account and/or quarter.
- Retention + archival policy for old chunks.
- Circuit-breaker/fallback behavior for parser/model failure.
- Observability: ingestion latency, extraction quality, retrieval hit quality, token/cost metrics.

## 8. Security & Compliance
- Tenant/account-level access controls on retrieval filters.
- Encryption in transit and at rest.
- PII policy checks before embedding/indexing.
- Full audit log for input documents and generated output.

## 9. Implementation Roadmap

### Phase 1 (Current Foundation)
- PDF/PPTX extraction, chunking, vector storage, hybrid retrieval, recommendation pipeline.

### Phase 2
- OCR pipeline for scanned docs.
- Human-in-the-loop approval for low-confidence recommendations.
- Evaluation dashboard + drift monitoring.

### Phase 3
- Multi-agent specialization (risk classifier, dependency reasoner, recommendation ranker).
- Auto-integration into PMO governance tools.

## 10. Open Gaps / Loopholes to Close
1. No OCR for scan-only documents.
2. Current local FAISS is not multi-tenant cloud-grade.
3. Limited automated evaluation harness for extraction/recommendation quality.
4. Need stricter metadata governance (taxonomy normalization for account/project aliases).
5. Need robust dedup/versioning for re-uploaded WSRs.
