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

    def get_eins_by_search(self, query, page=0):
        """Get organization EINs using keyword search to work around total result limits from ProPublica API"""
        pass

    def get_organization_details(self, ein):
        """Get financial data for a specific organization"""
        pass

    def extract_latest_filing_info(self, org_details):
        """Extract the most recent Form 990 filing information with revenue and compensation data"""
        pass

    def extract_executive_compensation(self, filing):
        """Extract executive compensation from various possible fields"""
        pass

    def process_search_results(self, query):
        """Process all pages for a given search query"""
        logger.info(f"Processing search query: '{query}'")
        page = 0
        pass

    def scrape_nonprofits_segmented(self):
        """Main scraping function using multiple targeted searches to work around the 10K rate limit"""
        logger.info("Starting segmented {self.state} nonprofit data collection ...")

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
        """Save results to Excel file"""
        pass


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