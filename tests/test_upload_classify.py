from pathlib import Path

from insight_engine.product.uploads import UPLOADER_TYPES, classify_upload, pair_captions


def test_classify_text_media_caption() -> None:
    assert classify_upload(Path("a.csv")) == "text"
    assert classify_upload(Path("paper.pdf")) == "text"
    assert classify_upload(Path("a.mp4")) == "media"
    assert classify_upload(Path("a.mp3")) == "media"
    assert classify_upload(Path("a.srt")) == "caption"
    assert classify_upload(Path("shot.png")) == "image"
    assert classify_upload(Path("logo.svg")) == "image"
    assert classify_upload(Path("main.py")) == "code"
    assert classify_upload(Path("bundle.zip")) == "archive"
    assert classify_upload(Path("notes.docx")) == "office"
    assert classify_upload(Path("a.bin")) == "unsupported"


def test_uploader_types_include_images_code_archives() -> None:
    for ext in ("jpg", "png", "svg", "py", "zip", "docx", "pdf", "mp4"):
        assert ext in UPLOADER_TYPES


def test_pair_captions_by_stem() -> None:
    extractable, images, media, paired, bad = pair_captions(
        [
            Path("notes.txt"),
            Path("clip.mp4"),
            Path("clip.srt"),
            Path("solo.vtt"),
            Path("pic.png"),
            Path("x.bin"),
        ]
    )
    assert Path("notes.txt") in extractable
    assert Path("solo.vtt") in extractable
    assert Path("pic.png") in images
    assert Path("clip.mp4") in media
    assert paired[Path("clip.mp4")] == Path("clip.srt")
    assert Path("x.bin") in bad
