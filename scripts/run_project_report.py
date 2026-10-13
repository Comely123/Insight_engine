#!/usr/bin/env python3
"""Create a sample research project (if needed) and run report export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.research_repository import ResearchRepository
from insight_engine.research.service import ResearchWorkbenchService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--window", type=int, default=90)
    args = parser.parse_args()

    initialize_database()
    with get_connection() as conn:
        svc = ResearchWorkbenchService(conn)
        repo = ResearchRepository(conn)
        project_id = args.project_id
        if not project_id:
            projects = repo.list_projects()
            if projects:
                project_id = projects[0]["project_id"]
            else:
                created = svc.create_project(
                    name="宠物毛发祈福与纪念研究",
                    research_question="活体祈福与离世纪念需求如何分布？",
                    target_market="中国",
                    geo_scope="中国",
                    keywords=["祈福", "编织", "手绳", "毛发", "纪念"],
                    synonyms=["平安结", "纪念品"],
                    exclude_keywords=[],
                )
                project_id = created["project_id"]
        result = svc.run_project(project_id, window_days=args.window, export=True)
    print(
        json.dumps(
            {
                "project_id": project_id,
                "run_id": result["run_id"],
                "docs": result["document_count"],
                "alerts": len(result["alerts"]),
                "report_path": result.get("report_path"),
                "citation_ok": result["report"].get("citation_validation", {}).get("ok"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
