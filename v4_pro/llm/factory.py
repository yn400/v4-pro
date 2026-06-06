"""
LLM 工厂函数 — 根据配置自动选择并创建适配器。
"""

from __future__ import annotations

import logging

from v4_pro.config import Settings, get_settings
from v4_pro.llm.base import AbstractLLM
from v4_pro.llm.openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)


def create_llm(settings: Settings | None = None) -> AbstractLLM:
    """
    根据配置创建 LLM 适配器实例。

    支持的 provider:
    - openai  → OpenAIAdapter (base_url 可指向中转站)
    - zhipu   → OpenAIAdapter (智谱兼容 OpenAI 接口)
    - tongyi  → OpenAIAdapter (通义千问兼容 OpenAI 接口)
    - anthropic → (暂未实现，预留)

    Args:
        settings: V4 Pro 配置对象，默认使用全局单例

    Returns:
        AbstractLLM 实例

    Raises:
        ValueError: provider 不支持或 API Key 未配置
    """
    if settings is None:
        settings = get_settings()

    provider = settings.llm_provider

    if provider in ("openai", "zhipu", "tongyi"):
        api_key = settings.provider_api_key
        if not api_key:
            raise ValueError(
                f"未配置 {provider.upper()} API Key！\n"
                f"请在 .env 中设置 V4_{provider.upper()}_API_KEY=your-key\n"
                f"或设置 V4_LLM_PROVIDER 为其他可用 provider。"
            )

        base_url = settings.provider_base_url
        if base_url is None:
            raise ValueError(f"Provider '{provider}' 没有配置 base_url")

        logger.info(
            "创建 OpenAIAdapter provider=%s model=%s base_url=%s",
            provider,
            settings.provider_model,
            base_url,
        )

        return OpenAIAdapter(
            api_key=api_key,
            model=settings.provider_model,
            base_url=base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

    elif provider == "anthropic":
        # TODO: 实现 AnthropicAdapter（需要 anthropic 库）
        raise NotImplementedError(
            "Anthropic Claude 适配器尚未实现。\n"
            "请暂时使用 openai 兼容的 provider（如智谱、通义千问等）。"
        )

    else:
        raise ValueError(f"不支持的 LLM Provider: {provider}")
