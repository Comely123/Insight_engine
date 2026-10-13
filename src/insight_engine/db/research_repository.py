"""Persistence for research projects, keyword versions, alerts, reports."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from insight_engine.models.research import (
    KeywordVersionCreate,
    ResearchProjectCreate,
    TrendAlertRecord,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ResearchRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_project(self, project: ResearchProjectCreate) -> None:
        now = _utc_now()
        self.conn.execute(
            """
            INSERT INTO research_projects (
              project_id, name, research_question, target_market, geo_scope,
              time_start, time_end, price_min, price_max, source_filters_json,
              quality_requirements, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.project_id,
                project.name,
                project.research_question,
                project.target_market,
                project.geo_scope,
                project.time_start,
                project.time_end,
                project.price_min,
                project.price_max,
                json.dumps(project.source_filters, ensure_ascii=False),
                project.quality_requirements,
                project.notes,
                now,
                now,
            ),
        )

    def update_project(self, project: ResearchProjectCreate) -> None:
        self.conn.execute(
            """
            UPDATE research_projects SET
              name=?, research_question=?, target_market=?, geo_scope=?,
              time_start=?, time_end=?, price_min=?, price_max=?,
              source_filters_json=?, quality_requirements=?, notes=?, updated_at=?
            WHERE project_id=?
            """,
            (
                project.name,
                project.research_question,
                project.target_market,
                project.geo_scope,
                project.time_start,
                project.time_end,
                project.price_min,
                project.price_max,
                json.dumps(project.source_filters, ensure_ascii=False),
                project.quality_requirements,
                project.notes,
                _utc_now(),
                project.project_id,
            ),
        )

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM research_projects ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM research_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def next_keyword_version_number(self, project_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) AS m
            FROM project_keyword_versions WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        return int(row["m"]) + 1

    def add_keyword_version(self, version: KeywordVersionCreate) -> None:
        self.conn.execute(
            """
            INSERT INTO project_keyword_versions (
              version_id, project_id, version_number, keywords_json, synonyms_json,
              exclude_keywords_json, change_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.project_id,
                version.version_number,
                json.dumps(version.keywords, ensure_ascii=False),
                json.dumps(version.synonyms, ensure_ascii=False),
                json.dumps(version.exclude_keywords, ensure_ascii=False),
                version.change_note,
                _utc_now(),
            ),
        )

    def list_keyword_versions(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM project_keyword_versions
            WHERE project_id = ?
            ORDER BY version_number DESC
            """,
            (project_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["keywords"] = json.loads(d.get("keywords_json") or "[]")
            d["synonyms"] = json.loads(d.get("synonyms_json") or "[]")
            d["exclude_keywords"] = json.loads(d.get("exclude_keywords_json") or "[]")
            out.append(d)
        return out

    def latest_keyword_version(self, project_id: str) -> dict[str, Any] | None:
        versions = self.list_keyword_versions(project_id)
        return versions[0] if versions else None

    def create_run(
        self,
        *,
        project_id: str,
        keyword_version_id: str | None,
        window_days: int,
    ) -> str:
        run_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO project_runs (
              run_id, project_id, keyword_version_id, window_days, started_at, status
            ) VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (run_id, project_id, keyword_version_id, window_days, _utc_now()),
        )
        return run_id

    def finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        metrics: dict[str, Any] | None,
        alert_count: int,
        report_path: str | None,
        error_summary: str | None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE project_runs SET
              finished_at=?, status=?, metrics_json=?, alert_count=?,
              report_path=?, error_summary=?
            WHERE run_id=?
            """,
            (
                _utc_now(),
                status,
                json.dumps(metrics or {}, ensure_ascii=False),
                alert_count,
                report_path,
                error_summary,
                run_id,
            ),
        )

    def insert_alert(self, alert: TrendAlertRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO trend_alerts (
              alert_id, project_id, run_id, alert_type, severity, title, trigger_reason,
              metric_values_json, compare_window_days, sample_size,
              supporting_evidence_json, opposing_evidence_json, quality_notes,
              review_suggestion, review_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert.alert_id,
                alert.project_id,
                alert.run_id,
                alert.alert_type,
                alert.severity,
                alert.title,
                alert.trigger_reason,
                json.dumps(alert.metric_values, ensure_ascii=False),
                alert.compare_window_days,
                alert.sample_size,
                json.dumps(alert.supporting_evidence, ensure_ascii=False),
                json.dumps(alert.opposing_evidence, ensure_ascii=False),
                alert.quality_notes,
                alert.review_suggestion,
                alert.review_status,
                _utc_now(),
            ),
        )

    def list_alerts(self, project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if project_id:
            rows = self.conn.execute(
                """
                SELECT * FROM trend_alerts WHERE project_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM trend_alerts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metric_values"] = json.loads(d.get("metric_values_json") or "{}")
            d["supporting_evidence"] = json.loads(d.get("supporting_evidence_json") or "[]")
            d["opposing_evidence"] = json.loads(d.get("opposing_evidence_json") or "[]")
            out.append(d)
        return out

    def set_alert_status(self, alert_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE trend_alerts SET review_status = ? WHERE alert_id = ?",
            (status, alert_id),
        )

    def insert_report_export(
        self,
        *,
        project_id: str | None,
        run_id: str | None,
        format: str,
        file_path: str,
        citation_ok: bool,
        citation_errors: list[str],
    ) -> str:
        export_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO report_exports (
              export_id, project_id, run_id, format, file_path,
              citation_ok, citation_errors_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                export_id,
                project_id,
                run_id,
                format,
                file_path,
                int(citation_ok),
                json.dumps(citation_errors, ensure_ascii=False),
                _utc_now(),
            ),
        )
        return export_id
