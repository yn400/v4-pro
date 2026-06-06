"""
V4 Pro LLM 适配器层。

提供统一的 LLM 调用接口，支持:
- OpenAI / 中转站（OpenAI 兼容 API）
- 智谱 AI (GLM)
- 通义千问 (Qwen)
- Anthropic Claude
"""

from v4_pro.llm.base import AbstractLLM, ChatMessage, LLMResponse
from v4_pro.llm.factory import create_llm

__all__ = ["AbstractLLM", "ChatMessage", "LLMResponse", "create_llm"]
