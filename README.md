# 🏛️ Nonprofit Revenue Scraper

An interactive Python tool that scrapes nonprofit financial data from ProPublica's Nonprofit Explorer API to identify organizations with revenue between $250K - $1M, including executive compensation details.

## 📊 Features

- **Interactive State Selection**: Beautiful CLI interface with arrow key navigation through all 50 US states and territories
- **Revenue Filtering**: Automatically filters nonprofits with revenue between $250,000 - $1,000,000
- **Executive Compensation Data**: Extracts available executive compensation information from Form 990 filings
- **Smart Data Collection**: Uses multiple search strategies to work around API limitations and ensure comprehensive coverage
- **Excel Export**: Generates formatted Excel spreadsheets with professional styling
- **Duplicate Prevention**: Intelligent deduplication to avoid counting the same organization multiple times
- **Progress Tracking**: Real-time logging and progress indicators
- **Graceful Interruption**: Save partial results if the process is interrupted

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- Internet connection for API access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/cameronbrady1527/nonprofit-revenue-scraper.git
   cd nonprofit-scraper
   ```

2. **Create a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Mac/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Usage

Run the script and follow the interactive prompts:

```bash
python nonprofit_scraper.py
```

You'll see an interactive menu like this:

```
🏛️  Nonprofit Data Scraper
==================================================
Select a state to scrape nonprofit data for organizations
with revenue between $250K - $1M

? Choose a state (use arrow keys, press Enter to select)
❯ Alabama (AL)
  Alaska (AK)
  Arizona (AZ)
  Arkansas (AR)
  California (CA)
  ...
```

Use the **arrow keys** to navigate and **Enter** to select your state.

## 📋 Output

The script generates an Excel file with the following columns:

| Column | Description |
|--------|-------------|
| Organization Name | Legal name of the nonprofit |
| EIN | Employer Identification Number (formatted as XX-XXXXXXX) |
| Filing Year | Most recent tax filing year |
| Total Revenue | Formatted revenue amount (e.g., $500,000) |
| Executive Compensation | Total executive compensation if available |
| Revenue (Raw) | Unformatted revenue for analysis |
| Compensation (Raw) | Unformatted compensation for analysis |

**Example filename**: `ct_nonprofits_250k_1m_20250528_143022.xlsx`

## 🔧 How It Works

### API Strategy
The script uses ProPublica's Nonprofit Explorer API, which has a 10,000 result limit per search. To work around this:

1. **Keyword-Based Searches**: Searches using common nonprofit terms like "foundation", "association", "church", etc.
2. **State-Specific Terms**: Includes major cities and state names in searches
3. **Alphabetical Searches**: Uses single letters and common letter combinations to catch missed organizations
4. **Deduplication**: Tracks processed organizations by EIN to avoid duplicates

### Data Processing
- Extracts the **most recent filing** for each organization
- Filters organizations with revenue between **$250K - $1M**
- Attempts to extract executive compensation from multiple Form 990 fields
- Handles different form types (990, 990-EZ, 990-PF)

## ⚡ Performance

- **Runtime**: 2-8 hours depending on state size and number of qualifying nonprofits
- **API Calls**: Respectful rate limiting (0.3-1 second delays between requests)
- **Expected Results**: 200-800 qualifying nonprofits per state (varies significantly)
- **Memory Usage**: Minimal - processes data incrementally

## 🛡️ Rate Limiting & Best Practices

The script includes built-in protections:

- **Respectful delays** between API calls
- **Error handling** for network timeouts
- **Progress logging** to monitor status
- **Partial save functionality** if interrupted
- **Duplicate prevention** to avoid redundant API calls

## 📁 Project Structure

```
nonprofit-scraper/
├── nonprofit_scraper.py      # Main script
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── .gitignore                # Git ignore rules
└── venv/                     # Virtual environment (not in git)
```

## 🔍 Sample Output Summary

```
=== CONNECTICUT SUMMARY ===
Total nonprofits found: 447
Revenue range: $250,012 - $999,987
Organizations with compensation data: 312
Compensation range: $45,000 - $275,000
Average compensation: $87,450
```

## 🐛 Troubleshooting

### Common Issues

**Import Errors**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

**API Timeouts**
- The script automatically retries failed requests
- If you see many timeout errors, check your internet connection
- Consider running during off-peak hours

**No Results Found**
- Some smaller states may have fewer qualifying nonprofits
- Try running with a different revenue range (modify the script)
- Check that the state code is correct

**Interrupted Execution**
- Press `Ctrl+C` to gracefully stop and save partial results
- The script will save whatever data has been collected so far

## 🤝 Contributing

Contributions are welcome! Here are some ways to help:

- **Add more search terms** for better coverage
- **Improve error handling** for edge cases
- **Add support for different revenue ranges**
- **Optimize API usage** patterns
- **Add data validation** features
- **Create visualization tools** for the output data

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Submit a pull request with a clear description

## 📊 Data Sources

- **ProPublica Nonprofit Explorer API**: Primary data source
- **IRS Form 990 Data**: Tax filings from 2012-present
- **Coverage**: 1.8+ million nonprofit tax filings

## ⚖️ Legal & Ethical Use

- Data is sourced from public IRS filings via ProPublica's API
- All data collection respects ProPublica's terms of service
- Rate limiting prevents server overload
- Data should be used for legitimate research, journalism, or analysis purposes

## 📈 Future Enhancements

- [ ] Multi-year data collection and trend analysis
- [ ] Additional financial metrics extraction
- [ ] Board member and key personnel data
- [ ] Geographic mapping and visualization
- [ ] Sector-specific analysis tools
- [ ] Automated report generation
- [ ] Database storage option
- [ ] Web interface for easier use

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **ProPublica** for providing the Nonprofit Explorer API
- **IRS** for making nonprofit tax data publicly available
- **Python community** for the excellent libraries used in this project

## 📞 Support

If you encounter issues or have questions:

1. Check the [Issues](https://github.com/cameronbrady1527/nonprofit-revenue-scraper/issues) page
2. Search existing issues for solutions
3. Create a new issue with detailed information about your problem
4. Include your Python version, operating system, and error messages

---

**⭐ If this tool helps your research or work, please consider giving it a star!**

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-brightgreen.svg)