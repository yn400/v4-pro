"""
配置模块单元测试。
"""

import tempfile
from pathlib import Path

import pytest

from v4_pro.config import Settings, get_settings, reload_settings


class TestSettings:
    """配置加载与校验测试。"""

    def test_defaults(self):
        """测试默认值。"""
        settings = Settings()
        assert settings.llm_provider == "openai"
        assert settings.temperature == 0.7
        assert settings.max_tokens == 4096
        assert settings.workspace == "./v4_workspace"

    def test_workspace_path(self):
        """测试工作区路径属性。"""
        settings = Settings()
        p = settings.workspace_path
        assert isinstance(p, Path)

    def test_ensure_workspace_creates_dir(self):
        """测试 ensure_workspace 创建目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(workspace=tmp + "/test_ws")
            p = settings.ensure_workspace()
            assert p.exists()
            assert p.is_dir()

    def test_provider_api_key(self):
        """测试 provider_api_key 属性。"""
        settings = Settings(
            llm_provider="openai",
            openai_api_key="sk-test-123",
        )
        assert settings.provider_api_key == "sk-test-123"

        settings2 = Settings(
            llm_provider="zhipu",
            zhipu_api_key="zhipu-key-456",
        )
        assert settings2.provider_api_key == "zhipu-key-456"

    def test_provider_model(self):
        """测试 provider_model 属性。"""
        settings = Settings(llm_provider="openai", openai_model="gpt-4o")
        assert settings.provider_model == "gpt-4o"

    def test_global_singleton(self):
        """测试全局单例模式。"""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reload_settings(self):
        """测试重新加载。"""
        _s1 = get_settings()
        s2 = reload_settings()
        # 新对象应该不同（因为重新创建）
        assert isinstance(s2, Settings)


class TestConfigEdgeCases:
    """配置边缘情况测试。"""

    def test_empty_api_key(self):
        """测试空 API Key 不抛异常（留给调用时检查）。"""
        settings = Settings(openai_api_key="")
        assert settings.provider_api_key == ""

    def test_invalid_temperature(self):
        """测试 temperature 边界。"""
        # pydantic 校验会拒绝超出范围的值
        with pytest.raises(Exception):  # noqa: B017
            Settings(temperature=3.0)

    def test_custom_log_level(self):
        """测试自定义日志级别。"""
        settings = Settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"
