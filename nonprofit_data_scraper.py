from typing import List
import requests
import pandas as pd
import time
import logging
import inquirer
import string
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from form_990_parser import Form990Parser
from gemini_pdf_parser import GeminiPDFParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

US_STATES = [
    ('Alabama', 'AL'),
    ('Alaska', 'AK'),
    ('Arizona', 'AZ'),
    ('Arkansas', 'AR'),
    ('California', 'CA'),
    ('Colorado', 'CO'),
    ('Connecticut', 'CT'),
    ('Delaware', 'DE'),
    ('Florida', 'FL'),
    ('Georgia', 'GA'),
    ('Hawaii', 'HI'),
    ('Idaho', 'ID'),
    ('Illinois', 'IL'),
    ('Indiana', 'IN'),
    ('Iowa', 'IA'),
    ('Kansas', 'KS'),
    ('Kentucky', 'KY'),
    ('Louisiana', 'LA'),
    ('Maine', 'ME'),
    ('Maryland', 'MD'),
    ('Massachusetts', 'MA'),
    ('Michigan', 'MI'),
    ('Minnesota', 'MN'),
    ('Mississippi', 'MS'),
    ('Missouri', 'MO'),
    ('Montana', 'MT'),
    ('Nebraska', 'NE'),
    ('Nevada', 'NV'),
    ('New Hampshire', 'NH'),
    ('New Jersey', 'NJ'),
    ('New Mexico', 'NM'),
    ('New York', 'NY'),
    ('North Carolina', 'NC'),
    ('North Dakota', 'ND'),
    ('Ohio', 'OH'),
    ('Oklahoma', 'OK'),
    ('Oregon', 'OR'),
    ('Pennsylvania', 'PA'),
    ('Rhode Island', 'RI'),
    ('South Carolina', 'SC'),
    ('South Dakota', 'SD'),
    ('Tennessee', 'TN'),
    ('Texas', 'TX'),
    ('Utah', 'UT'),
    ('Vermont', 'VT'),
    ('Virginia', 'VA'),
    ('Washington', 'WA'),
    ('West Virginia', 'WV'),
    ('Wisconsin', 'WI'),
    ('Wyoming', 'WY'),
    ('District of Columbia', 'DC'),
    ('Puerto Rico', 'PR'),
    ('US Virgin Islands', 'VI'),
    ('American Samoa', 'AS'),
    ('Guam', 'GU'),
    ('Northern Mariana Islands', 'MP')
]

