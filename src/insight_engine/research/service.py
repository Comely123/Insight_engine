"""Research workbench orchestration: project → filter → trends → alerts → report."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from insight_engine.config import Settings, get_settings
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.db.research_repository import ResearchRepository
from insight_engine.models.research import KeywordVersionCreate, ResearchProjectCreate
from insight_engine.reports.builder import build_research_report, export_report
from insight_engine.research.keywords import filter_document_ids, fetch_documents_by_ids
from insight_engine.trends.alerts import generate_alerts
from insight_engine.trends.metrics import compute_trend_metrics


class ResearchWorkbenchService:
    def __init__(self, conn: sqlite3.Connection, settings: Settings | None = None) -> None:
        self.conn = conn
        self.settings = settings or get_settings()
        self.repo = ResearchRepository(conn)

    def create_project(
        self,
        *,
        name: str,
        research_question: str | None = None,
        target_market: str | None = None,
        geo_scope: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        keywords: list[str] | None = None,
        synonyms: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        change_note: str = "initial",
        price_min: float | None = None,
        price_max: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        self.repo.create_project(
            ResearchProjectCreate(
                project_id=project_id,
                name=name,
                research_question=research_question,
                target_market=target_market,
                geo_scope=geo_scope,
                time_start=time_start,
                time_end=time_end,
                price_min=price_min,
                price_max=price_max,
                notes=notes,
            )
        )
        version = self.add_keyword_version(
            project_id,
            keywords=keywords or [],
            synonyms=synonyms or [],
            exclude_keywords=exclude_keywords or [],
            change_note=change_note,
        )
        self.conn.commit()
        return {"project_id": project_id, "keyword_version": version}

    def add_keyword_version(
        self,
        project_id: str,
        *,
        keywords: list[str],
        synonyms: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        n = self.repo.next_keyword_version_number(project_id)
        version_id = str(uuid.uuid4())
        payload = KeywordVersionCreate(
            version_id=version_id,
            project_id=project_id,
            version_number=n,
            keywords=keywords,
            synonyms=synonyms or [],
            exclude_keywords=exclude_keywords or [],
            change_note=change_note,
        )
        self.repo.add_keyword_version(payload)
        self.conn.commit()
        return {
            "version_id": version_id,
            "version_number": n,
            "keywords": keywords,
            "synonyms": synonyms or [],
            "exclude_keywords": exclude_keywords or [],
            "change_note": change_note,
        }

    def search_project_documents(self, project_id: str) -> list[dict[str, Any]]:
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError("project not found")
        kv = self.repo.latest_keyword_version(project_id)
        source_filters = json.loads(project.get("source_filters_json") or "{}")
        source_names = source_filters.get("source_names")
        ids = filter_document_ids(
            self.conn,
            keywords=(kv or {}).get("keywords") or [],
            synonyms=(kv or {}).get("synonyms") or [],
            exclude_keywords=(kv or {}).get("exclude_keywords") or [],
            time_start=project.get("time_start"),
            time_end=project.get("time_end"),
            source_names=source_names,
        )
        return fetch_documents_by_ids(self.conn, ids)

    def ensure_behavior_claims(self, document_ids: list[str] | None = None) -> int:
        """Insert behavior_stage/demand_subtype claims for docs missing them (no full re-analysis)."""
        from insight_engine.db.analysis_repository import AnalysisRepository
        from insight_engine.models.analysis import DocumentAnalysisResult
        from insight_engine.research.behavior import classify_behavior_and_subtype

        sql = """
            SELECT d.document_id, d.title, d.normalized_content, d.raw_content,
                   d.published_at, d.collected_at
            FROM documents d
            WHERE d.is_duplicate = 0
              AND NOT EXISTS (
                SELECT 1 FROM claims c
                WHERE c.document_id = d.document_id AND c.claim_type = 'behavior_stage'
              )
        """
        rows = [dict(r) for r in self.conn.execute(sql).fetchall()]
        if document_ids is not None:
            wanted = set(document_ids)
            rows = [r for r in rows if r["document_id"] in wanted]
        if not rows:
            return 0

        ar = AnalysisRepository(self.conn)
        run_id = str(uuid.uuid4())
        ar.create_run(
            run_id=run_id,
            analyzer_type="rules_behavior",
            model_name=None,
            prompt_version="research-rules-v1",
            config={"mode": "behavior_only"},
        )
        created = 0
        for row in rows:
            claims = classify_behavior_and_subtype(
                document_id=row["document_id"],
                title=row.get("title"),
                content=row.get("normalized_content") or row.get("raw_content"),
            )
            result = DocumentAnalysisResult(
                document_id=row["document_id"],
                claims=claims,
                event_title=row.get("title") or row["document_id"][:8],
                event_summary="behavior_stage enrichment",
                analyzer="rules",
                prompt_version="research-rules-v1",
                confidence=0.5,
            )
            ar.persist_document_analysis(
                run_id=run_id,
                result=result,
                event_time=row.get("published_at") or row.get("collected_at"),
            )
            created += 1
        ar.finalize_run(
            run_id=run_id,
            status="succeeded",
            document_count=created,
            error_summary=None,
        )
        self.conn.commit()
        return created


    def run_project(
        self,
        project_id: str,
        *,
        window_days: int = 30,
        export: bool = True,
        reanalyze_missing: bool = True,
    ) -> dict[str, Any]:
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError("project not found")
        kv = self.repo.latest_keyword_version(project_id)
        docs = self.search_project_documents(project_id)
        doc_ids = [d["document_id"] for d in docs]

        run_id = self.repo.create_run(
            project_id=project_id,
            keyword_version_id=(kv or {}).get("version_id"),
            window_days=window_days,
        )
        self.conn.commit()

        try:
            if reanalyze_missing:
                self.ensure_behavior_claims(doc_ids)

            trend = compute_trend_metrics(
                self.conn,
                window_days=window_days,
                document_ids=doc_ids,
                project_id=project_id,
                persist=True,
            )
            alert_models = generate_alerts(
                self.conn, trend, project_id=project_id, run_id=run_id
            )
            for a in alert_models:
                self.repo.insert_alert(a)

            payload = build_research_report(
                self.conn,
                project=project,
                keyword_version=kv,
                report=trend,
                alerts=[a.model_dump() for a in alert_models],
            )
            report_path = None
            if export:
                out_dir = self.settings.data_dir / "exports" / "reports" / project_id
                paths = export_report(
                    self.conn, payload, out_dir=out_dir, basename=f"report_{run_id[:8]}"
                )
                report_path = str(paths["markdown"])
                cite_ok = bool(payload.get("citation_validation", {}).get("ok"))
                cite_errs = payload.get("citation_validation", {}).get("errors") or []
                for fmt, path in paths.items():
                    self.repo.insert_report_export(
                        project_id=project_id,
                        run_id=run_id,
                        format=fmt,
                        file_path=str(path),
                        citation_ok=cite_ok,
                        citation_errors=cite_errs if fmt == "markdown" else [],
                    )

            self.repo.finalize_run(
                run_id,
                status="succeeded",
                metrics=trend.to_dict(),
                alert_count=len(alert_models),
                report_path=report_path,
                error_summary=None,
            )
            self.conn.commit()
            return {
                "run_id": run_id,
                "document_count": len(doc_ids),
                "trend": trend.to_dict(),
                "alerts": [a.model_dump() for a in alert_models],
                "report": payload,
                "report_path": report_path,
            }
        except Exception as exc:  # noqa: BLE001
            self.repo.finalize_run(
                run_id,
                status="failed",
                metrics=None,
                alert_count=0,
                report_path=None,
                error_summary=str(exc),
            )
            self.conn.commit()
            raise

    def review_alert(self, alert_id: str, status: str, *, note: str | None = None) -> None:
        from datetime import datetime, timezone

        self.repo.set_alert_status(alert_id, status)
        self.conn.execute(
            """
            INSERT INTO human_reviews (
              review_id, target_type, target_id, action, previous_value, new_value,
              note, reviewer, created_at
            ) VALUES (?, 'alert', ?, ?, NULL, ?, ?, 'local_user', ?)
            """,
            (
                str(uuid.uuid4()),
                alert_id,
                "confirm" if status == "confirmed" else status,
                status,
                note,
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )
        self.conn.commit()
