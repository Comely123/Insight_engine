"""
Multi-platform collector scaffolds.

These adapters are intentionally not implementing login bypass, captcha bypass,
or unofficial download sites. Enable only when official API / authorized access
is configured.
"""

from __future__ import annotations

from insight_engine.collectors.base import BaseCollector, CollectResult


class _StubPlatformCollector(BaseCollector):
    source_kind = "stub_platform"
    enabled_by_default = False
    require_env: str = ""

    def available(self) -> bool:
        return False

    def collect(self, keywords: list[str], *, limit: int = 50) -> CollectResult:
        return CollectResult(
            collector_id=self.collector_id,
            status="not_configured",
            items=[],
            errors=[
                f"{self.display_name} 适配器已预留，但未配置官方/授权接入。"
                f"请通过官方 API 或授权数据服务启用（环境变量示意：{self.require_env}）。"
                "系统不会实现绕过登录、验证码或平台反自动化的采集。"
            ],
            notes="scaffold-only",
        )


class WeiboCollector(_StubPlatformCollector):
    collector_id = "weibo"
    display_name = "微博（待官方/授权接入）"
    require_env = "INSIGHT_WEIBO_API_TOKEN"


class XiaohongshuCollector(_StubPlatformCollector):
    collector_id = "xiaohongshu"
    display_name = "小红书（待官方/授权接入）"
    require_env = "INSIGHT_XHS_API_TOKEN"


class DouyinCollector(_StubPlatformCollector):
    collector_id = "douyin"
    display_name = "抖音（待官方/授权接入）"
    require_env = "INSIGHT_DOUYIN_API_TOKEN"


class BilibiliCollector(_StubPlatformCollector):
    collector_id = "bilibili"
    display_name = "哔哩哔哩（待官方/授权接入）"
    require_env = "INSIGHT_BILIBILI_API_TOKEN"


class ZhihuCollector(_StubPlatformCollector):
    collector_id = "zhihu"
    display_name = "知乎（待官方/授权接入）"
    require_env = "INSIGHT_ZHIHU_API_TOKEN"


PLATFORM_STUBS = [
    WeiboCollector(),
    XiaohongshuCollector(),
    DouyinCollector(),
    BilibiliCollector(),
    ZhihuCollector(),
]
