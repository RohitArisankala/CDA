from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import requests

from pharma_agent.enrich import clean_company_name, is_likely_company_record
from pharma_agent.models import CompanyRecord, normalize_record


class CompanySource(Protocol):
    def collect(self, *, query: str, max_results: int) -> list[CompanyRecord]:
        ...


class JsonFileSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def collect(self, *, query: str, max_results: int) -> list[CompanyRecord]:
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        records = [normalize_record(item) for item in data[:max_results]]
        return [record for record in records if is_likely_company_record(record)]


class SerperSearchSource:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("SERPER_API_KEY is not configured.")

    def collect(self, *, query: str, max_results: int) -> list[CompanyRecord]:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=18,
        )
        response.raise_for_status()
        payload = response.json()
        organic_results = payload.get("organic", [])

        records: list[CompanyRecord] = []
        for item in organic_results[:max_results]:
            record = normalize_record(
                {
                    "name": clean_company_name(item.get("title") or "Unknown company"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                    "source": item.get("link") or "Serper",
                    "source_type": "search",
                    "confidence": 0.45,
                }
            )
            if is_likely_company_record(record):
                records.append(record)
        return records
