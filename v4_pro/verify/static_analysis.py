"""
质量门禁 — 静态分析模块。

集成 pylint / eslint，若未安装则降级为内置简单检查。
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StaticAnalyzer:
    """
    静态代码分析器。

    支持两种模式:
    1. 外部 linter 模式: 调用系统已安装的 pylint / eslint
    2. 内置降级模式: 正则 + AST 基础检查
    """

    # 支持的语言 → linter 映射
    LINTERS = {
        ".py": {"name": "pylint", "cmd": ["pylint", "--output-format=json"]},
        ".js": {"name": "eslint", "cmd": ["eslint", "--format=json"]},
        ".ts": {"name": "eslint", "cmd": ["eslint", "--format=json"]},
    }

    # 内置检查规则
    BUILTIN_PYTHON_CHECKS = [
        {
            "pattern": r"except\s*:",
            "title": "裸 except 语句",
            "severity": "P1",
            "suggestion": "指定具体的异常类型，如 except ValueError:",
        },
        {
            "pattern": r"print\(",
            "title": "使用了 print() 而非 logging",
            "severity": "P2",
            "suggestion": "使用 logging 模块替代 print",
        },
        {
            "pattern": r"TODO|FIXME|HACK",
            "title": "代码中含有 TODO/FIXME/HACK",
            "severity": "P2",
            "suggestion": "完成或清理这些标记",
        },
        {
            "pattern": r"import\s+\*",
            "title": "使用了 import * (star import)",
            "severity": "P2",
            "suggestion": "显式导入需要的符号",
        },
        {
            "pattern": r"\.has_key\(",
            "title": "使用了已废弃的 .has_key() 方法",
            "severity": "P2",
            "suggestion": "使用 in 操作符替代 .has_key()",
        },
        {
            "pattern": r"if\s+.*\s*==\s*True\b",
            "title": "与 True 的显式比较",
            "severity": "P2",
            "suggestion": "直接使用 if x: 替代 if x == True:",
        },
        {
            "pattern": r"if\s+.*\s*==\s*None\b",
            "title": "与 None 的比较使用 ==",
            "severity": "P2",
            "suggestion": "使用 is None 替代 == None",
        },
    ]

    BUILTIN_JS_CHECKS = [
        {
            "pattern": r"console\.log\(",
            "title": "生产代码中的 console.log",
            "severity": "P2",
            "suggestion": "移除或使用条件编译包裹",
        },
        {
            "pattern": r"var\s+",
            "title": "使用 var 而非 let/const",
            "severity": "P2",
            "suggestion": "使用 let 或 const 替代 var",
        },
        {
            "pattern": r"==(?!=)",
            "title": "使用 == 而非 ===",
            "severity": "P2",
            "suggestion": "使用严格相等 ===",
        },
    ]

    def analyze(self, code_dir: Path) -> dict[str, Any]:
        """
        对指定目录执行静态分析。

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
                    "line": 0,
                    "category": "static_analysis",
                    "suggestion": "检查路径是否正确",
                }],
                "summary": {"files_scanned": 0, "tool": "none"},
            }

        # 收集所有源码文件
        files = self._collect_source_files(code_dir)
        logger.info("静态分析: 发现 %d 个源码文件", len(files))

        if not files:
            return {
                "passed": True,
                "issues": [],
                "summary": {"files_scanned": 0, "tool": "none"},
            }

        # 按语言分组
        py_files = [f for f in files if f.suffix == ".py"]
        js_files = [f for f in files if f.suffix in (".js", ".ts")]

        all_issues = []
        tools_used = []

        # Python 文件 → pylint 或内置检查
        if py_files:
            pylint_issues, used_pylint = self._check_python(py_files)
            all_issues.extend(pylint_issues)
            tools_used.append("pylint" if used_pylint else "builtin-py")

        # JS/TS 文件 → eslint 或内置检查
        if js_files:
            eslint_issues, used_eslint = self._check_javascript(js_files)
            all_issues.extend(eslint_issues)
            tools_used.append("eslint" if used_eslint else "builtin-js")

        # 赋予唯一 ID
        for i, issue in enumerate(all_issues):
            issue.setdefault("id", f"SA-{i+1:03d}")
            issue.setdefault("category", "static_analysis")

        passed = not any(i.get("severity") == "P0" for i in all_issues)

        return {
            "passed": passed,
            "issues": all_issues,
            "summary": {
                "files_scanned": len(files),
                "tool": ", ".join(tools_used) if tools_used else "none",
            },
        }

    def _collect_source_files(self, root: Path) -> list[Path]:
        """递归收集源码文件，排除 __pycache__、node_modules 等。"""
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        extensions = {".py", ".js", ".ts", ".jsx", ".tsx"}

        files = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in extensions:
                # 检查路径中是否有排除目录
                parts = set(path.parts)
                if not parts & exclude_dirs:
                    files.append(path)
        return files

    def _check_python(self, files: list[Path]) -> tuple[list[dict], bool]:
        """检查 Python 文件 — pylint 优先，降级到内置。"""
        # 尝试 pylint
        if self._has_command("pylint"):
            try:
                return self._run_pylint(files), True
            except Exception as e:
                logger.warning("pylint 执行失败，降级到内置检查: %s", e)

        # 降级到内置检查
        logger.info("pylint 未安装，使用内置规则检查 %d 个 Python 文件", len(files))
        return self._builtin_check(files, self.BUILTIN_PYTHON_CHECKS), False

    def _check_javascript(self, files: list[Path]) -> tuple[list[dict], bool]:
        """检查 JS/TS 文件 — eslint 优先，降级到内置。"""
        if self._has_command("eslint"):
            try:
                return self._run_eslint(files), True
            except Exception as e:
                logger.warning("eslint 执行失败，降级到内置检查: %s", e)

        logger.info("eslint 未安装，使用内置规则检查 %d 个 JS 文件", len(files))
        return self._builtin_check(files, self.BUILTIN_JS_CHECKS), False

    def _run_pylint(self, files: list[Path]) -> list[dict]:
        """运行 pylint 并解析 JSON 输出。"""
        import json

        issues = []
        for f in files:
            try:
                result = subprocess.run(
                    ["pylint", "--output-format=json", str(f)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.stdout.strip():
                    pylint_issues = json.loads(result.stdout)
                    for pi in pylint_issues:
                        severity_map = {
                            "error": "P0",
                            "fatal": "P0",
                            "warning": "P1",
                            "refactor": "P2",
                            "convention": "P2",
                        }
                        issues.append({
                            "severity": severity_map.get(pi.get("type", ""), "P2"),
                            "title": pi.get("message", ""),
                            "file": pi.get("path", str(f)),
                            "line": pi.get("line", 0),
                            "suggestion": f"pylint: {pi.get('symbol', '')}",
                        })
            except Exception as e:
                logger.debug("pylint failed for %s: %s", f, e)

        return issues

    def _run_eslint(self, files: list[Path]) -> list[dict]:
        """运行 eslint 并解析 JSON 输出。"""
        import json

        issues = []
        for f in files:
            try:
                result = subprocess.run(
                    ["eslint", "--format=json", str(f)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.stdout.strip():
                    eslint_results = json.loads(result.stdout)
                    for er in eslint_results:
                        for msg in er.get("messages", []):
                            severity_map = {"2": "P0", "1": "P1", "0": "P2"}
                            issues.append({
                                "severity": severity_map.get(str(msg.get("severity", 2)), "P2"),
                                "title": msg.get("message", ""),
                                "file": er.get("filePath", str(f)),
                                "line": msg.get("line", 0),
                                "suggestion": f"eslint: {msg.get('ruleId', '')}",
                            })
            except Exception as e:
                logger.debug("eslint failed for %s: %s", f, e)

        return issues

    def _builtin_check(
        self, files: list[Path], rules: list[dict]
    ) -> list[dict]:
        """使用内置的正则规则检查文件。"""
        issues = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                lines = content.split("\n")
                for rule in rules:
                    for i, line in enumerate(lines, start=1):
                        if re.search(rule["pattern"], line):
                            # 跳过注释行中的 TODO（这本身就是 TODO 的目的）
                            if rule["title"].startswith("代码中含有 TODO") and line.strip().startswith("#"):
                                continue
                            issues.append({
                                "severity": rule["severity"],
                                "title": rule["title"],
                                "file": str(f),
                                "line": i,
                                "suggestion": rule["suggestion"],
                            })
            except Exception as e:
                logger.warning("无法读取 %s: %s", f, e)

        return issues

    @staticmethod
    def _has_command(cmd: str) -> bool:
        """检查命令是否在 PATH 中可用。"""
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
