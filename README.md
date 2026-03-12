# Pharmacy Research Agent

Python app for finding pharmacy companies by location, tracking workflow stages, and downloading generated Word reports from a clean web UI.

## Features

- Search pharmacy companies by city, state, or region
- Blue and white gradient frontend with a clean dashboard
- `Start Searching` button to launch a location-based research job
- Live workflow stage updates for search, research, cleanup, and report generation
- Download card for the newest Word output file
- Report library with saved `.docx` files
- Sample mode for demo data and live mode for Serper-powered search
- Reads API keys from `.env`, with `.env.example` as a fallback
- Visits company pages in live mode to extract cleaner company details
- Broadens discovery with LinkedIn, Naukri, AmbitionBox, PharmaCompass, and other query-targeted sources

## Project Structure

- `web_app.py` runs the Flask web interface.
- `app.py` remains the CLI entry point.
- `pharma_agent/config.py` loads environment files.
- `pharma_agent/search.py` handles company discovery.
- `pharma_agent/fetch.py` fetches result pages and extracts contact details.
- `pharma_agent/enrich.py` applies extraction and deduplication logic.
- `pharma_agent/pipeline.py` runs the staged workflow.
- `pharma_agent/reporting.py` writes the Word document.
- `pharma_agent/service.py` builds source-specific location queries and saves reports.
- `templates/index.html` contains the dashboard markup.
- `static/styles.css` contains the blue-and-white UI styling.
- `static/app.js` handles job creation, polling, and downloads.

## Setup

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Add `SERPER_API_KEY` to either `.env` or `.env.example`.

## Run The Web App

```powershell
python web_app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Web Workflow

1. Enter a location like `Hyderabad` or `Mumbai`.
2. Click `Start Searching`.
3. The app runs pharmacy-related searches plus source-targeted queries for LinkedIn, Naukri, and other sources.
4. In live mode it opens candidate pages and extracts company details from the actual site.
5. It also searches related job openings for each company.
6. Results are cleaned, merged, and exported to a Word file.

## Notes

- “All available companies” is still best-effort, not guaranteed exhaustive.
- Live search quality depends on the results returned by Serper and whether source pages allow fetching.
- Some sources like LinkedIn may limit page access, but their search results can still help discovery.
