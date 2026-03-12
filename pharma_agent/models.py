from dataclasses import dataclass, field


@dataclass(slots=True)
class JobRecord:
    title: str
    company: str
    location: str = "Not found"
    apply_link: str = "Not found"
    source: str = "Unknown"
    summary: str = "Not found"


@dataclass(slots=True)
class CompanyRecord:
    name: str
    location: str = "Not found"
    website: str = "Not found"
    domain: str = "Not found"
    email: str = "Not found"
    phone: str = "Not found"
    products: str = "Not found"
    description: str = "Not found"
    source: str = "Unknown"
    source_type: str = "unknown"
    confidence: float = 0.0
    jobs: list[JobRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResearchResult:
    query: str
    title: str
    companies: list[CompanyRecord]


def normalize_record(raw: dict) -> CompanyRecord:
    name = raw.get("name") or raw.get("company_name") or raw.get("title") or "Unknown company"
    website = raw.get("website") or raw.get("link") or "Not found"
    products = raw.get("products") or raw.get("specialization") or raw.get("snippet") or "Not found"
    description = raw.get("description") or raw.get("snippet") or products

    notes = raw.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]

    confidence = raw.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    return CompanyRecord(
        name=name,
        location=raw.get("location") or "Not found",
        website=website,
        domain=raw.get("domain") or "Not found",
        email=raw.get("email") or "Not found",
        phone=raw.get("phone") or "Not found",
        products=products,
        description=description,
        source=raw.get("source") or website or "Unknown",
        source_type=raw.get("source_type") or "unknown",
        confidence=confidence,
        jobs=raw.get("jobs") or [],
        notes=notes,
    )
