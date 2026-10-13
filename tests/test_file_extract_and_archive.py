import zipfile
from pathlib import Path

from insight_engine.product.archive_expand import expand_archives
from insight_engine.product.brief_coverage import cover_brief_asks, split_brief_asks
from insight_engine.product.file_extract import extract_code_summary, extract_svg_text


def test_extract_svg_text(tmp_path: Path) -> None:
    p = tmp_path / "a.svg"
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>祈福价格 99</text></svg>',
        encoding="utf-8",
    )
    assert "祈福" in extract_svg_text(p)


def test_extract_code_summary(tmp_path: Path) -> None:
    p = tmp_path / "svc.py"
    p.write_text(
        "import json\n\ndef analyze_market():\n    return 1\n",
        encoding="utf-8",
    )
    body, meta = extract_code_summary(p)
    assert "代码文件" in body
    assert "analyze_market" in body
    assert meta["ext"] == ".py"


def test_expand_zip(tmp_path: Path) -> None:
    zpath = tmp_path / "pack.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("notes.txt", "宠物毛发祈福讨论")
        zf.writestr("nested/code.py", "print('hi')\n")
    files, notes, temps = expand_archives([zpath])
    names = {f.name for f in files}
    assert "notes.txt" in names
    assert "code.py" in names
    assert notes
    assert temps


def test_brief_coverage_marks_gaps() -> None:
    asks = split_brief_asks("价格接受度如何？\n竞品有哪些差异？卫生顾虑？")
    assert len(asks) >= 2
    cov = cover_brief_asks(
        "价格接受度如何？卫生顾虑？完全无关的外太空殖民？",
        keywords=["价格"],
        themes=["price: 99"],
        titles=["毛发祈福价格讨论"],
        findings=["已确认价格分布"],
        literature={"rows": [{"title": "a", "excerpt": "卫生与隐私", "top_terms": "卫生"}]},
    )
    statuses = {r["ask"][:4]: r["status"] for r in cov["rows"]}
    assert cov["coverage_lines"]
    assert any(r["status"] in {"addressed", "partial"} for r in cov["rows"])
    assert any(r["status"] == "gap" for r in cov["rows"])
