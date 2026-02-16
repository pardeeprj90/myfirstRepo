# Technical Design - WSR Analysis Agent

## Stack
- LangChain
- LangGraph
- Pinecone

## Core Components

1. `extract_wsr_text_from_file`
   - Handles pdf/pptx/docx/txt extraction

2. `clean_wsr_text`
   - Removes noise and normalizes content

3. `chunk_wsr_text`
   - Splits content into overlap chunks and attaches metadata

4. Pinecone integration (`_get_vector_store`)
   - Creates/uses index
   - Stores and queries vectorized chunks

5. Analysis helpers
   - `_extract_signal_lines`
   - `_detect_reporting_gaps`
   - `_recommend_with_llm`
   - `_compare_progress`

6. LangGraph workflow
   - `preprocess_current`
   - `preprocess_previous`
   - `upsert_documents`
   - `retrieve_history`
   - `analyze_current`
   - `analyze_previous`
   - `compare_weeks`
   - `build_report`

## Output Contract
- `current_week_analysis`
- `previous_week_analysis`
- `progress_comparison`
- `retrieved_history_count`
