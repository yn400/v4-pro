"""
V4 Pro 配置管理 — 基于 pydantic-settings，自动从 .env 加载。

所有配置项都带有类型校验和默认值，
可通过环境变量或 .env 文件覆盖。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 支持的 LLM Provider 列表 ──────────────────────────────
LLMProvider = Literal["openai", "zhipu", "tongyi", "anthropic"]


class Settings(BaseSettings):
    """V4 Pro 全局配置，所有字段均可通过环境变量设置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="V4_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM Provider ──
    llm_provider: LLMProvider = Field(
        default="openai",
        description="LLM 提供商: openai / zhipu / tongyi / anthropic",
    )

    # ── OpenAI 兼容接口 ──
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI 兼容 API 地址",
    )
    openai_model: str = Field(default="gpt-4o", description="模型名称")

    # ── 智谱 AI (GLM) ──
    zhipu_api_key: str = Field(default="", description="智谱 API Key")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        description="智谱 API 地址",
    )
    zhipu_model: str = Field(default="glm-4-plus", description="智谱模型名")

    # ── 通义千问 (Qwen) ──
    tongyi_api_key: str = Field(default="", description="通义千问 API Key")
    tongyi_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="通义千问 API 地址",
    )
    tongyi_model: str = Field(default="qwen-max", description="通义千问模型名")

    # ── Anthropic Claude ──
    anthropic_api_key: str = Field(default="", description="Anthropic API Key")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude 模型名",
    )

    # ── 通用模型参数 ──
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成温度")
    max_tokens: int = Field(default=4096, ge=1, le=128000, description="最大输出 token 数")

    # ── 工作区 ──
    workspace: str = Field(default="./v4_workspace", description="工作区路径")

    # ── 日志 ──
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="日志级别"
    )

    @model_validator(mode="after")
    def _validate_api_key(self) -> Settings:
        """确保当前 provider 对应的 API Key 已设置。"""
        key_map = {
            "openai": self.openai_api_key,
            "zhipu": self.zhipu_api_key,
            "tongyi": self.tongyi_api_key,
            "anthropic": self.anthropic_api_key,
        }
        if not key_map.get(self.llm_provider, ""):
            # 不在这里抛异常 — 用户可能还没配置；后续调用时再报清晰的错误
            pass
        return self

    @property
    def provider_api_key(self) -> str:
        """返回当前 provider 对应的 API Key。"""
        key_map = {
            "openai": self.openai_api_key,
            "zhipu": self.zhipu_api_key,
            "tongyi": self.tongyi_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return key_map[self.llm_provider]

    @property
    def provider_base_url(self) -> str | None:
        """返回当前 provider 的 base_url（OpenAI 兼容接口用）。"""
        url_map = {
            "openai": self.openai_base_url,
            "zhipu": self.zhipu_base_url,
            "tongyi": self.tongyi_base_url,
            "anthropic": None,  # Anthropic 不用 OpenAI 兼容接口
        }
        return url_map[self.llm_provider]

    @property
    def provider_model(self) -> str:
        """返回当前 provider 对应的模型名。"""
        model_map = {
            "openai": self.openai_model,
            "zhipu": self.zhipu_model,
            "tongyi": self.tongyi_model,
            "anthropic": self.anthropic_model,
        }
        return model_map[self.llm_provider]

    @property
    def workspace_path(self) -> Path:
        """返回工作区的 Path 对象。"""
        return Path(self.workspace).resolve()

    def ensure_workspace(self) -> Path:
        """确保工作区目录存在，返回其 Path。"""
        p = self.workspace_path
        p.mkdir(parents=True, exist_ok=True)
        return p


# ── 全局单例（惰性初始化）──────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """强制重新加载配置（用于测试或运行时切换 provider）。"""
    global _settings
    _settings = Settings()
    return _settings
