"""
上下文增强引擎 (ContextEnricher)。

读取工作区中已有的所有 JSON 决策文件，
自动提取技术栈、编码规范、架构约束等信息，
以结构化字典形式提供给 PromptLoader 注入后续 Prompt。

这是 V4 Pro "防碎片化"的核心机制：
每一步都站在前面所有决策的肩膀上。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ContextEnricher:
    """
    上下文增强器。

    扫描工作区中的 JSON 文件，提取关键上下文信息:
    - tech_stack: 语言、框架、数据库等
    - coding_standards: 行宽、命名风格、类型注解要求等
    - architecture_constraints: 分层约束、禁止的跨层调用等
    - frozen_specs: 冻结的接口规范
    """

    # 定义哪些文件参与上下文提取，以及提取优先级
    CONTEXT_FILES = [
        "research.json",
        "define.json",
        "design.json",
        "generate.json",
        "frozen_spec.json",
    ]

    def __init__(self, workspace: Path):
        """
        Args:
            workspace: 工作区目录路径
        """
        self.workspace = Path(workspace)
        logger.debug("ContextEnricher 初始化 workspace=%s", self.workspace)

    def enrich(self) -> dict[str, Any]:
        """
        扫描工作区，提取所有上下文信息。

        Returns:
            上下文字典，可直接传给 PromptLoader.render_with_context()
        """
        context: dict[str, Any] = {
            "tech_stack": {},
            "coding_standards": {},
            "architecture_constraints": [],
            "frozen_specs": None,
        }

        # 按优先级处理每个文件
        for filename in self.CONTEXT_FILES:
            filepath = self.workspace / filename
            if not filepath.exists():
                continue

            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("无法读取 %s: %s", filename, e)
                continue

            self._extract_from_file(filename, data, context)

        # 去重架构约束
        context["architecture_constraints"] = list(
            dict.fromkeys(context["architecture_constraints"])
        )

        has_content = any(
            context[k]
            for k in ["tech_stack", "coding_standards", "architecture_constraints"]
        ) or context.get("frozen_specs")

        if has_content:
            logger.info(
                "上下文增强: tech=%d, standards=%d, constraints=%d, frozen=%s",
                len(context["tech_stack"]),
                len(context["coding_standards"]),
                len(context["architecture_constraints"]),
                "yes" if context["frozen_specs"] else "no",
            )

        return context

    def _extract_from_file(
        self, filename: str, data: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """
        从单个 JSON 文件中提取上下文信息。

        不同文件类型有不同的提取策略:
        - design.json: 包含最完整的 tech_stack 和 coding_standards
        - frozen_spec.json: 冻结的接口规范
        - generate.json: 已生成文件列表
        """
        if "design" in filename:
            self._extract_tech_stack(data, context)
            self._extract_coding_standards(data, context)
            self._extract_arch_constraints(data, context)

        elif "frozen_spec" in filename:
            context["frozen_specs"] = data

        elif "generate" in filename:
            # 从已生成文件中提取额外的技术栈信息
            meta = data.get("_meta", {})
            if meta.get("model"):
                # 记录用了什么模型生成
                pass

    def _extract_tech_stack(
        self, data: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """提取技术栈信息。"""
        tech = data.get("tech_stack", {})
        if tech:
            context["tech_stack"] = {
                "language": tech.get("language", ""),
                "framework": tech.get("framework", ""),
                "database": tech.get("database", ""),
                "cache": tech.get("cache", ""),
                "message_queue": tech.get("message_queue", ""),
            }
            # 过滤空值
            context["tech_stack"] = {
                k: v for k, v in context["tech_stack"].items() if v
            }
            # 追加 other
            other = tech.get("other", [])
            if other:
                context["tech_stack"]["other_tools"] = ", ".join(other)

    def _extract_coding_standards(
        self, data: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """提取编码规范。"""
        standards = data.get("coding_standards", {})
        if standards:
            context["coding_standards"] = {
                "max_line_length": str(standards.get("max_line_length", 120)),
                "naming_style": standards.get("naming_style", "snake_case"),
                "require_type_annotations": str(
                    standards.get("require_type_annotations", True)
                ),
                "require_docstrings": str(standards.get("require_docstrings", True)),
                "error_handling_pattern": standards.get(
                    "error_handling_pattern", "try-except"
                ),
            }

    def _extract_arch_constraints(
        self, data: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """提取架构约束 — 禁止的跨层调用。"""
        layers = data.get("architecture", {}).get("layers", [])
        for layer in layers:
            name = layer.get("name", "")
            forbidden = layer.get("forbidden_dependencies", [])
            for dep in forbidden:
                constraint = f"❌ {name} 层禁止直接依赖 {dep} 层"
                if constraint not in context["architecture_constraints"]:
                    context["architecture_constraints"].append(constraint)

        # 也提取允许的依赖方向
        for layer in layers:
            name = layer.get("name", "")
            allowed = layer.get("allowed_dependencies", [])
            for dep in allowed:
                constraint = f"✅ {name} 层可以依赖 {dep} 层"
                if constraint not in context["architecture_constraints"]:
                    context["architecture_constraints"].append(constraint)

    def get_frozen_specs(self) -> dict[str, Any] | None:
        """
        获取冻结规范（如果存在）。

        Returns:
            冻结规范字典，或 None
        """
        frozen_file = self.workspace / "frozen_spec.json"
        if frozen_file.exists():
            return json.loads(frozen_file.read_text(encoding="utf-8"))
        return None
