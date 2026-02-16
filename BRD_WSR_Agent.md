# Business Requirements Document (BRD)
## AI-Powered Weekly Status Report (WSR) Analysis Agent

## 1. Executive Summary
Organizations running multiple projects receive WSRs in different formats (PDF/PPTX), structures, and quality levels. Current review is largely manual and consumes significant PMO, Delivery Manager, and Account Leadership bandwidth.

This initiative introduces an AI agent that ingests WSR files, extracts risk/dependency signals, finds historical analogs, and proposes actionable recommendations with confidence.

## 2. Current Pain Areas

### 2.1 Operational Pain
- WSR review is manual, fragmented, and highly dependent on reviewer experience.
- Analysts spend substantial effort locating implicit risks hidden in narrative slides, charts, and tables.
- Historical learning is not systematically reused; recommendations vary by reviewer.

### 2.2 Time & Cost Pain
- Current average time to understand one WSR deeply: **~60 minutes**.
- With high project volume, this creates review bottlenecks and delayed escalations.
- Senior delivery leaders spend time on repetitive triage rather than strategic interventions.

### 2.3 Quality Pain
- Risks/dependencies are often not explicit section headers.
- Signal loss from non-textual content (tables/charts).
- Inconsistent recommendation quality and ownership assignment.

## 3. Business Objectives
- Reduce first-pass WSR analysis time from ~60 min to ≤15 min per report.
- Improve consistency and precision of risk/dependency identification.
- Reuse past WSR knowledge to drive evidence-based recommendations.
- Enable scalable weekly processing (e.g., 200+ WSR uploads/week).

## 4. Scope

### In Scope
- Ingestion of PDF and PPTX WSR files.
- Metadata tagging from UI inputs (`account`, `project_name`, `week_date`).
- Content extraction (text + tables + chart labels/series where available).
- Cleaning, chunking, vectorization, retrieval, and recommendation generation.
- Output report with risks, dependencies, recommendations, confidence.

### Out of Scope (Phase 1)
- OCR pipeline for image-only scanned documents.
- Auto-writing updates into external PM tools (Jira/ADO).
- Full multilingual support beyond English-dominant content.

## 5. Stakeholders
- PMO Head
- Delivery Excellence Team
- Account Delivery Leads
- Program/Project Managers
- Architecture & Data Platform Team

## 6. Target Users and User Stories

### Primary Users
- PMO analysts, Delivery Managers, Account leads.

### User Stories
- As a PMO analyst, I upload weekly WSR files and receive a concise risk/dependency summary with recommendations.
- As an account lead, I want recommendations grounded in similar historical scenarios, so escalation quality improves.
- As a delivery leader, I want metadata-filtered insights by account/project/week for context-accurate decisions.

## 7. Functional Requirements
1. System shall accept PDF/PPTX uploads.
2. System shall capture metadata inputs (`account`, `project_name`, `week_date`) at ingestion time.
3. System shall extract textual content, tables, and chart values where accessible.
4. System shall clean noisy headers/footers/spaces and normalize structure.
5. System shall chunk content and attach metadata for retrieval.
6. System shall store vectorized chunks for historical reuse.
7. System shall retrieve relevant historical chunks using semantic + lexical + metadata filtering.
8. System shall infer risks/dependencies even when not explicitly labeled.
9. System shall produce actionable recommendations with suggested owners and confidence.
10. System shall bound context passed to LLM for reliable latency/cost.

## 8. Non-Functional Requirements
- **Accuracy:** High precision extraction of risks/dependencies; low hallucination behavior.
- **Scalability:** Sustain 200+ WSR/week ingestion and query load.
- **Latency:** First-pass analysis target under a few minutes per file at scale.
- **Traceability:** Store chunk metadata and references for auditability.
- **Security:** Data access controls by account/project; encryption in storage/transit.
- **Reliability:** Graceful fallback when specific parsers/components are unavailable.

## 9. Expected Benefits and KPI Impact

### 9.1 Time Savings
- Baseline: ~60 min/WSR manual deep analysis.
- Target with agent: ≤15 min/WSR assisted review.
- **Net savings: ~45 min per WSR**.

At 200 WSR/week:
- Manual effort: 12,000 minutes (~200 hrs/week).
- Assisted effort: 3,000 minutes (~50 hrs/week).
- **Savings: ~150 hrs/week**.

### 9.2 Quality Gains
- Earlier detection of recurring risks.
- More consistent recommendation quality and owner assignment.
- Better cross-project learning reuse via historical retrieval.

### 9.3 Organizational Impact
- Faster and better-informed governance reviews.
- Better prioritization of escalations.
- Reduced burnout from repetitive manual synthesis work.

## 10. Risks and Mitigations
- **Risk:** Poor extraction from scanned PDFs.
  - **Mitigation:** OCR pipeline in Phase 2; enforce upload quality checks.
- **Risk:** Recommendation hallucination.
  - **Mitigation:** retrieval-grounded prompts + confidence + human review.
- **Risk:** Data growth affects retrieval performance.
  - **Mitigation:** vector DB partitioning and retention strategy.

## 11. Success Criteria (Phase 1)
- 70%+ reduction in first-pass review effort on pilot teams.
- ≥85% stakeholder satisfaction for recommendation usefulness.
- Stable production operation across pilot volume with SLA adherence.
