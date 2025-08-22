# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a nonprofit data collection and analysis toolkit that scrapes financial data from ProPublica's Nonprofit Explorer API. The project focuses on identifying nonprofits with revenue between $250K-$1M and extracting executive compensation information from Form 990 tax filings.

## Core Architecture

### Main Entry Points
- `nonprofit_data_scraper.py` - Interactive scraper with state selection and comprehensive search strategies
- `simple_990_scraper.py` - Simplified version without PDF parsing capabilities  
- `form_990_parser.py` - Main PDF parsing and financial data extraction engine

### PDF Parsing System
The project offers two PDF parsing approaches with startup selection:

#### Gemini AI Parsing (Recommended)
- **Primary method**: Uses Google's Gemini 2.5 Flash model for intelligent PDF analysis
- **API**: Requires `GOOGLE_AI_API_KEY` environment variable
- **Output**: Structured JSON with Pydantic validation via `FinancialDataResponse` model
- **Features**: Fast, accurate, handles both text and scanned PDFs
- **Error handling**: Automatic retry logic with exponential backoff

#### OCR Parsing (Legacy)
- **Primary**: `pdfplumber` for text extraction
- **Fallback**: OCR with `pytesseract` and `pdf2image` for scanned documents
- **Data structures**: `ParsedFinancialData` dataclass with revenue, expenses, and executive compensation
- **Form handling**: Supports both pre-2008 and post-2008 Form 990 formats via `FormVersion` enum

### Search Strategy
The scraper overcomes ProPublica API's 10,000 result limit through multiple search approaches:
- Keyword-based searches (foundation, association, church, etc.)
- State-specific terms and major cities
- Alphabetical searches with single letters and combinations
- EIN-based deduplication to prevent double-counting

### Models Directory
Contains experimental and improved versions:
- `form_990_parser_v2.py` - Enhanced parser with better error handling
- `nonprofit_data_scraper_v2.py` - Improved scraper implementation
- `parser_test.py` - Testing utilities for parser validation
- `gemini_pdf_parser.py` - Gemini AI-based PDF parsing with Pydantic models

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv nonprofit_scraper_env
nonprofit_scraper_env\Scripts\activate  # Windows
source nonprofit_scraper_env/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### Running the Tools
```bash
# Main interactive scraper
python nonprofit_data_scraper.py

# Simple scraper (no PDF parsing)
python simple_990_scraper.py

# Test parser functionality (if available)
python models/parser_test.py
```

### Testing
No formal test framework is configured. Testing is done through:
- Manual execution of scrapers with sample data
- Parser validation with known Form 990 documents
- Output verification through Excel file inspection

## Key Dependencies
- `requests` - API communication with ProPublica
- `pandas` + `openpyxl` - Data processing and Excel export
- `pdfplumber` - Primary PDF text extraction
- `pytesseract` + `pdf2image` - OCR fallback for scanned PDFs
- `inquirer` - Interactive CLI state selection
- `logging` - Comprehensive progress tracking and debugging

## Data Flow
1. User selects state via interactive CLI
2. Multiple API searches executed with different strategies
3. Results filtered by revenue range ($250K-$1M)
4. Form 990 PDFs downloaded and parsed for compensation data
5. Data exported to timestamped Excel files with formatting

## Output Format
Excel files with columns: Organization Name, EIN, Filing Year, Total Revenue, Executive Compensation, and raw numeric values for analysis.

## Rate Limiting
Built-in delays (0.3-1 second) between API calls to respect ProPublica's servers. Includes retry logic for failed requests and graceful interruption handling.