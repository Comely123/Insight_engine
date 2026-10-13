from pathlib import Path

from insight_engine.product.uploads import classify_upload, pair_captions


def test_classify_text_media_caption() -> None:
    assert classify_upload(Path("a.csv")) == "text"
    assert classify_upload(Path("a.mp4")) == "media"
    assert classify_upload(Path("a.mp3")) == "media"
    assert classify_upload(Path("a.srt")) == "caption"
    assert classify_upload(Path("a.docx")) == "unsupported"


def test_pair_captions_by_stem() -> None:
    texts, media, paired, bad = pair_captions(
        [
            Path("notes.txt"),
            Path("clip.mp4"),
            Path("clip.srt"),
            Path("solo.vtt"),
            Path("x.bin"),
        ]
    )
    assert Path("notes.txt") in texts
    assert Path("solo.vtt") in texts
    assert Path("clip.mp4") in media
    assert paired[Path("clip.mp4")] == Path("clip.srt")
    assert Path("x.bin") in bad
