from pathlib import Path

from insight_engine.ingest.service import ImportService, detect_format
from insight_engine.models.documents import PermissionStatus
from insight_engine.product import pdf_extract


def test_detect_format_pdf() -> None:
    assert detect_format(Path("paper.pdf")) == "pdf"


def test_import_pdf_literature(tmp_settings, tmp_path: Path, db_conn) -> None:
    pdf_path = tmp_path / "lit.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 placeholder")

    original = pdf_extract.extract_pdf_text

    def _fake(_path, **_kwargs):
        return "这是一篇关于宠物毛发祈福的文献摘要，讨论价格与需求共性。"

    pdf_extract.extract_pdf_text = _fake  # type: ignore[assignment]
    try:
        result = ImportService(db_conn, tmp_settings).import_file(
            pdf_path,
            permission_status=PermissionStatus.USER_OWNED,
            save_copy=False,
        )
    finally:
        pdf_extract.extract_pdf_text = original  # type: ignore[assignment]

    assert result.status in {"succeeded", "partial"}
    assert result.row_count_imported >= 1
