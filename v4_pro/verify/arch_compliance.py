"""
质量门禁 — 架构合规检查模块。

检查代码的模块依赖关系是否符合设计文档中定义的分层约束。
例如: controller 不能直接调用 dao，必须通过 service 层。

实现原理:
1. 解析 Python 代码的 import 语句
2. 根据文件路径推断模块所属的层
3. 检查是否存在违反分层约束的依赖
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ArchComplianceChecker:
    """
    架构合规检查器。

    根据设计文档中的分层约束，检查代码模块依赖是否合规。
    """

    # 常见的层名 → 文件路径模式映射（用于自动推断）
    DEFAULT_LAYER_PATTERNS = {
        "controller": [r"controller", r"handler", r"view", r"route"],
        "service": [r"service", r"usecase", r"business", r"application"],
        "repository": [r"repository", r"dao", r"mapper", r"data"],
        "model": [r"model", r"entity", r"domain", r"schema"],
        "infrastructure": [r"infra", r"util", r"config", r"middleware", r"common"],
    }

    def __init__(self, design_doc: dict[str, Any]):
        """
        Args:
            design_doc: 设计文档 JSON（design.json 的内容）
        """
        self.design = design_doc

        # 解析分层约束
        self.layers: dict[str, dict] = {}
        self.forbidden_deps: dict[str, set[str]] = {}  # layer → {forbidden layers}
        self.allowed_deps: dict[str, set[str]] = {}    # layer → {allowed layers}

        self._parse_layer_constraints()

    def check(self, code_dir: Path) -> dict[str, Any]:
        """
        检查代码目录的架构合规性。

        Args:
            code_dir: 代码目录路径

        Returns:
            {"passed": bool, "issues": list, "summary": dict}
        """
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {
                "passed": False,
                "issues": [{
                    "severity": "P0",
                    "title": f"目录不存在: {code_dir}",
                    "file": str(code_dir),
                }],
                "summary": {"modules_analyzed": 0},
            }

        if not self.layers:
            return {
                "passed": True,
                "issues": [],
                "summary": {
                    "modules_analyzed": 0,
                    "note": "设计文档中未定义分层约束，跳过架构合规检查",
                },
            }

        # 收集所有 Python 文件
        py_files = list(code_dir.rglob("*.py"))
        py_files = [
            f for f in py_files
            if "__pycache__" not in f.parts and "node_modules" not in f.parts
        ]

        if not py_files:
            return {
                "passed": True,
                "issues": [],
                "summary": {"modules_analyzed": 0},
            }

        # 推断每个文件所属的层
        file_layers = self._infer_layers(py_files)

        # 分析每个文件的 import
        issues = []
        for filepath in py_files:
            file_layer = file_layers.get(str(filepath))
            if not file_layer:
                continue  # 无法推断层的文件跳过

            imports = self._extract_imports(filepath)
            for imported_module in imports:
                # 尝试推断被导入模块所属的层
                imported_layer = self._find_layer_for_import(
                    imported_module, file_layers, py_files
                )
                if imported_layer and imported_layer != file_layer:
                    # 检查是否违反约束
                    if imported_layer in self.forbidden_deps.get(file_layer, set()):
                        issues.append({
                            "severity": "P1",
                            "title": (
                                f"架构违规: [{file_layer}] 层直接依赖了 [{imported_layer}] 层"
                            ),
                            "file": str(filepath),
                            "line": self._find_import_line(filepath, imported_module),
                            "category": "arch_compliance",
                            "suggestion": (
                                f"设计约束禁止 {file_layer} 层直接依赖 {imported_layer} 层。"
                                f"考虑通过中间层解耦或调整依赖方向。"
                            ),
                        })

        # 赋予唯一 ID
        for i, issue in enumerate(issues):
            issue["id"] = f"ARCH-{i+1:03d}"

        passed = not any(i.get("severity") == "P0" for i in issues)

        return {
            "passed": passed,
            "issues": issues,
            "summary": {
                "modules_analyzed": len(py_files),
                "layers_detected": list(set(file_layers.values())),
                "constraints_checked": len(self.forbidden_deps),
            },
        }

    def _parse_layer_constraints(self) -> None:
        """从设计文档中解析分层约束。"""
        layers = self.design.get("architecture", {}).get("layers", [])
        if not layers:
            # 也检查旧格式
            layers = self.design.get("layers", [])

        for layer in layers:
            name = layer.get("name", "")
            if not name:
                continue

            self.layers[name] = layer

            forbidden = layer.get("forbidden_dependencies", [])
            self.forbidden_deps[name] = set(forbidden)

            allowed = layer.get("allowed_dependencies", [])
            self.allowed_deps[name] = set(allowed)

        logger.debug(
            "解析分层约束: layers=%s, rules=%d",
            list(self.layers.keys()),
            sum(len(v) for v in self.forbidden_deps.values()),
        )

    def _infer_layers(self, files: list[Path]) -> dict[str, str]:
        """
        根据文件路径推断每个文件所属的层。

        优先级:
        1. 设计文档中的层名直接出现在路径中
        2. DEFAULT_LAYER_PATTERNS 模糊匹配
        """
        file_layers: dict[str, str] = {}

        for f in files:
            path_str = str(f).lower().replace("\\", "/")

            # 精确匹配设计文档中的层名
            for layer_name in self.layers:
                if layer_name.lower() in path_str:
                    file_layers[str(f)] = layer_name
                    break

            # 如果精确匹配没有，用模式匹配
            if str(f) not in file_layers:
                for layer_name, patterns in self.DEFAULT_LAYER_PATTERNS.items():
                    for pattern in patterns:
                        if pattern in path_str.split("/")[-2]:  # 检查父目录
                            # 尝试匹配设计文档中的层名
                            matched_design_layer = self._match_design_layer(layer_name)
                            if matched_design_layer:
                                file_layers[str(f)] = matched_design_layer
                            break

        return file_layers

    def _match_design_layer(self, generic_layer: str) -> str | None:
        """将通用层名映射到设计文档中的具体层名。"""
        for name in self.layers:
            if generic_layer in name.lower() or name.lower() in generic_layer:
                return name
        return None

    def _extract_imports(self, filepath: Path) -> list[str]:
        """从 Python 文件中提取所有 import 的模块名。"""
        imports = []
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except Exception as e:
            logger.debug("解析 import 失败 %s: %s", filepath, e)

        return imports

    def _find_layer_for_import(
        self,
        module_name: str,
        file_layers: dict[str, str],
        all_files: list[Path],
    ) -> str | None:
        """
        推断被导入模块所属的层。

        策略: 在被分析的文件列表中查找与模块名匹配的文件。
        """
        # 将模块名转换为可能的文件路径
        module_parts = module_name.split(".")
        possible_name = module_parts[-1]

        for f in all_files:
            if f.stem == possible_name:
                return file_layers.get(str(f))

        # 也检查完整路径匹配
        module_path = "/".join(module_parts)
        for f in all_files:
            if module_path in str(f).lower().replace("\\", "/").replace(".py", ""):
                return file_layers.get(str(f))

        return None

    def _find_import_line(self, filepath: Path, module_name: str) -> int:
        """查找 import 语句的行号。"""
        try:
            for i, line in enumerate(filepath.read_text(encoding="utf-8").split("\n"), 1):
                if module_name in line and ("import" in line or "from" in line):
                    return i
        except Exception:
            pass
        return 0
