"""Public 3-step product pipeline: ingest → analyze → report → wipe raw → archive."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.collectors.registry import get_collector
from insight_engine.config import Settings, get_settings
from insight_engine.db.connection import get_connection
from insight_engine.db.session_repository import SessionRepository
from insight_engine.ingest.service import ImportService
from insight_engine.llm.factory import get_llm_provider
from insight_engine.media.asr.factory import get_asr_provider
from insight_engine.media.ingest import MediaIngestService
from insight_engine.media.pipeline import MediaPipeline
from insight_engine.media.subtitles import load_subtitle_file
from insight_engine.models.documents import PermissionStatus
from insight_engine.ops.ephemeral import delete_path_quietly, wipe_raw_document_bodies
from insight_engine.ops.logging_util import get_logger
from insight_engine.product.narrative import (
    build_rule_narrative,
    enrich_narrative_with_llm,
    narrative_to_markdown,
)
from insight_engine.product.pdf_extract import extract_pdf_text
from insight_engine.product.uploads import pair_captions
from insight_engine.reports.builder import build_research_report, export_report
from insight_engine.research.service import ResearchWorkbenchService
from insight_engine.trends.alerts import generate_alerts
from insight_engine.trends.metrics import compute_trend_metrics

log = get_logger("insight_engine.product")

DEFAULT_BRIEF = (
    "我想分析的是一个小活动，不是新兴产业。"
    "活动大致是：养宠人士寄一撮宠物毛发，由机构集中编织成福袋类祈福物，"
    "再统一送至祈福地点为小动物祈福。"
    "关注中国国内的讨论热度、需求结构、价格与付费线索、正反声音、"
    "相关商业化信号与普及前景所需的数据证据；不需要主观创新打分。"
)


class PublicAnalysisService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(
        self,
        *,
        mode: str,
        keywords: list[str],
        research_brief: str | None = None,
        upload_paths: list[Path] | None = None,
        collector_ids: list[str] | None = None,
        anonymous_id: str | None = None,
        llm_api_key: str | None = None,
        llm_base_url: str | None = None,
        llm_model: str | None = None,
        use_llm: bool = False,
        window_days: int = 90,
    ) -> dict[str, Any]:
        keywords = [k.strip() for k in keywords if k.strip()]
        if mode == "collect" and not keywords:
            raise ValueError("网络采集请填写至少一个关键词")
        brief = (research_brief or "").strip()
        session_id = str(uuid.uuid4())
        collector_ids = collector_ids or (
            ["news_search_rss"] if mode == "collect" else []
        )

        base = (llm_base_url or "").lower()
        prefer_local = use_llm and not (llm_api_key or "").strip() and (
            "127.0.0.1" in base or "localhost" in base or base == ""
        )
        llm = get_llm_provider(
            api_key=llm_api_key,
            base_url=llm_base_url,
            model=llm_model,
            prefer_local=prefer_local,
        )
        if not use_llm:
            llm_mode = "rules_only"
        elif llm_api_key:
            llm_mode = "user_key"
        elif prefer_local:
            llm_mode = "local_default"
        else:
            llm_mode = "cloud_needs_key"

        doc_ids: list[str] = []
        ingest_notes: list[str] = []
        temp_files: list[Path] = []

        with get_connection() as conn:
            importer = ImportService(conn, self.settings)

            if mode == "upload":
                if not upload_paths:
                    raise ValueError("请上传至少一个文件")
                text_paths, media_paths, media_caption_map, unsupported = pair_captions(
                    [Path(p) for p in upload_paths]
                )
                for path in unsupported:
                    ingest_notes.append(f"{path.name}: 不支持的文件类型，已跳过")

                for path in text_paths:
                    import_path = path
                    try:
                        if path.suffix.lower() in {".srt", ".vtt"}:
                            cues = load_subtitle_file(path)
                            body = "\n".join(c.text for c in cues if c.text)
                            if not body.strip():
                                ingest_notes.append(f"{path.name}: 字幕为空")
                                continue
                            content_type = "subtitle"
                            title = path.name
                        elif path.suffix.lower() == ".pdf":
                            body = extract_pdf_text(path)
                            content_type = "literature_pdf"
                            title = path.stem
                        else:
                            body = None
                            content_type = None
                            title = path.name

                        if body is not None:
                            tmp = Path(tempfile.mkdtemp(prefix="insight_doc_")) / f"{path.stem}.json"
                            tmp.write_text(
                                json.dumps(
                                    {
                                        "documents": [
                                            {
                                                "title": title,
                                                "content": body,
                                                "source_name": f"upload:{path.name}",
                                                "content_type": content_type,
                                            }
                                        ]
                                    },
                                    ensure_ascii=False,
                                ),
                                encoding="utf-8",
                            )
                            temp_files.append(tmp)
                            import_path = tmp
                    except Exception as exc:  # noqa: BLE001
                        ingest_notes.append(f"{path.name}: 解析失败 {exc}")
                        continue

                    result = importer.import_file(
                        import_path,
                        source_name=f"upload:{path.name}",
                        permission_status=PermissionStatus.USER_OWNED,
                        license_note="User upload via public product",
                        save_copy=False,
                    )
                    ingest_notes.append(
                        f"{path.name}: imported={result.row_count_imported} status={result.status}"
                    )
                    rows = conn.execute(
                        "SELECT document_id FROM documents WHERE batch_id = ?",
                        (result.batch_id,),
                    ).fetchall()
                    doc_ids.extend(r["document_id"] for r in rows)

                media_svc = MediaIngestService(conn, self.settings)
                media_pipe = MediaPipeline(conn, self.settings)
                asr_ok = get_asr_provider().available()
                for path in media_paths:
                    try:
                        asset = media_svc.import_media(
                            path,
                            permission_status=PermissionStatus.USER_OWNED,
                            source_name=f"upload:{path.name}",
                            license_note="User media upload via public product",
                            copy_into_media_dir=True,
                            subtitle_path=media_caption_map.get(path),
                        )
                        proc = media_pipe.process_media(
                            asset["media_id"],
                            run_asr=asr_ok,
                            run_ocr=False,
                            run_keyframes=False,
                            subtitle_path=media_caption_map.get(path),
                            force=True,
                        )
                        refreshed = media_svc.repo.get_asset(asset["media_id"]) or {}
                        mid_doc = refreshed.get("document_id")
                        if mid_doc:
                            doc_ids.append(mid_doc)
                            ingest_notes.append(
                                f"{path.name}: media={proc.get('status')} doc=ok asr={'on' if asr_ok else 'off'}"
                            )
                        else:
                            # Fallback stub so analysis can still see the file existed
                            stub = Path(tempfile.mkdtemp(prefix="insight_media_")) / f"{path.stem}.json"
                            dur = refreshed.get("duration_seconds")
                            stub.write_text(
                                json.dumps(
                                    {
                                        "documents": [
                                            {
                                                "title": path.name,
                                                "content": (
                                                    f"用户上传媒体文件：{path.name}。"
                                                    f"时长约 {dur or '未知'} 秒。"
                                                    "未能提取字幕/转写文本"
                                                    + ("（未安装 ASR）" if not asr_ok else "")
                                                    + "。可同时上传同名 .srt 字幕以便分析。"
                                                ),
                                                "source_name": f"upload:{path.name}",
                                                "content_type": "media_stub",
                                            }
                                        ]
                                    },
                                    ensure_ascii=False,
                                ),
                                encoding="utf-8",
                            )
                            temp_files.append(stub)
                            result = importer.import_file(
                                stub,
                                source_name=f"upload:{path.name}",
                                permission_status=PermissionStatus.USER_OWNED,
                                license_note="Media stub without transcript",
                                save_copy=False,
                            )
                            rows = conn.execute(
                                "SELECT document_id FROM documents WHERE batch_id = ?",
                                (result.batch_id,),
                            ).fetchall()
                            doc_ids.extend(r["document_id"] for r in rows)
                            ingest_notes.append(
                                f"{path.name}: media={proc.get('status')} 无转写，已记入占位说明"
                            )
                        # Ephemeral: drop copied media file after extract
                        local = refreshed.get("local_path")
                        if local:
                            delete_path_quietly(local)
                    except Exception as exc:  # noqa: BLE001
                        ingest_notes.append(f"{path.name}: 媒体处理失败 {exc}")

            elif mode == "collect":
                # Write collected items to a temp JSON then import
                collected_docs = []
                for cid in collector_ids:
                    collector = get_collector(cid)
                    if collector is None:
                        ingest_notes.append(f"{cid}: unknown collector")
                        continue
                    cres = collector.collect(keywords, limit=80)
                    ingest_notes.append(
                        f"{collector.display_name}: status={cres.status} items={len(cres.items)}"
                    )
                    for err in cres.errors[:5]:
                        ingest_notes.append(f"  - {err}")
                    for item in cres.items:
                        collected_docs.append(
                            {
                                "title": item.title,
                                "content": item.content,
                                "original_url": item.original_url,
                                "published_at": item.published_at,
                                "source_name": item.source_name or collector.display_name,
                                "content_type": item.content_type,
                            }
                        )
                if not collected_docs:
                    # Still archive empty attempt
                    SessionRepository(conn).insert_session(
                        {
                            "session_id": session_id,
                            "anonymous_id": anonymous_id,
                            "mode": mode,
                            "keywords": keywords,
                            "research_brief": brief,
                            "collector_ids": collector_ids,
                            "document_count": 0,
                            "unique_document_count": 0,
                            "report_summary": "未采集到可用样本",
                            "metrics": {"ingest_notes": ingest_notes},
                            "llm_mode": llm_mode,
                        }
                    )
                    conn.commit()
                    return {
                        "session_id": session_id,
                        "status": "empty",
                        "message": "未采集到与关键词匹配的公开数据，请更换关键词或改用上传。",
                        "ingest_notes": ingest_notes,
                        "report": None,
                    }
                tmp = Path(tempfile.mkdtemp(prefix="insight_collect_")) / "collect.json"
                tmp.write_text(
                    json.dumps({"documents": collected_docs}, ensure_ascii=False),
                    encoding="utf-8",
                )
                temp_files.append(tmp)
                result = importer.import_file(
                    tmp,
                    source_name="collector_bundle",
                    permission_status=PermissionStatus.ALLOWED,
                    license_note="Compliant public RSS/collector import",
                    save_copy=False,
                )
                rows = conn.execute(
                    "SELECT document_id FROM documents WHERE batch_id = ?",
                    (result.batch_id,),
                ).fetchall()
                doc_ids.extend(r["document_id"] for r in rows)
            else:
                raise ValueError("mode 必须是 upload 或 collect")

            if not doc_ids:
                SessionRepository(conn).insert_session(
                    {
                        "session_id": session_id,
                        "anonymous_id": anonymous_id,
                        "mode": mode,
                        "keywords": keywords,
                        "research_brief": brief,
                        "collector_ids": collector_ids,
                        "document_count": 0,
                        "unique_document_count": 0,
                        "report_summary": "未得到可分析文档",
                        "metrics": {"ingest_notes": ingest_notes},
                        "llm_mode": llm_mode,
                    }
                )
                conn.commit()
                return {
                    "session_id": session_id,
                    "status": "empty",
                    "message": "导入后没有可分析文档，请检查文件格式（需含正文 content 字段）。",
                    "ingest_notes": ingest_notes,
                    "report": None,
                }

            # Analyze (rules always; LLM optional)
            analysis = AnalysisService(conn, llm=llm).analyze_documents(
                document_ids=doc_ids,
                use_llm=use_llm,
            )

            # Project-scoped report
            research = ResearchWorkbenchService(conn, self.settings)
            created = research.create_project(
                name=f"公开检索 {session_id[:8]}",
                research_question=brief,
                target_market="中国",
                geo_scope="中国",
                keywords=keywords,
                synonyms=[],
                exclude_keywords=[],
                change_note="public product auto",
            )
            project_id = created["project_id"]
            # Restrict to ingested docs via keyword filter; also pass ids into metrics
            trend = compute_trend_metrics(
                conn,
                window_days=window_days,
                document_ids=doc_ids,
                project_id=project_id,
                persist=True,
            )
            alerts = generate_alerts(conn, trend, project_id=project_id, run_id=None)
            project = research.repo.get_project(project_id)
            kv = research.repo.latest_keyword_version(project_id)
            report_payload = build_research_report(
                conn,
                project=project or {"project_id": project_id, "name": "公开检索"},
                keyword_version=kv,
                report=trend,
                alerts=[a.model_dump() for a in alerts],
            )
            narrative = build_rule_narrative(
                conn=conn,
                document_ids=doc_ids,
                keywords=keywords,
                brief=brief,
                trend=trend.to_dict(),
                alerts=[a.model_dump() for a in alerts],
                mode=mode,
            )
            if use_llm:
                narrative = enrich_narrative_with_llm(narrative, llm=llm)
            report_payload["public_narrative"] = narrative

            out_dir = self.settings.data_dir / "exports" / "public_reports" / session_id
            paths = export_report(
                conn, report_payload, out_dir=out_dir, basename="report"
            )
            public_md = out_dir / "public_narrative.md"
            public_md.write_text(narrative_to_markdown(narrative), encoding="utf-8")
            paths["public_markdown"] = public_md

            # Ephemeral wipe of raw bodies
            wiped = wipe_raw_document_bodies(conn, doc_ids)
            for p in temp_files:
                delete_path_quietly(p)
                delete_path_quietly(p.parent)

            unique_n = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM documents
                WHERE document_id IN ({",".join("?" for _ in doc_ids)}) AND is_duplicate = 0
                """,
                doc_ids,
            ).fetchone()["c"] if doc_ids else 0

            summary = report_payload["public_narrative"].get("one_liner", "")
            SessionRepository(conn).insert_session(
                {
                    "session_id": session_id,
                    "anonymous_id": anonymous_id,
                    "mode": mode,
                    "keywords": keywords,
                    "research_brief": brief,
                    "collector_ids": collector_ids,
                    "document_count": len(doc_ids),
                    "unique_document_count": unique_n,
                    "report_run_id": analysis.run_id,
                    "report_summary": summary,
                    "metrics": {
                        "trend": trend.to_dict(),
                        "ingest_notes": ingest_notes,
                        "wiped_documents": wiped,
                        "report_path": str(paths.get("markdown")),
                    },
                    "llm_mode": llm_mode,
                }
            )
            conn.commit()

        log.info(
            "public run session=%s mode=%s docs=%s wiped=%s llm=%s",
            session_id,
            mode,
            len(doc_ids),
            wiped,
            llm_mode,
        )
        return {
            "session_id": session_id,
            "status": "succeeded",
            "ingest_notes": ingest_notes,
            "document_count": len(doc_ids),
            "unique_document_count": unique_n,
            "wiped_documents": wiped,
            "report": report_payload,
            "report_paths": {k: str(v) for k, v in paths.items()},
            "llm_mode": llm_mode,
        }

