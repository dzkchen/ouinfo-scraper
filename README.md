# OUInfo-Scraper

Small CLI tools that scrape public program and scholarship listings from [OUInfo](https://www.ouinfo.ca/) and save them as JSON. [`csv_convert.py`](csv_convert.py) is just a quick script I made to turn the 2024-2025 reddit (Ontario G12) spreadsheet to a json file. Data is cleaned up a good bit (Not doing 2022-2024 for now).

Work in process (didn't check all of output file to verify if it's correct), feel free to contribute and possibly give it a star if you use it :)

## Tech stack

language: python  
http client: requests  
html parsing: beautifulsoup4  
cli: argparse  
serialization: json (stdlib)

## Sample Output

Shapes below are from `scrape_programs.py --limit 1` and `scrape_scholarships.py --limit 1`; field values change with OUInfo. The Reddit CSV example matches `csv_convert.py` output shape (default file `reddit_programs_24_25.json`).

### Programs (`ouinfo_programs.json`)

Object keyed by OUAC code (or a disambiguated id if the code repeats).

```json
{
  "CBA": {
    "programCode": "CBA",
    "university": "Carleton University",
    "programName": "Accounting",
    "admissionAverage": "80%",
    "prerequisites": [
      "English (ENG4U)",
      "Advanced Functions (MHF4U)",
      "Calculus (MCV4U) or Math for Data Management (MDM4U). (Calculus [MCV4U] recommended.)",
      "3 best 4U/M courses"
    ],
    "suppAppRequired": false,
    "url": "https://www.ouinfo.ca/programs/carleton/cba"
  }
}
```

### Scholarships (`ouinfo_scholarships.json`)

Object keyed by university name; each value is a list of scholarship records.

```json
{
  "Algoma University": [
    {
      "name": "Algoma University Alumni Award I and II",
      "url": "https://www.ouinfo.ca/scholarships/algoma/algoma-university-alumni-award-i",
      "deadline": "Jun. 30, 2026",
      "value": "$2,000",
      "renewable": "no",
      "applicationRequired": "yes",
      "forIndigenousApplicantsOnly": "no",
      "gradeRangeRequired": "other criteria",
      "forEquitySeekingApplicantsOnly": "no"
    }
  ]
}
```

### Reddit program averages (`reddit_programs_24_25.json`)

```json
{
  "programs": [
    {
      "university": "Brock",
      "program_code": "BG",
      "top_6_averages": [89, 95, 80],
      "average": 88
    }
  ]
}
```

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

### CSV → JSON (`csv_convert.py`)

Reads a CSV with columns University, OUAC Code, Program name, and Top 6 Average. Rows are grouped by `(University, OUAC Code)`; each group lists top‑6 averages from the file and an `average`. Rows with a blank or non-numeric average are skipped and summarized in the console output.

Defaults: input [`resources/24_25_data.csv`](resources/24_25_data.csv), output `./reddit_programs_24_25.json`.

```bash
python csv_convert.py
python csv_convert.py -i resources/24_25_data.csv -o reddit_programs_24_25.json
```

Use `python scrape_programs.py --help` / `python scrape_scholarships.py --help` / `python csv_convert.py --help` for options.
