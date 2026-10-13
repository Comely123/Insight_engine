#!/usr/bin/env python3
"""Repeatable local performance baseline (not an SLA)."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.config import get_settings, reset_settings_cache
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.ingest.service import ImportService
from insight_engine.llm.null_provider import NullLLMProvider
from insight_engine.ops.logging_util import get_logger
from insight_engine.research.service import ResearchWorkbenchService
from insight_engine.search.fts import SearchFilters, search_documents
from insight_engine.trends.metrics import compute_trend_metrics

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "fixtures"
log = get_logger("insight_engine.bench")


def _timed(name: str, fn):
    t0 = time.perf_counter()
    result = fn()
    ms = (time.perf_counter() - t0) * 1000
    return ms, result


def main() -> None:
    # Isolated bench DB under data/benchmarks
    bench_dir = ROOT / "data" / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    db_path = bench_dir / f"bench_{uuid.uuid4().hex[:8]}.db"
    os.environ["INSIGHT_DATA_DIR"] = str(bench_dir)
    os.environ["INSIGHT_DB_PATH"] = str(db_path)
    reset_settings_cache()
    settings = get_settings()
    initialize_database(settings)

    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "db_path": str(db_path),
        "note": "Single-run baseline; not a stable performance guarantee.",
    }

    metrics: dict[str, float] = {}
    with get_connection(db_path) as conn:
        ms, _ = _timed(
            "import_csv",
            lambda: ImportService(conn, settings).import_file(
                SAMPLES / "pet_blessing_sample.csv", save_copy=False
            ),
        )
        metrics["import_csv_ms"] = ms

        ms, _ = _timed(
            "import_json",
            lambda: ImportService(conn, settings).import_file(
                SAMPLES / "pet_blessing_sample.json", save_copy=False
            ),
        )
        metrics["import_json_ms"] = ms

        ms, hits = _timed(
            "fts_search",
            lambda: search_documents(conn, SearchFilters(query="祈福", limit=50)),
        )
        metrics["fts_search_ms"] = ms
        metrics["fts_hits"] = float(len(hits))

        ms, summary = _timed(
            "analyze_rules",
            lambda: AnalysisService(conn, llm=NullLLMProvider()).analyze_documents(),
        )
        metrics["analyze_rules_ms"] = ms
        metrics["analyze_events"] = float(summary.events_created)

        ms, report = _timed(
            "trend_90d",
            lambda: compute_trend_metrics(conn, window_days=90, persist=False),
        )
        metrics["trend_90d_ms"] = ms
        metrics["trend_unique_docs"] = float(report.unique_documents)

        def _project():
            svc = ResearchWorkbenchService(conn, settings)
            created = svc.create_project(
                name="bench",
                research_question="bench",
                keywords=["祈福", "编织", "毛发"],
            )
            return svc.run_project(created["project_id"], window_days=90, export=True)

        ms, proj = _timed("project_report", _project)
        metrics["project_report_ms"] = ms
        metrics["project_docs"] = float(proj["document_count"])

    db_size = db_path.stat().st_size if db_path.exists() else 0
    out = {
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": env,
        "metrics_ms": metrics,
        "db_size_bytes": db_size,
        "disclaimer": "Do not treat a single run as an SLA.",
    }
    out_path = bench_dir / f"bench_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("bench complete path=%s", out_path)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"wrote: {out_path}")


if __name__ == "__main__":
    main()
