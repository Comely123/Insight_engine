"""Build a simple PDF from report markdown/text (CJK-capable when system font exists)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def _find_cjk_font() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def markdown_to_pdf_bytes(text: str, *, title: str = "分析报告") -> bytes:
    """Return PDF bytes. Raises RuntimeError if fpdf2 or CJK font unavailable."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("缺少 fpdf2，请执行 pip install fpdf2") from exc

    font = _find_cjk_font()
    if font is None:
        raise RuntimeError("未找到中文字体，无法生成 PDF（Windows 需微软雅黑/黑体）")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # ttc needs uni=True style in fpdf2
    pdf.add_font("zh", fname=str(font))
    pdf.set_font("zh", size=14)
    pdf.multi_cell(0, 10, title)
    pdf.ln(4)
    pdf.set_font("zh", size=10)
    # Normalize markdown-ish to plain-ish lines
    body = (text or "").replace("\r\n", "\n")
    for line in body.split("\n"):
        line = line.replace("**", "").replace("`", "")
        if line.startswith("#"):
            line = line.lstrip("#").strip()
            pdf.set_font("zh", size=12)
            pdf.multi_cell(0, 8, line or " ")
            pdf.set_font("zh", size=10)
        else:
            pdf.multi_cell(0, 6, line if line.strip() else " ")
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
