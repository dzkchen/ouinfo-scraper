# ouinfo-scraper

Small CLI tools that scrape public program and scholarship listings from [OUInfo](https://www.ouinfo.ca/) and save them as JSON.

## Tech stack

language: python  
http client: requests  
html parsing: beautifulsoup4  
cli: argparse  
serialization: json (stdlib)

## Requirements

- Python 3.10+
- Dependencies: see [`requirements.txt`](requirements.txt)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Programs

Scrapes undergraduate program detail pages → `ouinfo_programs.json` (object keyed by OUAC / disambiguated id).

```bash
python scrape_programs.py
python scrape_programs.py --limit 50
python scrape_programs.py -o my_programs.json
```

### Scholarships

Scrapes scholarship detail pages → `ouinfo_scholarships.json` (object keyed by university name).

```bash
python scrape_scholarships.py
python scrape_scholarships.py --limit 10
python scrape_scholarships.py -o my_scholarships.json
```

Use `python scrape_programs.py --help` / `python scrape_scholarships.py --help` for options.
