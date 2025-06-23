from datetime import datetime
from typing import List
import requests
import pandas as pd
import time
import logging
import inquirer
import string

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
    def __init__(self, state_code, state_name):
        self.state_code = state_code
        self.state_name = state_name
        self.base_url = "https://projects.propublica.org/nonprofits/api/v2"
        self.session = requests.Session()
        self.results = []
        self.processed_eins = set()

    def get_eins_by_search(self, query, page=0) -> List[int]:
        """Get organization EINs using keyword search to work around total result limits from ProPublica API"""
        search_url = f"{self.base_url}/search.json"
        params = {
            "q": query,
            "state[id]": self.state_code,
            "page": page,
            "c_code[id]": "3"
        }

        eins = []

        try:
            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            
            response_orgs = response.json()["organizations"]
            for org in response_orgs:
                ein = org["ein"]
                if ein not in self.processed_eins:
                    eins.append(ein)

            return eins

        except requests.RequestException as e:
            logger.error(f"Error fetching page {page} for query '{query}': {e}")
            raise requests.RequestException

    def get_page_total(self, query) -> int:
        search_url = f"{self.base_url}/search.json"
        params = {
            "q": query,
            "state[id]": self.state_code,
            "c_code[id]": "3"
        }

        try:
            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()

            total_pages = response.json()["num_pages"]

        except Exception as e:
            logger.error(f"Error getting page number: {e}")
            
            total_pages = 0

        return total_pages


    def get_organization_details(self, ein):
        """Get financial data for a specific organization"""
        # returns the JSON object
        url = f"{self.base_url}/organizations/{ein}.json"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        
        except requests.RequestException as e:
            logger.error(f"Error fetching details for EIN {ein}: {e}")
            raise requests.RequestException

    def extract_latest_filing_info(self, org_details):
        """Extract the most recent Form 990 filing information with filing year, revenue, and compensation data"""

        filings_with_data = org_details.get("filings_with_data", [])
        
        most_recent_year = 0
        most_recent_filing = None
        
        for filing in filings_with_data:
            if filing.get("tax_prd_yr", "") > most_recent_year:
                most_recent_year = filing.get("tax_prd_yr", "")
                most_recent_filing = filing

        if not filings_with_data:
            return "N/A", 0, 0

        revenue = most_recent_filing.get("totrevenue", 0)
        expenses = most_recent_filing.get("totfuncexpns", 0)
        comp_percent_of_expenses = most_recent_filing.get("pct_compnsatncurrofcr", 0.0) if most_recent_filing.get("pct_compnsatncurrofcr", 0.0) >= 0 else 0
            
        executive_comp = round(expenses * comp_percent_of_expenses, 2)

        return most_recent_year, revenue, executive_comp

    def process_search_results(self, query):
        """Process all pages for a given search query"""
        logger.info(f"Processing search query: '{query}'")
        page = 0
        result_eins = []

        num_pages = self.get_page_total(query)

        while (page <= num_pages):
            try:
                incoming_eins = self.get_eins_by_search(query, page)

                if incoming_eins != []:
                    result_eins += incoming_eins
            
            except requests.RequestException as e:
                logger.error(f"Error getting the EINs for organizations on page {page}: {e}")
                break

            page += 1

        # print(result_eins)
        
        for ein in result_eins:
            try:
                org_details = self.get_organization_details(ein)

                name = org_details["organization"]["name"]
                filing_year, revenue, exec_comp = self.extract_latest_filing_info(org_details)

                if int(revenue) >= 250000 and int(revenue) <= 1000000:
                    self.results.append([name, ein, filing_year, revenue, exec_comp])
            except requests.RequestException as e:
                logger.error(f"Error getting the organization details from the API for EIN {ein}")

            time.sleep(0.1)


    def scrape_nonprofits_segmented(self):
        """Main scraping function using multiple targeted searches to work around the 10K rate limit"""
        logger.info(f"Starting segmented {self.state_name} nonprofit data collection ...")

        common_nonprofit_terms = [
            "foundation", "association", "society", "institute", "center", "council", "community",
            "trust", "fund", "alliance", "coalition", "network", "group", "organization",
            "charity", "church", "temple", "synagogue", "school", "college", "university",
            "hospital", "health", "medical", "community", "family", "children", "youth", "project", "mindfulness",
            "arts", "museum", "library", "research", "education", "housing", "veterans",
            "services", "support", "relief", "development", "international", "american"
        ]

        state_terms = [self.state_name.lower(), self.state_code.lower()]

        # TODO: add major cities .... maybe separate this into a function
        
        all_terms = common_nonprofit_terms + state_terms

        for term in all_terms:
            logger.info(f"Searching for nonprofits with term: '{term}'")
            self.process_search_results(term)

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
        """Save results to Excel file with formatting"""
        if not self.results:
            logger.warning("No results to save")
            return
        
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.state_code.lower()}_nonprofits_250k_1m_{timestamp}.xlsx"
        
        # Create DataFrame
        df = pd.DataFrame(self.results)
        
        # Save to Excel with formatting
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Nonprofits', index=False)
            
            # Get the worksheet
            worksheet = writer.sheets['Nonprofits']
            
            # Adjust column widths
            column_widths = {
                'A': 50,  # Organization Name
                'B': 15,  # EIN
                'C': 12,  # Filing Year
                'D': 18,  # Total Revenue
                'E': 25,  # Executive Compensation
                'F': 15,  # Revenue (Raw)
                'G': 20,  # Compensation (Raw)
            }
            
            for col, width in column_widths.items():
                worksheet.column_dimensions[col].width = width
            
            # Add summary statistics
            summary_row = len(df) + 3
            worksheet[f'A{summary_row}'] = 'SUMMARY STATISTICS'
            worksheet[f'A{summary_row+1}'] = f'Total Organizations: {len(df)}'
            
            # Calculate summary stats for organizations with valid compensation data
            # valid_comp = df[df['Compensation (Raw)'] != 'N/A']['Compensation (Raw)']
            # if len(valid_comp) > 0:
            #     worksheet[f'A{summary_row+2}'] = f'Organizations with Compensation Data: {len(valid_comp)}'
            #     worksheet[f'A{summary_row+3}'] = f'Average Executive Compensation: ${valid_comp.mean():,.0f}'
            #     worksheet[f'A{summary_row+4}'] = f'Median Executive Compensation: ${valid_comp.median():,.0f}'
        
        logger.info(f"Results saved to {filename}")
        print(f"\n📊 Results saved to: {filename}")


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
        state_code, state_name = select_state()

        if not state_code:
            return
        
        print(f"\n✅ Selected: {state_name} ({state_code})")
        print(f"🚀 Starting data collection for {state_name} ...")
        print(f"📊 Looking for nonprofits with revenue between $250K - $1M")
        print(f"⏱️ This may take several hours. Press Ctrl+C to stop and save partial results.\n")

        # initialize and run scraper
        scraper = NonprofitRevenueScraper(state_code, state_name)
        scraper.scrape_nonprofits_segmented()
        
        scraper.save_to_excel()


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