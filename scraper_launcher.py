#!/usr/bin/env python3
"""
Nonprofit Scraper Launcher
Choose between sync and async versions
"""

import inquirer
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def select_scraper_type():
    """Choose between sync and async scraper"""
    print("🚀 Nonprofit Data Scraper")
    print("=" * 50)
    print("Choose scraper version:\n")
    
    choices = [
        "🔥 Async Scraper (FAST - Recommended for large datasets)",
        "📝 Sync Scraper (STABLE - Original version)"
    ]
    
    questions = [
        inquirer.List('scraper_type',
                      message="Choose scraper version",
                      choices=choices,
                      carousel=True)
    ]
    
    try:
        answers = inquirer.prompt(questions)
        if not answers:
            return None
        
        return "async" if "Async" in answers['scraper_type'] else "sync"
    
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None

def select_parsing_method():
    """Choose parsing method"""
    print("\n🤖 PDF Parsing Method Selection")
    print("=" * 50)
    print("Choose how to extract financial data from PDFs:\n")
    
    choices = [
        "Gemini AI (Recommended - Fast and accurate)",
        "OCR (Legacy - Slower, requires Tesseract installation)"
    ]
    
    questions = [
        inquirer.List('method',
                      message="Choose parsing method",
                      choices=choices,
                      carousel=True)
    ]
    
    try:
        answers = inquirer.prompt(questions)
        if not answers:
            return None
        
        return "gemini" if "Gemini" in answers['method'] else "ocr"
    
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None

def select_state():
    """Choose state to scrape"""
    US_STATES = [
        ('Alabama', 'AL'), ('Alaska', 'AK'), ('Arizona', 'AZ'), ('Arkansas', 'AR'),
        ('California', 'CA'), ('Colorado', 'CO'), ('Connecticut', 'CT'), ('Delaware', 'DE'),
        ('Florida', 'FL'), ('Georgia', 'GA'), ('Hawaii', 'HI'), ('Idaho', 'ID'),
        ('Illinois', 'IL'), ('Indiana', 'IN'), ('Iowa', 'IA'), ('Kansas', 'KS'),
        ('Kentucky', 'KY'), ('Louisiana', 'LA'), ('Maine', 'ME'), ('Maryland', 'MD'),
        ('Massachusetts', 'MA'), ('Michigan', 'MI'), ('Minnesota', 'MN'), ('Mississippi', 'MS'),
        ('Missouri', 'MO'), ('Montana', 'MT'), ('Nebraska', 'NE'), ('Nevada', 'NV'),
        ('New Hampshire', 'NH'), ('New Jersey', 'NJ'), ('New Mexico', 'NM'), ('New York', 'NY'),
        ('North Carolina', 'NC'), ('North Dakota', 'ND'), ('Ohio', 'OH'), ('Oklahoma', 'OK'),
        ('Oregon', 'OR'), ('Pennsylvania', 'PA'), ('Rhode Island', 'RI'), ('South Carolina', 'SC'),
        ('South Dakota', 'SD'), ('Tennessee', 'TN'), ('Texas', 'TX'), ('Utah', 'UT'),
        ('Vermont', 'VT'), ('Virginia', 'VA'), ('Washington', 'WA'), ('West Virginia', 'WV'),
        ('Wisconsin', 'WI'), ('Wyoming', 'WY'), ('District of Columbia', 'DC')
    ]
    
    print("\n🏛️  State Selection")
    print("=" * 50)
    print("Select a state to scrape nonprofit data:\n")

    choices = [f"{name} ({code})" for name, code in US_STATES]
    
    questions = [
        inquirer.List('state',
                      message="Choose a state",
                      choices=choices,
                      carousel=True)
    ]

    try:
        answers = inquirer.prompt(questions)
        if not answers:
            return None, None
        
        selected = answers['state']
        state_code = selected.split('(')[-1].rstrip(')')
        state_name = selected.split(' (')[0]
        
        return state_code, state_name
    
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return None, None

