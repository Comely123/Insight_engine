"""Orchestrate rule (and optional LLM) analysis into the evidence store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from pydantic import ValidationError

from insight_engine.analysis.rules import analyze_document_rules, load_rules
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.llm.base import LLMProvider
from insight_engine.llm.factory import get_llm_provider
from insight_engine.models.analysis import AnalysisRunSummary, DocumentAnalysisResult

LLM_SYSTEM_PROMPT = """You are a research extraction assistant.
Return ONLY a JSON object with keys:
document_id, topic, intent, stance, prices (number array),
event_title, event_summary, facts, inferences, unknowns,
claims (array of {claim_type, claim_value, polarity, confidence, is_inference, evidence}).
Each evidence item MUST include document_id matching the given document and a non-empty excerpt
copied from the provided text. Do not invent URLs or timestamps.
intent must be one of: interest, inquiry, purchase_intent, payment, fulfillment, unknown.
stance must be one of: positive, negative, neutral, unknown.
Separate facts, inferences, and unknowns.
"""

PROMPT_VERSION_LLM = "llm-extract-v1"


class AnalysisService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: LLMProvider | None = None,
        rules_path: str | None = None,
    ) -> None:
        self.conn = conn
        self.repo = AnalysisRepository(conn)
        self.llm = llm if llm is not None else get_llm_provider()
        self.rules_path = rules_path

    def list_analyzable_documents(self, *, include_duplicates: bool = False) -> list[dict[str, Any]]:
        sql = """
            SELECT document_id, title, normalized_content, raw_content, published_at,
                   collected_at, source_name, permission_status, content_type
            FROM documents
        """
        if not include_duplicates:
            sql += " WHERE is_duplicate = 0"
        sql += " ORDER BY COALESCE(published_at, collected_at) ASC"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def analyze_documents(
        self,
        *,
        document_ids: list[str] | None = None,
        use_llm: bool = False,
        include_duplicates: bool = False,
        research_keywords: list[str] | None = None,
        research_brief: str | None = None,
    ) -> AnalysisRunSummary:
        rules = load_rules(self.rules_path)
        prompt_version = str(rules.get("prompt_version", "rules-v1"))
        analyzer_type = "rules"
        model_name = None

        if use_llm and self.llm.available():
            analyzer_type = "hybrid"
            model_name = getattr(self.llm, "model", self.llm.name)
            prompt_version = f"{prompt_version}+{PROMPT_VERSION_LLM}"
        elif use_llm and not self.llm.available():
            analyzer_type = "rules"
            # continue without LLM; note in errors

        run_id = str(uuid.uuid4())
        started_docs = self.list_analyzable_documents(include_duplicates=include_duplicates)
        if document_ids is not None:
            wanted = set(document_ids)
            started_docs = [d for d in started_docs if d["document_id"] in wanted]

        self.repo.create_run(
            run_id=run_id,
            analyzer_type=analyzer_type,
            model_name=model_name,
            prompt_version=prompt_version,
            config={
                "use_llm": use_llm,
                "include_duplicates": include_duplicates,
                "research_keywords": list(research_keywords or [])[:40],
                "research_brief": (research_brief or "")[:500],
            },
        )
        self.conn.commit()

        errors: list[str] = []
        if use_llm and not self.llm.available():
            errors.append("LLM requested but not configured; fell back to rules-only")

        claims_created = 0
        events_created = 0

        for doc in started_docs:
            content = doc.get("normalized_content") or doc.get("raw_content") or ""
            try:
                result = analyze_document_rules(
                    document_id=doc["document_id"],
                    title=doc.get("title"),
                    content=content,
                    rules_path=self.rules_path,
                    content_type=doc.get("content_type"),
                    research_keywords=research_keywords,
                    research_brief=research_brief,
                )
                if use_llm and self.llm.available():
                    result = self._maybe_enrich_with_llm(run_id, doc, result)

                # Schema already validated via Pydantic construction
                self.repo.persist_document_analysis(
                    run_id=run_id,
                    result=result,
                    event_time=doc.get("published_at") or doc.get("collected_at"),
                )
                events_created += 1
                claims_created += len(result.claims)
            except Exception as exc:  # noqa: BLE001
                msg = f"{doc['document_id']}: {exc}"
                errors.append(msg)
                self.repo.insert_model_output(
                    run_id=run_id,
                    document_id=doc["document_id"],
                    output_type="document_analysis",
                    raw_output=None,
                    validated_json=None,
                    validation_status="invalid",
                    error_message=str(exc),
                )

        status = "succeeded"
        if errors and events_created == 0:
            status = "failed"
        elif errors:
            status = "partial"

        summary = AnalysisRunSummary(
            run_id=run_id,
            status=status,
            analyzer_type=analyzer_type,
            document_count=len(started_docs),
            claims_created=claims_created,
            events_created=events_created,
            errors=errors,
            started_at="",
            finished_at=None,
            model_name=model_name,
            prompt_version=prompt_version,
        )
        self.repo.finalize_run(
            run_id=run_id,
            status=status,
            document_count=len(started_docs),
            error_summary="; ".join(errors[:5]) if errors else None,
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT started_at, finished_at FROM analysis_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        summary.started_at = row["started_at"]
        summary.finished_at = row["finished_at"]
        return summary

    def _maybe_enrich_with_llm(
        self,
        run_id: str,
        doc: dict[str, Any],
        rules_result: DocumentAnalysisResult,
    ) -> DocumentAnalysisResult:
        content = doc.get("normalized_content") or doc.get("raw_content") or ""
        user_prompt = (
            f"document_id: {doc['document_id']}\n"
            f"title: {doc.get('title') or ''}\n"
            f"text:\n{content[:6000]}\n"
        )
        try:
            raw = self.llm.complete_json(
                system_prompt=LLM_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            rules_result.unknowns = list(rules_result.unknowns) + [f"llm_failed: {exc}"]
            self.repo.insert_model_output(
                run_id=run_id,
                document_id=doc["document_id"],
                output_type="llm_raw",
                raw_output=None,
                validated_json=None,
                validation_status="invalid",
                error_message=str(exc),
            )
            return rules_result

        raw["document_id"] = doc["document_id"]
        for claim in raw.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            for ev in claim.get("evidence") or []:
                if isinstance(ev, dict):
                    ev["document_id"] = doc["document_id"]

        try:
            validated = DocumentAnalysisResult.model_validate(raw)
            validated.analyzer = "hybrid"
            validated.model_name = getattr(self.llm, "model", self.llm.name)
            validated.prompt_version = PROMPT_VERSION_LLM
            return validated
        except ValidationError as exc:
            rules_result.unknowns = list(rules_result.unknowns) + [
                f"llm_schema_invalid: {exc.error_count()} errors"
            ]
            self.repo.insert_model_output(
                run_id=run_id,
                document_id=doc["document_id"],
                output_type="llm_raw",
                raw_output=json.dumps(raw, ensure_ascii=False)[:20000],
                validated_json=None,
                validation_status="invalid",
                error_message=str(exc),
            )
            return rules_result
