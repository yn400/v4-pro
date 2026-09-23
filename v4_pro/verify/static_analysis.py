"""
质量门禁 — 静态分析模块。

集成 pylint / eslint，若未安装则降级为内置检查。
v2.0: 内置规则带稳定 rule_id，注释/字符串掩码后匹配，
print 规则对测试文件与 CLI 模块豁免。
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from v4_pro.gate import is_test_file, mask_strings_and_comments

logger = logging.getLogger(__name__)


class StaticAnalyzer:
    """静态代码分析器。"""

    LINTERS = {
        ".py": {"name": "pylint", "cmd": ["pylint", "--output-format=json"]},
        ".js": {"name": "eslint", "cmd": ["eslint", "--format=json"]},
        ".ts": {"name": "eslint", "cmd": ["eslint", "--format=json"]},
    }

    # 内置检查规则（应用于掩掉字符串/注释后的代码）
    BUILTIN_PYTHON_CHECKS = [
        {
            "pattern": r"except\s*:",
            "rule_id": "SA/bare-except",
            "title": "裸 except 语句",
            "severity": "P1",
            "suggestion": "指定具体的异常类型，如 except ValueError:",
        },
        {
            "pattern": r"import\s+\*",
            "rule_id": "SA/star-import",
            "title": "使用了 import * (star import)",
            "severity": "P2",
            "suggestion": "显式导入需要的符号",
        },
        {
            "pattern": r"\.has_key\(",
            "rule_id": "SA/has-key",
            "title": "使用了已废弃的 .has_key() 方法",
            "severity": "P2",
            "suggestion": "使用 in 操作符替代 .has_key()",
        },
        {
            "pattern": r"if\s+\w+\s*==\s*True\b",
            "rule_id": "SA/eq-true",
            "title": "与 True 的显式比较",
            "severity": "P2",
            "suggestion": "直接使用 if x: 替代 if x == True:",
        },
        {
            "pattern": r"if\s+\w+\s*==\s*None\b",
            "rule_id": "SA/eq-none",
            "title": "与 None 的比较使用 ==",
            "severity": "P2",
            "suggestion": "使用 is None 替代 == None",
        },
    ]

    # print 规则单独处理（CLI/测试豁免）
    PRINT_RULE = {
        "pattern": r"\bprint\s*\(",
        "rule_id": "SA/print-instead-of-logging",
        "title": "库代码中使用 print() 而非 logging",
        "severity": "P2",
        "suggestion": "库/服务代码使用 logging；CLI 入口和测试中的 print 是合法的",
    }

    BUILTIN_JS_CHECKS = [
        {
            "pattern": r"console\.log\s*\(",
            "rule_id": "SA/console-log",
            "title": "生产代码中的 console.log",
            "severity": "P2",
            "suggestion": "移除或使用条件编译包裹",
        },
        {
            "pattern": r"\bvar\s+[A-Za-z_$]",
            "rule_id": "SA/js-var",
            "title": "使用 var 而非 let/const",
            "severity": "P2",
            "suggestion": "使用 let 或 const 替代 var",
        },
        {
            "pattern": r"[^=!<>]==(?!=)[^=]",
            "rule_id": "SA/loose-equality",
            "title": "使用 == 而非 ===",
            "severity": "P2",
            "suggestion": "使用严格相等 ===",
        },
    ]

    def analyze(self, code_dir: Path, extra_test_paths: list[str] | None = None) -> dict[str, Any]:
        """对指定目录执行静态分析。"""
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {
                "passed": False,
                "issues": [{
                    "severity": "P0",
                    "rule_id": "SA/dir-not-found",
                    "title": f"目录不存在: {code_dir}",
                    "file": str(code_dir),
                    "line": 0,
                    "category": "static_analysis",
                    "suggestion": "检查路径是否正确",
                }],
                "summary": {"files_scanned": 0, "tool": "none"},
            }

        files = self._collect_source_files(code_dir)
        logger.info("静态分析: 发现 %d 个源码文件", len(files))

        if not files:
            return {
                "passed": True,
                "issues": [],
                "summary": {"files_scanned": 0, "tool": "none"},
            }

        py_files = [f for f in files if f.suffix == ".py"]
        js_files = [f for f in files if f.suffix in (".js", ".ts", ".jsx", ".tsx")]

        all_issues = []
        tools_used = []

        if py_files:
            pylint_issues, used_pylint = self._check_python(py_files, extra_test_paths)
            all_issues.extend(pylint_issues)
            tools_used.append("pylint" if used_pylint else "builtin-py")

        if js_files:
            eslint_issues, used_eslint = self._check_javascript(js_files, extra_test_paths)
            all_issues.extend(eslint_issues)
            tools_used.append("eslint" if used_eslint else "builtin-js")

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
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        extensions = {".py", ".js", ".ts", ".jsx", ".tsx"}
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                if not set(path.parts) & exclude_dirs:
                    files.append(path)
        return files

    def _check_python(self, files: list[Path], extra_test_paths: list[str] | None) -> tuple[list[dict], bool]:
        if self._has_command("pylint"):
            try:
                return self._run_pylint(files), True
            except Exception as e:
                logger.warning("pylint 执行失败，降级到内置检查: %s", e)

        logger.info("pylint 未安装，使用内置规则检查 %d 个 Python 文件", len(files))
        issues = self._builtin_check(files, self.BUILTIN_PYTHON_CHECKS, extra_test_paths)
        issues.extend(self._print_check(files, extra_test_paths))
        return issues, False

    def _check_javascript(self, files: list[Path], extra_test_paths: list[str] | None) -> tuple[list[dict], bool]:
        if self._has_command("eslint"):
            try:
                return self._run_eslint(files), True
            except Exception as e:
                logger.warning("eslint 执行失败，降级到内置检查: %s", e)

        logger.info("eslint 未安装，使用内置规则检查 %d 个 JS 文件", len(files))
        return self._builtin_check(files, self.BUILTIN_JS_CHECKS, extra_test_paths), False

    def _run_pylint(self, files: list[Path]) -> list[dict]:
        import json

        issues = []
        for f in files:
            try:
                result = subprocess.run(
                    ["pylint", "--output-format=json", str(f)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.stdout.strip():
                    for pi in json.loads(result.stdout):
                        severity_map = {
                            "error": "P0", "fatal": "P0",
                            "warning": "P1", "refactor": "P2", "convention": "P2",
                        }
                        issues.append({
                            "severity": severity_map.get(pi.get("type", ""), "P2"),
                            "rule_id": f"pylint/{pi.get('symbol', 'unknown')}",
                            "title": pi.get("message", ""),
                            "file": pi.get("path", str(f)),
                            "line": pi.get("line", 0),
                            "suggestion": f"pylint: {pi.get('symbol', '')}",
                        })
            except Exception as e:
                logger.debug("pylint failed for %s: %s", f, e)
        return issues

    def _run_eslint(self, files: list[Path]) -> list[dict]:
        import json

        issues = []
        for f in files:
            try:
                result = subprocess.run(
                    ["eslint", "--format=json", str(f)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.stdout.strip():
                    for er in json.loads(result.stdout):
                        for msg in er.get("messages", []):
                            severity_map = {"2": "P0", "1": "P1", "0": "P2"}
                            issues.append({
                                "severity": severity_map.get(str(msg.get("severity", 2)), "P2"),
                                "rule_id": f"eslint/{msg.get('ruleId') or 'unknown'}",
                                "title": msg.get("message", ""),
                                "file": er.get("filePath", str(f)),
                                "line": msg.get("line", 0),
                                "suggestion": f"eslint: {msg.get('ruleId', '')}",
                            })
            except Exception as e:
                logger.debug("eslint failed for %s: %s", f, e)
        return issues

    def _builtin_check(
        self, files: list[Path], rules: list[dict], extra_test_paths: list[str] | None
    ) -> list[dict]:
        issues = []
        for f in files:
            try:
                content = mask_strings_and_comments(f.read_text(encoding="utf-8"))
                lines = content.split("\n")
                for rule in rules:
                    for i, line in enumerate(lines, start=1):
                        if re.search(rule["pattern"], line):
                            issues.append({
                                "severity": rule["severity"],
                                "rule_id": rule["rule_id"],
                                "title": rule["title"],
                                "file": str(f),
                                "line": i,
                                "suggestion": rule["suggestion"],
                            })
            except Exception as e:
                logger.warning("无法读取 %s: %s", f, e)
        return issues

    def _print_check(self, files: list[Path], extra_test_paths: list[str] | None) -> list[dict]:
        """print() 检查 — 测试文件、CLI 模块（argparse/click/typer、__main__）豁免。"""
        issues = []
        rule = self.PRINT_RULE
        for f in files:
            if is_test_file(f, extra_test_paths):
                continue
            try:
                raw = f.read_text(encoding="utf-8")
                if re.search(r"\b(argparse|click|typer)\b|__main__", raw):
                    continue
                content = mask_strings_and_comments(raw)
                for i, line in enumerate(content.split("\n"), start=1):
                    if re.search(rule["pattern"], line):
                        issues.append({
                            "severity": rule["severity"],
                            "rule_id": rule["rule_id"],
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
        try:
            result = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