async def run_async_scraper(state_code, state_name, parsing_method):
    """Run the async scraper"""
    from async_nonprofit_scraper import AsyncNonprofitScraper
    
    print(f"\n🔥 Starting ASYNC scraper...")
    print(f"State: {state_name} ({state_code})")
    print(f"Method: {parsing_method.upper()}")
    print(f"Concurrency: 10 API calls, 3 PDF processes")
    print(f"Search Queries: ~138 total (41 nonprofit terms + 2 state terms + 95 alphabetical)")
    print(f"⚡ This should be much faster than the sync version!\n")
    
    scraper = AsyncNonprofitScraper(
        state_code=state_code,
        state_name=state_name,
        parsing_method=parsing_method,
        max_concurrent_api=10,
        max_concurrent_pdf=3
    )
    
    # Use comprehensive search strategy (matches sync version)
    import string
    
    # 41 common nonprofit terms
    common_nonprofit_terms = [
        "foundation", "association", "society", "institute", "center", "council",
        "trust", "fund", "alliance", "coalition", "network", "group", "organization",
        "charity", "church", "temple", "synagogue", "school", "college", "university",
        "hospital", "health", "medical", "community", "family", "children", "youth", "project",
        "arts", "museum", "library", "research", "education", "housing", "veterans",
        "services", "support", "relief", "development", "international", "american"
    ]
    
    # State-specific terms
    state_terms = [state_name.lower(), state_code.lower()]
    
    # Alphabetical searches (26 single letters + 69 two-letter combinations = 95 total)
    alphabet_searches = list(string.ascii_lowercase) + [
        "al", "am", "an", "ar", "as", "at", "ca", "ce", "ch", "ci", "co", "cr",
        "de", "di", "do", "ea", "ed", "el", "em", "en", "ex", "fa", "fi", "fo",
        "fr", "ge", "gl", "go", "gr", "ha", "he", "hi", "ho", "hu", "in", "is",
        "ja", "jo", "ka", "ki", "la", "le", "li", "lo", "ma", "me", "mi", "mo",
        "na", "ne", "no", "of", "op", "or", "pa", "pe", "pr", "qu", "ra", "re",
        "ri", "ro", "sa", "sc", "se", "sh", "so", "st", "su", "ta", "te", "th",
        "ti", "to", "tr", "un", "up", "ur", "va", "vi", "wa", "we", "wi", "wo", "yo"
    ]
    
    # Combine all search strategies (~138 total searches)
    search_terms = common_nonprofit_terms + state_terms + alphabet_searches
    
    try:
        await scraper.scrape_async(search_terms)
        scraper.save_to_excel()
        
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        if scraper.results:
            print(f"💾 Saving {len(scraper.results)} partial results...")
            scraper.save_to_excel()

def run_sync_scraper(state_code, state_name, parsing_method):
    """Run the sync scraper"""
    from nonprofit_data_scraper import NonprofitRevenueScraper
    
    print(f"\n📝 Starting SYNC scraper...")
    print(f"State: {state_name} ({state_code})")
    print(f"Method: {parsing_method.upper()}")
    print(f"⏱️ This will take longer but is the stable original version.\n")
    
    scraper = NonprofitRevenueScraper(state_code, state_name, parsing_method)
    
    try:
        scraper.scrape_nonprofits_segmented()
        
        if scraper.results:
            print(f"\n💾 Saving {len(scraper.results)} results...")
            scraper.save_to_excel()
        else:
            print("\n❌ No results to save")
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        if scraper.results:
            print(f"💾 Saving {len(scraper.results)} partial results...")
            scraper.save_to_excel()

async def main():
    """Main launcher function"""
    try:
        # Step 1: Choose scraper type
        scraper_type = select_scraper_type()
        if not scraper_type:
            return
        
        # Step 2: Choose parsing method
        parsing_method = select_parsing_method()
        if not parsing_method:
            return
        
        # Step 3: Choose state
        state_code, state_name = select_state()
        if not state_code:
            return
        
        # Show summary
        print(f"\n" + "="*60)
        print(f"📋 CONFIGURATION SUMMARY")
        print(f"="*60)
        print(f"🔧 Scraper Type: {scraper_type.upper()}")
        print(f"🤖 Parsing Method: {parsing_method.upper()}")
        print(f"🏛️  State: {state_name} ({state_code})")
        print(f"💰 Target Revenue: $250K - $1M")
        print(f"="*60)
        
        # Confirm before starting
        confirm = inquirer.confirm("Ready to start scraping?", default=True)
        if not confirm:
            print("👋 Goodbye!")
            return
        
        # Run appropriate scraper
        if scraper_type == "async":
            await run_async_scraper(state_code, state_name, parsing_method)
        else:
            run_sync_scraper(state_code, state_name, parsing_method)
            
        print("\n🎉 Scraping completed!")
        
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())