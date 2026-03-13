from __future__ import annotations

import json
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
CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/about-us")


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


def _extract_ld_json_name(soup: BeautifulSoup) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text(" ", strip=True)
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                return str(item.get("name")).strip()
    return "Not found"


def _extract_name_from_text(text: str) -> str:
    match = re.search(r"([A-Z][A-Za-z0-9&'.,\- ]{2,80}?\s(?:Pharma|Pharmaceuticals?|Laboratories|Labs|Healthcare|Biotech|Life Sciences|Limited|Ltd|Pvt Ltd|Private Limited))", text)
    return match.group(1).strip() if match else "Not found"


def _extract_name_from_domain(domain: str) -> str:
    if domain == "Not found":
        return "Not found"
    base = domain.split(".")[0].strip()
    if len(base) < 3:
        return "Not found"
    return re.sub(r"[-_]+", " ", base).title()


def _extract_footer_name(text: str) -> str:
    match = re.search(
        r"(?:copyright|all rights reserved)[^A-Za-z0-9]{0,12}([A-Z][A-Za-z0-9&'.,\- ]{2,80}?\s(?:Pharma|Pharmaceuticals?|Laboratories|Labs|Healthcare|Biotech|Life Sciences|Limited|Ltd|Pvt Ltd|Private Limited))",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else "Not found"


def _extract_company_name(soup: BeautifulSoup, fallback: str, text: str, domain: str) -> str:
    candidates = []

    ld_name = _extract_ld_json_name(soup)
    if ld_name != "Not found":
        candidates.append(ld_name)

    for selector in ["meta[property='og:site_name']", "meta[property='og:title']", "meta[name='application-name']"]:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            candidates.append(tag.get("content", "").strip())

    if soup.h1:
        candidates.append(soup.h1.get_text(" ", strip=True))
    if soup.title:
        candidates.append(soup.title.get_text(" ", strip=True))
    logo = soup.select_one("img[alt*='logo' i], img[class*='logo' i]")
    if logo and logo.get("alt"):
        candidates.append(logo.get("alt", "").strip())

    text_name = _extract_name_from_text(text)
    if text_name != "Not found":
        candidates.append(text_name)
    footer_name = _extract_footer_name(text)
    if footer_name != "Not found":
        candidates.append(footer_name)
    domain_name = _extract_name_from_domain(domain)
    if domain_name != "Not found":
        candidates.append(domain_name)

    candidates.append(fallback)

    for candidate in candidates:
        cleaned = clean_company_name(candidate)
        if is_likely_company_name(cleaned):
            return cleaned
    return clean_company_name(fallback)


def _fetch_page(url: str, timeout: int) -> tuple[str, BeautifulSoup] | None:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return text, soup


def fetch_company_details(record: CompanyRecord, timeout: int = 20) -> CompanyRecord:
    if record.website == "Not found":
        return record

    try:
        fetched = _fetch_page(record.website, timeout)
        if not fetched:
            return record
        compact_text, soup = fetched
    except requests.RequestException as exc:
        record.notes.append(f"Page fetch failed: {exc}")
        return record

    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_description = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_tag:
        meta_description = meta_tag.get("content", "").strip()

    domain = extract_domain(record.website)
    company_name = _extract_company_name(soup, _pick_first(record.name, page_title), compact_text, domain)
    email = _extract_email(compact_text, soup)
    phone = _extract_phone(compact_text, soup)
    location = _pick_first(record.location, infer_location(compact_text))
    products = _pick_first(record.products, _extract_products(compact_text), meta_description)
    description = _pick_first(meta_description, record.description, compact_text[:280])

    website = record.website
    home_canonical = soup.find("link", rel=lambda value: value and "canonical" in str(value).lower())
    if home_canonical and home_canonical.get("href"):
        website = urljoin(record.website, home_canonical.get("href"))

    if email == "Not found" or phone == "Not found" or location == "Not found":
        for path in CONTACT_PATHS:
            try:
                contact_text, contact_soup = _fetch_page(urljoin(website, path), timeout)
            except requests.RequestException:
                continue
            email = _pick_first(email, _extract_email(contact_text, contact_soup))
            phone = _pick_first(phone, _extract_phone(contact_text, contact_soup))
            location = _pick_first(location, infer_location(contact_text))
            if email != "Not found" and phone != "Not found" and location != "Not found":
                break

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
        jobs=record.jobs,
    )
    enriched.notes.append("Details extracted from the company page.")

    if not is_likely_company_record(enriched):
        enriched.notes.append("Filtered after page extraction because the page did not look like a company profile.")

    return enriched
