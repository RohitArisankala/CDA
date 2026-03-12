# Pharmacy Research Agent

Python app for finding pharmacy companies by location, tracking workflow stages, and downloading generated Word reports from a clean web UI.

## Features

- Search pharmacy companies by city, state, or region
- Blue and white gradient frontend with a clean dashboard
- `Start Searching` button to launch a live location-based research job
- Live workflow stage updates for search, research, cleanup, and report generation
- Download card for the newest Word output file
- Report library with saved `.docx` files
- Reads API keys from `.env`, with `.env.example` as a fallback
- Visits company pages and contact pages in live mode to extract cleaner company details
- Broadens discovery with LinkedIn, Naukri, AmbitionBox, PharmaCompass, and other query-targeted sources
- Filters down to strong unique company records before export

## Notes

- The app now runs live search only.
- The app prefers official company-style records and drops weak or duplicate entries more aggressively.
- Some aggregator sources are used only for discovery; final output prefers stronger company records.
