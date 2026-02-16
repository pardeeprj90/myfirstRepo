# BRD - Weekly Status Report Analysis Agent

## Problem Statement
Delivery Assurance teams spend significant time manually reviewing weekly WSR files and may miss risks/dependencies in unstructured content.

## Business Need
Create an AI agent that automates WSR analysis for current and previous week reports using retrieval-backed context and consistent rules.

## Scope
### In Scope
- Multi-format WSR ingestion: PDF, PPTX, DOCX, TXT
- Data cleaning and chunking
- Metadata tagging (`account`, `project_name`, `week_date`)
- Pinecone vector storage and filtered retrieval
- Risk/dependency extraction
- Reporting gap identification
- Recommendation generation
- Previous-week progress tracking

### Out of Scope
- OCR engine implementation
- Automatic ticket creation in external tools

## Success Criteria
- Faster weekly WSR review
- Improved consistency of risk/dependency identification
- Clear progress tracking from previous week


## File Storage Strategy
- User uploads file through UI (no manual path input).
- Backend stores file in server/object storage and registers metadata.
- Registry returns `file_id` used for analysis calls.
- Previous week file is auto-selected by same account/project with nearest earlier `week_date`.
