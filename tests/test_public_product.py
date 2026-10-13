"""Public product: upload → analyze → wipe raw → archive session."""

from __future__ import annotations

import json
from pathlib import Path

from insight_engine.config import Settings
from insight_engine.db.connection import get_connection
from insight_engine.db.session_repository import SessionRepository
from insight_engine.product.pipeline import PublicAnalysisService


def test_upload_pipeline_wipes_raw_and_archives(tmp_settings: Settings, tmp_path: Path) -> None:
    payload = {
        "documents": [
            {
                "title": "宠物毛发祈福体验",
                "content": (
                    "养宠人士寄送宠物毛发编织福袋祈福，价格大约 99 元。"
                    "有人表示想付款参加，也有人担心隐私与卫生。"
                    "这是询价与购买意向线索。"
                ),
                "source_name": "user_upload",
                "published_at": "2026-10-01T10:00:00Z",
            },
            {
                "title": "离世纪念毛发编织",
                "content": "离世纪念用宠物毛发编织纪念品，已付款完成履约寄送。",
                "source_name": "user_upload_b",
                "published_at": "2026-10-05T10:00:00Z",
            },
        ]
    }
    upload = tmp_path / "upload.json"
    upload.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = PublicAnalysisService(tmp_settings).run(
        mode="upload",
        keywords=["宠物毛发", "祈福"],
        upload_paths=[upload],
        anonymous_id="test-anon",
        use_llm=False,
        window_days=365,
    )

    assert result["status"] == "succeeded"
    assert result["document_count"] >= 1
    assert result["wiped_documents"] >= 1
    assert result["report"] is not None
    assert result["report"]["public_narrative"]["degree_positioning"]

    with get_connection(tmp_settings.db_path) as conn:
        rows = conn.execute(
            "SELECT raw_content, normalized_content, processing_status FROM documents"
        ).fetchall()
        assert rows
        for r in rows:
            assert r["raw_content"] is None
            assert r["normalized_content"] == "[ephemeral:cleared]"
            assert r["processing_status"] == "analyzed_ephemeral"

        sessions = SessionRepository(conn).list_sessions(limit=10)
        assert len(sessions) >= 1
        assert sessions[0]["mode"] == "upload"
        assert "宠物毛发" in sessions[0]["keywords"]
