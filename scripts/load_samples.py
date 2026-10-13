#!/usr/bin/env python3
"""Load bundled sample files into the local database."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from insight_engine.config import get_settings
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.ingest.service import ImportService
from insight_engine.models.documents import PermissionStatus


def main() -> None:
    settings = get_settings()
    initialize_database(settings)
    # Product no longer ships demo corpora under data/samples.
    # Prefer tests/fixtures for local smoke loads when present.
    fixture_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    samples = sorted(fixture_dir.glob("*")) if fixture_dir.exists() else []
    samples = [p for p in samples if p.is_file()]
    if not samples:
        print(f"No loadable fixtures in {fixture_dir} (data/samples is intentionally empty).")
        return

    with get_connection(settings.db_path) as conn:
        service = ImportService(conn, settings)
        for path in samples:
            if path.suffix.lower() not in {".csv", ".json", ".txt", ".md", ".markdown"}:
                continue
            result = service.import_file(
                path,
                source_name=f"sample:{path.stem}",
                permission_status=PermissionStatus.USER_OWNED,
                license_note="Bundled fictional/desensitized research sample",
                save_copy=True,
            )
            print(
                f"{path.name}: status={result.status} "
                f"imported={result.row_count_imported} dupes={result.row_count_dupes} "
                f"errors={len(result.errors)}"
            )


if __name__ == "__main__":
    main()
