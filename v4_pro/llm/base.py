"""
LLM 适配器抽象基类。

所有 LLM Provider 适配器都必须继承 AbstractLLM 并实现 chat() 方法。
这样 CLI / Engine 层不需要关心底层用的是哪个模型。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """一条聊天消息，兼容 OpenAI Chat Completions 格式。"""

    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    """LLM 调用返回的统一结构。"""

    content: str  # 模型回复的文本
    model: str = ""  # 实际使用的模型名
    usage: dict[str, int] = field(default_factory=dict)  # {"prompt_tokens": N, "completion_tokens": N}
    finish_reason: str = "stop"  # "stop" | "length" | "error"
    raw: Any = None  # 原始响应对象（调试用）


class AbstractLLM(ABC):
    """
    LLM 适配器抽象基类。

    子类只需实现 chat() 方法即可。
    """

    def __init__(self, model: str, temperature: float = 0.7, max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        发送消息列表，获取模型回复。

        Args:
            messages: 消息列表（system + user + assistant 交替）
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token 数

        Returns:
            LLMResponse: 统一的响应结构
        """
        ...

    def single_turn(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        快捷方法：单轮对话（system + user）。

        大多数 V4 Pro 调用场景都是 system prompt + user input 的单轮结构。
        """
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(model={self.model!r})>"
