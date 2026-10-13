"""Extract plain text from uploaded PDF literature."""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path | str, *, max_chars: int = 80000) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf，请执行 pip install pypdf") from exc

    path = Path(path)
    reader = PdfReader(str(path))
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        text = text.strip()
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    joined = "\n\n".join(parts)
    if not joined.strip():
        raise ValueError("未能从 PDF 提取到文字（可能是扫描件/纯图片 PDF）")
    return joined[:max_chars]
