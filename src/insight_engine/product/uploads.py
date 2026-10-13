"""Classify public upload paths: text docs vs audiovisual media vs captions."""

from __future__ import annotations

from pathlib import Path

TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".txt",
    ".md",
    ".markdown",
    ".log",
    ".text",
}
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
}


def classify_upload(path: Path) -> str:
    """Return 'text' | 'media' | 'caption' | 'unsupported'."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in MEDIA_EXTENSIONS:
        return "media"
    if ext in CAPTION_EXTENSIONS:
        return "caption"
    return "unsupported"


def pair_captions(
    paths: list[Path],
) -> tuple[list[Path], list[Path], dict[Path, Path], list[Path]]:
    """
    Returns:
      text_paths (incl. unpaired captions),
      media_paths,
      media → caption map,
      unsupported paths
    """
    texts: list[Path] = []
    media: list[Path] = []
    captions: list[Path] = []
    unsupported: list[Path] = []
    for p in paths:
        kind = classify_upload(p)
        if kind == "text":
            texts.append(p)
        elif kind == "media":
            media.append(p)
        elif kind == "caption":
            captions.append(p)
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
    return texts + unpaired_captions, media, paired, unsupported
