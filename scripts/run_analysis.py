#!/usr/bin/env python3
"""Run Phase 2 rule analysis on documents in the local database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.db.connection import get_connection, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Run structured analysis")
    parser.add_argument("--use-llm", action="store_true", help="Try optional LLM enrichment")
    parser.add_argument("--include-duplicates", action="store_true")
    args = parser.parse_args()

    initialize_database()
    with get_connection() as conn:
        service = AnalysisService(conn)
        summary = service.analyze_documents(
            use_llm=args.use_llm,
            include_duplicates=args.include_duplicates,
        )
    print(
        f"run_id={summary.run_id} status={summary.status} "
        f"docs={summary.document_count} events={summary.events_created} "
        f"claims={summary.claims_created} errors={len(summary.errors)}"
    )
    for err in summary.errors[:10]:
        print(f"  - {err}")


if __name__ == "__main__":
    main()
