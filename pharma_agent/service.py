from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests

from pharma_agent.config import load_app_env
from pharma_agent.enrich import dedupe_records, enrich_record, is_likely_company_record, quality_score
from pharma_agent.fetch import fetch_company_details
from pharma_agent.models import JobRecord
from pharma_agent.pipeline import PharmacyResearchAgent
from pharma_agent.reporting import build_report
from pharma_agent.search import JsonFileSource, SerperSearchSource

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"
SAMPLE_FILE = BASE_DIR / "sample_companies.json"
SERPER_URL = "https://google.serper.dev/search"


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "pharma-report"


def build_location_queries(location: str) -> list[str]:
    place = location.strip()
    return [
        f"pharmacy companies in {place}",
        f"pharmaceutical companies in {place}",
        f"pharma manufacturers in {place}",
        f"pharma distributors in {place}",
        f"site:linkedin.com/company pharmaceutical company {place}",
        f"site:linkedin.com/company pharma {place}",
        f"site:naukri.com pharmaceutical company {place}",
        f"site:ambitionbox.com pharma companies {place}",
        f"site:pharmacompass.com company {place}",
        f"site:zaubacorp.com pharmaceutical {place}",
    ]


def _serper_search(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": limit},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("organic", [])[:limit]


def search_company_jobs(company_name: str, location: str, api_key: str) -> list[JobRecord]:
    queries = [
        f'{company_name} jobs {location}',
        f'site:linkedin.com/jobs/view {company_name} {location}',
        f'site:naukri.com {company_name} jobs {location}',
        f'site:foundit.in {company_name} jobs {location}',
        f'site:indeed.com {company_name} jobs {location}',
    ]

    seen_links: set[str] = set()
    jobs: list[JobRecord] = []

    for query in queries:
        try:
            items = _serper_search(query, api_key, limit=4)
        except Exception:
            continue

        for item in items:
            title = (item.get("title") or "Not found").strip()
            snippet = (item.get("snippet") or "").strip()
            link = item.get("link") or "Not found"
            lowered = f"{title} {snippet}".lower()
            if link in seen_links:
                continue
            if not any(keyword in lowered for keyword in ("job", "career", "opening", "vacancy", "hiring", "recruitment")):
                continue
            seen_links.add(link)
            jobs.append(
                JobRecord(
                    title=title,
                    company=company_name,
                    location=location,
                    apply_link=link,
                    source=link,
                    summary=snippet or "Not found",
                )
            )
            if len(jobs) >= 5:
                return jobs

    return jobs


def run_research_workflow(
    *,
    query: str,
    title: str,
    max_results: int,
    mode: str,
    progress_callback=None,
) -> dict:
    load_app_env()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if mode == "sample":
        source = JsonFileSource(SAMPLE_FILE)
        agent = PharmacyResearchAgent(source)
        result = agent.run(
            query=query,
            max_results=max_results,
            title=title,
            progress_callback=progress_callback,
        )
    else:
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            raise ValueError("SERPER_API_KEY is not configured. Use sample mode or add the key to .env or .env.example.")
        source = SerperSearchSource(api_key=api_key)
        queries = build_location_queries(query)
        per_query_results = max(1, max_results)

        if progress_callback:
            progress_callback("search", "active", f"Searching pharmacy companies for {query} across {len(queries)} sources and query variations.")

        raw_records = []
        for index, current_query in enumerate(queries, start=1):
            raw_records.extend(source.collect(query=current_query, max_results=per_query_results))
            if progress_callback:
                progress_callback("search", "active", f"Search source {index} of {len(queries)} completed.")

        if progress_callback:
            progress_callback("search", "completed", f"Collected {len(raw_records)} source candidates for {query}.")
            progress_callback("research", "active", "Opening company pages and extracting contact details.")

        extracted_records = []
        for index, record in enumerate(raw_records, start=1):
            fetched = fetch_company_details(record)
            fetched = enrich_record(fetched)
            if is_likely_company_record(fetched):
                extracted_records.append(fetched)
            if progress_callback:
                progress_callback("research", "active", f"Processed company page {index} of {len(raw_records)}.")

        if progress_callback:
            progress_callback("research", "completed", f"Extracted details from {len(extracted_records)} company pages.")
            progress_callback("dedupe", "active", "Merging duplicate companies from multiple sources.")

        deduped = dedupe_records(extracted_records)
        deduped = [record for record in deduped if quality_score(record) >= 4.0]

        if progress_callback:
            progress_callback("dedupe", "completed", f"Reduced the list to {len(deduped)} strong unique companies in {query}.")
            progress_callback("report", "active", "Finding related job openings from LinkedIn, Naukri, and other sources.")

        for index, company in enumerate(deduped, start=1):
            company.jobs = search_company_jobs(company.name, query, api_key)
            if progress_callback:
                progress_callback("report", "active", f"Added job search results for company {index} of {len(deduped)}.")

        result = type("ResearchResultLike", (), {"query": query, "title": title, "companies": deduped})()

    if progress_callback and mode == "sample":
        progress_callback("report", "active", "Building the Word report for download.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-{slugify(title)}-{uuid4().hex[:8]}.docx"
    output_path = OUTPUT_DIR / filename
    build_report(result, output_path)

    if progress_callback:
        progress_callback("report", "completed", f"Saved report as {filename}.")
        progress_callback("complete", "completed", "Research workflow finished.")

    return {
        "filename": filename,
        "path": str(output_path),
        "title": result.title,
        "query": result.query,
        "company_count": len(result.companies),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def list_reports() -> list[dict]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reports: list[dict] = []

    for path in sorted(OUTPUT_DIR.glob("*.docx"), key=lambda item: item.stat().st_mtime, reverse=True):
        reports.append(
            {
                "filename": path.name,
                "title": path.stem,
                "size_kb": round(path.stat().st_size / 1024, 1),
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )

    return reports
