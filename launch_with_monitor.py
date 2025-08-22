#!/usr/bin/env python3
"""
Launch script that starts both the GUI monitor and the async scraper
"""

import subprocess
import threading
import time
import os
import sys
from scraper_launcher import select_scraper_type, select_parsing_method, select_state

def launch_monitor():
    """Launch the GUI monitor in a separate process"""
    try:
        subprocess.run([sys.executable, "scraper_monitor.py"], check=False)
    except Exception as e:
        print(f"Error launching monitor: {e}")

def cleanup_monitor_files():
    """Clean up monitor files from previous runs"""
    try:
        if os.path.exists("scraper_stats.json"):
            os.remove("scraper_stats.json")
        if os.path.exists("scraper_logs.txt"):
            os.remove("scraper_logs.txt")
    except Exception:
        pass

def main():
    """Main launcher function"""
    print("🖥️  Nonprofit Scraper with GUI Monitor")
    print("=" * 50)
    
    # Clean up old monitor files
    cleanup_monitor_files()
    
    # Start monitor in background thread
    print("🚀 Starting GUI monitor...")
    monitor_thread = threading.Thread(target=launch_monitor, daemon=True)
    monitor_thread.start()
    
    # Give monitor time to start
    time.sleep(2)
    
    try:
        # Get user choices
        scraper_type = select_scraper_type()
        if not scraper_type:
            return
        
        parsing_method = select_parsing_method()
        if not parsing_method:
            return
        
        state_code, state_name = select_state()
        if not state_code:
            return
        
        # Show summary
        print(f"\\n" + "="*60)
        print(f"📋 CONFIGURATION SUMMARY")
        print(f"="*60)
        print(f"🔧 Scraper Type: {scraper_type.upper()}")
        print(f"🤖 Parsing Method: {parsing_method.upper()}")
        print(f"🏛️  State: {state_name} ({state_code})")
        print(f"🖥️  Monitor: GUI window opened")
        print(f"💰 Target Revenue: $250K - $1M")
        print(f"="*60)
        
        # Run the scraper based on type
        if scraper_type == "async":
            print("\\n🔥 Starting ASYNC scraper with GUI monitoring...")
            print("📺 Check the GUI window for real-time stats and logs!")
            
            # Import and run async scraper
            import asyncio
            from async_nonprofit_scraper import AsyncNonprofitScraper
            
            async def run_monitored_async_scraper():
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
                
                scraper = AsyncNonprofitScraper(
                    state_code=state_code,
                    state_name=state_name,
                    parsing_method=parsing_method,
                    max_concurrent_api=10,
                    max_concurrent_pdf=3
                )
                
                try:
                    await scraper.scrape_async(search_terms)
                    scraper.save_to_excel()
                    
                except KeyboardInterrupt:
                    print("\\n🛑 Interrupted by user")
                    if scraper.results:
                        print(f"💾 Saving {len(scraper.results)} partial results...")
                        scraper.save_to_excel()
            
            # Run the async scraper
            asyncio.run(run_monitored_async_scraper())
            
        else:
            print("\\n📝 Starting SYNC scraper...")
            print("⚠️  Note: Sync scraper doesn't have GUI integration yet")
            
            # Import and run sync scraper
            from nonprofit_data_scraper import NonprofitRevenueScraper
            
            scraper = NonprofitRevenueScraper(state_code, state_name, parsing_method)
            
            try:
                scraper.scrape_nonprofits_segmented()
                
                if scraper.results:
                    print(f"\\n💾 Saving {len(scraper.results)} results...")
                    scraper.save_to_excel()
                else:
                    print("\\n❌ No results to save")
                    
            except KeyboardInterrupt:
                print("\\n🛑 Interrupted by user")
                if scraper.results:
                    print(f"💾 Saving {len(scraper.results)} partial results...")
                    scraper.save_to_excel()
        
        print("\\n🎉 Scraping completed!")
        print("📺 Monitor window will stay open - close it manually when done")
        
        # Keep main thread alive so monitor stays open
        input("\\nPress Enter to exit and close monitor...")
        
    except KeyboardInterrupt:
        print("\\n👋 Goodbye!")
    except Exception as e:
        print(f"\\n❌ Error: {e}")
    finally:
        # Cleanup
        cleanup_monitor_files()

if __name__ == "__main__":
    main()