class NonprofitRevenueScraper:
    def __init__(self, state_code, state_name, parsing_method="ocr"):
        self.state_code = state_code
        self.state_name = state_name
        self.parsing_method = parsing_method
        self.base_url = "https://projects.propublica.org/nonprofits/api/v2"
        self.session = requests.Session()
        self.results = []
        self.processed_eins = set()
        
        # Initialize parsers based on method
        if parsing_method == "gemini":
            try:
                self.gemini_parser = GeminiPDFParser()
                self.form_parser = Form990Parser()  # Keep OCR as fallback
                self.gemini_failures = 0  # Track consecutive Gemini failures
                logger.info("Initialized with Gemini PDF parsing (OCR fallback available)")
            except ValueError as e:
                logger.error(f"Failed to initialize Gemini parser: {e}")
                logger.info("Falling back to OCR parsing only")
                self.parsing_method = "ocr"  # Switch to OCR
                self.form_parser = Form990Parser()
        else:
            self.form_parser = Form990Parser()
            logger.info("Initialized with OCR PDF parsing")

    def get_eins_by_search(self, query, page=0) -> List[int]:
        """Get organization EINs using keyword search to work around total result limits from ProPublica API"""
        url = f"{self.base_url}/search.json?c_code%5Bid%5D=3&q={query}&state%5Bid%5D={self.state_code}&page={page}"

        eins = []

        try:
            response = self.session.get(url, timeout=10)
            
            # Check for 404 (no more pages) - this is normal, not an error
            if response.status_code == 404:
                logger.debug(f"No more pages available for query '{query}' at page {page}")
                return None  # Signal that we've reached the end
            
            response.raise_for_status()
            
            response_data = response.json()
            response_orgs = response_data.get("organizations", [])
            
            # If no organizations returned, we've reached the end
            if not response_orgs:
                logger.debug(f"No organizations found on page {page} for query '{query}'")
                return None
            
            for org in response_orgs:
                ein = org["ein"]
                if ein not in self.processed_eins:
                    eins.append(ein)
                    self.processed_eins.add(ein)  # Track processed EINs

            return eins

        except requests.RequestException as e:
            logger.error(f"Error fetching page {page} for query '{query}': {e}")
            raise requests.RequestException

    def get_organization_details(self, ein):
        """Get financial data for a specific organization"""
        # returns the JSON object
        url = f"{self.base_url}/organizations/{ein}.json"

        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            logger.error(f"Error fetching details for EIN {ein}: {e}")
            raise requests.RequestException

    def extract_latest_filing_info(self, org_details):
        """Extract the most recent Form 990 filing information with filing year, revenue, and compensation data"""

        filings_with_data = org_details.get("filings_with_data", [])
        filings_without_data = org_details.get("filings_without_data", [])
        
        logger.debug(f"Found {len(filings_with_data)} filings with data, {len(filings_without_data)} without data")
        
        # Debug: show all available filing years
        all_years_with = [f.get("tax_prd_yr", 0) for f in filings_with_data]
        all_years_without = [f.get("tax_prd_yr", 0) for f in filings_without_data]
        logger.debug(f"Years with data: {all_years_with}, Years without data: {all_years_without}")
        
        # Find the most recent filing from filings_with_data first (preferred)
        most_recent_year = 0
        most_recent_filing = None
        is_filing_with_data = False
        
        # First, try to find the most recent filing that HAS data
        for filing in filings_with_data:
            year = filing.get("tax_prd_yr", 0)
            if year > most_recent_year:
                most_recent_year = year
                most_recent_filing = filing
                is_filing_with_data = True
        
        # If no filings with data, or if filings_without_data has a more recent year, check those too
        for filing in filings_without_data:
            year = filing.get("tax_prd_yr", 0)
            if year > most_recent_year:
                most_recent_year = year
                most_recent_filing = filing
                is_filing_with_data = False
        
        logger.debug(f"Selected most recent filing: year {most_recent_year}, has_data: {is_filing_with_data}")
        
        # Handle case where no valid filing was found
        if most_recent_filing is None or most_recent_year == 0:
            logger.info(f"⚠️  No valid filing found - years with data: {all_years_with}, years without: {all_years_without}")
            
            # Try to use ANY filing if available, even with year 0
            all_filings = filings_with_data + filings_without_data
            if all_filings:
                most_recent_filing = all_filings[0]  # Use the first available filing
                most_recent_year = most_recent_filing.get("tax_prd_yr", 0)
                is_filing_with_data = most_recent_filing in filings_with_data
                logger.info(f"📋 Using fallback filing: year {most_recent_year}, has_data: {is_filing_with_data}")
            else:
                logger.error("No filings available at all")
                return 0, "N/A", "N/A", "none"

        if is_filing_with_data:
            # Data is available directly from ProPublica API - no PDF needed!
            revenue = most_recent_filing.get("totrevenue")
            expenses = most_recent_filing.get("totfuncexpns")
            comp_percent_of_expenses = most_recent_filing.get("pct_compnsatncurrofcr")
            
            # Check if we have usable data
            has_revenue = revenue is not None and revenue > 0
            
            # Debug: let's see what compensation data we actually have
            if comp_percent_of_expenses is None:
                logger.info(f"❓ Missing compensation data - expenses: {expenses}, comp_percent: {comp_percent_of_expenses}")
            
            # Fixed logic: allow 0 expenses and 0 compensation percentage
            has_compensation_data = (expenses is not None and 
                                   comp_percent_of_expenses is not None and comp_percent_of_expenses >= 0)
            
            if has_revenue:
                logger.debug(f"✅ Using ProPublica API revenue data: ${revenue:,.2f}")
            else:
                revenue = None  # Will trigger PDF parsing
                logger.debug("❌ No usable revenue data in ProPublica API")
                
            if has_compensation_data:
                executive_comp = round(expenses * comp_percent_of_expenses, 2)
                logger.debug(f"✅ Using ProPublica API compensation data: ${executive_comp:,.2f} ({comp_percent_of_expenses:.1%} of ${expenses:,.2f})")
            else:
                executive_comp = None  # Will trigger PDF parsing
                logger.debug("❌ No usable compensation data in ProPublica API")
            
            # If we have both values from API, we're done
            if has_revenue and has_compensation_data:
                logger.debug(f"🎉 Complete data from ProPublica API - no PDF parsing needed!")
                return most_recent_year, revenue, executive_comp, "api"
            
            # If we only have partial data from API, we'll try PDF for the missing pieces
            if has_revenue or has_compensation_data:
                logger.debug(f"Partial data from API (revenue: {has_revenue}, compensation: {has_compensation_data}), checking for PDF")
                
                # Check if PDF is actually available before trying to parse
                pdf_url = most_recent_filing.get("pdf_url")
                if pdf_url and pdf_url != "null" and pdf_url.strip():
                    logger.debug(f"📄 PDF available, trying to parse for missing data")
                    try:
                        pdf_revenue, pdf_exec_comp = self.extract_financials_from_pdf(most_recent_filing)
                        
                        # Use API data when available, PDF data for missing pieces
                        final_revenue = revenue if has_revenue else (pdf_revenue if pdf_revenue != "N/A" else "N/A")
                        final_exec_comp = executive_comp if has_compensation_data else (pdf_exec_comp if pdf_exec_comp != "N/A" else "N/A")
                        
                        # Determine data source - hybrid if we used both, otherwise pdf if we got new data
                        source = "api" if has_revenue and has_compensation_data else ("pdf" if (pdf_revenue != "N/A" or pdf_exec_comp != "N/A") else "api")
                        return most_recent_year, final_revenue, final_exec_comp, source
                        
                    except Exception as e:
                        logger.warning(f"PDF parsing failed for partial data case: {e}")
                        # Return what we have from API, N/A for missing
                        final_revenue = revenue if has_revenue else "N/A"
                        final_exec_comp = executive_comp if has_compensation_data else "N/A"
                        return most_recent_year, final_revenue, final_exec_comp, "api"
                else:
                    logger.debug("❌ No PDF available for additional data extraction")
                    # Return what we have from API, N/A for missing
                    final_revenue = revenue if has_revenue else "N/A"
                    final_exec_comp = executive_comp if has_compensation_data else "N/A"
                    return most_recent_year, final_revenue, final_exec_comp, "api"

        else:
            # No API data available, try PDF parsing if PDF exists
            pdf_url = most_recent_filing.get("pdf_url") if most_recent_filing else None
            
            if pdf_url and pdf_url != "null" and pdf_url.strip():
                logger.debug(f"📄 No API data available, attempting PDF parsing for filing year {most_recent_year}")
                try:
                    revenue, executive_comp = self.extract_financials_from_pdf(most_recent_filing)
                    
                    # If both values are N/A, log the issue but continue
                    if revenue == "N/A" and executive_comp == "N/A":
                        logger.warning(f"Could not extract financial data from PDF for EIN - filing year {most_recent_year}")
                        logger.debug(f"PDF URL was: {pdf_url}")
                        return most_recent_year, revenue, executive_comp, "none"
                    else:
                        return most_recent_year, revenue, executive_comp, "pdf"
                        
                except Exception as e:
                    revenue, executive_comp = "N/A", "N/A"
                    logger.error(f"Error parsing data from most recent filing year {most_recent_year}: {e}")
                    logger.debug("Returning default values (N/A) for revenue and executive compensation")
                    return most_recent_year, revenue, executive_comp, "none"
            else:
                logger.info(f"No PDF available for filing year {most_recent_year}, returning N/A values")
                revenue, executive_comp = "N/A", "N/A"
                return most_recent_year, revenue, executive_comp, "none"

    def extract_financials_from_pdf(self, filing):
        """Extract executive compensation from various possible fields using either OCR or Gemini"""
        try:
            if self.parsing_method == "gemini":
                # Check if we should fall back to OCR due to too many Gemini failures
                if self.gemini_failures >= 5:
                    logger.warning("Too many consecutive Gemini failures, switching to OCR for this filing")
                    return self._parse_with_ocr(filing)
                
                # Try Gemini first
                pdf_bytes = self._download_pdf_for_gemini(filing)
                if pdf_bytes:
                    result = self.gemini_parser.parse_with_retry(pdf_bytes)
                    
                    if result.get("success"):
                        revenue = result.get("total_revenue")
                        exec_comp = result.get("total_executive_compensation")
                        
                        # Handle None values
                        if revenue is None:
                            revenue = "N/A"
                        if exec_comp is None:
                            exec_comp = "N/A"
                        
                        # Reset failure counter on success
                        self.gemini_failures = 0
                        logger.info(f"Gemini extraction - Revenue: {revenue}, Executive Compensation: {exec_comp}")
                        return revenue, exec_comp
                    else:
                        self.gemini_failures += 1
                        logger.error(f"Gemini parsing failed: {result.get('error', 'Unknown error')}")
                        
                        # Try OCR as fallback for this specific filing
                        logger.info("Falling back to OCR for this filing")
                        return self._parse_with_ocr(filing)
                else:
                    self.gemini_failures += 1
                    logger.error("Could not download PDF for Gemini parsing")
                    
                    # Try OCR as fallback for this specific filing
                    logger.info("Falling back to OCR for this filing")
                    return self._parse_with_ocr(filing)
            else:
                # Use OCR parsing (legacy method)
                return self._parse_with_ocr(filing)
        
        except Exception as e:
            logger.error(f"Error parsing data from filing year {filing.get('tax_prd_yr', 'Unknown')} using {self.parsing_method}: {e}")
            return "N/A", "N/A"
    
    def _parse_with_ocr(self, filing):
        """Parse using OCR method"""
        try:
            result = self.form_parser.parse_990_form(filing, "pdf_url")
            
            if result.get("success"):
                financial_data = result.get("financial_data", {})
                executive_comp = result.get("executive_compensation", {})
                
                revenue = financial_data.get("total_revenue", "N/A")
                
                # Calculate total executive compensation
                exec_comp = "N/A"
                if executive_comp:
                    total_comp = sum(executive_comp.values())
                    if total_comp > 0:
                        exec_comp = total_comp

                if revenue != "N/A" and exec_comp != "N/A":
                    logger.debug(f"OCR extraction - Revenue: ${revenue:,.2f}, Executive Compensation: ${exec_comp:,.2f}")
                else:
                    logger.warning(f"Could not extract complete financial data from PDF for tax year {filing.get('tax_prd_yr', 'Unknown')}")

                return revenue, exec_comp
            else:
                logger.error(f"OCR parsing failed: {result.get('error', 'Unknown error')}")
                return "N/A", "N/A"
                
        except Exception as e:
            logger.error(f"OCR parsing error: {e}")
            return "N/A", "N/A"
    
    def _download_pdf_for_gemini(self, filing):
        """Download PDF bytes for Gemini parsing with enhanced error handling"""
        try:
            pdf_url = filing.get("pdf_url")
            if not pdf_url:
                logger.error("No PDF URL found in filing")
                return None
            
            # Use the same download strategy as the main parser
            if hasattr(self, 'form_parser'):
                pdf_bytes = self.form_parser.download_pdf_from_json(filing, "pdf_url")
            else:
                # Fallback: create a temporary parser just for downloading
                from form_990_parser import Form990Parser
                temp_parser = Form990Parser()
                pdf_bytes = temp_parser.download_pdf_from_json(filing, "pdf_url")
            
            if pdf_bytes and pdf_bytes.startswith(b'%PDF'):
                return pdf_bytes
            else:
                logger.error("Could not download valid PDF content")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading PDF for Gemini: {e}")
            return None

    def process_search_results(self, query):
        """Process all pages for a given search query"""
        logger.info(f"Processing search query: '{query}'")
        page = 0
        result_eins = []
        consecutive_errors = 0

        while consecutive_errors < 3:  # Stop after 3 consecutive errors
            try:
                incoming_eins = self.get_eins_by_search(query, page)

                if incoming_eins is None:
                    # Reached end of available pages
                    logger.info(f"Reached end of results for query '{query}' at page {page}")
                    break
                elif incoming_eins:  # Non-empty list
                    result_eins.extend(incoming_eins)  # Flatten the list
                    consecutive_errors = 0  # Reset error counter
                    
                    logger.debug(f"Found {len(incoming_eins)} new EINs on page {page} for query '{query}'")
                else:
                    # Empty list, but not None - continue to next page
                    logger.debug(f"No new EINs found on page {page} for query '{query}'")
                    
            except requests.RequestException as e:
                logger.error(f"Error getting the EINs for organizations on page {page}: {e}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    logger.warning(f"Too many consecutive errors for query '{query}', stopping search")
                    break

            page += 1

        logger.info(f"Query '{query}' completed: {len(result_eins)} unique EINs found across {page} pages")

        # Process each EIN with rate limiting and progress tracking
        api_count = 0
        pdf_count = 0
        
        for i, ein in enumerate(result_eins):
            try:
                org_details = self.get_organization_details(ein)

                name = org_details["organization"]["name"]
                filing_year, revenue, exec_comp, data_source = self.extract_latest_filing_info(org_details)

                self.results.append([name, ein, filing_year, revenue, exec_comp])
                
                # Track data sources
                if data_source == "api":
                    api_count += 1
                elif data_source == "pdf":
                    pdf_count += 1
                
                # Format values for display
                rev_display = f"${revenue:,.0f}" if isinstance(revenue, (int, float)) else revenue
                comp_display = f"${exec_comp:,.0f}" if isinstance(exec_comp, (int, float)) else exec_comp
                
                # Show individual organization progress with data source
                source_icon = "🔢" if data_source == "api" else "🤖" if data_source == "pdf" else "❓"
                print(f"  {source_icon} {name[:40]:<40} | Rev: {rev_display:<12} | Comp: {comp_display:<12}")
                
                # Show summary progress every 25 organizations
                if (i + 1) % 25 == 0:
                    print(f"  📊 Progress: {i + 1}/{len(result_eins)} | API: {api_count} | AI: {pdf_count} | N/A: {(i + 1) - api_count - pdf_count}")
                
                # Add delay between requests to avoid rate limiting
                if i > 0 and i % 10 == 0:  # Every 10 requests
                    logger.debug(f"Rate limiting: processed {i} organizations, pausing...")
                    time.sleep(2)  # 2 second pause
                else:
                    time.sleep(0.5)  # 500ms between each request
                
            except requests.RequestException as e:
                logger.error(f"Error getting the organization details from the API for EIN {ein}")
            except Exception as e:
                logger.error(f"Unexpected error processing EIN {ein}: {e}")
        
        # Final summary for this query
        total_processed = len(result_eins)
        na_count = total_processed - api_count - pdf_count
        print(f"  ✅ Query '{query}' complete: {total_processed} orgs | API: {api_count} | AI: {pdf_count} | N/A: {na_count}")


    def scrape_nonprofits_segmented(self):
        """Main scraping function using multiple targeted searches to work around the 10K rate limit"""
        logger.info(f"Starting segmented {self.state_name} nonprofit data collection ...")

        common_nonprofit_terms = [
            "foundation", "association", "society", "institute", "center", "council",
            "trust", "fund", "alliance", "coalition", "network", "group", "organization",
            "charity", "church", "temple", "synagogue", "school", "college", "university",
            "hospital", "health", "medical", "community", "family", "children", "youth", "project",
            "arts", "museum", "library", "research", "education", "housing", "veterans",
            "services", "support", "relief", "development", "international", "american"
        ]

        state_terms = [self.state_name.lower(), self.state_code.lower()]

        # TODO: add major cities .... maybe separate this into a function
        
        all_terms = common_nonprofit_terms + state_terms

        for term in all_terms:
            logger.info(f"Searching for nonprofits with term: '{term}'")
            self.process_search_results(term)
            time.sleep(1)

        logger.info("Starting alphabetical search ...")
        alphabet_searches = list(string.ascii_lowercase) + [
            "al", "am", "an", "ar", "as", "at", "ca", "ce", "ch", "ci", "co", "cr",
            "de", "di", "do", "ea", "ed", "el", "em", "en", "ex", "fa", "fi", "fo",
            "fr", "ge", "gl", "go", "gr", "ha", "he", "hi", "ho", "hu", "in", "is",
            "ja", "jo", "ka", "ki", "la", "le", "li", "lo", "ma", "me", "mi", "mo",
            "na", "ne", "no", "of", "op", "or", "pa", "pe", "pr", "qu", "ra", "re",
            "ri", "ro", "sa", "sc", "se", "sh", "so", "st", "su", "ta", "te", "th",
            "ti", "to", "tr", "un", "up", "ur", "va", "vi", "wa", "we", "wi", "wo", "yo"
        ]

        for search_term in alphabet_searches:
            logger.info(f"Alphabetical search: '{search_term}'")
            self.process_search_results(search_term)
            time.sleep(0.5)

        logger.info(f"Collection complete. Found {len(self.results)} unique nonprofits in target revenue range")
        logger.info(f"Total unique organizations processed: {len(self.processed_eins)}")

    def save_to_excel(self, filename=None):
        """Save results to Excel file in output directory"""
        import os
        from datetime import datetime
        
        if not self.results:
            logger.warning("No results to save")
            print("❌ No results to save")
            return
        
        # Create output directory if it doesn't exist
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_state_name = self.state_name.replace(" ", "_").replace("(", "").replace(")", "")
            filename = f"nonprofit_data_{clean_state_name}_{self.parsing_method}_{timestamp}.xlsx"
        
        filepath = os.path.join(output_dir, filename)
        
        try:
            # Create DataFrame
            df = pd.DataFrame(self.results, columns=[
                'Organization Name', 
                'EIN', 
                'Filing Year', 
                'Total Revenue', 
                'Executive Compensation'
            ])
            
            # Add summary columns for easier analysis
            df['Revenue_Numeric'] = pd.to_numeric(df['Total Revenue'], errors='coerce')
            df['Compensation_Numeric'] = pd.to_numeric(df['Executive Compensation'], errors='coerce')
            
            # Sort by revenue (descending)
            df = df.sort_values('Revenue_Numeric', ascending=False, na_position='last')
            
            # Save to Excel with formatting
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Nonprofit Data', index=False)
                
                # Get the workbook and worksheet
                workbook = writer.book
                worksheet = writer.sheets['Nonprofit Data']
                
                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            logger.info(f"✅ Results saved to: {filepath}")
            print(f"✅ Results saved to: {filepath}")
            print(f"📊 Total organizations saved: {len(df)}")
            
            # Show some summary stats
            valid_revenue = df['Revenue_Numeric'].dropna()
            valid_compensation = df['Compensation_Numeric'].dropna()
            
            if len(valid_revenue) > 0:
                print(f"💰 Revenue range: ${valid_revenue.min():,.0f} - ${valid_revenue.max():,.0f}")
            if len(valid_compensation) > 0:
                print(f"👥 Compensation range: ${valid_compensation.min():,.0f} - ${valid_compensation.max():,.0f}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")
            print(f"❌ Error saving to Excel: {e}")
            return None


def select_parsing_method():
    """Interactive parsing method selection menu"""
    print("\n🤖 PDF Parsing Method Selection")
    print("=" * 50)
    print("Choose how to extract financial data from PDFs when ProPublica data is unavailable:\n")
    
    choices = [
        "Gemini AI (Recommended - Fast and accurate)",
        "OCR (Legacy - Slower, requires Tesseract installation)"
    ]
    
    questions = [
        inquirer.List('method',
                      message="Choose parsing method (use arrow keys, press Enter to select)",
                      choices=choices,
                      carousel=True)
    ]
    
    try:
        answers = inquirer.prompt(questions)
        if not answers:
            print("\nOperation cancelled.")
            return None
        
        selected = answers['method']
        
        if "Gemini" in selected:
            # Check for API key
            api_key = os.getenv('GOOGLE_AI_API_KEY')
            if not api_key:
                print("\n⚠️  Warning: GOOGLE_AI_API_KEY not found in .env file.")
                print("Please add your Gemini API key to the .env file:")
                print("GOOGLE_AI_API_KEY=your-api-key-here")
                print("You can get an API key at: https://makersuite.google.com/app/apikey")
                
                continue_anyway = inquirer.confirm("Continue anyway? (Gemini parsing will fail without API key)")
                if not continue_anyway:
                    return None
            else:
                print(f"✅ Gemini API key loaded from .env file")
            return "gemini"
        else:
            return "ocr"
    
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None

def select_state():
    """Interactive state selection menu"""
    print("\n🏛️  Nonprofit Data Scraper")
    print("=" * 50)
    print("Select a state to scrape nonprofit data for organizations\nwith revenue between 250K - $1M\n")

    # create choices list with state names for display
    choices = [f"{name} ({code})" for name, code in US_STATES]

    questions = [
        inquirer.List('state',
                      message="Choose a state (use arrow keys, press Enter to select)",
                      choices=choices,
                      carousel=True)
    ]

    try:
        answers = inquirer.prompt(questions)
        if not answers:
            print("\nOperation cancelled.")
            return None, None
        
        selected = answers['state']

        # extract state code from selection
        state_code = selected.split('(')[-1].rstrip(')')
        state_name = selected.split(' (')[0]

        return state_code, state_name
    
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None, None

def main():
    try:
        # Select parsing method first
        parsing_method = select_parsing_method()
        if not parsing_method:
            return
            
        # Select state
        state_code, state_name = select_state()
        if not state_code:
            return
        
        print(f"\n✅ Selected: {state_name} ({state_code})")
        print(f"🤖 PDF Parsing Method: {parsing_method.upper()}")
        print(f"🚀 Starting data collection for {state_name} ...")
        print(f"📊 Looking for nonprofits with revenue between $250K - $1M")
        print(f"⏱️ This may take several hours. Press Ctrl+C to stop and save partial results.\n")

        # initialize and run scraper with selected parsing method
        scraper = NonprofitRevenueScraper(state_code, state_name, parsing_method)
        
        scraper.scrape_nonprofits_segmented()
        
        # Save results on normal completion
        if scraper.results:
            print(f"\n💾 Saving {len(scraper.results)} results...")
            scraper.save_to_excel()
        else:
            print("\n❌ No results to save")


    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        print("\n\n🛑 Script interrupted by user")

        if 'scraper' in locals() and scraper.results:
            logger.info(f"Saving {len(scraper.results)} results collected so far ...")
            print(f"💾 Saving {len(scraper.results)} results collected so far ...")

            scraper.save_to_excel()
        print("👋 Goodbye!")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if 'scraper' in locals() and scraper.results:
            logger.info(f"Saving {len(scraper.results)} results collected so far ...")
            print("💾 Saving {len(scraper.results)} results collected so far ...")
            
            scraper.save_to_excel()

if __name__ == "__main__":
    main()