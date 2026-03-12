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
    "jobs in ",
    "vacancies",
    "careers",
    "hiring",
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
    "naukri",
    "indeed",
    "foundit",
    "glassdoor",
)
AGGREGATOR_DOMAIN_PARTS = (
    "linkedin",
    "ambitionbox",
    "pharmacompass",
    "zaubacorp",
    "tradeindia",
    "indiamart",
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


def is_official_domain(domain: str) -> bool:
    return domain != "Not found" and not any(part in domain for part in AGGREGATOR_DOMAIN_PARTS + BAD_DOMAIN_PARTS)


def is_likely_company_name(name: str) -> bool:
    cleaned = clean_company_name(name).lower()
    if cleaned == "unknown company":
        return False
    if any(pattern in cleaned for pattern in BAD_NAME_PATTERNS):
        return False
    if len(cleaned.split()) > 8:
        return False
    return any(token in cleaned for token in GOOD_COMPANY_SUFFIXES) or len(cleaned.split()) <= 4


def quality_score(record: CompanyRecord) -> float:
    score = 0.0
    if record.website != "Not found":
        score += 2.0
    if record.email != "Not found":
        score += 1.5
    if record.phone != "Not found":
        score += 1.5
    if record.location != "Not found":
        score += 1.0
    if record.products != "Not found":
        score += 1.0
    if record.description != "Not found":
        score += 0.5
    if is_official_domain(extract_domain(record.website)):
        score += 2.5
    return score


def has_minimum_company_data(record: CompanyRecord) -> bool:
    fields = sum(
        1 for value in [record.website, record.email, record.phone, record.location, record.products] if value != "Not found"
    )
    return fields >= 2


def is_likely_company_record(record: CompanyRecord) -> bool:
    name = clean_company_name(record.name).lower()
    domain = extract_domain(record.website)
    description = (record.description or "").lower()
    website = (record.website or "").lower()

    if not is_likely_company_name(name):
        return False
    if any(pattern in description for pattern in ("top 10", "top 20", "best pharma", "list of companies", "wikipedia")):
        return False
    if any(pattern in website for pattern in ("/jobs", "jobs-", "careers", "vacancies")):
        return False
    if domain != "Not found" and any(part in domain for part in BAD_DOMAIN_PARTS):
        return False
    if not has_minimum_company_data(record) and not is_official_domain(domain):
        return False
    return True


def merge_records(primary: CompanyRecord, secondary: CompanyRecord) -> CompanyRecord:
    if primary.location == "Not found" and secondary.location != "Not found":
        primary.location = secondary.location
    if primary.website == "Not found" and secondary.website != "Not found":
        primary.website = secondary.website
    if primary.domain == "Not found" and secondary.domain != "Not found":
        primary.domain = secondary.domain
    if primary.email == "Not found" and secondary.email != "Not found":
        primary.email = secondary.email
    if primary.phone == "Not found" and secondary.phone != "Not found":
        primary.phone = secondary.phone
    if primary.products == "Not found" and secondary.products != "Not found":
        primary.products = secondary.products
    if primary.description == "Not found" and secondary.description != "Not found":
        primary.description = secondary.description
    if hasattr(secondary, "jobs") and secondary.jobs:
        seen = {job.apply_link for job in primary.jobs}
        for job in secondary.jobs:
            if job.apply_link not in seen:
                primary.jobs.append(job)
                seen.add(job.apply_link)
    for note in secondary.notes:
        if note not in primary.notes:
            primary.notes.append(note)
    primary.confidence = max(primary.confidence, secondary.confidence)
    return primary


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
        record.confidence = min(0.35 + quality_score(record) / 10.0, 0.98)

    return record


def dedupe_records(records: list[CompanyRecord]) -> list[CompanyRecord]:
    deduped: dict[str, CompanyRecord] = {}

    for record in records:
        if not is_likely_company_record(record):
            continue

        normalized_name = clean_company_name(record.name).lower()
        key = record.domain if is_official_domain(record.domain) else normalized_name
        existing = deduped.get(key)

        if existing is None:
            deduped[key] = record
            continue

        existing_score = quality_score(existing)
        current_score = quality_score(record)
        if current_score > existing_score:
            deduped[key] = merge_records(record, existing)
        else:
            deduped[key] = merge_records(existing, record)

    final_records = [record for record in deduped.values() if is_likely_company_record(record)]
    final_records.sort(key=lambda item: (not is_official_domain(item.domain), item.name.lower()))
    return final_records
