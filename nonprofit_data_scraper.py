import requests
import pandas as pd
from time import sleep
import logging
import inquirer

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
        pass

    def scrape_nonprofits_segmented(self):
        """Main scraping function using multiple targeted searches to work around the 10K rate limit"""
        logger.info("Starting segmented {self.state} nonprofit data collection ...")

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
    scraper = NonprofitRevenueScraper()

    try:
        state_code, state_name = select_state()
        
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