"""
质量门禁 — 安全扫描模块。

AST（Python）+ 精确正则，检测常见安全漏洞。
v2.0 误报控制:
- Python 注释/文档字符串先掩码再匹配（tokenize 实现，非逐行猜测）
- subprocess 仅在 shell=True 时判 P1，参数列表形式降为 P2
- innerHTML 降为 P1（清空操作合法），清空赋值豁免
- 测试文件豁免 random/占位符类规则
- 每条规则带稳定 rule_id，支持行内 # v4pro:ignore 抑制
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from v4_pro.gate import is_test_file, mask_comments

logger = logging.getLogger(__name__)


class SecurityScanner:
    """安全漏洞扫描器。"""

    # ── 危险函数调用（AST 级）──
    DANGEROUS_CALLS = [
        {
            "functions": ["eval"],
            "rule_id": "SEC/dynamic-exec",
            "title": "使用了 eval() 动态执行代码",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-95",
            "suggestion": "避免使用 eval/exec，安全替代方案如 ast.literal_eval",
        },
        {
            "functions": ["exec"],
            "rule_id": "SEC/exec-dynamic",
            "title": "使用了 exec() 动态执行代码",
            "severity": "P1",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-95",
            "suggestion": "exec 用于元编程框架内部合法；应用代码避免使用",
        },
        {
            "functions": ["pickle.loads", "pickle.load", "cPickle.loads", "dill.loads"],
            "rule_id": "SEC/unsafe-deserialize",
            "title": "使用了不安全的反序列化",
            "severity": "P0",
            "owasp": "A08:2021 – 软件和数据完整性故障",
            "cwe": "CWE-502",
            "suggestion": "使用 json.loads 或安全序列化格式替代 pickle",
        },
        {
            "functions": ["os.system", "os.popen"],
            "rule_id": "SEC/os-command",
            "title": "使用了直接执行系统命令的函数",
            "severity": "P1",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-78",
            "suggestion": "使用 subprocess.run 参数列表方式（shell=False）",
        },
        {
            "functions": ["yaml.load"],
            "rule_id": "SEC/unsafe-yaml",
            "title": "使用了不安全的 YAML 加载",
            "severity": "P0",
            "owasp": "A08:2021 – 软件和数据完整性故障",
            "cwe": "CWE-502",
            "suggestion": "使用 yaml.safe_load() 替代 yaml.load()",
        },
        # subprocess.call/Popen 在 visitor 里特判：仅 shell=True 才是 P1
    ]

    # ── 正则模式（应用于掩码注释后的源码）──
    PATTERNS = [
        # SQL 注入
        {
            "pattern": r"execute\s*\(\s*['\"].*%s.*['\"]|execute\s*\(\s*['\"].*%\s*\(",
            "rule_id": "SEC/sql-percent-format",
            "title": "潜在的 SQL 注入（%s 格式化拼接 SQL）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-89",
            "suggestion": "使用参数化查询（? 或 %(name)s 占位符由驱动处理）",
        },
        {
            "pattern": r"""\.execute\s*\(\s*f['"]""",
            "rule_id": "SEC/sql-fstring",
            "title": "潜在的 SQL 注入（f-string 拼接 SQL）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-89",
            "suggestion": "使用参数化查询替代 f-string",
        },
        {
            "pattern": r"""\.execute\s*\(\s*['"][^'"]*(SELECT|INSERT|UPDATE|DELETE)[^'"]*['"]\s*\+""",
            "rule_id": "SEC/sql-concat",
            "title": "潜在的 SQL 注入（+ 拼接 SQL 语句）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-89",
            "suggestion": "使用参数化查询",
        },
        # 硬编码密钥（排除占位符 — 那类归 SMELL/placeholder-secret）
        {
            "pattern": r"""(?i)(?:[\w.]*\.)?(?:api[_-]?key|apikey|secret[_-]?key|secret|password|passwd|token|jwt_secret)\s*=\s*["'](?!your)(?!change)(?!test)(?!dummy)(?!placeholder)(?!xxx)(?!<)[^'"]{8,}["']""",
            "rule_id": "SEC/hardcoded-secret",
            "title": "硬编码密钥/密码（字符串字面量赋值）",
            "severity": "P0",
            "owasp": "A07:2021 – 身份识别和身份验证失败",
            "cwe": "CWE-798",
            "suggestion": "使用环境变量或密钥管理服务存储敏感信息",
        },
        {
            "pattern": r"""(?i)(aws_access_key_id|aws_secret_access_key|private_key)\s*=\s*["'][^'"]{8,}["']""",
            "rule_id": "SEC/hardcoded-cloud-key",
            "title": "硬编码云服务密钥",
            "severity": "P0",
            "owasp": "A07:2021 – 身份识别和身份验证失败",
            "cwe": "CWE-798",
            "suggestion": "使用环境变量或 IAM 角色",
        },
        # XSS
        {
            "pattern": r"""innerHTML\s*=\s*(?!["'][\s"']*["']\s*;)""",
            "rule_id": "SEC/innerhtml",
            "title": "使用 innerHTML 插入内容（XSS 风险）",
            "severity": "P1",
            "owasp": "A03:2021 – Injection (XSS)",
            "cwe": "CWE-79",
            "suggestion": "使用 textContent，或经 DOMPurify 等库清理后再赋值",
        },
        {
            "pattern": r"document\.write\s*\(",
            "rule_id": "SEC/document-write",
            "title": "使用了 document.write()（XSS 风险）",
            "severity": "P1",
            "owasp": "A03:2021 – Injection (XSS)",
            "cwe": "CWE-79",
            "suggestion": "使用安全的 DOM 操作方式",
        },
        # 命令注入（字符串拼接形态）
        {
            "pattern": r"os\.system\s*\([^)]*\+",
            "rule_id": "SEC/os-command-concat",
            "title": "潜在的 OS 命令注入（字符串拼接）",
            "severity": "P0",
            "owasp": "A03:2021 – Injection",
            "cwe": "CWE-78",
            "suggestion": "使用 subprocess.run 参数列表方式",
        },
        # 路径遍历（要求路径操作上下文）
        {
            "pattern": r"""(?:open|os\.path\.\w+|Path|os\.chdir|os\.listdir|os\.remove|shutil\.\w+)\s*\([^)]*\.\./""",
            "rule_id": "SEC/path-traversal",
            "title": "路径操作中包含 ../（潜在路径遍历）",
            "severity": "P1",
            "owasp": "A01:2021 – 访问控制失效",
            "cwe": "CWE-22",
            "suggestion": "用 pathlib.resolve() 规范化路径并校验在允许目录内",
        },
        # 日志敏感信息
        {
            "pattern": r"(?i)\b(?:log|logger|logging)\.\w*\s*\([^)]*\b(?:password|passwd|secret|api[_-]?key|token)\b",
            "rule_id": "SEC/log-sensitive",
            "title": "日志语句中可能包含敏感字段",
            "severity": "P1",
            "owasp": "A09:2021 – 安全日志记录和监控故障",
            "cwe": "CWE-532",
            "suggestion": "对敏感字段脱敏后再记录",
        },
        # 不安全随机数（测试文件豁免 — 由调用方处理）
        {
            "pattern": r"\brandom\.(random|randint|randrange|choice)\s*\(",
            "rule_id": "SEC/weak-random",
            "title": "使用了非加密安全的随机数（random 模块）",
            "severity": "P2",
            "owasp": "A02:2021 – 加密机制失效",
            "cwe": "CWE-338",
            "suggestion": "安全场景（密钥/令牌/随机密码）使用 secrets 模块",
        },
        # 弱哈希
        {
            "pattern": r"hashlib\.(md5|sha1)\s*\(",
            "rule_id": "SEC/weak-hash",
            "title": "使用了弱哈希算法（MD5/SHA1）",
            "severity": "P2",
            "owasp": "A02:2021 – 加密机制失效",
            "cwe": "CWE-328",
            "suggestion": "安全场景使用 hashlib.sha256() 及以上",
        },
        # HTTP 明文 API 调用
        {
            "pattern": r"""['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[^'"]*['"]""",
            "rule_id": "SEC/http-plaintext",
            "title": "使用 HTTP 明文 URL（传输未加密）",
            "severity": "P1",
            "owasp": "A02:2021 – 加密机制失效",
            "cwe": "CWE-319",
            "suggestion": "使用 HTTPS",
        },
    ]

    def scan(self, code_dir: Path, extra_test_paths: list[str] | None = None,
             skip_rules: set[str] | None = None) -> dict[str, Any]:
        """
        对指定目录执行安全扫描。

        skip_rules: 需要跳过的 rule_id 集合（semgrep 生效时让位给深度规则，避免一鱼两报）。
        """
        code_dir = Path(code_dir)
        if not code_dir.exists():
            return {
                "passed": False,
                "issues": [{
                    "severity": "P0",
                    "rule_id": "SEC/dir-not-found",
                    "title": f"目录不存在: {code_dir}",
                    "file": str(code_dir),
                    "line": 0,
                }],
                "summary": {"files_scanned": 0},
            }

        files = self._collect_source_files(code_dir)
        logger.info("安全扫描: 扫描 %d 个文件", len(files))

        all_issues: list[dict] = []

        for f in files:
            test_file = is_test_file(f, extra_test_paths)
            try:
                source = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if f.suffix == ".py":
                try:
                    all_issues.extend(self._ast_scan(f, source, test_file))
                except SyntaxError:
                    pass
                # 单遍扫描: 掩掉注释、保留字符串（密钥/URL/SQL 都在字符串里）
                all_issues.extend(self._pattern_scan(f, mask_comments(source), test_file, source))
            elif f.suffix in (".js", ".jsx", ".ts", ".tsx"):
                from v4_pro.gate import mask_js_comments
                all_issues.extend(self._pattern_scan(f, mask_js_comments(source), test_file, source))

        # 去重
        seen = set()
        unique = []
        for issue in all_issues:
            key = (issue.get("file", ""), issue.get("line", 0), issue.get("rule_id", ""))
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        for i, issue in enumerate(unique):
            issue.setdefault("id", f"SEC-{i+1:03d}")
            issue.setdefault("category", "security_scan")

        if skip_rules:
            unique = [i for i in unique if i.get("rule_id") not in skip_rules]

        passed = not any(i.get("severity") == "P0" for i in unique)

        return {
            "passed": passed,
            "issues": unique,
            "summary": {"files_scanned": len(files)},
        }

    def _collect_source_files(self, root: Path) -> list[Path]:
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        extensions = {".py", ".js", ".jsx", ".ts", ".tsx"}
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions:
                if not set(path.parts) & exclude_dirs:
                    files.append(path)
        return files

    def _ast_scan(self, filepath: Path, source: str, test_file: bool) -> list[dict]:
        tree = ast.parse(source)
        visitor = _SecurityVisitor(filepath, self.DANGEROUS_CALLS, test_file)
        visitor.visit(tree)
        return visitor.issues

    def _pattern_scan(
        self, filepath: Path, masked_source: str, test_file: bool, raw_source: str
    ) -> list[dict]:
        issues = []
        raw_lines = set()
        # 正则/规则定义行与其元数据行是数据不是可执行代码 — 豁免（消除"审自己"的自指误报）
        for i, line in enumerate(raw_source.split("\n"), start=1):
            stripped = line.strip()
            if (
                stripped.startswith('"title":')
                or stripped.startswith('"suggestion":')
                or "re.compile(" in line
                or "re.search(" in line
                or "(r'" in line
                or '(r"' in line
                or ": r'" in line
                or ': r"' in line
                or "= r'" in line
                or '= r"' in line
            ):
                raw_lines.add(i)
        lines = masked_source.split("\n")
        for rule in self.PATTERNS:
            if test_file and rule["rule_id"] in ("SEC/weak-random", "SEC/hardcoded-secret"):
                continue
            for i, line in enumerate(lines, start=1):
                if i in raw_lines:
                    continue
                if re.search(rule["pattern"], line):
                    issues.append({
                        "severity": rule["severity"],
                        "rule_id": rule["rule_id"],
                        "title": rule["title"],
                        "file": str(filepath),
                        "line": i,
                        "owasp_category": rule.get("owasp", ""),
                        "cwe": rule.get("cwe", ""),
                        "suggestion": rule.get("suggestion", ""),
                        "code_snippet": line.strip()[:120],
                    })
        return issues


