"""Build a simple PDF from report markdown/text (CJK-capable when system font exists)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def _find_cjk_font() -> Path | None:
    # Prefer single-face TTF; some TTC faces break fpdf2 width metrics without margins.
    candidates = [
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simkai.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
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
    return (
        (line or "")
        .replace("\t", " ")
        .replace("**", "")
        .replace("`", "")
        .replace("\u200b", "")
        .strip()
    )


def markdown_to_pdf_bytes(text: str, *, title: str = "分析报告") -> bytes:
    """Return PDF bytes. Raises RuntimeError if fpdf2 or CJK font unavailable."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("缺少 fpdf2，请执行 pip install fpdf2") from exc

    font = _find_cjk_font()
    if font is None:
        raise RuntimeError("未找到中文字体，无法生成 PDF（Windows 需黑体/楷体）")

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(left=18, top=18, right=18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.add_font("zh", "", str(font))
    width = float(pdf.epw)

    pdf.set_font("zh", size=16)
    pdf.multi_cell(width, 10, _clean_line(title) or "分析报告")
    pdf.ln(3)

    body = (text or "").replace("\r\n", "\n")
    for raw in body.split("\n"):
        line = _clean_line(raw)
        if not line:
            pdf.ln(3)
            continue
        if raw.lstrip().startswith("#"):
            pdf.set_font("zh", size=13)
            pdf.multi_cell(width, 8, line.lstrip("#").strip() or " ")
            pdf.set_font("zh", size=10)
            pdf.ln(1)
        else:
            pdf.set_font("zh", size=10)
            pdf.multi_cell(width, 6, line)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
