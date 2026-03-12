from __future__ import annotations

from pathlib import Path
from typing import Callable

from pharma_agent.enrich import dedupe_records, enrich_record
from pharma_agent.models import ResearchResult
from pharma_agent.search import CompanySource

ProgressCallback = Callable[[str, str, str], None]


class PharmacyResearchAgent:
    def __init__(self, source: CompanySource) -> None:
        self.source = source

    def run(
        self,
        *,
        query: str,
        max_results: int,
        title: str,
        progress_callback: ProgressCallback | None = None,
    ) -> ResearchResult:
        if progress_callback:
            progress_callback("search", "active", "Collecting pharmacy company candidates.")
        search_results = self.source.collect(query=query, max_results=max_results)
        if progress_callback:
            progress_callback("search", "completed", f"Collected {len(search_results)} source candidates.")
            progress_callback("research", "active", "Extracting domains, contact details, and confidence signals.")

        enriched = [enrich_record(record) for record in search_results]
        if progress_callback:
            progress_callback("research", "completed", f"Enriched {len(enriched)} company records.")
            progress_callback("dedupe", "active", "Merging duplicate companies into cleaner profiles.")

        deduped = dedupe_records(enriched)
        if progress_callback:
            progress_callback("dedupe", "completed", f"Reduced the list to {len(deduped)} unique companies.")

        return ResearchResult(query=query, title=title, companies=deduped)
