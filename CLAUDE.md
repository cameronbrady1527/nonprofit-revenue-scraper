# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a nonprofit data collection and analysis toolkit that scrapes financial data from ProPublica's Nonprofit Explorer API. The project focuses on identifying nonprofits with revenue between $250K-$1M and extracting executive compensation information from Form 990 tax filings.

**Key Features:**
- **Dual Architecture**: Sync and async processing options
- **AI-Powered PDF Parsing**: Gemini 2.5 Flash with OCR fallback
- **Real-Time GUI Monitoring**: Live statistics and error tracking
- **Comprehensive Error Categorization**: Distinguishes rate limits from legitimate no-data cases
- **Advanced Search Strategy**: ~138 search queries to overcome API limits

## Core Architecture

### Main Entry Points
- **`launch_with_monitor.py`** - **RECOMMENDED**: Unified launcher with real-time GUI monitoring
- **`scraper_launcher.py`** - Interactive launcher to choose sync/async, parsing method, and state
- **`nonprofit_data_scraper.py`** - Original sync scraper with comprehensive search strategies
- **`async_nonprofit_scraper.py`** - High-performance async scraper (5-10x faster)
- **`scraper_monitor.py`** - Real-time GUI monitoring dashboard
- **`simple_990_scraper.py`** - Simplified version without PDF parsing capabilities

### Performance Architectures

#### Async Scraper (Recommended for Large Datasets)
- **Concurrency**: 10 concurrent API calls + 3 concurrent PDF processes
- **Speed**: 5-10x faster than sync version
- **Features**: Real-time GUI monitoring, advanced error tracking
- **Best for**: Full state scrapes with thousands of organizations

#### Sync Scraper (Stable Original)
- **Approach**: Sequential processing with rate limiting
- **Features**: Proven reliability, comprehensive logging
- **Best for**: Smaller datasets, debugging, conservative processing

### PDF Parsing System
The project offers two PDF parsing approaches with intelligent fallback:

#### Gemini AI Parsing (Recommended)
- **Primary method**: Uses Google's Gemini 2.5 Flash model (gemini-2.5-flash-preview-05-20)
- **API**: Requires `GOOGLE_AI_API_KEY` environment variable
- **Features**: 
  - File API for optimal PDF handling with fallback to direct content parsing
  - Structured JSON output with Pydantic validation via `FinancialDataResponse` model
  - Automatic retry logic with exponential backoff
  - Rate limit detection and reporting
- **Fallback**: Automatically falls back to OCR if Gemini fails

#### OCR Parsing (Legacy)
- **Primary**: `pdfplumber` for text extraction
- **Fallback**: OCR with `pytesseract` and `pdf2image` for scanned documents
- **Data structures**: `ParsedFinancialData` dataclass with revenue, expenses, and executive compensation
- **Form handling**: Supports both pre-2008 and post-2008 Form 990 formats via `FormVersion` enum

### Advanced Search Strategy
Comprehensive approach to overcome ProPublica API's 10,000 result limit:
- **41 Nonprofit terms**: foundation, association, charity, hospital, etc.
- **2 State terms**: state name and code
- **95 Alphabetical searches**: single letters + strategic two-letter combinations
- **Total**: ~138 unique search queries per state
- **Deduplication**: Real-time EIN tracking to prevent processing duplicates

### Error Categorization & Monitoring
Advanced error tracking distinguishes between:
- **API**: ProPublica provided data directly ✅
- **AI**: Successfully extracted via Gemini/OCR ✅  
- **Rate Limits**: Gemini API quota exceeded or 429 errors ⚠️
- **Errors**: Download failures, parsing failures, network issues ❌
- **N/A**: Legitimately no data available (no PDF, no filings) ℹ️

### Real-Time GUI Monitor
Three-panel monitoring dashboard:
- **Top Left**: Progress bar, current activity, timing statistics
- **Top Right**: Data source breakdown, success rates, error categories
- **Bottom**: Live color-coded logs with auto-scrolling

### Core Files
- **`gemini_pdf_parser.py`** - Gemini AI PDF parsing with Pydantic models and File API
- **`form_990_parser.py`** - Legacy OCR parsing engine
- **`MONITOR_README.md`** - GUI monitoring documentation

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv nonprofit_scraper_env
nonprofit_scraper_env\Scripts\activate  # Windows
source nonprofit_scraper_env/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Set up Gemini AI API key (for AI parsing)
# Create .env file with: GOOGLE_AI_API_KEY=your_api_key_here
```

### Running the Tools

#### Recommended: GUI Monitoring
```bash
# Launch with real-time GUI monitoring (BEST EXPERIENCE)
python launch_with_monitor.py

# Monitor only (if running scraper separately)
python scraper_monitor.py
```

#### Direct Scraper Execution
```bash
# Interactive launcher (sync or async choice)
python scraper_launcher.py

# Original sync scraper
python nonprofit_data_scraper.py

# Async scraper directly
python async_nonprofit_scraper.py

# Simple scraper (no PDF parsing)
python simple_990_scraper.py
```

### Testing & Validation
No formal test framework is configured. Testing is done through:
- Manual execution of scrapers with sample data
- Parser validation with known Form 990 documents
- Output verification through Excel file inspection
- GUI monitoring for real-time error detection

## Key Dependencies
- **Core Processing**: `requests`, `aiohttp`, `asyncio`
- **Data & Export**: `pandas`, `openpyxl`, `numpy`
- **PDF Processing**: `pdfplumber`, `pytesseract`, `pdf2image`, `pypdfium2`
- **AI Integration**: `google-generativeai`, `pydantic`
- **User Interface**: `inquirer`, `tkinter` (GUI monitoring)
- **Environment**: `python-dotenv`, `logging`

## Data Flow
1. **Launch**: User chooses scraper type (sync/async), parsing method (Gemini/OCR), and state
2. **Search Phase**: Execute ~138 search queries across nonprofit terms, state terms, and alphabetical combinations
3. **Collection**: Gather unique EINs with real-time deduplication
4. **Processing**: Extract financial data using ProPublica API + PDF parsing (concurrent in async mode)
5. **Monitoring**: Real-time GUI updates showing progress, errors, and success rates
6. **Export**: Generate timestamped Excel files with comprehensive data and formatting

## Output Format
Excel files with columns: Organization Name, EIN, Filing Year, Total Revenue, Executive Compensation, plus computed numeric columns for analysis. Files include:
- Auto-adjusted column widths
- Revenue-sorted organization list
- Summary statistics (revenue/compensation ranges)
- Clear distinction between data sources (API vs AI vs N/A)

## Performance & Rate Limiting
- **Sync**: Built-in delays (0.3-1 second) with retry logic
- **Async**: Semaphore-controlled concurrency (10 API + 3 PDF concurrent)
- **Smart Rate Limiting**: Detects and reports API rate limits vs legitimate no-data cases
- **Graceful Interruption**: Saves partial results on Ctrl+C
- **Error Recovery**: Automatic fallback from Gemini to OCR parsing