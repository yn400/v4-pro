"""
质量门禁 — 安全扫描模块。

使用 AST（Python）+ 正则模式检测常见安全漏洞:
- SQL 注入
- XSS
- 硬编码密钥
- 路径遍历
- 命令注入
- 不安全反序列化
- 日志敏感信息泄露
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecurityScanner:
    """
    安全漏洞扫描器。

    针对 Python 代码使用 AST 进行深度分析，
    同时支持正则模式匹配通用漏洞模式。
    """

    # ── 危险函数调用模式 ──
    DANGEROUS_CALLS = [
        {
            "functions": ["eval", "exec"],
            "title": "使用了 eval()/exec() 动态执行代码",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "suggestion": "避免使用 eval/exec，使用安全的替代方案（如 ast.literal_eval）",
        },
        {
            "functions": ["pickle.loads", "pickle.load", "cPickle.loads", "dill.loads"],
            "title": "使用了不安全的反序列化",
            "severity": "P0",
            "owasp": "A08:2021 – 软件和数据完整性故障",
            "suggestion": "使用 json.loads 或安全的序列化库替代 pickle",
        },
        {
            "functions": ["os.system", "os.popen", "subprocess.call", "subprocess.Popen"],
            "title": "使用了可能执行外部命令的函数",
            "severity": "P1",
            "owasp": "A03:2021 – Injection",
            "suggestion": "使用 subprocess.run 并设置 shell=False，参数用列表传递",
        },
        {
            "functions": ["yaml.load"],
            "title": "使用了不安全的 YAML 加载",
            "severity": "P0",
            "owasp": "A08:2021",
            "suggestion": "使用 yaml.safe_load() 替代 yaml.load()",
        },
        # 注：open() 本身不属于危险调用，路径遍历风险由 _pattern_scan 的专项规则覆盖
    ]

    # ── 正则模式 ──
    PATTERNS = [
        # SQL 注入
        {
            "pattern": r"execute\s*\(\s*['\"].*%\s*.*['\"]",
            "title": "潜在的 SQL 注入（字符串格式化拼接 SQL）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "suggestion": "使用参数化查询（? 占位符）替代字符串拼接",
        },
        {
            "pattern": r"""\.execute\s*\(\s*["']\s*SELECT.*\+""",
            "title": "潜在的 SQL 注入（用 + 拼接 SQL）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "suggestion": "使用参数化查询",
        },
        {
            "pattern": r"\.execute\s*\(\s*f['\"]",
            "title": "潜在的 SQL 注入（f-string 拼接 SQL）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "suggestion": "使用参数化查询替代 f-string",
        },
        # 硬编码密钥
        {
            "pattern": r"""(?i)(api_key|apikey|secret|password|token)\s*=\s*["'][^'"]{8,}["']""",
            "title": "可能的硬编码密钥/密码",
            "severity": "P0",
            "owasp": "A07:2021 – 身份识别和身份验证失败",
            "suggestion": "使用环境变量或密钥管理服务存储敏感信息",
        },
        {
            "pattern": r"""(?i)(access_key|secret_key|private_key)\s*=\s*["'][^'"]+["']""",
            "title": "可能的硬编码云服务密钥",
            "severity": "P0",
            "owasp": "A07:2021",
            "suggestion": "使用环境变量或 IAM 角色",
        },
        # XSS
        {
            "pattern": r"innerHTML\s*=",
            "title": "使用了 innerHTML（潜在 XSS 风险）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection (XSS)",
            "suggestion": "使用 textContent 或经过 HTML 转义后再赋值",
        },
        {
            "pattern": r"document\.write\(",
            "title": "使用了 document.write()（XSS 风险）",
            "severity": "P1",
            "owasp": "A03:2021",
            "suggestion": "使用安全的 DOM 操作方式",
        },
        # 命令注入
        {
            "pattern": r"os\.system\s*\(\s*.*\+",
            "title": "潜在的 OS 命令注入（字符串拼接）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "suggestion": "使用 subprocess.run 参数列表方式，避免字符串拼接",
        },
        # 路径遍历：要求 ../ 出现在路径操作上下文中，而非字符串定义或正则表达式里
        {
            "pattern": r"""(?:open|os\.path\.|Path|os\.chdir|os\.listdir|os\.remove|shutil)\s*\(.*\.\./""",
            "title": "潜在路径遍历风险（函数调用参数含 ../）",
            "severity": "P0",
            "owasp": "A01:2021",
            "suggestion": "使用 pathlib.resolve() 规范化路径并验证在允许范围内",
        },
        # 日志敏感信息
        {
            "pattern": r"(?i)log.*password",
            "title": "日志中可能包含密码信息",
            "severity": "P1",
            "owasp": "A09:2021 – 安全日志记录和监控故障",
            "suggestion": "确保日志中不包含密码、Token 等敏感信息",
        },
        # 不安全随机数
        {
            "pattern": r"random\.random\s*\(",
            "title": "使用了非加密安全的随机数（random.random）",
            "severity": "P2",
            "owasp": "A02:2021 – 加密机制失效",
            "suggestion": "安全场景使用 secrets 模块替代 random",
        },
    ]

    def scan(self, code_dir: Path) -> dict[str, Any]:
        """
        对指定目录执行安全扫描。

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
                "summary": {"files_scanned": 0},
            }

        # 收集 Python 文件
        files = self._collect_source_files(code_dir)
        logger.info("安全扫描: 扫描 %d 个文件", len(files))

        all_issues = []

        for f in files:
            if f.suffix == ".py":
                try:
                    source = f.read_text(encoding="utf-8")
                    # AST 分析
                    ast_issues = self._ast_scan(f, source)
                    all_issues.extend(ast_issues)
                except Exception as e:
                    logger.debug("AST 扫描失败 %s: %s", f, e)

            # 正则模式匹配（所有文本文件）
            try:
                source = f.read_text(encoding="utf-8")
                pattern_issues = self._pattern_scan(f, source)
                all_issues.extend(pattern_issues)
            except Exception:
                pass

        # 去重（同一行同一标题视为重复）
        seen = set()
        unique = []
        for issue in all_issues:
            key = (issue.get("file", ""), issue.get("line", 0), issue.get("title", ""))
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        # 赋予唯一 ID
        for i, issue in enumerate(unique):
            issue.setdefault("id", f"SEC-{i+1:03d}")
            issue.setdefault("category", "security_scan")

        passed = not any(i.get("severity") == "P0" for i in unique)

        return {
            "passed": passed,
            "issues": unique,
            "summary": {
                "files_scanned": len(files),
            },
        }

    def _collect_source_files(self, root: Path) -> list[Path]:
        """收集源码文件。"""
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build",
        }
        extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".xml", ".yml", ".yaml"}

        files = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in extensions:
                parts = set(path.parts)
                if not parts & exclude_dirs:
                    files.append(path)
        return files

    def _ast_scan(self, filepath: Path, source: str) -> list[dict]:
        """使用 AST 深度分析 Python 代码。"""
        issues = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return issues

        visitor = _SecurityVisitor(filepath, self.DANGEROUS_CALLS)
        visitor.visit(tree)
        issues.extend(visitor.issues)

        return issues

    def _pattern_scan(self, filepath: Path, source: str) -> list[dict]:
        """使用正则模式匹配漏洞。"""
        issues = []
        lines = source.split("\n")

        for pattern_rule in self.PATTERNS:
            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                # 跳过注释行，避免误报（如注释中解释 ../ 路径遍历的说明文字）
                if (
                    stripped.startswith("#")
                    or stripped.startswith("//")
                    or stripped.startswith("*")
                    or stripped.startswith('"""')
                    or stripped.startswith("'''")
                ):
                    continue
                if re.search(pattern_rule["pattern"], line):
                    issues.append({
                        "severity": pattern_rule["severity"],
                        "title": pattern_rule["title"],
                        "file": str(filepath),
                        "line": i,
                        "owasp_category": pattern_rule.get("owasp", ""),
                        "suggestion": pattern_rule.get("suggestion", ""),
                        "code_snippet": line.strip()[:120],
                    })

        return issues


