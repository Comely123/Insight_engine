"""Classify public upload paths: text / code / image / archive / media / caption."""

from __future__ import annotations

from pathlib import Path

from insight_engine.product.archive_expand import ARCHIVE_EXTENSIONS, is_archive
from insight_engine.product.file_extract import (
    CODE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TEXT_DOC_EXTENSIONS,
)

CAPTION_EXTENSIONS = {".srt", ".vtt"}
MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".wma",
}
OFFICE_EXTENSIONS = {".docx"}

# Shown in Streamlit file_uploader (no dots)
UPLOADER_TYPES = sorted(
    {
        e.lstrip(".")
        for e in (
            TEXT_DOC_EXTENSIONS
            | CODE_EXTENSIONS
            | IMAGE_EXTENSIONS
            | CAPTION_EXTENSIONS
            | MEDIA_EXTENSIONS
            | OFFICE_EXTENSIONS
            | ARCHIVE_EXTENSIONS
            | {
                ".zip",
                ".tar",
                ".gz",  # for *.tar.gz (suffix is .gz)
                ".tgz",
                ".bz2",
                ".docx",
                ".ipynb",
            }
        )
    }
)


def classify_upload(path: Path) -> str:
    """
    Return one of:
      text | code | image | archive | media | caption | office | unsupported
    """
    name = path.name.lower()
    if is_archive(path) or name.endswith(".tar.gz") or name.endswith(".tar.bz2"):
        return "archive"
    ext = path.suffix.lower()
    if ext in CAPTION_EXTENSIONS:
        return "caption"
    if ext in MEDIA_EXTENSIONS:
        return "media"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in OFFICE_EXTENSIONS:
        return "office"
    if ext in CODE_EXTENSIONS or name in {"makefile", "dockerfile", "cmakelists.txt"}:
        return "code"
    if ext in TEXT_DOC_EXTENSIONS:
        return "text"
    return "unsupported"


def pair_captions(
    paths: list[Path],
) -> tuple[list[Path], list[Path], list[Path], dict[Path, Path], list[Path]]:
    """
    Returns:
      extractable_paths (text/code/office/unpaired captions — go through file_extract),
      image_paths,
      media_paths,
      media → caption map,
      unsupported paths
    """
    extractable: list[Path] = []
    images: list[Path] = []
    media: list[Path] = []
    captions: list[Path] = []
    unsupported: list[Path] = []
    for p in paths:
        kind = classify_upload(p)
        if kind in {"text", "code", "office"}:
            extractable.append(p)
        elif kind == "image":
            images.append(p)
        elif kind == "media":
            media.append(p)
        elif kind == "caption":
            captions.append(p)
        elif kind == "archive":
            # Caller should expand archives first; leftover archives are unsupported here
            unsupported.append(p)
        else:
            unsupported.append(p)

    by_stem: dict[str, Path] = {c.stem.lower(): c for c in captions}
    paired: dict[Path, Path] = {}
    used: set[Path] = set()
    for m in media:
        cap = by_stem.get(m.stem.lower())
        if cap is not None:
            paired[m] = cap
            used.add(cap)
    unpaired_captions = [c for c in captions if c not in used]
    return extractable + unpaired_captions, images, media, paired, unsupported
