from insight_engine.llm.presets import PRESETS, preset_by_id


def test_cn_presets_present() -> None:
    ids = {p.id for p in PRESETS}
    for need in (
        "qwen",
        "zhipu",
        "moonshot",
        "doubao",
        "hunyuan",
        "baichuan",
        "yi",
        "siliconflow",
        "deepseek",
        "openai",
    ):
        assert need in ids
        assert preset_by_id(need) is not None
        assert preset_by_id(need).base_url
