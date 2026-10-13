"""OpenAI-compatible LLM presets (incl. major CN providers)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMPreset:
    id: str
    label: str
    base_url: str
    models: tuple[str, ...]
    needs_key: bool = True
    note: str = ""


# All of these speak OpenAI-compatible Chat Completions (/v1/chat/completions).
PRESETS: tuple[LLMPreset, ...] = (
    LLMPreset(
        id="rules",
        label="仅规则统计（不调用大模型）",
        base_url="",
        models=(),
        needs_key=False,
    ),
    LLMPreset(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"),
    ),
    LLMPreset(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        models=("deepseek-chat", "deepseek-reasoner"),
    ),
    LLMPreset(
        id="qwen",
        label="通义千问（阿里云 DashScope 兼容模式）",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=("qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"),
        note="使用 DashScope API Key",
    ),
    LLMPreset(
        id="zhipu",
        label="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        models=("glm-4-flash", "glm-4-air", "glm-4", "glm-4-plus"),
        note="使用智谱 API Key；Base 已含 /v4",
    ),
    LLMPreset(
        id="moonshot",
        label="月之暗面 Kimi",
        base_url="https://api.moonshot.cn/v1",
        models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-latest"),
    ),
    LLMPreset(
        id="doubao",
        label="豆包 / 火山方舟",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        models=("doubao-pro-32k", "doubao-lite-32k"),
        note="模型名请填方舟控制台的推理接入点 ID（endpoint id）",
    ),
    LLMPreset(
        id="hunyuan",
        label="腾讯混元",
        base_url="https://api.hunyuan.cloud.tencent.com/v1",
        models=("hunyuan-lite", "hunyuan-standard", "hunyuan-turbo", "hunyuan-large"),
    ),
    LLMPreset(
        id="baichuan",
        label="百川",
        base_url="https://api.baichuan-ai.com/v1",
        models=("Baichuan4-Turbo", "Baichuan4", "Baichuan3-Turbo"),
    ),
    LLMPreset(
        id="yi",
        label="零一万物 Yi",
        base_url="https://api.lingyiwanwu.com/v1",
        models=("yi-lightning", "yi-large", "yi-medium"),
    ),
    LLMPreset(
        id="siliconflow",
        label="硅基流动 SiliconFlow（聚合）",
        base_url="https://api.siliconflow.cn/v1",
        models=(
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "THUDM/glm-4-9b-chat",
        ),
        note="一个 Key 可切换多种开源/国产模型",
    ),
    LLMPreset(
        id="local",
        label="本机 / 自部署（Ollama、vLLM 等）",
        base_url="http://127.0.0.1:11434/v1",
        models=("qwen2.5:7b", "qwen2.5:14b", "llama3.2", "deepseek-r1:7b"),
        needs_key=False,
        note="多数本机服务可用任意非空 Key，默认填 local",
    ),
    LLMPreset(
        id="custom",
        label="自定义 OpenAI 兼容接口",
        base_url="https://api.openai.com/v1",
        models=("gpt-4o-mini",),
        note="自行填写 Base URL 与模型名",
    ),
)


def preset_by_id(preset_id: str) -> LLMPreset | None:
    for p in PRESETS:
        if p.id == preset_id:
            return p
    return None


def preset_ids() -> list[str]:
    return [p.id for p in PRESETS]