class _SecurityVisitor(ast.NodeVisitor):
    """AST 访问器 — 检测危险函数调用。"""

    def __init__(self, filepath: Path, dangerous_calls: list[dict], test_file: bool):
        self.filepath = filepath
        self.issues: list[dict] = []
        self.test_file = test_file
        self.call_map: dict[str, dict] = {}
        for rule in dangerous_calls:
            for func in rule["functions"]:
                self.call_map[func] = rule

    def visit_Call(self, node: ast.Call) -> None:
        func_name = self._get_func_name(node)

        if func_name:
            rule = self.call_map.get(func_name)
            if rule:
                self._emit(node, rule)

            # subprocess 特判：shell=True 才是命令注入高危
            if func_name in ("subprocess.call", "subprocess.Popen", "subprocess.run", "subprocess.check_output", "subprocess.check_call"):
                has_shell = any(
                    kw.arg == "shell" and self._is_true(kw.value) for kw in node.keywords
                )
                first_arg_str = bool(node.args) and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
                if has_shell or (func_name != "subprocess.run" and first_arg_str):
                    self.issues.append({
                        "severity": "P1",
                        "rule_id": "SEC/subprocess-shell",
                        "title": f"{func_name} 使用 shell=True 或拼接命令（命令注入风险）",
                        "file": str(self.filepath),
                        "line": node.lineno,
                        "owasp_category": "A03:2021 – Injection",
                        "cwe": "CWE-78",
                        "suggestion": "参数用列表传递并保持 shell=False",
                        "code_snippet": f"line {node.lineno}",
                    })

        self.generic_visit(node)

    @staticmethod
    def _is_true(value: ast.expr) -> bool:
        return isinstance(value, ast.Constant) and value.value is True

    def _emit(self, node: ast.Call, rule: dict) -> None:
        if rule.get("rule_id") == "SEC/unsafe-yaml":
            # yaml.load(stream, Loader=SafeLoader) 是安全的
            for kw in node.keywords:
                if kw.arg == "Loader":
                    loader = kw.value
                    name = loader.id if isinstance(loader, ast.Name) else (
                        loader.attr if isinstance(loader, ast.Attribute) else ""
                    )
                    if "Safe" in name or "Cloader" in name.replace("CSafeLoader", "Safe"):
                        return
        self.issues.append({
            "severity": rule["severity"],
            "rule_id": rule["rule_id"],
            "title": rule["title"],
            "file": str(self.filepath),
            "line": node.lineno,
            "owasp_category": rule.get("owasp", ""),
            "cwe": rule.get("cwe", ""),
            "suggestion": rule["suggestion"],
            "code_snippet": f"line {node.lineno}",
        })

    @staticmethod
    def _get_func_name(node: ast.Call) -> str | None:
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
