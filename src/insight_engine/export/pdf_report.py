"""Build PDF from report narrative + distribution charts (no CSV table)."""

from __future__ import annotations

import math
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from insight_engine.ui.theme import MACARON


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
    if not text:
        return [" "]
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_hbar(
    pdf: Any,
    *,
    title: str,
    counts: dict[str, Any] | None,
    label_zh: dict[str, str],
) -> None:
    items = [
        (label_zh.get(str(k), str(k)), int(v))
        for k, v in (counts or {}).items()
        if int(v) > 0
    ]
    items.sort(key=lambda x: x[1], reverse=True)
    items = items[:8]
    pdf.set_font("zh", size=12)
    pdf.multi_cell(0, 7, title or "分布", new_x="LMARGIN", new_y="NEXT")
    if not items:
        pdf.set_font("zh", size=9)
        pdf.multi_cell(0, 5, "暂无数据", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        return
    max_v = max(v for _, v in items) or 1
    left = pdf.l_margin
    usable = float(pdf.epw)
    label_w = min(42.0, usable * 0.38)
    bar_max = usable - label_w - 14
    row_h = 6.5
    for i, (lab, val) in enumerate(items):
        y = pdf.get_y()
        if y > pdf.h - pdf.b_margin - 20:
            pdf.add_page()
            y = pdf.get_y()
        pdf.set_font("zh", size=9)
        pdf.set_xy(left, y)
        pdf.cell(label_w, row_h, (lab or "")[:16], new_x="RIGHT", new_y="TOP")
        bw = max(2.0, bar_max * (val / max_v))
        r, g, b = _hex_to_rgb(MACARON[i % len(MACARON)])
        pdf.set_fill_color(r, g, b)
        pdf.rect(left + label_w + 2, y + 1.2, bw, row_h - 2.4, style="F")
        pdf.set_xy(left + label_w + 2 + bw + 1, y)
        pdf.cell(12, row_h, str(val), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _draw_donut_legend(
    pdf: Any,
    *,
    title: str,
    counts: dict[str, Any] | None,
    label_zh: dict[str, str],
) -> None:
    """Donut approximation: colored legend + share bars (reliable CJK PDF)."""
    items = [
        (label_zh.get(str(k), str(k)), int(v))
        for k, v in (counts or {}).items()
        if int(v) > 0
    ]
    items.sort(key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in items) or 1
    pdf.set_font("zh", size=12)
    pdf.multi_cell(0, 7, title or "分布", new_x="LMARGIN", new_y="NEXT")
    if not items:
        pdf.set_font("zh", size=9)
        pdf.multi_cell(0, 5, "暂无数据", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        return

    # Simple pie using triangles around center
    cx = pdf.l_margin + 28
    cy = pdf.get_y() + 22
    radius = 18
    start = -math.pi / 2
    for i, (_, val) in enumerate(items):
        sweep = 2 * math.pi * (val / total)
        r, g, b = _hex_to_rgb(MACARON[i % len(MACARON)])
        pdf.set_fill_color(r, g, b)
        pdf.set_draw_color(255, 255, 255)
        # Approximate wedge with a fan of thin triangles
        steps = max(6, int(abs(sweep) / (math.pi / 24)))
        for s in range(steps):
            a0 = start + sweep * (s / steps)
            a1 = start + sweep * ((s + 1) / steps)
            x0, y0 = cx + radius * math.cos(a0), cy + radius * math.sin(a0)
            x1, y1 = cx + radius * math.cos(a1), cy + radius * math.sin(a1)
            pdf.polygon(
                [(cx, cy), (x0, y0), (x1, y1)],
                style="F",
            )
        start += sweep

    # Inner hole (donut)
    pdf.set_fill_color(255, 255, 255)
    pdf.ellipse(cx - 8, cy - 8, 16, 16, style="F")

    # Legend to the right of pie
    lx = pdf.l_margin + 58
    ly = cy - 20
    pdf.set_font("zh", size=9)
    for i, (lab, val) in enumerate(items[:8]):
        r, g, b = _hex_to_rgb(MACARON[i % len(MACARON)])
        pdf.set_fill_color(r, g, b)
        pdf.rect(lx, ly + i * 6 + 1, 3.5, 3.5, style="F")
        pdf.set_xy(lx + 5, ly + i * 6)
        pct = 100.0 * val / total
        pdf.cell(0, 5.5, f"{lab}  {val}（{pct:.0f}%）", new_x="LMARGIN", new_y="TOP")
    pdf.set_y(max(cy + radius + 6, ly + len(items[:8]) * 6 + 4))
    pdf.ln(2)


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


def report_to_pdf_bytes(
    narrative: dict[str, Any],
    *,
    title: str = "分析报告",
    include_charts: bool = True,
) -> bytes:
    """
    PDF = narrative text + distribution charts.
    Explicitly excludes CSV / sample table rows.
    """
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    from insight_engine.product.narrative import narrative_to_markdown
    from insight_engine.ui.charts import LABEL_ZH, pick_report_chart_slots

    font = _find_cjk_font()
    if font is None:
        raise RuntimeError("未找到中文字体，无法生成 PDF（Windows 需黑体/楷体）")

    # Markdown without any table dump (narrative_to_markdown already omits CSV rows)
    md = narrative_to_markdown(narrative)
    # Strip accidental CSV-ish sections if LLM added them
    md_lines = []
    skip = False
    for line in md.split("\n"):
        low = line.lower()
        if "csv" in low or "对照表" in line and line.strip().startswith("#"):
            skip = True
            continue
        if skip and line.startswith("#"):
            skip = False
        if not skip:
            md_lines.append(line)
    md = "\n".join(md_lines)

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(left=18, top=18, right=18)
    pdf.set_auto_page_break(auto=True, margin=18)
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
    pdf.ln(1)
    write_line("（含分布图；不含 CSV 样本表）", size=9, h=5)
    pdf.ln(2)

    for raw in md.replace("\r\n", "\n").split("\n"):
        line = _clean_line(raw)
        if not line:
            pdf.ln(2)
            continue
        if raw.lstrip().startswith("#"):
            write_line(line.lstrip("#").strip() or " ", size=13, h=8)
            pdf.ln(1)
        else:
            write_line(line, size=10, h=5.5)

    if include_charts:
        pdf.add_page()
        write_line("分布图（2×2）", size=14, h=9)
        pdf.ln(2)
        stats = narrative.get("stats") or {}
        profile = str(narrative.get("analysis_profile") or "mixed")
        slots = pick_report_chart_slots(stats, profile=profile)
        for title_c, counts, kind in slots:
            if kind == "donut":
                _draw_donut_legend(
                    pdf, title=title_c, counts=counts, label_zh=LABEL_ZH
                )
            else:
                # hbar / area → bar chart in PDF
                _draw_hbar(pdf, title=title_c, counts=counts, label_zh=LABEL_ZH)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
