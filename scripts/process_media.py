#!/usr/bin/env python3
"""CLI: import and/or process a local media file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.media.ingest import MediaIngestService
from insight_engine.media.pipeline import MediaPipeline
from insight_engine.models.documents import PermissionStatus


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path, help="Local media file")
    p.add_argument("--subtitle", type=Path, default=None)
    p.add_argument("--asr", action="store_true")
    p.add_argument("--ocr", action="store_true")
    p.add_argument("--no-keyframes", action="store_true")
    p.add_argument("--copy", action="store_true")
    args = p.parse_args()

    initialize_database()
    with get_connection() as conn:
        asset = MediaIngestService(conn).import_media(
            args.path,
            permission_status=PermissionStatus.USER_OWNED,
            subtitle_path=args.subtitle,
            copy_into_media_dir=args.copy,
        )
        result = MediaPipeline(conn).process_media(
            asset["media_id"],
            run_asr=args.asr,
            run_ocr=args.ocr,
            run_keyframes=not args.no_keyframes,
        )
    print(json.dumps({"asset": asset["media_id"], "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
