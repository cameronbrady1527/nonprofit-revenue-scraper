import requests
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import re
from io import BytesIO
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import logging

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FormVersion(Enum):
    """Enum to distinguish between form versions"""
    PRE_2008 = "pre_2008"
    POST_2008 = "post_2008"
    UNKNOWN = "unknown"

@dataclass
class ParsedFinancialData:
    """Data structure to hold parsed financial information"""
    total_revenue: Optional[float] = None
    program_service_revenue: Optional[float] = None
    contributions_grants: Optional[float] = None
    investment_income: Optional[float] = None
    other_revenue: Optional[float] = None
    total_expenses: Optional[float] = None
    net_assets: Optional[float] = None
    
    # Executive compensation data
    executive_compensation: Dict[str, float] = None
    highest_paid_employee: Optional[float] = None
    
    # Metadata
    tax_year: Optional[int] = None
    organization_name: Optional[str] = None
    form_version: FormVersion = FormVersion.UNKNOWN
    confidence_score: float = 0.0
    
    def __post_init__(self):
        if self.executive_compensation is None:
            self.executive_compensation = {}

class Form990Parser:
    """
    Comprehensive Form 990 parser that handles both pre-2008 and post-2008 formats.
    
    The parser works in several stages:
    1. Document Analysis: Determines form version and structure
    2. Text Extraction: Uses OCR or direct text extraction
    3. Pattern Matching: Uses regex patterns specific to each form version
    4. Data Validation: Validates and cleans extracted data
    5. Confidence Scoring: Assigns confidence scores to extracted data
    """
    
    def __init__(self):
        # Compile regex patterns for better performance
        self._compile_patterns()
        
    def _compile_patterns(self):
        """
        Compile all regex patterns used for parsing.
        
        Why we use regex patterns:
        - Form 990s have consistent formatting and line structures
        - Numbers appear in predictable locations with specific formatting
        - Regex allows us to capture variations in spacing and formatting
        """
        
        # POST-2008 PATTERNS (more standardized)
        self.post_2008_patterns = {
            # Part I Summary patterns - these appear on the first page
            'total_revenue_part1': [
                r'Total revenue.*?[\s\$]+([\d,]+)',
                r'12\s+Total revenue.*?([\d,]+)',
                r'Line 12.*?Total revenue.*?([\d,]+)'
            ],
            
            # Part VIII detailed revenue patterns
            'total_revenue_part8': [
                r'Part VIII.*?Statement of Revenue.*?Total.*?([\d,]+)',
                r'12\s+Total revenue \(must equal Part VIII.*?line 12\).*?([\d,]+)',
                r'TOTAL REVENUE.*?([\d,]+)'
            ],
            
            # Specific revenue line items from Part VIII
            'contributions_grants': [
                r'1h\s+Total.*?contributions.*?([\d,]+)',
                r'Contributions.*?grants.*?line 1h.*?([\d,]+)',
                r'Total contributions.*?([\d,]+)'
            ],
            
            'program_service_revenue': [
                r'2g\s+Total.*?program service revenue.*?([\d,]+)',
                r'Program service revenue.*?line 2g.*?([\d,]+)',
                r'Total program service revenue.*?([\d,]+)'
            ],
            
            'investment_income': [
                r'3\s+Investment income.*?([\d,]+)',
                r'Line 3.*?Investment income.*?([\d,]+)'
            ],
            
            # Part VII Executive Compensation patterns
            'executive_compensation': [
                r'Part VII.*?Section A.*?Officers.*?Directors.*?Trustees.*?Key Employees.*?Highest Compensated Employees',
                r'(President|CEO|Executive Director|Chief Executive).*?([\d,]+)',
                r'Compensation.*?([\d,]+)'
            ],
            
            # Part IX Expenses
            'total_expenses': [
                r'25\s+Total functional expenses.*?([\d,]+)',
                r'Total expenses.*?line 25.*?([\d,]+)',
                r'TOTAL EXPENSES.*?([\d,]+)'
            ]
        }
        
        # PRE-2008 PATTERNS (less standardized, more variations)
        self.pre_2008_patterns = {
            'total_revenue': [
                r'Total revenue.*?([\d,]+)',
                r'REVENUE.*?TOTAL.*?([\d,]+)',
                r'Total support and revenue.*?([\d,]+)'
            ],
            
            'contributions': [
                r'Contributions.*?gifts.*?grants.*?([\d,]+)',
                r'Direct public support.*?([\d,]+)',
                r'Government grants.*?([\d,]+)'
            ],
            
            'program_revenue': [
                r'Program service revenue.*?([\d,]+)',
                r'Fees for services.*?([\d,]+)'
            ],
            
            'executive_compensation': [
                r'(President|CEO|Executive Director).*?compensation.*?([\d,]+)',
                r'Officers.*?compensation.*?([\d,]+)'
            ],
            
            'total_expenses': [
                r'Total expenses.*?([\d,]+)',
                r'EXPENSES.*?TOTAL.*?([\d,]+)'
            ]
        }
        
        # Compile all patterns for performance
        self._compiled_patterns = {}
        for version in ['post_2008_patterns', 'pre_2008_patterns']:
            pattern_dict = getattr(self, version)
            self._compiled_patterns[version] = {}
            for key, patterns in pattern_dict.items():
                self._compiled_patterns[version][key] = [
                    re.compile(pattern, re.IGNORECASE | re.DOTALL) 
                    for pattern in patterns
                ]

    def download_pdf_from_json(self, json_data: Dict, pdf_key: str) -> Optional[bytes]:
        """
        Download PDF from URL specified in JSON object.
        
        Args:
            json_data: Dictionary containing the PDF URL
            pdf_key: Key in the dictionary that contains the PDF URL
            
        Returns:
            PDF content as bytes, or None if download fails
        """
        try:
            pdf_url = json_data.get(pdf_key)
            if not pdf_url:
                logger.error(f"No URL found for key: {pdf_key}")
                return None
            
            logger.info(f"Downloading PDF from: {pdf_url}")
            
            # Strategy 1: Try with advanced browser-like headers and session warming
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Referer': 'https://projects.propublica.org/nonprofits/',
                'Cache-Control': 'max-age=0'
            }

            session = requests.Session()
            session.headers.update(headers)
            
            # Session warming - visit the main site first to look like a real user
            try:
                logger.debug("Warming session by visiting main site...")
                warm_response = session.get('https://projects.propublica.org/nonprofits/', timeout=10)
                if warm_response.status_code == 200:
                    logger.debug("Session warmed successfully")
                time.sleep(1)  # Brief pause between requests
            except Exception as e:
                logger.debug(f"Session warming failed (continuing anyway): {e}")
            
            response = session.get(pdf_url, timeout=30, allow_redirects=True)
            # response.raise_for_status()
            
            if response.status_code == 403:
                logger.warning("403 Forbidden on Strategy 1. Trying strategy 2 ...")

                # Strategy 2: Try without special headers
                simple_headers = {'User-Agent': 'python-requests/2.28.0'}
                response = session.get(pdf_url, headers=simple_headers, timeout=30, allow_redirects=True)

            if response.status_code == 403:
                logger.warning("Still receiving 403 - trying Strategy 3 (different session) ...")

                # Strategy 3: Try with a completely new session and different approach
                new_session = requests.Session()
                
                # Use different user agent and headers
                alt_headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'identity',  # Don't use compression
                    'Connection': 'keep-alive',
                    'Pragma': 'no-cache',
                    'Cache-Control': 'no-cache'
                }
                new_session.headers.update(alt_headers)
                
                # Try to get a different entry point first
                try:
                    # Extract organization ID from URL to visit their page first
                    import re
                    match = re.search(r'(\d{2}-\d{7})', pdf_url)
                    if match:
                        ein = match.group(1).replace('-', '')
                        org_url = f'https://projects.propublica.org/nonprofits/organizations/{ein}'
                        logger.debug(f"Visiting organization page first: {org_url}")
                        new_session.get(org_url, timeout=10)
                        time.sleep(2)
                except Exception as e:
                    logger.debug(f"Could not visit org page: {e}")
                
                response = new_session.get(pdf_url, timeout=30)

            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' in content_type and response.status_code == 200:
                logger.warning("Received HTML instead of PDF - possible redirect or login page")

                if b'pdf' in response.content.lower():
                    html_text = response.content.decode('utf-8', errors='ignore')
                    pdf_links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html_text, re.IGNORECASE)

                    if pdf_links:
                        new_pdf_url = pdf_links[0]
                        if not new_pdf_url.startswith('http'):
                            from urllib.parse import urljoin
                            new_pdf_url = urljoin(pdf_url, new_pdf_url)

                        logger.info(f"Found PDF link in HTML, trying: {new_pdf_url}")
                        response = session.get(new_pdf_url, timeout=30, allow_redirects=True)

            response.raise_for_status()


            # Verify it's actually a PDF
            if not response.content.startswith(b'%PDF'):
                if b'%PDF' in response.content[:1000]:
                    logger.warning("PDF marker found but not at start - proceeding anyway ...")
                else:
                    logger.error("Downloaded content is not a valid PDF")
                    logger.debug(f"Content starts with: {response.content[:100]}")
                    logger.debug(f"Content type: {response.headers.get('content-type')}")
                    return None

            logger.info(f"Successfully downloaded PDF ({len(response.content)} bytes)")
            return response.content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error downloading PDF: {str(e)}")
            return None
        
        except Exception as e:
            logger.error(f"Unexpected error downloading PDF: {str(e)}")
            return None

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> Tuple[str, bool]:
        """
        Extract text from PDF using multiple methods.
        
        This function implements a fallback strategy:
        1. Try pdfplumber first (fast, works for text-based PDFs)
        2. Fall back to OCR for scanned PDFs (slower but works on images)
        
        Args:
            pdf_bytes: PDF content as bytes
            
        Returns:
            Tuple of (extracted_text, is_ocr_used)
        """
        logger.info("Starting text extraction from PDF")
        
        # Method 1: Try pdfplumber first (for text-based PDFs)
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                text_content = ""
                page_count = len(pdf.pages)
                logger.info(f"PDF has {page_count} pages")
                
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_content += f"\n--- Page {page_num + 1} ---\n{page_text}"
                
                # If we extracted substantial text, use it
                if len(text_content.strip()) > 200:  # Minimum threshold for meaningful content
                    logger.info("Successfully extracted text using pdfplumber")
                    return text_content, False
                    
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {str(e)}")
        
        # Method 2: Fall back to OCR for scanned PDFs
        logger.info("Falling back to OCR extraction")
        return self._extract_text_with_ocr(pdf_bytes), True

    def _extract_text_with_ocr(self, pdf_bytes: bytes) -> str:
        """
        Extract text using OCR (Optical Character Recognition).
        
        OCR Process:
        1. Convert PDF pages to images
        2. Use Tesseract OCR to recognize text in images
        3. Combine text from all pages
        
        This is slower but necessary for scanned documents.
        """
        try:
            logger.info("Converting PDF to images for OCR")
            images = convert_from_bytes(pdf_bytes, dpi=300)  # Higher DPI for better OCR
            
            full_text = ""
            for page_num, image in enumerate(images):
                logger.info(f"Processing page {page_num + 1} with OCR")
                
                # Configure Tesseract for better accuracy
                custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,()$%- '
                
                page_text = pytesseract.image_to_string(image, config=custom_config)
                full_text += f"\n--- Page {page_num + 1} ---\n{page_text}"
            
            logger.info("OCR extraction completed")
            return full_text
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            return ""

    def determine_form_version(self, text: str) -> FormVersion:
        """
        Determine if this is a pre-2008 or post-2008 Form 990.
        
        Version Detection Strategy:
        - Look for specific indicators unique to each version
        - Post-2008 forms have Part VIII, Part VII structure
        - Pre-2008 forms have different section headers and organization
        
        Args:
            text: Extracted text from the PDF
            
        Returns:
            FormVersion enum indicating the form version
        """
        logger.info("Determining form version")
        
        # Post-2008 indicators (more reliable patterns)
        post_2008_indicators = [
            r'Part VIII.*Statement of Revenue',
            r'Part VII.*Officers.*Directors.*Trustees.*Key Employees',
            r'Schedule J.*Compensation Information',
            r'Part VI.*Governance.*Management.*Disclosure',
            r'990\s*\(2008\)|990\s*\(2009\)|990\s*\(201\d\)|990\s*\(202\d\)'  # Year indicators
        ]
        
        # Pre-2008 indicators
        pre_2008_indicators = [
            r'990\s*\(2001\)|990\s*\(2002\)|990\s*\(2003\)|990\s*\(2004\)|990\s*\(2005\)|990\s*\(2006\)|990\s*\(2007\)',
            r'Revenue.*Expenses.*and.*Changes.*in.*Net.*Assets',  # Old format header
            r'Part I.*Revenue.*Expenses.*and.*Changes'
        ]
        
        post_2008_score = sum(1 for pattern in post_2008_indicators 
                             if re.search(pattern, text, re.IGNORECASE))
        pre_2008_score = sum(1 for pattern in pre_2008_indicators 
                            if re.search(pattern, text, re.IGNORECASE))
        
        logger.info(f"Version scores - Post-2008: {post_2008_score}, Pre-2008: {pre_2008_score}")
        
        if post_2008_score > pre_2008_score and post_2008_score > 0:
            return FormVersion.POST_2008
        elif pre_2008_score > 0:
            return FormVersion.PRE_2008
        else:
            return FormVersion.UNKNOWN

    def extract_financial_data(self, text: str, form_version: FormVersion) -> ParsedFinancialData:
        """
        Extract financial data using version-specific patterns.
        
        This is the core parsing logic that:
        1. Selects appropriate patterns based on form version
        2. Applies regex patterns to find financial data
        3. Cleans and validates the extracted numbers
        4. Calculates confidence scores
        
        Args:
            text: Extracted text from PDF
            form_version: Detected form version
            
        Returns:
            ParsedFinancialData object with extracted information
        """
        logger.info(f"Extracting financial data for {form_version.value} form")
        
        data = ParsedFinancialData(form_version=form_version)
        
        # Select pattern set based on version
        if form_version == FormVersion.POST_2008:
            patterns = self._compiled_patterns['post_2008_patterns']
        else:
            patterns = self._compiled_patterns['pre_2008_patterns']
        
        # Extract each type of financial data
        extraction_results = {}

        # Revenue data extraction
        if form_version == FormVersion.POST_2008:
            # Try Part I summary first, then Part VIII detailed
            data.total_revenue = (self._extract_single_value(text, patterns.get('total_revenue_part1', [])) or
                                  self._extract_single_value(text, patterns.get('total_revenue_part8', [])))
            
        else:
            data.total_revenue = self._extract_single_value(text, patterns.get('total_revenue', []))
        
        data.contributions_grants = self._extract_single_value(text, patterns.get('contributions_grants', []) or patterns.get('contributions', []))
        data.program_service_revenue = self._extract_single_value(text, patterns.get('program_service_revenue', []) or patterns.get('program_revenue', []))
        data.investment_income = self._extract_single_value(text, patterns.get('investment_income', []))
        data.total_expenses = self._extract_single_value(text, patterns.get('total_expenses', []))
        
        # Executive compensation extraction (more complex)
        data.executive_compensation = self._extract_executive_compensation(text, patterns, form_version)
        
        # Extract organization metadata
        data.organization_name = self._extract_organization_name(text)
        data.tax_year = self._extract_tax_year(text)
        
        # Calculate confidence score
        data.confidence_score = self._calculate_confidence_score(data)
        
        logger.info(f"Extraction completed with confidence score: {data.confidence_score:.2f}")
        return data

    def _extract_single_value(self, text: str, patterns: List[re.Pattern]) -> Optional[float]:
        """
        Extract a single financial value using multiple pattern attempts.
        
        Pattern Matching Strategy:
        1. Try each pattern in order of specificity (most specific first)
        2. For each match, clean and validate the number
        3. Return the first valid match found
        
        Args:
            text: Text to search in
            patterns: List of compiled regex patterns
            
        Returns:
            Extracted value as float, or None if not found
        """
        for pattern in patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Clean the matched string and convert to float
                cleaned_value = self._clean_financial_value(match)
                if cleaned_value is not None:
                    logger.debug(f"Found value: {cleaned_value} using pattern: {pattern.pattern}")
                    return cleaned_value
        return None

    def _clean_financial_value(self, value_str: str) -> Optional[float]:
        """
        Clean and convert a financial value string to float.
        
        Cleaning Process:
        1. Remove common formatting: $, commas, parentheses
        2. Handle negative values (parentheses indicate negative)
        3. Validate the result is a reasonable number
        
        Args:
            value_str: Raw string extracted from text
            
        Returns:
            Cleaned float value or None if invalid
        """
        if not value_str:
            return None
            
        # Handle various string formats
        if isinstance(value_str, tuple):
            value_str = value_str[-1]  # Take the last element if it's a tuple
            
        # Remove common formatting
        cleaned = str(value_str).strip()
        
        # Check for negative values (often in parentheses)
        is_negative = cleaned.startswith('(') and cleaned.endswith(')')
        if is_negative:
            cleaned = cleaned[1:-1]  # Remove parentheses
        
        # Remove currency symbols and formatting
        cleaned = re.sub(r'[\$,\s]', '', cleaned)
        
        # Try to convert to float
        try:
            value = float(cleaned)
            if is_negative:
                value = -value
                
            # Sanity check: Form 990 values should be reasonable
            if abs(value) > 1e12:  # More than $1 trillion seems unreasonable
                logger.warning(f"Suspicious large value: {value}")
                return None
                
            return value
            
        except (ValueError, TypeError):
            logger.debug(f"Could not convert to float: {value_str}")
            return None

    def _extract_executive_compensation(self, text: str, patterns: Dict, 
                                      form_version: FormVersion) -> Dict[str, float]:
        """
        Extract executive compensation data.
        
        Executive Compensation Extraction:
        1. Look for Part VII (post-2008) or equivalent sections (pre-2008)
        2. Find officer/director names and titles
        3. Extract compensation amounts for each person
        4. Handle various title formats (CEO, President, Executive Director, etc.)
        
        This is more complex because:
        - Multiple people may be listed
        - Titles vary significantly
        - Compensation may be split across columns
        """
        compensation_data = {}
        
        if form_version == FormVersion.POST_2008:
            # Look for Part VII table structure
            part7_match = re.search(r'Part VII.*?Section A.*?Officers.*?Directors.*?Trustees.*?Key Employees.*?Highest Compensated Employees(.*?)(?=Part VIII|$)', 
                                   text, re.IGNORECASE | re.DOTALL)
            
            if part7_match:
                part7_text = part7_match.group(1)
                
                # Common executive titles and their variations
                executive_patterns = [
                    (r'(Chief Executive Officer|CEO).*?([\d,]+)', 'CEO'),
                    (r'(President)(?!.*Vice).*?([\d,]+)', 'President'),
                    (r'(Executive Director).*?([\d,]+)', 'Executive Director'),
                    (r'(Chief Financial Officer|CFO).*?([\d,]+)', 'CFO'),
                    (r'(Chief Operating Officer|COO).*?([\d,]+)', 'COO'),
                    (r'(Vice President).*?([\d,]+)', 'Vice President'),
                    (r'(Secretary).*?([\d,]+)', 'Secretary'),
                    (r'(Treasurer).*?([\d,]+)', 'Treasurer')
                ]
                
                for pattern, title in executive_patterns:
                    matches = re.findall(pattern, part7_text, re.IGNORECASE)
                    for match in matches:
                        if isinstance(match, tuple) and len(match) >= 2:
                            compensation = self._clean_financial_value(match[1])
                            if compensation is not None and compensation > 0:
                                compensation_data[title] = compensation
                                
        else:  # Pre-2008 format
            # Look for compensation sections in pre-2008 forms
            compensation_patterns = patterns.get('executive_compensation', [])
            for pattern in compensation_patterns:
                matches = pattern.findall(text)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        title = match[0]
                        compensation = self._clean_financial_value(match[1])
                        if compensation is not None and compensation > 0:
                            compensation_data[title] = compensation
        
        return compensation_data

    def _extract_organization_name(self, text: str) -> Optional[str]:
        """Extract organization name from the form header."""
        # Look for name patterns at the beginning of the form
        name_patterns = [
            r'Name of organization[:\s]+(.*?)(?:\n|EIN)',
            r'Legal name of organization[:\s]+(.*?)(?:\n|$)',
            r'^([A-Z][A-Za-z\s,\.]+(?:INC|CORP|FOUNDATION|FUND|SOCIETY|ASSOCIATION|ORGANIZATION))'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text[:2000], re.IGNORECASE | re.MULTILINE)  # Search in first 2000 chars
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and len(name) < 200:  # Reasonable name length
                    return name
        return None

    def _extract_tax_year(self, text: str) -> Optional[int]:
        """Extract tax year from the form."""
        # Look for year patterns
        year_patterns = [
            r'tax year (\d{4})',
            r'Tax year beginning.*?(\d{4})',
            r'Form 990.*?(\d{4})',
            r'calendar year (\d{4})'
        ]
        
        for pattern in year_patterns:
            match = re.search(pattern, text[:1000], re.IGNORECASE)
            if match:
                year = int(match.group(1))
                if 1990 <= year <= 2030:  # Reasonable year range
                    return year
        return None

    def _calculate_confidence_score(self, data: ParsedFinancialData) -> float:
        """
        Calculate a confidence score for the extracted data.
        
        Confidence Scoring Strategy:
        1. Check how many key fields were successfully extracted
        2. Validate relationships between fields (e.g., total revenue should be sum of components)
        3. Check for reasonable values (not too large or small)
        
        Score ranges:
        - 0.0-0.3: Low confidence (few fields extracted)
        - 0.3-0.7: Medium confidence (some fields with minor issues)
        - 0.7-1.0: High confidence (most fields extracted with validation)
        """
        score = 0.0
        max_score = 0.0
        
        # Core financial data checks
        if data.total_revenue is not None:
            score += 0.3
            max_score += 0.3
        
        if data.total_expenses is not None:
            score += 0.2
            max_score += 0.2
            
        if data.contributions_grants is not None:
            score += 0.1
            max_score += 0.1
            
        if data.program_service_revenue is not None:
            score += 0.1
            max_score += 0.1
            
        # Executive compensation checks
        if data.executive_compensation:
            score += 0.15
            max_score += 0.15
            
        # Metadata checks
        if data.organization_name:
            score += 0.1
            max_score += 0.1
            
        if data.tax_year:
            score += 0.05
            max_score += 0.05
            
        # Validation checks (bonus points for consistency)
        if (data.total_revenue and data.contributions_grants and 
            data.program_service_revenue):
            # Check if components roughly add up to total (within 20% variance)
            components_sum = (data.contributions_grants or 0) + (data.program_service_revenue or 0)
            if abs(components_sum - data.total_revenue) / data.total_revenue < 0.2:
                score += 0.1
                
        max_score += 0.1
        
        # Return normalized score
        return score / max_score if max_score > 0 else 0.0

    def parse_990_form(self, json_response: Dict, pdf_url_key: str) -> Dict:
        """
        Main parsing function that orchestrates the entire process.
        
        Complete Parsing Pipeline:
        1. Download PDF from JSON response
        2. Extract text (with OCR fallback)
        3. Determine form version
        4. Extract financial data using appropriate patterns
        5. Validate and return results
        
        Args:
            json_response: Dictionary containing PDF URL
            pdf_url_key: Key for the PDF URL in the dictionary
            
        Returns:
            Dictionary with parsed data and metadata
        """
        try:
            logger.info("Starting Form 990 parsing process")
            
            # Step 1: Download PDF
            pdf_bytes = self.download_pdf_from_json(json_response, pdf_url_key)
            if not pdf_bytes:
                return {"error": "Could not download PDF", "confidence": 0.0}
            
            # Step 2: Extract text
            text, used_ocr = self.extract_text_from_pdf(pdf_bytes)
            if not text or len(text.strip()) < 100:
                return {"error": "Could not extract meaningful text from PDF", "confidence": 0.0}
            
            # Step 3: Determine form version
            form_version = self.determine_form_version(text)
            if form_version == FormVersion.UNKNOWN:
                logger.warning("Could not determine form version, proceeding with post-2008 patterns")
                form_version = FormVersion.POST_2008
            
            # Step 4: Extract financial data
            parsed_data = self.extract_financial_data(text, form_version)
            
            # Step 5: Prepare results
            result = {
                "success": True,
                "form_version": form_version.value,
                "used_ocr": used_ocr,
                "confidence_score": parsed_data.confidence_score,
                "organization_name": parsed_data.organization_name,
                "tax_year": parsed_data.tax_year,
                "financial_data": {
                    "total_revenue": parsed_data.total_revenue,
                    "contributions_grants": parsed_data.contributions_grants,
                    "program_service_revenue": parsed_data.program_service_revenue,
                    "investment_income": parsed_data.investment_income,
                    "total_expenses": parsed_data.total_expenses
                },
                "executive_compensation": parsed_data.executive_compensation,
                "text_preview": text[:500] + "..." if len(text) > 500 else text
            }
            
            logger.info(f"Parsing completed successfully with confidence: {parsed_data.confidence_score:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error during parsing: {str(e)}")
            return {
                "error": f"Parsing failed: {str(e)}", 
                "confidence": 0.0,
                "success": False
            }

