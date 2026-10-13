"""SRT / VTT subtitle parsers -> timed segments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleCue:
    start_time: float
    end_time: float
    text: str


_TS = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{1,3})"
)


def _parse_ts(value: str) -> float:
    m = _TS.search(value.strip())
    if not m:
        raise ValueError(f"invalid timestamp: {value!r}")
    ms = m.group("ms").ljust(3, "0")[:3]
    return (
        int(m.group("h")) * 3600
        + int(m.group("m")) * 60
        + int(m.group("s"))
        + int(ms) / 1000.0
    )


def parse_srt(text: str) -> list[SubtitleCue]:
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if len(lines) < 2:
            continue
        # skip index line if numeric
        idx = 0
        if re.fullmatch(r"\d+", lines[0].strip()):
            idx = 1
        if idx >= len(lines):
            continue
        if "-->" not in lines[idx]:
            continue
        left, right = [p.strip() for p in lines[idx].split("-->")]
        body = "\n".join(lines[idx + 1 :]).strip()
        if not body:
            continue
        cues.append(
            SubtitleCue(
                start_time=_parse_ts(left),
                end_time=_parse_ts(right.split()[0]),
                text=body,
            )
        )
    return cues


def parse_vtt(text: str) -> list[SubtitleCue]:
    cleaned = text.replace("\r\n", "\n")
    if cleaned.lstrip().startswith("WEBVTT"):
        cleaned = re.sub(r"^WEBVTT.*\n", "", cleaned.lstrip(), count=1)
    # drop NOTE / STYLE blocks roughly
    cleaned = re.sub(r"NOTE.*?(?=\n\n|\Z)", "", cleaned, flags=re.S)
    return parse_srt(cleaned)


def load_subtitle_file(path: Path) -> list[SubtitleCue]:
    raw = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(raw)
    if suffix == ".vtt":
        return parse_vtt(raw)
    raise ValueError(f"unsupported subtitle type: {suffix}")
