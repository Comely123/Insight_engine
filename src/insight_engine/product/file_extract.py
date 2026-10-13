"""Extract analyzable text from images (OCR), SVG, code, Office-ish, plain files."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from insight_engine.media.ocr.factory import get_ocr_provider

CODE_EXTENSIONS = {
    ".py",
    ".pyw",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".r",
    ".m",
    ".mm",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".less",
    ".vue",
    ".svelte",
    ".xml",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".gradle",
    ".cmake",
    ".makefile",
    ".mk",
    ".ipynb",
    ".dart",
    ".lua",
    ".pl",
    ".pm",
    ".ex",
    ".exs",
    ".erl",
    ".hs",
    ".clj",
    ".lisp",
    ".vim",
    ".dockerfile",
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".svg",
}

# Treated as readable text / structured docs (non-code)
TEXT_DOC_EXTENSIONS = {
    ".csv",
    ".json",
    ".txt",
    ".md",
    ".markdown",
    ".log",
    ".text",
    ".pdf",
    ".rtf",
    ".tsv",
}


def _read_text(path: Path, *, max_chars: int = 120_000) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\x00", "")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[截断]"
    return text


def extract_svg_text(path: Path) -> str:
    raw = _read_text(path, max_chars=200_000)
    # Strip tags but keep text nodes / title / desc / tspan
    texts = re.findall(
        r"<(?:text|tspan|title|desc)[^>]*>([^<]+)</(?:text|tspan|title|desc)>",
        raw,
        flags=re.I,
    )
    if texts:
        body = "\n".join(t.strip() for t in texts if t.strip())
    else:
        body = re.sub(r"<[^>]+>", " ", raw)
        body = re.sub(r"\s+", " ", body).strip()
    return body


def extract_docx_text(path: Path, *, max_chars: int = 80_000) -> str:
    with zipfile.ZipFile(path) as zf:
        name = "word/document.xml"
        if name not in zf.namelist():
            return ""
        xml = zf.read(name).decode("utf-8", errors="replace")
    texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    body = "\n".join(t for t in texts if t)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[截断]"
    return body


def extract_image_ocr(path: Path) -> tuple[str, dict[str, Any]]:
    """OCR raster images; SVG uses XML text extraction (no OCR engine)."""
    meta: dict[str, Any] = {"extractor": "ocr", "path": path.name}
    if path.suffix.lower() == ".svg":
        text = extract_svg_text(path)
        meta["extractor"] = "svg_text"
        return text, meta

    ocr = get_ocr_provider()
    if not ocr.available():
        meta["extractor"] = "ocr_unavailable"
        return (
            f"[图片文件：{path.name}。未安装/未启用 OCR（需 Tesseract + Pillow），"
            "无法提取画面文字。可安装后重试，或同时上传同主题文本。]",
            meta,
        )
    try:
        result = ocr.recognize(path)
        text = (result.text or "").strip()
        meta["ocr_provider"] = ocr.name
        if not text:
            text = f"[图片 {path.name}：OCR 未识别到文字]"
        return text, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        return f"[图片 {path.name}：OCR 失败 {exc}]", meta


def extract_code_summary(path: Path) -> tuple[str, dict[str, Any]]:
    ext = path.suffix.lower() or "(noext)"
    body = _read_text(path)
    lines = body.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    # Lightweight signals
    imports = [
        ln.strip()
        for ln in non_empty[:80]
        if re.match(r"^\s*(import |from |#include |require\(|using )", ln)
    ]
    defs = [
        ln.strip()
        for ln in non_empty
        if re.match(
            r"^\s*(def |class |function |func |fn |public |private |export )",
            ln,
        )
    ][:40]
    header = [
        f"代码文件：{path.name}",
        f"语言/扩展：{ext}",
        f"行数：{len(lines)}（非空 {len(non_empty)}）",
    ]
    if imports:
        header.append("依赖/引入线索：" + "；".join(imports[:12]))
    if defs:
        header.append("结构线索：" + "；".join(defs[:16]))
    header.append("--- 正文 ---")
    text = "\n".join(header) + "\n" + body
    return text, {"extractor": "code", "ext": ext, "lines": len(lines)}


def extract_upload_text(path: Path) -> tuple[str, str, dict[str, Any]]:
    """
    Returns (body, content_type, meta).
    content_type hints for taxonomy / profile.
    """
    ext = path.suffix.lower()
    meta: dict[str, Any] = {}

    if ext in IMAGE_EXTENSIONS:
        body, meta = extract_image_ocr(path)
        return body, "image_ocr", meta

    if ext == ".docx":
        from insight_engine.product.doc_genre import (
            classify_document_genre,
            genre_to_content_type,
        )

        body = extract_docx_text(path) or f"[docx 无文本：{path.name}]"
        genre = classify_document_genre(body, title=path.stem)
        return body, genre_to_content_type(genre), {"extractor": "docx", "genre": genre}

    if ext in CODE_EXTENSIONS or path.name.lower() in {"makefile", "dockerfile", "cmakelists.txt"}:
        body, meta = extract_code_summary(path)
        return body, "source_code", meta

    if ext in {".txt", ".md", ".markdown", ".log", ".text", ".rtf", ".tsv"}:
        return _read_text(path), "text", {"extractor": "plain"}

    if ext == ".csv":
        return _read_text(path), "csv", {"extractor": "plain"}

    if ext == ".json":
        return _read_text(path), "json", {"extractor": "plain"}

    if ext in {".yml", ".yaml", ".toml", ".xml", ".html", ".htm"}:
        body, meta = extract_code_summary(path)
        return body, "source_code", meta

    # Fallback: try UTF-8 text
    try:
        body = _read_text(path)
        if body.strip():
            return body, "text", {"extractor": "fallback_text"}
    except Exception:  # noqa: BLE001
        pass
    return f"[无法解析的文件：{path.name}]", "unknown", {"extractor": "none"}
