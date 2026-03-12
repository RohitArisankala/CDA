from __future__ import annotations

import re
from urllib.parse import urlparse

from pharma_agent.models import CompanyRecord

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
COMMON_SUFFIXES = (
    "official site",
    "home",
    "welcome",
    "linkedin",
    "facebook",
    "instagram",
)
BAD_NAME_PATTERNS = (
    "top ",
    "best ",
    "list of ",
    "companies in ",
    "manufacturers in ",
    "distributors in ",
    "pharma companies in ",
    "pharmaceutical companies in ",
    "wikipedia",
)
BAD_DOMAIN_PARTS = (
    "justdial",
    "sulekha",
    "tradeindia",
    "indiamart",
    "exportersindia",
    "clickindia",
    "yellowpages",
    "wikipedia",
    "wikidata",
    "mapquest",
)
GOOD_COMPANY_SUFFIXES = (
    "pharma",
    "pharmaceutical",
    "pharmaceuticals",
    "laboratories",
    "labs",
    "healthcare",
    "health care",
    "lifesciences",
    "life sciences",
    "biotech",
    "biosciences",
    "formulations",
    "medicines",
    "drugs",
    "limited",
    "ltd",
    "private limited",
    "pvt ltd",
    "inc",
)


def clean_company_name(value: str) -> str:
    name = re.split(r"\s+[|:-]\s+", value or "", maxsplit=1)[0].strip()
    name = re.sub(r"\s*\([^)]*\)$", "", name).strip()
    lowered = name.lower()
    for suffix in COMMON_SUFFIXES:
        if lowered.endswith(suffix):
            name = name[: -len(suffix)].strip(" -:|")
            lowered = name.lower()
    return name or "Unknown company"


def extract_domain(url: str) -> str:
    if not url or url == "Not found":
        return "Not found"
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().removeprefix("www.")
    return host or "Not found"


def infer_location(text: str) -> str:
    if not text:
        return "Not found"
    match = re.search(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),\s*(India|USA|United States|UK|United Kingdom|Canada|Germany|Singapore)\b",
        text,
    )
    if match:
        return f"{match.group(1)}, {match.group(2)}"
    return "Not found"


def is_likely_company_name(name: str) -> bool:
    cleaned = clean_company_name(name).lower()
    if cleaned == "unknown company":
        return False
    if any(pattern in cleaned for pattern in BAD_NAME_PATTERNS):
        return False
    if len(cleaned.split()) > 8:
        return False
    return any(token in cleaned for token in GOOD_COMPANY_SUFFIXES) or len(cleaned.split()) <= 4


def is_likely_company_record(record: CompanyRecord) -> bool:
    name = clean_company_name(record.name).lower()
    domain = extract_domain(record.website)
    description = (record.description or "").lower()

    if not is_likely_company_name(name):
        return False
    if any(pattern in description for pattern in ("top 10", "top 20", "best pharma", "list of companies", "wikipedia")):
        return False
    if domain != "Not found" and any(part in domain for part in BAD_DOMAIN_PARTS):
        return False
    return True


def enrich_record(record: CompanyRecord) -> CompanyRecord:
    combined_text = " ".join(
        part for part in [record.name, record.description, record.products, record.source] if part and part != "Not found"
    )

    if record.name == "Unknown company":
        record.name = clean_company_name(record.description)
    else:
        record.name = clean_company_name(record.name)

    if record.domain == "Not found":
        record.domain = extract_domain(record.website)

    if record.email == "Not found":
        email_match = EMAIL_RE.search(combined_text)
        if email_match:
            record.email = email_match.group(0)
            record.notes.append("Email inferred from source text.")

    if record.phone == "Not found":
        phone_match = PHONE_RE.search(combined_text)
        if phone_match:
            record.phone = phone_match.group(0)
            record.notes.append("Phone inferred from source text.")

    if record.location == "Not found":
        inferred_location = infer_location(combined_text)
        if inferred_location != "Not found":
            record.location = inferred_location
            record.notes.append("Location inferred from source text.")

    if record.confidence <= 0:
        confidence = 0.35
        if record.website != "Not found":
            confidence += 0.2
        if record.email != "Not found":
            confidence += 0.15
        if record.phone != "Not found":
            confidence += 0.15
        if record.location != "Not found":
            confidence += 0.1
        if record.products != "Not found":
            confidence += 0.05
        record.confidence = min(confidence, 0.95)

    return record


def dedupe_records(records: list[CompanyRecord]) -> list[CompanyRecord]:
    deduped: dict[str, CompanyRecord] = {}

    for record in records:
        if not is_likely_company_record(record):
            continue

        key = record.domain if record.domain != "Not found" else clean_company_name(record.name).lower()
        existing = deduped.get(key)
        if existing is None or record.confidence > existing.confidence:
            deduped[key] = record
        elif existing is not None:
            existing.notes.extend(note for note in record.notes if note not in existing.notes)
            if existing.products == "Not found" and record.products != "Not found":
                existing.products = record.products
            if existing.location == "Not found" and record.location != "Not found":
                existing.location = record.location
            if existing.email == "Not found" and record.email != "Not found":
                existing.email = record.email
            if existing.phone == "Not found" and record.phone != "Not found":
                existing.phone = record.phone

    return sorted(deduped.values(), key=lambda item: item.name.lower())
