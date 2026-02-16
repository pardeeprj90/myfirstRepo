# FRD - AI Delivery Assurance Agent

## Functional Requirements

1. **Input Support**
   - Accept current and previous week files (`pdf`, `pptx`, `docx`, `txt`)
   - Capture metadata: `account`, `project_name`, `week_date`

2. **Document Processing**
   - Extract text from files
   - Clean headers/footers-like repeats and whitespace noise
   - Chunk text with overlap and section inference

3. **Vectorization & Storage**
   - Generate embeddings via LangChain
   - Store chunks in Pinecone with metadata
   - Retrieve context with metadata filters

4. **Analysis**
   - Detect risks and dependencies using explicit-section-first logic
   - Use keyword fallback for unstructured data
   - Detect reporting gaps (owner/date/mitigation gaps)
   - Generate recommendations grounded on retrieved context

5. **Progress Tracking**
   - Compare current vs previous week extracted signals
   - Label signals as new/existing/no-longer-reported

6. **Orchestration**
   - Use LangGraph workflow nodes for deterministic execution sequence

## Non-Functional Requirements
- Readable code with comments and docstrings
- Production-friendly modularity
- Metadata traceability
