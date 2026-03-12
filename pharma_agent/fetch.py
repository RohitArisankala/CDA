from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pharma_agent.enrich import EMAIL_RE, PHONE_RE, clean_company_name, extract_domain, infer_location, is_likely_company_name, is_likely_company_record
from pharma_agent.models import CompanyRecord

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
PRODUCT_HINTS = (
    "tablet",
    "capsule",
    "injectable",
    "medicine",
    "drug",
    "api",
    "formulation",
    "pharmaceutical",
    "nutraceutical",
    "oncology",
    "antibiotic",
)


def _pick_first(*values: str) -> str:
    for value in values:
        if value and value != "Not found":
            return value.strip()
    return "Not found"


def _extract_email(text: str, soup: BeautifulSoup) -> str:
    mailto = soup.select_one("a[href^='mailto:']")
    if mailto and mailto.get("href"):
        return mailto.get("href", "").replace("mailto:", "").strip() or "Not found"
    match = EMAIL_RE.search(text)
    return match.group(0) if match else "Not found"


def _extract_phone(text: str, soup: BeautifulSoup) -> str:
    tel = soup.select_one("a[href^='tel:']")
    if tel and tel.get("href"):
        return tel.get("href", "").replace("tel:", "").strip() or "Not found"
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else "Not found"


def _extract_products(text: str) -> str:
    lowered = text.lower()
    found = [hint for hint in PRODUCT_HINTS if hint in lowered]
    if found:
        unique = []
        for item in found:
            if item not in unique:
                unique.append(item)
        return ", ".join(unique[:5])
    return "Not found"


def _extract_company_name(soup: BeautifulSoup, fallback: str) -> str:
    candidates = []

    for selector in ["meta[property='og:site_name']", "meta[property='og:title']", "meta[name='application-name']"]:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            candidates.append(tag.get("content", "").strip())

    if soup.h1:
        candidates.append(soup.h1.get_text(" ", strip=True))
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))
    candidates.append(fallback)

    for candidate in candidates:
        cleaned = clean_company_name(candidate)
        if is_likely_company_name(cleaned):
            return cleaned
    return clean_company_name(fallback)


def fetch_company_details(record: CompanyRecord, timeout: int = 20) -> CompanyRecord:
    if record.website == "Not found":
        return record

    try:
        response = requests.get(
            record.website,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        record.notes.append(f"Page fetch failed: {exc}")
        return record

    soup = BeautifulSoup(response.text, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_description = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_tag:
        meta_description = meta_tag.get("content", "").strip()

    body_text = soup.get_text(" ", strip=True)
    compact_text = re.sub(r"\s+", " ", body_text)
    company_name = _extract_company_name(soup, _pick_first(record.name, page_title))
    email = _extract_email(compact_text, soup)
    phone = _extract_phone(compact_text, soup)
    location = _pick_first(record.location, infer_location(compact_text))
    products = _pick_first(record.products, _extract_products(compact_text), meta_description)
    description = _pick_first(meta_description, record.description, compact_text[:280])

    home_canonical = soup.find("link", rel=lambda value: value and "canonical" in str(value).lower())
    website = record.website
    if home_canonical and home_canonical.get("href"):
        website = urljoin(record.website, home_canonical.get("href"))

    enriched = CompanyRecord(
        name=company_name,
        location=location,
        website=website,
        domain=extract_domain(website),
        email=_pick_first(record.email, email),
        phone=_pick_first(record.phone, phone),
        products=products,
        description=description,
        source=record.source,
        source_type="page_extract",
        confidence=min(max(record.confidence, 0.72), 0.97),
        notes=[note for note in record.notes if not note.startswith("Page fetch failed:")],
    )
    enriched.notes.append("Details extracted from the company page.")

    if not is_likely_company_record(enriched):
        enriched.notes.append("Filtered after page extraction because the page did not look like a company profile.")

    return enriched
