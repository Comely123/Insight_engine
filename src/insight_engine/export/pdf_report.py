"""Build a simple PDF from report markdown/text (CJK-capable when system font exists)."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path


def _find_cjk_font() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simkai.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _clean_line(line: str) -> str:
    text = (
        (line or "")
        .replace("\t", " ")
        .replace("**", "")
        .replace("`", "")
        .replace("\u200b", "")
        .replace("\xa0", " ")
    )
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _chunk_text(text: str, max_chars: int = 42) -> list[str]:
    """Hard-wrap long CJK lines so fpdf never sees an unsplittable mega-token."""
    if not text:
        return [" "]
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def markdown_to_pdf_bytes(text: str, *, title: str = "分析报告") -> bytes:
    try:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
    except ImportError as exc:
        raise RuntimeError("缺少 fpdf2，请执行 pip install fpdf2") from exc

    font = _find_cjk_font()
    if font is None:
        raise RuntimeError("未找到中文字体，无法生成 PDF（Windows 需黑体/楷体）")

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.add_font("zh", "", str(font))
    width = max(float(pdf.epw), 1.0)

    def write_line(content: str, *, size: int = 10, h: float = 6) -> None:
        pdf.set_font("zh", size=size)
        pdf.set_x(pdf.l_margin)
        for part in _chunk_text(content, max_chars=40 if size >= 13 else 46):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                width,
                h,
                part or " ",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    write_line(_clean_line(title) or "分析报告", size=16, h=10)
    pdf.ln(2)

    body = (text or "").replace("\r\n", "\n")
    for raw in body.split("\n"):
        line = _clean_line(raw)
        if not line:
            pdf.ln(3)
            continue
        if raw.lstrip().startswith("#"):
            write_line(line.lstrip("#").strip() or " ", size=13, h=8)
            pdf.ln(1)
        else:
            write_line(line, size=10, h=6)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
