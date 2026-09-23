"""
AI 代码异味检测器 — 检测 LLM 生成代码的典型失败模式。

这些模式传统 linter 不查或查不准，却是 AI 代码最高频的质量问题:
- SMELL/except-swallow      except: pass 吞异常（AI 最爱写）
- SMELL/overbroad-except    except Exception 兜大网
- SMELL/stub-implementation 桩函数（看起来实现了，实际是 pass/NotImplementedError）
- SMELL/duplicate-function  同名函数重复定义（AI 改写时忘记删旧版）
- SMELL/placeholder-secret  占位符密钥（YOUR_API_KEY / changeme / ${API_KEY}）
- SMELL/placeholder-value   占位符 URL/数据（example.com 等）
- SMELL/todo-hotspot        TODO 热点文件
- SMELL/js-empty-catch      JS 空 catch

设计原则: 全部基于 AST / 精确模式，测试文件自动豁免大部分规则，
保证「报出来的都是真问题」，不用数量换覆盖率。
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from v4_pro.gate import (
    is_test_file,
    mask_js_comments,
)

logger = logging.getLogger(__name__)

# 占位符值模式 — AI 生成代码最爱留的假值
_PLACEHOLDER_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(your|my|insert|replace|enter|add)[_-]?(api[_-]?key|apikey|token|secret|password|passwd)"),
    re.compile(r"(?i)^(x{3,}|changeme|change_me|change-me|dummy[_-]?(key|token|secret|pass)|fake[_-]?(key|token|secret)|test[_-]?api[_-]?key|placeholder)[!_]?"),
    re.compile(r"^\$\{?[A-Z][A-Z0-9_]{2,}\}?$"),  # ${API_KEY} / $API_KEY 风格
    re.compile(r"(?i)^(api|secret|token|auth)[_-]?(key|token)$"),  # 字面值就叫 "API_KEY"
]

_PLACEHOLDER_VALUE_PATTERNS = [
    re.compile(r"(?i)(your|their)[_-](domain|site|email|name)"),
    re.compile(r"(?i)^(foo|bar|baz|test)@example\.(com|org)$"),
    re.compile(r"(?i)example\.com/(api|v1|endpoint|your)"),
    re.compile(r"(?i)^https?://(your|my)-(api|server|domain)"),
]

_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")


def _python_comment_tokens(source: str) -> list:
    """用 tokenize 精确提取 Python 注释 token。"""
    import io
    import tokenize

    try:
        return [
            tok for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


class AiSmellDetector:
    """AI 代码异味检测器。"""

    def scan(self, code_dir: Path, extra_test_paths: list[str] | None = None) -> dict[str, Any]:
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {"passed": True, "issues": [], "summary": {"files_scanned": 0}}

        issues: list[dict] = []
        files = self._collect(code_dir)
        for f in files:
            test_file = is_test_file(f, extra_test_paths)
            suffix = f.suffix.lower()
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if suffix == ".py":
                issues.extend(self._scan_python(f, source, test_file))
            elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
                issues.extend(self._scan_js(f, source, test_file))

        for i, issue in enumerate(issues):
            issue.setdefault("id", f"SMELL-{i+1:03d}")
            issue.setdefault("category", "ai_smell")

        p0 = [x for x in issues if x["severity"] == "P0"]
        return {
            "passed": not p0,
            "issues": issues,
            "summary": {"files_scanned": len(files), "tool": "builtin-ast"},
        }

    # ── Python（AST）─────────────────────────────────────────

    def _scan_python(self, filepath: Path, source: str, test_file: bool) -> list[dict]:
        issues: list[dict] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return issues

        # 文档字符串节点 — 是说明文字不是字面量配置，跳过占位符检测
        docstring_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant) \
                        and isinstance(body[0].value.value, str):
                    docstring_ids.add(id(body[0].value))

        # 同名函数重复定义
        seen_names: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen_names:
                    issues.append(self._issue(
                        filepath, node.lineno, "SMELL/duplicate-function", "P1",
                        f"函数 {node.name}() 在同一文件中定义了两次（第 {seen_names[node.name]} 行与第 {node.lineno} 行）"
                        "——通常是 AI 改写代码时忘记删除旧版本",
                        "删除其中一个实现；确认调用方使用的是哪个版本",
                    ))
                else:
                    seen_names[node.name] = node.lineno

        for node in ast.walk(tree):
            # 桩函数
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not test_file and self._is_stub(node):
                    issues.append(self._issue(
                        filepath, node.lineno, "SMELL/stub-implementation", "P1",
                        f"函数 {node.name}() 疑似桩实现（函数体只有 pass/.../NotImplementedError/返回常量 None）"
                        "——AI 常生成看起来完整、实际未实现的函数",
                        "补全实现，或用 TODO 注释显式标记未完成状态",
                    ))

            # 异常处理
            if isinstance(node, ast.ExceptHandler):
                swallow_worthy = node.type is None or self._names_contains(
                    node.type, {"Exception", "BaseException"}
                )
                if swallow_worthy and self._is_swallowed(node):
                    issues.append(self._issue(
                        filepath, node.lineno, "SMELL/except-swallow", "P1",
                        "异常被静默吞掉（except Exception/裸 except 体内只有 pass/...）"
                        "——错误发生时无任何感知，这是 AI 生成代码中最常见的隐藏故障来源",
                        "至少记录日志 logger.exception(e)，或抛出带上下文的新异常；"
                        "窄类型 except（如 OSError）的 pass 属于惯用法，不会被标记",
                    ))
                elif not test_file and self._is_overbroad(node):
                    issues.append(self._issue(
                        filepath, node.lineno, "SMELL/overbroad-except", "P2",
                        "except Exception 兜底捕获过宽——会掩盖任意 bug",
                        "捕获具体异常类型；确实需要兜底时记录日志并考虑重新抛出",
                    ))

            # 占位符字符串（跳过文档字符串 — 里面的示例文本不是配置值）
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstring_ids:
                issues.extend(self._check_placeholder(filepath, node, node.value, test_file))

        # TODO 热点（只统计注释里的标记 — tokenize 精确定位注释）
        todo_count = sum(
            len(_TODO_RE.findall(tok.string))
            for tok in _python_comment_tokens(source)
        )
        if todo_count >= 5:
            issues.append(self._issue(
                filepath, 1, "SMELL/todo-hotspot", "P3",
                f"文件含 {todo_count} 个 TODO/FIXME/HACK 标记——可能是 AI 生成的半成品",
                "逐项完成或转为 issue 跟踪",
            ))

        return issues

    def _is_stub(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        # 抽象方法/重载声明是合法的接口定义，不算桩
        for dec in node.decorator_list:
            name = dec.id if isinstance(dec, ast.Name) else (
                dec.attr if isinstance(dec, ast.Attribute) else ""
            )
            if name in ("abstractmethod", "overload", "setter", "getter"):
                return False
        body = node.body
        # 去掉开头的文档字符串（即使函数体只有文档字符串）
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        if not body:
            # 只剩文档字符串
            return True
        if len(body) != 1:
            return False
        stmt = body[0]
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is Ellipsis:
            return True
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            fn = stmt.exc
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.func.id if isinstance(fn, ast.Call) and isinstance(fn.func, ast.Name) else (
                    fn.attr if isinstance(fn, ast.Attribute) else ""
                )
            )
            return name == "NotImplementedError"
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is None:
            return True
        return False

    @staticmethod
    def _names_contains(node: ast.expr, names: set[str]) -> bool:
        """判断异常类型表达式（含元组）是否包含给定名字。"""
        if isinstance(node, ast.Name):
            return node.id in names
        if isinstance(node, ast.Attribute):
            return node.attr in names
        if isinstance(node, ast.Tuple):
            return any(AiSmellDetector._names_contains(e, names) for e in node.elts)
        return False

    @staticmethod
    def _is_swallowed(node: ast.ExceptHandler) -> bool:
        return all(
            isinstance(s, ast.Pass)
            or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis)
            for s in node.body
        )

    @staticmethod
    def _is_overbroad(node: ast.ExceptHandler) -> bool:
        return node.type is not None and (
            (isinstance(node.type, ast.Name) and node.type.id == "Exception")
            or (isinstance(node.type, ast.Tuple) and any(
                isinstance(e, ast.Name) and e.id == "Exception" for e in node.type.elts
            ))
        )

    def _check_placeholder(
        self, filepath: Path, node: ast.Constant, value: str, test_file: bool
    ) -> list[dict]:
        if test_file:
            return []
        # 是否出现在含敏感名目标的赋值里（由访问器记录，这里用父节点近似：
        # AST 不含父指针，改为扫描所在行文本）
        for pat in _PLACEHOLDER_SECRET_PATTERNS:
            if pat.search(value):
                return [self._issue(
                    filepath, node.lineno, "SMELL/placeholder-secret", "P1",
                    f"疑似占位符密钥: {value[:40]!r}——AI 生成代码常留假密钥，"
                    "运行时既不工作也容易连真实服务失败",
                    "改为从环境变量读取，并在部署配置中注入真实值",
                )]
        for pat in _PLACEHOLDER_VALUE_PATTERNS:
            if pat.search(value):
                return [self._issue(
                    filepath, node.lineno, "SMELL/placeholder-value", "P2",
                    f"疑似占位符值: {value[:40]!r}——运行时会静默失败或指向不存在的服务",
                    "替换为真实配置值或环境变量",
                )]
        return []

    # ── JS/TS（正则）─────────────────────────────────────────

    def _scan_js(self, filepath: Path, source: str, test_file: bool) -> list[dict]:
        issues: list[dict] = []
        masked = mask_js_comments(source)
        lines = masked.split("\n")

        for i, line in enumerate(lines, 1):
            if re.search(r"catch\s*(\([^)]*\))?\s*\{\s*\}", line):
                issues.append(self._issue(
                    filepath, i, "SMELL/js-empty-catch", "P1",
                    "空 catch 块——错误被静默吞掉",
                    "记录错误或向上抛出",
                ))
            if not test_file:
                issues.extend(self._check_placeholder_js(filepath, node_line=line, line_no=i))
        return issues

    def _check_placeholder_js(self, filepath: Path, node_line: str, line_no: int) -> list[dict]:
        m = re.search(r"""['"]([^'"]{4,80})['"]""", node_line)
        if not m:
            return []
        value = m.group(1)
        for pat in _PLACEHOLDER_SECRET_PATTERNS:
            if pat.search(value):
                return [self._issue(
                    filepath, line_no, "SMELL/placeholder-secret", "P1",
                    f"疑似占位符密钥: {value[:40]!r}",
                    "改为从环境变量或配置服务读取",
                )]
        for pat in _PLACEHOLDER_VALUE_PATTERNS:
            if pat.search(value):
                return [self._issue(
                    filepath, line_no, "SMELL/placeholder-value", "P2",
                    f"疑似占位符值: {value[:40]!r}",
                    "替换为真实配置值",
                )]
        return []

    # ── 公共 ─────────────────────────────────────────────────

    @staticmethod
    def _issue(filepath: Path, line: int, rule_id: str, severity: str, title: str, suggestion: str) -> dict:
        return {
            "severity": severity,
            "rule_id": rule_id,
            "title": title,
            "file": str(filepath),
            "line": line,
            "suggestion": suggestion,
        }

    @staticmethod
    def _collect(root: Path) -> list[Path]:
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                if not set(path.parts) & exclude_dirs:
                    files.append(path)
        return files
