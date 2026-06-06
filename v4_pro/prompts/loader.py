"""
Prompt 模板加载器。

扫描 prompts/ 目录下的 .prompt 文件，
使用 Jinja2 进行变量插值渲染。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


class PromptLoader:
    """
    Prompt 模板加载与渲染引擎。

    用法:
        loader = PromptLoader(prompts_dir="prompts")
        rendered = loader.render("research", requirement="做一个电商App")
        # rendered 是填充了变量的完整 system prompt
    """

    def __init__(self, prompts_dir: str | Path = "prompts"):
        """
        Args:
            prompts_dir: .prompt 模板文件所在目录
        """
        self.prompts_dir = Path(prompts_dir).resolve()
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompt 模板目录不存在: {self.prompts_dir}")

        # Jinja2 环境，从模板目录加载文件
        self._env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            autoescape=False,  # Prompt 是纯文本
            trim_blocks=True,
            lstrip_blocks=True,
        )
        logger.debug("PromptLoader 初始化完成，目录: %s", self.prompts_dir)

    def list_templates(self) -> list[str]:
        """列出所有可用的模板名称（不含 .prompt 后缀）。"""
        templates = []
        for f in self.prompts_dir.glob("*.prompt"):
            templates.append(f.stem)
        return sorted(templates)

    def get_template(self, name: str) -> Template:
        """
        获取 Jinja2 Template 对象。

        Args:
            name: 模板名（不含 .prompt 后缀），如 "research"

        Returns:
            Jinja2 Template

        Raises:
            FileNotFoundError: 模板文件不存在
        """
        filename = f"{name}.prompt"
        try:
            return self._env.get_template(filename)
        except Exception as e:
            available = self.list_templates()
            raise FileNotFoundError(
                f"模板 '{name}' 不存在。可用模板: {available}"
            ) from e

    def render(self, name: str, **variables) -> str:
        """
        加载并渲染指定模板。

        Args:
            name: 模板名（不含 .prompt 后缀）
            **variables: 模板变量（如 requirement="..."）

        Returns:
            渲染后的完整 prompt 文本
        """
        template = self.get_template(name)
        rendered = template.render(**variables)
        logger.info("模板 '%s' 渲染完成，长度: %d 字符", name, len(rendered))
        return rendered

    def render_with_context(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        **variables,
    ) -> str:
        """
        渲染模板，并自动注入上下文增强信息。

        如果 context 不为空，会将其内容追加到 prompt 末尾
        （以 "## 上下文增强" 为标题）。

        Args:
            name: 模板名
            context: 上下文字典（由 ContextEnricher 生成）
            **variables: 其他模板变量

        Returns:
            渲染后的完整 prompt
        """
        rendered = self.render(name, **variables)

        if context:
            context_text = self._format_context(context)
            rendered = rendered + "\n\n" + context_text

        return rendered

    @staticmethod
    def _format_context(context: dict[str, Any]) -> str:
        """将上下文字典格式化为自然语言文本块。"""
        parts = ["## 上下文增强（自动注入）\n"]

        # 技术栈
        tech = context.get("tech_stack", {})
        if tech:
            parts.append("### 技术栈")
            for k, v in tech.items():
                parts.append(f"- {k}: {v}")
            parts.append("")

        # 编码规范
        standards = context.get("coding_standards", {})
        if standards:
            parts.append("### 编码规范")
            for k, v in standards.items():
                parts.append(f"- {k}: {v}")
            parts.append("")

        # 架构约束
        constraints = context.get("architecture_constraints", [])
        if constraints:
            parts.append("### 架构约束（必须遵守）")
            for c in constraints:
                parts.append(f"- {c}")
            parts.append("")

        # 冻结规范
        frozen = context.get("frozen_specs")
        if frozen:
            parts.append("### 冻结规范（棘轮约束，不可违反）")
            parts.append(f"```json\n{frozen}\n```")
            parts.append("")

        return "\n".join(parts)
