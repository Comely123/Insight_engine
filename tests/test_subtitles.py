from __future__ import annotations

from insight_engine.media.subtitles import parse_srt, parse_vtt


def test_parse_srt_timestamps_and_text():
    raw = """1
00:00:00,000 --> 00:00:01,500
价格 128 元

2
00:00:01,500 --> 00:00:03,000
第二句
"""
    cues = parse_srt(raw)
    assert len(cues) == 2
    assert cues[0].start_time == 0.0
    assert cues[0].end_time == 1.5
    assert "128" in cues[0].text


def test_parse_vtt():
    raw = """WEBVTT

00:00:00.000 --> 00:00:01.000
hello
"""
    cues = parse_vtt(raw)
    assert len(cues) == 1
    assert cues[0].text == "hello"
