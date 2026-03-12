from __future__ import annotations

from pathlib import Path

from docx import Document

from pharma_agent.models import ResearchResult


def build_report(result: ResearchResult, output_file: str | Path) -> Path:
    document = Document()
    document.add_heading(result.title, level=1)
    document.add_paragraph(f"Location: {result.query}")
    document.add_paragraph(f"Companies found: {len(result.companies)}")

    for index, record in enumerate(result.companies, start=1):
        document.add_heading(f"{index}. {record.name}", level=2)
        document.add_paragraph(f"Location: {record.location}")
        document.add_paragraph(f"Website: {record.website}")
        document.add_paragraph(f"Email: {record.email}")
        document.add_paragraph(f"Phone: {record.phone}")
        document.add_paragraph(f"Products / Specialization: {record.products}")
        document.add_paragraph(f"Description: {record.description}")

        if record.jobs:
            document.add_paragraph("Open Roles:")
            for job in record.jobs[:5]:
                document.add_paragraph(
                    f"- {job.title} | {job.location} | Apply: {job.apply_link}",
                    style="List Bullet",
                )

    path = Path(output_file)
    document.save(path)
    return path
