from __future__ import annotations

import argparse
from pathlib import Path

from pharma_agent.config import load_app_env
from pharma_agent.pipeline import PharmacyResearchAgent
from pharma_agent.reporting import build_report
from pharma_agent.search import JsonFileSource, SerperSearchSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect pharmacy company details and export them to a Word document."
    )
    parser.add_argument(
        "--query",
        default="pharmacy companies in India",
        help="Search query to use with the live search provider.",
    )
    parser.add_argument(
        "--input-file",
        help="Optional JSON file containing company records. If provided, no web search is performed.",
    )
    parser.add_argument(
        "--output-file",
        default="pharma_companies.docx",
        help="Path to the generated Word document.",
    )
    parser.add_argument(
        "--title",
        default="Pharmacy Companies Research",
        help="Document title.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of company records to include.",
    )
    return parser


def main() -> int:
    load_app_env()

    parser = build_parser()
    args = parser.parse_args()

    if args.input_file:
        source = JsonFileSource(args.input_file)
    else:
        source = SerperSearchSource()

    agent = PharmacyResearchAgent(source)
    result = agent.run(query=args.query, max_results=args.max_results, title=args.title)
    if not result.companies:
        parser.error("No company records were found.")

    output_path = build_report(result, Path(args.output_file))
    print(f"Generated Word report: {output_path.resolve()}")
    return 0
