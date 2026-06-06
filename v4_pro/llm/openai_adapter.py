"""
OpenAI 兼容接口适配器。

支持所有提供 OpenAI 兼容 API 的服务：
- OpenAI 官方
- 智谱 AI (GLM)  — base_url: https://open.bigmodel.cn/api/paas/v4
- 通义千问 (Qwen) — base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
- 各类中转站
"""

from __future__ import annotations

import logging

from openai import OpenAI

from v4_pro.llm.base import AbstractLLM, ChatMessage, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIAdapter(AbstractLLM):
    """
    OpenAI 兼容接口适配器。

    通过 base_url 参数适配不同的服务商，
    智谱、通义千问等只要支持 /v1/chat/completions 就能用。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

        # 初始化 OpenAI 客户端
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        发送聊天请求到 OpenAI 兼容接口。

        Args:
            messages: 消息列表
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token 数

        Returns:
            LLMResponse

        Raises:
            RuntimeError: API 调用失败时抛出
        """
        temp = temperature if temperature is not None else self.temperature
        mt = max_tokens if max_tokens is not None else self.max_tokens

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[m.to_dict() for m in messages],
                temperature=temp,
                max_tokens=mt,
            )

            choice = response.choices[0]
            content = choice.message.content or ""

            # 提取 token 用量
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            logger.info(
                "LLM 调用成功 model=%s tokens=%s",
                self.model,
                usage.get("total_tokens", "?"),
            )

            return LLMResponse(
                content=content,
                model=response.model or self.model,
                usage=usage,
                finish_reason=choice.finish_reason or "stop",
                raw=response,
            )

        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            raise RuntimeError(f"LLM API 调用失败 [{self.model}]: {e}") from e