# Usage example and testing
def main():
    """Example usage of the Form 990 parser."""
    
    # Initialize the parser
    parser = Form990Parser()
    
    # Example API response with PDF URL
    api_response = {
        "organization_name": "Example Nonprofit Organization",
        "pdf_url": "https://example.com/form990.pdf",
        "tax_year": 2023,
        "filing_date": "2024-03-15"
    }

    api_response1 = {
        "tax_prd": 200912,
        "tax_prd_yr": 2009,
        "formtype": 0,
        "formtype_str": "990",
        "pdf_url": "https://projects.propublica.org/nonprofits/download-filing?path=2010_08_EO%2F14-2007220_990_200912.pdf"
    }
    
    # Parse the form
    result = parser.parse_990_form(api_response1, "pdf_url")
    
    # Display results
    print(json.dumps(result, indent=2, default=str))
    
    if result.get("success"):
        print(f"\n--- PARSING SUMMARY ---")
        print(f"Organization: {result.get('organization_name', 'Unknown')}")
        print(f"Tax Year: {result.get('tax_year', 'Unknown')}")
        print(f"Form Version: {result.get('form_version', 'Unknown')}")
        print(f"Confidence Score: {result.get('confidence_score', 0):.2%}")
        print(f"Used OCR: {result.get('used_ocr', False)}")
        
        financial_data = result.get('financial_data', {})
        if financial_data.get('total_revenue'):
            print(f"Total Revenue: ${financial_data['total_revenue']:,.2f}")
        
        exec_comp = result.get('executive_compensation', {})
        if exec_comp:
            print(f"Executive Compensation:")
            for title, amount in exec_comp.items():
                print(f"  {title}: ${amount:,.2f}")

if __name__ == "__main__":
    main()