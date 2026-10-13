from insight_engine.export.pdf_report import markdown_to_pdf_bytes


def test_markdown_to_pdf_bytes_chinese() -> None:
    data = markdown_to_pdf_bytes(
        "# 标题\n\n这是一段中文报告内容，包含价格 99 元与祈福关键词。\n",
        title="活动洞察报告",
    )
    assert data[:4] == b"%PDF"
    assert len(data) > 500