class _SecurityVisitor(ast.NodeVisitor):
    """AST 访问器 — 检测危险的函数调用和模式。"""

    def __init__(self, filepath: Path, dangerous_calls: list[dict]):
        self.filepath = filepath
        self.dangerous_calls = dangerous_calls
        self.issues: list[dict] = []

        # 构建函数名 → 规则映射
        self.call_map = {}
        for rule in dangerous_calls:
            for func in rule["functions"]:
                self.call_map[func] = rule

    def visit_Call(self, node: ast.Call) -> None:
        """检测危险的函数调用。"""
        func_name = self._get_func_name(node)
        if func_name and func_name in self.call_map:
            rule = self.call_map[func_name]
            self.issues.append({
                "severity": rule["severity"],
                "title": rule["title"],
                "file": str(self.filepath),
                "line": node.lineno,
                "owasp_category": rule.get("owasp", ""),
                "suggestion": rule["suggestion"],
                "code_snippet": f"line {node.lineno}",
            })

        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node: ast.Call) -> str | None:
        """从 Call 节点提取完整函数名。"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            obj = node.func
            parts = [obj.attr]
            while isinstance(obj.value, ast.Attribute):
                obj = obj.value
                parts.append(obj.attr)
            if isinstance(obj.value, ast.Name):
                parts.append(obj.value.id)
            return ".".join(reversed(parts))
        return None
