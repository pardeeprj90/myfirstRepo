# WSR Analysis Agent

Production-focused Weekly Status Report analysis agent built with:
- LangChain
- LangGraph
- Pinecone

## Required Files

```text
.
├── src/
│   └── wsr_assurance/
│       ├── workflow.py
│       ├── delivery_assurance.py
│       └── __init__.py
├── wsr_agent_workflow.py
├── delivery_assurance_agent.py
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables
- `OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX` (optional)
- `PINECONE_CLOUD` (optional)
- `PINECONE_REGION` (optional)

## Core Flow
1. Upload/register WSR file.
2. Analyze current file.
3. Auto-pick previous week file (same account + project) if available.
4. Generate risks, dependencies, gaps, recommendations, and progress comparison.


## Dependency Baseline
- This project tracks modern LangChain/LangGraph package lines (`langchain>=0.3`, `langgraph>=0.3`).
- Imports are split-package style (`langchain_core`, `langchain_openai`, `langchain_text_splitters`, `langchain_pinecone`), aligned with current releases.
