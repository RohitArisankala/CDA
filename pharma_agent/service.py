from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests

from pharma_agent.config import load_app_env
from pharma_agent.enrich import (
    clean_company_name,
    dedupe_records,
    enrich_record,
    extract_domain,
    is_likely_company_record,
    is_official_domain,
    quality_score,
)
from pharma_agent.fetch import fetch_company_details
from pharma_agent.models import JobRecord
from pharma_agent.pipeline import PharmacyResearchAgent
from pharma_agent.reporting import build_report
from pharma_agent.search import JsonFileSource, SerperSearchSource

BASE_DIR = Path(__file__).resolve().parent.parent
if os.environ.get("VERCEL"):
    OUTPUT_DIR = Path("/tmp") / "outputs"
else:
    OUTPUT_DIR = BASE_DIR / "outputs"
SAMPLE_FILE = BASE_DIR / "sample_companies.json"
SERPER_URL = "https://google.serper.dev/search"
MAX_FETCH_WORKERS = 6
MAX_JOB_WORKERS = 3
MAX_COMPANIES_FOR_JOB_SEARCH = 5
MAX_FETCH_CANDIDATES = 14


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "pharma-report"


def build_location_queries(location: str) -> list[str]:
    place = location.strip()
    return [
        f"pharmaceutical companies in {place}",
        f"pharma manufacturers in {place}",
        f"pharmacy companies in {place}",
        f"site:linkedin.com/company pharma {place}",
        f"site:pharmacompass.com company {place}",
        f"site:zaubacorp.com pharmaceutical {place}",
    ]


def _candidate_priority(record) -> tuple[int, float, str]:
    domain = extract_domain(record.website)
    official = 1 if is_official_domain(domain) else 0
    info_score = quality_score(record)
    return (-official, -info_score, clean_company_name(record.name).lower())


def _select_fetch_candidates(records: list, limit: int) -> list:
    selected = []
    seen_keys: set[str] = set()

    for record in sorted(records, key=_candidate_priority):
        domain = extract_domain(record.website)
        key = domain if domain != "Not found" else clean_company_name(record.name).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append(record)
        if len(selected) >= limit:
            break

    return selected


def _serper_search(query: str, api_key: str, limit: int = 5) -> list[dict]:
    response = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": limit},
        timeout=18,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("organic", [])[:limit]


def search_company_jobs(company_name: str, location: str, api_key: str) -> list[JobRecord]:
    queries = [
        f'{company_name} jobs {location}',
        f'site:linkedin.com/jobs/view {company_name} {location}',
    ]

    seen_links: set[str] = set()
    jobs: list[JobRecord] = []

    for query in queries:
        try:
            items = _serper_search(query, api_key, limit=2)
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
            if len(jobs) >= 2:
                return jobs

    return jobs


def _fetch_and_enrich(record):
    fetched = fetch_company_details(record, timeout=10)
    fetched = enrich_record(fetched)
    return fetched if is_likely_company_record(fetched) else None


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
            raise ValueError("SERPER_API_KEY is not configured. Add the key to .env or .env.example.")
        source = SerperSearchSource(api_key=api_key)
        queries = build_location_queries(query)
        per_query_results = max(1, min(max_results, 5))

        if progress_callback:
            progress_callback("search", "active", f"Searching pharmacy companies for {query} across {len(queries)} source variations.")

        raw_records = []
        for index, current_query in enumerate(queries, start=1):
            raw_records.extend(source.collect(query=current_query, max_results=per_query_results))
            if progress_callback:
                progress_callback("search", "active", f"Search source {index} of {len(queries)} completed.")

        fetch_limit = min(MAX_FETCH_CANDIDATES, max(8, max_results * 4))
        candidate_records = _select_fetch_candidates(raw_records, fetch_limit)

        if progress_callback:
            progress_callback("search", "completed", f"Collected {len(raw_records)} source candidates and selected {len(candidate_records)} strong pages for extraction.")
            progress_callback("research", "active", "Opening the strongest company pages and extracting contact details.")

        extracted_records = []
        with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as executor:
            futures = [executor.submit(_fetch_and_enrich, record) for record in candidate_records]
            total = len(futures)
            processed = 0
            for future in as_completed(futures):
                processed += 1
                result_record = future.result()
                if result_record is not None:
                    extracted_records.append(result_record)
                if progress_callback:
                    progress_callback("research", "active", f"Processed company page {processed} of {total}.")

        if progress_callback:
            progress_callback("research", "completed", f"Extracted details from {len(extracted_records)} company pages.")
            progress_callback("dedupe", "active", "Merging duplicate companies from multiple sources.")

        deduped = dedupe_records(extracted_records)
        deduped = [record for record in deduped if quality_score(record) >= 3.5]

        if progress_callback:
            progress_callback("dedupe", "completed", f"Reduced the list to {len(deduped)} strong unique companies in {query}.")
            progress_callback("report", "active", "Checking a few top companies for related job openings.")

        target_companies = deduped[:MAX_COMPANIES_FOR_JOB_SEARCH]
        with ThreadPoolExecutor(max_workers=MAX_JOB_WORKERS) as executor:
            future_map = {
                executor.submit(search_company_jobs, company.name, query, api_key): company
                for company in target_companies
            }
            completed = 0
            total_jobs = len(future_map)
            for future in as_completed(future_map):
                completed += 1
                company = future_map[future]
                try:
                    company.jobs = future.result()
                except Exception:
                    company.jobs = []
                if progress_callback and total_jobs:
                    progress_callback("report", "active", f"Checked job openings for company {completed} of {total_jobs}.")

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
