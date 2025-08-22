import asyncio
import aiohttp
import time
import logging
from typing import List, Tuple
import pandas as pd
from datetime import datetime
import os
import json
from dotenv import load_dotenv

# Import the existing parsers (we'll adapt them)
from form_990_parser import Form990Parser
from gemini_pdf_parser import GeminiPDFParser

logger = logging.getLogger(__name__)

class AsyncNonprofitScraper:
    """Async version of the nonprofit scraper for much faster processing"""
    
    def __init__(self, state_code: str, state_name: str, parsing_method: str = "gemini", 
                 max_concurrent_api: int = 10, max_concurrent_pdf: int = 3):
        self.state_code = state_code
        self.state_name = state_name
        self.parsing_method = parsing_method
        self.base_url = "https://projects.propublica.org/nonprofits/api/v2"
        
        # Concurrency limits
        self.api_semaphore = asyncio.Semaphore(max_concurrent_api)
        self.pdf_semaphore = asyncio.Semaphore(max_concurrent_pdf)
        
        # Results storage
        self.results = []
        self.processed_eins = set()
        
        # Progress tracking
        self.total_orgs = 0
        self.completed_orgs = 0
        self.api_count = 0
        self.pdf_count = 0
        self.na_count = 0
        self.error_count = 0
        self.rate_limit_count = 0
        self.start_time = None
        self.current_query = ""
        
        # Monitor integration
        self.stats_file = "scraper_stats.json"
        self.logs_file = "scraper_logs.txt"
        
        # Initialize parsers
        if parsing_method == "gemini":
            try:
                self.gemini_parser = GeminiPDFParser()
                self.form_parser = Form990Parser()
                logger.info("Initialized with Gemini PDF parsing (OCR fallback available)")
            except ValueError as e:
                logger.error(f"Failed to initialize Gemini parser: {e}")
                logger.info("Falling back to OCR parsing only")
                self.parsing_method = "ocr"
                self.form_parser = Form990Parser()
        else:
            self.form_parser = Form990Parser()
            logger.info("Initialized with OCR PDF parsing")
    
    def update_monitor_stats(self):
        """Update the monitor with current statistics"""
        try:
            elapsed_time = time.time() - self.start_time if self.start_time else 0
            
            stats = {
                'total_orgs': self.total_orgs,
                'completed_orgs': self.completed_orgs,
                'api_count': self.api_count,
                'pdf_count': self.pdf_count,
                'na_count': self.na_count,
                'rate_limit_count': self.rate_limit_count,
                'error_count': self.error_count,
                'current_query': self.current_query,
                'elapsed_time': elapsed_time,
                'state_name': self.state_name,
                'parsing_method': self.parsing_method
            }
            
            with open(self.stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to update monitor stats: {e}")
    
    def log_to_monitor(self, message: str, level: str = "INFO"):
        """Log a message to the monitor"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {level}: {message}\n"
            
            with open(self.logs_file, "a", encoding="utf-8") as f:
                f.write(formatted_message)
        except Exception as e:
            logger.debug(f"Failed to log to monitor: {e}")
    
    async def get_eins_by_search_async(self, session: aiohttp.ClientSession, query: str, page: int = 0) -> List[int]:
        """Async version of EIN search"""
        url = f"{self.base_url}/search.json?c_code%5Bid%5D=3&q={query}&state%5Bid%5D={self.state_code}&page={page}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 404:
                    return None  # End of pages
                
                response.raise_for_status()
                data = await response.json()
                response_orgs = data.get("organizations", [])
                
                if not response_orgs:
                    return None
                
                eins = []
                for org in response_orgs:
                    ein = org["ein"]
                    if ein not in self.processed_eins:
                        eins.append(ein)
                        self.processed_eins.add(ein)
                
                return eins
                
        except Exception as e:
            logger.error(f"Error fetching page {page} for query '{query}': {e}")
            return []
    
    async def get_organization_details_async(self, session: aiohttp.ClientSession, ein: int) -> dict:
        """Async version of organization details fetch"""
        async with self.api_semaphore:  # Rate limiting
            url = f"{self.base_url}/organizations/{ein}.json"
            
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response.raise_for_status()
                    return await response.json()
            except Exception as e:
                logger.error(f"Error fetching details for EIN {ein}: {e}")
                raise
    
    async def download_pdf_async(self, session: aiohttp.ClientSession, pdf_url: str) -> bytes:
        """Async PDF download with session warming"""
        try:
            # Session warming
            try:
                async with session.get('https://projects.propublica.org/nonprofits/', timeout=aiohttp.ClientTimeout(total=5)) as warm_response:
                    pass  # Just establish connection
            except:
                pass  # Continue if warming fails
            
            # Download PDF with better headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Referer': 'https://projects.propublica.org/nonprofits/',
            }
            
            async with session.get(pdf_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 403:
                    # Try alternative approach
                    alt_headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
                        'Accept': '*/*',
                    }
                    async with session.get(pdf_url, headers=alt_headers, timeout=aiohttp.ClientTimeout(total=30)) as alt_response:
                        alt_response.raise_for_status()
                        content = await alt_response.read()
                else:
                    response.raise_for_status()
                    content = await response.read()
                
                if not content.startswith(b'%PDF'):
                    raise ValueError("Downloaded content is not a valid PDF")
                
                return content
                
        except Exception as e:
            logger.debug(f"PDF download failed: {e}")
            raise
    
    async def extract_financials_async(self, session: aiohttp.ClientSession, filing: dict) -> Tuple[str, str, str]:
        """Async version of financial extraction - returns (revenue, exec_comp, error_type)"""
        async with self.pdf_semaphore:  # Limit concurrent PDF processing
            try:
                pdf_url = filing.get("pdf_url")
                if not pdf_url or pdf_url == "null":
                    return "N/A", "N/A", "no_pdf_url"
                
                # Download PDF
                pdf_bytes = await self.download_pdf_async(session, pdf_url)
                
                if self.parsing_method == "gemini":
                    # Use Gemini parsing
                    result = self.gemini_parser.parse_with_retry(pdf_bytes)
                    if result.get("success"):
                        revenue = result.get("total_revenue") or "N/A"
                        exec_comp = result.get("total_executive_compensation") or "N/A"
                        return revenue, exec_comp, "success"
                    else:
                        # Check if it's a rate limit or API error
                        error_msg = result.get("error", "").lower()
                        if "rate" in error_msg or "quota" in error_msg or "429" in error_msg:
                            logger.warning(f"Gemini rate limit hit: {result.get('error')}")
                            return "RATE_LIMIT", "RATE_LIMIT", "rate_limit"
                        
                        logger.warning(f"Gemini parsing failed, trying OCR fallback: {result.get('error')}")
                        # Fall back to OCR
                        result = self.form_parser.parse_990_form({"pdf_url": pdf_url}, "pdf_url")
                        if result.get("success"):
                            financial_data = result.get("financial_data", {})
                            executive_comp = result.get("executive_compensation", {})
                            revenue = financial_data.get("total_revenue", "N/A")
                            exec_comp = sum(executive_comp.values()) if executive_comp else "N/A"
                            return revenue, exec_comp, "ocr_fallback"
                        else:
                            return "PARSE_FAILED", "PARSE_FAILED", "parse_failed"
                else:
                    # Use OCR parsing
                    result = self.form_parser.parse_990_form({"pdf_url": pdf_url}, "pdf_url")
                    if result.get("success"):
                        financial_data = result.get("financial_data", {})
                        executive_comp = result.get("executive_compensation", {})
                        revenue = financial_data.get("total_revenue", "N/A")
                        exec_comp = sum(executive_comp.values()) if executive_comp else "N/A"
                        return revenue, exec_comp, "success"
                    else:
                        return "PARSE_FAILED", "PARSE_FAILED", "parse_failed"
                
            except aiohttp.ClientResponseError as e:
                if e.status == 403:
                    logger.debug(f"PDF download forbidden (403): {pdf_url}")
                    return "DOWNLOAD_FORBIDDEN", "DOWNLOAD_FORBIDDEN", "download_403"
                elif e.status == 429:
                    logger.warning(f"Rate limited on PDF download: {pdf_url}")
                    return "RATE_LIMIT", "RATE_LIMIT", "rate_limit"
                else:
                    logger.debug(f"PDF download failed with HTTP {e.status}: {e}")
                    return "DOWNLOAD_ERROR", "DOWNLOAD_ERROR", "download_error"
            except Exception as e:
                logger.debug(f"PDF extraction failed with unexpected error: {e}")
                return "ERROR", "ERROR", "unexpected_error"
    
    async def process_organization_async(self, session: aiohttp.ClientSession, ein: int) -> dict:
        """Process a single organization asynchronously"""
        try:
            # Get organization details
            org_details = await self.get_organization_details_async(session, ein)
            name = org_details["organization"]["name"]
            
            # Extract filing information (synchronous part - use existing logic)
            filing_year, revenue, exec_comp, data_source = self.extract_latest_filing_info_sync(org_details)
            
            # If we need PDF parsing, do it async
            if data_source == "pdf_needed":
                # Find the filing to parse
                all_filings = org_details.get("filings_with_data", []) + org_details.get("filings_without_data", [])
                most_recent_filing = None
                most_recent_year = 0
                
                for filing in all_filings:
                    year = filing.get("tax_prd_yr", 0)
                    if year > most_recent_year:
                        most_recent_year = year
                        most_recent_filing = filing
                
                if most_recent_filing and most_recent_filing.get("pdf_url"):
                    revenue, exec_comp, error_type = await self.extract_financials_async(session, most_recent_filing)
                    
                    # Categorize the result
                    if error_type == "success" or error_type == "ocr_fallback":
                        data_source = "pdf"
                    elif error_type == "rate_limit":
                        data_source = "rate_limit"
                    elif error_type in ["parse_failed", "download_403", "download_error", "unexpected_error"]:
                        data_source = "error"
                    else:
                        data_source = "none"
                else:
                    revenue, exec_comp = "N/A", "N/A"
                    data_source = "none"
            
            # Update counters
            if data_source == "api":
                self.api_count += 1
            elif data_source == "pdf":
                self.pdf_count += 1
            elif data_source == "rate_limit":
                self.rate_limit_count += 1
            elif data_source == "error":
                self.error_count += 1
            else:
                self.na_count += 1
            
            self.completed_orgs += 1
            
            # Update monitor stats frequently
            if self.completed_orgs % 3 == 0:  # Update every 3 completed for more responsive GUI
                self.update_monitor_stats()
            
            # Progress display
            if self.completed_orgs % 5 == 0:  # Update every 5 completed
                progress_pct = (self.completed_orgs / self.total_orgs) * 100 if self.total_orgs > 0 else 0
                rate_limit_str = f" | 🚫 Rate Limits: {self.rate_limit_count}" if self.rate_limit_count > 0 else ""
                error_str = f" | ❌ Errors: {self.error_count}" if self.error_count > 0 else ""
                print(f"  🚀 Progress: {self.completed_orgs}/{self.total_orgs} ({progress_pct:.1f}%) | API: {self.api_count} | AI: {self.pdf_count} | N/A: {self.na_count}{rate_limit_str}{error_str}")
                
                # Log detailed progress to monitor
                if self.rate_limit_count > 0 or self.error_count > 0:
                    self.log_to_monitor(f"Progress: {self.completed_orgs}/{self.total_orgs} - Rate limits: {self.rate_limit_count}, Errors: {self.error_count}", "WARNING")
                else:
                    self.log_to_monitor(f"Progress: {self.completed_orgs}/{self.total_orgs} - {progress_pct:.1f}% complete", "INFO")
            
            return {
                "name": name,
                "ein": ein,
                "filing_year": filing_year,
                "revenue": revenue,
                "exec_comp": exec_comp,
                "data_source": data_source
            }
            
        except Exception as e:
            logger.error(f"Error processing EIN {ein}: {e}")
            self.log_to_monitor(f"Error processing EIN {ein}: {str(e)}", "ERROR")
            self.completed_orgs += 1
            self.error_count += 1
            return {
                "name": f"Error-{ein}",
                "ein": ein,
                "filing_year": 0,
                "revenue": "ERROR",
                "exec_comp": "ERROR",
                "data_source": "error"
            }
    
    def extract_latest_filing_info_sync(self, org_details: dict) -> Tuple[int, str, str, str]:
        """Synchronous version of filing info extraction - returns data_source"""
        # Use existing logic but simplified
        filings_with_data = org_details.get("filings_with_data", [])
        filings_without_data = org_details.get("filings_without_data", [])
        
        # Find most recent filing
        most_recent_year = 0
        most_recent_filing = None
        is_filing_with_data = False
        
        for filing in filings_with_data:
            year = filing.get("tax_prd_yr", 0)
            if year > most_recent_year:
                most_recent_year = year
                most_recent_filing = filing
                is_filing_with_data = True
        
        for filing in filings_without_data:
            year = filing.get("tax_prd_yr", 0)
            if year > most_recent_year:
                most_recent_year = year
                most_recent_filing = filing
                is_filing_with_data = False
        
        if not most_recent_filing:
            return 0, "N/A", "N/A", "none"
        
        if is_filing_with_data:
            # Try to use API data
            revenue = most_recent_filing.get("totrevenue")
            expenses = most_recent_filing.get("totfuncexpns")
            comp_percent = most_recent_filing.get("pct_compnsatncurrofcr")
            
            has_revenue = revenue is not None and revenue > 0
            has_comp = (expenses is not None and comp_percent is not None and comp_percent >= 0)
            
            if has_revenue and has_comp:
                exec_comp = round(expenses * comp_percent, 2) if expenses and comp_percent else 0
                return most_recent_year, revenue, exec_comp, "api"
            elif has_revenue or has_comp:
                # Partial data - might want PDF parsing
                revenue = revenue if has_revenue else "N/A"
                exec_comp = round(expenses * comp_percent, 2) if has_comp else "N/A"
                
                # For now, use what we have rather than PDF parsing for partial data
                return most_recent_year, revenue, exec_comp, "api"
        
        # Need PDF parsing
        return most_recent_year, "N/A", "N/A", "pdf_needed"
    
    async def collect_eins_for_query_async(self, session: aiohttp.ClientSession, query: str) -> List[int]:
        """Collect all EINs for a query using async pagination"""
        all_eins = []
        page = 0
        consecutive_errors = 0
        
        while consecutive_errors < 3:
            try:
                eins = await self.get_eins_by_search_async(session, query, page)
                
                if eins is None:  # End of pages
                    break
                elif eins:  # Non-empty list
                    all_eins.extend(eins)
                    consecutive_errors = 0
                    logger.debug(f"Query '{query}' page {page}: {len(eins)} EINs")
                
                page += 1
                
                # Small delay to be nice to the API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error on page {page} for query '{query}': {e}")
                if consecutive_errors >= 3:
                    break
                await asyncio.sleep(1)  # Wait longer on error
        
        logger.info(f"Query '{query}' completed: {len(all_eins)} unique EINs across {page} pages")
        return all_eins
    
    async def process_query_batch_async(self, session: aiohttp.ClientSession, eins: List[int], batch_size: int = 20):
        """Process organizations in batches"""
        total_eins = len(eins)
        self.total_orgs = total_eins
        self.current_query = "Processing organizations"
        self.update_monitor_stats()
        
        self.log_to_monitor(f"Starting to process {total_eins} unique organizations in batches of {batch_size}", "INFO")
        
        for i in range(0, total_eins, batch_size):
            batch = eins[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_eins + batch_size - 1) // batch_size
            
            print(f"  📦 Processing batch {batch_num}/{total_batches} ({len(batch)} organizations)")
            self.log_to_monitor(f"Processing batch {batch_num}/{total_batches} ({len(batch)} organizations)", "INFO")
            
            # Process batch concurrently
            tasks = [self.process_organization_async(session, ein) for ein in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Add successful results
            for result in batch_results:
                if isinstance(result, dict):
                    self.results.append([
                        result["name"],
                        result["ein"],
                        result["filing_year"],
                        result["revenue"],
                        result["exec_comp"]
                    ])
            
            # Small delay between batches
            await asyncio.sleep(0.5)
    
    async def scrape_async(self, search_terms: List[str] = None, include_alphabetical: bool = True):
        """Main async scraping function"""
        self.start_time = time.time()
        self.log_to_monitor(f"Starting async scraper for {self.state_name} ({self.state_code})", "INFO")
        
        if not search_terms:
            # Use the same comprehensive search strategy as sync version
            common_nonprofit_terms = [
                "foundation", "association", "society", "institute", "center", "council",
                "trust", "fund", "alliance", "coalition", "network", "group", "organization",
                "charity", "church", "temple", "synagogue", "school", "college", "university",
                "hospital", "health", "medical", "community", "family", "children", "youth", "project",
                "arts", "museum", "library", "research", "education", "housing", "veterans",
                "services", "support", "relief", "development", "international", "american"
            ]
            
            state_terms = [self.state_name.lower(), self.state_code.lower()]
            
            search_terms = common_nonprofit_terms + state_terms
            
            # Add alphabetical searches for maximum coverage
            if include_alphabetical:
                import string
                alphabet_searches = list(string.ascii_lowercase) + [
                    "al", "am", "an", "ar", "as", "at", "ca", "ce", "ch", "ci", "co", "cr",
                    "de", "di", "do", "ea", "ed", "el", "em", "en", "ex", "fa", "fi", "fo",
                    "fr", "ge", "gl", "go", "gr", "ha", "he", "hi", "ho", "hu", "in", "is",
                    "ja", "jo", "ka", "ki", "la", "le", "li", "lo", "ma", "me", "mi", "mo",
                    "na", "ne", "no", "of", "op", "or", "pa", "pe", "pr", "qu", "ra", "re",
                    "ri", "ro", "sa", "sc", "se", "sh", "so", "st", "su", "ta", "te", "th",
                    "ti", "to", "tr", "un", "up", "ur", "va", "vi", "wa", "we", "wi", "wo", "yo"
                ]
                search_terms.extend(alphabet_searches)
        
        start_time = time.time()
        
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            
            # Collect all EINs first (deduplication handled incrementally via self.processed_eins)
            print(f"🔍 Collecting EINs for {len(search_terms)} search terms...")
            self.log_to_monitor(f"Collecting EINs for {len(search_terms)} search terms", "INFO")
            all_eins = []
            
            for i, term in enumerate(search_terms):
                self.current_query = term
                self.update_monitor_stats()
                
                print(f"  🔎 Searching: '{term}' ({i+1}/{len(search_terms)})")
                self.log_to_monitor(f"Searching: '{term}' ({i+1}/{len(search_terms)})", "INFO")
                
                eins = await self.collect_eins_for_query_async(session, term)
                all_eins.extend(eins)
                
                if eins:
                    self.log_to_monitor(f"Found {len(eins)} new EINs for '{term}'", "SUCCESS")
            
            print(f"📊 Total unique organizations found: {len(all_eins)} (deduplication handled incrementally)")
            print(f"📋 Processed EINs tracker contains: {len(self.processed_eins)} unique EINs")
            
            # Process organizations in batches (all_eins already contains unique EINs)
            if all_eins:
                await self.process_query_batch_async(session, all_eins)
        
        elapsed = time.time() - self.start_time
        print(f"⏱️  Total processing time: {elapsed:.1f} seconds")
        print(f"📈 Average: {elapsed/len(all_eins):.2f} seconds per organization")
        print(f"🎯 Final stats: API: {self.api_count} | AI: {self.pdf_count} | N/A: {self.na_count} | Rate Limits: {self.rate_limit_count} | Errors: {self.error_count}")
        
        # Log completion to monitor
        self.current_query = "Completed"
        self.update_monitor_stats()
        self.log_to_monitor(f"Scraping completed! Processed {len(all_eins)} organizations in {elapsed:.1f} seconds", "SUCCESS")
        self.log_to_monitor(f"Final stats - API: {self.api_count}, AI: {self.pdf_count}, N/A: {self.na_count}, Rate Limits: {self.rate_limit_count}, Errors: {self.error_count}", "INFO")
        
        # Alert if we have significant rate limits or errors
        if self.rate_limit_count > 0:
            print(f"⚠️  WARNING: {self.rate_limit_count} organizations hit rate limits - consider slowing down processing")
            self.log_to_monitor(f"WARNING: {self.rate_limit_count} organizations hit rate limits", "WARNING")
        if self.error_count > 0:
            print(f"⚠️  WARNING: {self.error_count} organizations had processing errors - check logs for details")
            self.log_to_monitor(f"WARNING: {self.error_count} organizations had processing errors", "WARNING")
    
    def save_to_excel(self, filename=None):
        """Save results to Excel file in output directory"""
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
            filename = f"nonprofit_data_ASYNC_{clean_state_name}_{self.parsing_method}_{timestamp}.xlsx"
        
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


async def main_async():
    """Async main function"""
    load_dotenv()
    
    print("🚀 Async Nonprofit Scraper")
    print("=" * 50)
    
    # For demo, hardcode Connecticut and gemini
    state_code = "CT"
    state_name = "Connecticut"
    parsing_method = "gemini"
    
    print(f"State: {state_name} ({state_code})")
    print(f"Method: {parsing_method.upper()}")
    print(f"Concurrency: 10 API calls, 3 PDF processes")
    print()
    
    scraper = AsyncNonprofitScraper(
        state_code=state_code,
        state_name=state_name, 
        parsing_method=parsing_method,
        max_concurrent_api=10,  # Concurrent API calls
        max_concurrent_pdf=3    # Concurrent PDF processing
    )
    
    # Limited search terms for testing
    search_terms = ["foundation", "association"]
    
    try:
        await scraper.scrape_async(search_terms)
        scraper.save_to_excel()
        
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        if scraper.results:
            print(f"💾 Saving {len(scraper.results)} partial results...")
            scraper.save_to_excel()


if __name__ == "__main__":
    asyncio.run(main_async())