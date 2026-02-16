# Functional Requirements Document (FRD)
## AI Delivery Assurance Agent

## 1. System Purpose
Build an LLM-powered governance agent that ingests Weekly Status Reports (WSR) and produces standardized escalation analysis by strictly extracting factual delivery risks and comparing historical progress.

The system behaves like a deterministic audit engine using an LLM as a parser, not a chatbot.

## 2. Inputs & Outputs

### 2.1 Inputs
| Input | Type | Source |
|---|---|---|
| Current WSR | PDF/DOCX/Text | User upload / SharePoint / Email |
| Previous WSR | PDF/DOCX/Text | Historical repository |
| Historical WSRs | Optional | Database |
| Run Metadata | JSON | Project ID, Week date |

### 2.2 Outputs
Structured Markdown Output (strict schema):
- High Level Analysis
- Risks & Dependencies
- Progress Comparison from Previous Week
- Reporting Gaps
- Risks to Track in Risk Portal

Stored as:
- JSON (machine readable)
- Markdown (human readable)
- Governance DB record

## 3. Functional Modules

### 3.1 Document Processing Module
**Purpose:** Convert messy WSR files into structured analyzable text.

**Functional Rules**
- Detect and remove appendix section.
- Detect tables vs paragraphs.
- Preserve headings.
- Maintain week context.

**Output Schema**
```json
{
  "project_name": "",
  "reporting_date": "",
  "sections": {
    "summary": "",
    "milestones": "",
    "risks": "",
    "dependencies": "",
    "others": ""
  }
}
```

### 3.2 Risk Detection Engine
**Logic:**

Two-path detection:
- Path A — Structured WSR:
  - If Risks/Issues section exists: extract only from that section.
- Path B — Unstructured WSR:
  - If not present: keyword signal scan and create consolidated risk.

**Classification Rules**
| Condition | Classification |
|---|---|
| Owner + Mitigation + Due date | Controlled (exclude) |
| Closed/Resolved | Ignore |
| Missing any field | Uncontrolled |
| Partial fields | Partially Controlled |

### 3.3 Risk Normalization Engine
| Field | Rule |
|---|---|
| Status | Extract else N/A |
| Ageing | Calculate only if date exists |
| Impact | Timeline / Quality / Both |
| Due Date | Pick latest date |
| Mitigation | Missing/Vague if unclear |

### 3.4 Historical Comparison Engine
Compares current week vs previous week.

**Matching Strategy:**
- Semantic similarity (embedding), not keyword equality.

**Outputs**
| Condition | Result |
|---|---|
| Same risk | Progress update |
| Same description | Stagnant risk |
| Missing now | Risk closed |
| New risk | Newly introduced |

### 3.5 Reporting Quality Auditor
Strict validator using rule engine (not LLM reasoning).

Flags only when explicitly present:
| Rule | Trigger |
|---|---|
| Missing Owner | Owner field empty |
| Expired Due Date | Date < WSR date |
| Vague mitigation | Short generic phrases |
| Dependency no timeline | No ETA |

Must maintain 75% factual / 25% suggestion ratio.

### 3.6 Escalation Generator
Condition: Risk present in two consecutive weeks.

Generate statement format:
> Due to [cause], there will be impact on [effect]

No prediction allowed.

### 3.7 Output Formatter
Creates deterministic Markdown with:
- Fixed headings
- Fixed tables
- Empty section handling
- No extra text

## 4. Guardrail Enforcement Layer (Critical)
Runs after LLM generation.

| Check | Action |
|---|---|
| SLA detected | Remove line |
| Appendix content used | Regenerate/Remove |
| Hallucinated date | Remove |
| Missing section | Insert default text |
| Non factual statement | Reject response |

## 5. Non Functional Functionalities
| Attribute | Requirement |
|---|---|
| Determinism | Same input → same output |
| Latency | <15 sec per WSR |
| Auditability | Traceable extraction |
| Cost control | ≤2 LLM calls per WSR |
| Reliability | 99% structured output |


## 6. Prompt Compliance Mapping (Implemented)
- Appendix content excluded at preprocessing stage.
- SLA lines removed globally before extraction and before final output.
- Controlled and closed items excluded from primary risks/dependencies table.
- Structured path uses only explicit Risks/Dependencies sections; no keyword scan in that mode.
- Unstructured path produces a single consolidated risk/dependency statement.
- Output format fixed to required markdown sections and strict table schema.
- Missing information is represented as `N/A` or `No data available for this section.` without fabricated facts.
