from __future__ import annotations

from insight_engine.search.cjk_fts import space_cjk_chars, to_fts_match


def test_space_cjk_chars():
    assert space_cjk_chars("祈福手绳") == "祈 福 手 绳"
    assert space_cjk_chars("price128元") == "price128 元"


def test_to_fts_match_chinese_phrase():
    expr = to_fts_match("祈福 手绳")
    assert expr == '"祈 福" AND "手 绳"'
