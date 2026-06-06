"""
独立安全审计模块 (SecurityAuditor)。

v4-pro audit 命令的实现 — 对代码库进行全面安全审计，
覆盖 OWASP Top 10 中常见的至少 6 类漏洞。

与 SecurityScanner 的区别:
- 更详细的报告格式（包含风险评级、修复方案、CWE 编号）
- 支持 JSON + 可读文本双格式输出
- 独立的子命令，不依赖其他步骤
"""

from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecurityAuditor:
    """
    独立安全审计器。

    用法:
        auditor = SecurityAuditor()
        report = auditor.audit(Path("./generated/"))
        # report 包含详细的安全发现列表
    """

    def __init__(self):
        self._findings: list[dict] = []
        self._scanned_files = 0

    def audit(self, code_dir: Path) -> dict[str, Any]:
        """
        执行全面安全审计。

        Args:
            code_dir: 代码目录

        Returns:
            审计报告字典
        """
        self._findings = []
        self._scanned_files = 0

        code_dir = Path(code_dir)
        files = self._collect_files(code_dir)
        self._scanned_files = len(files)
        logger.info("安全审计: 扫描 %d 个文件", len(files))

        for filepath in files:
            try:
                source = filepath.read_text(encoding="utf-8")
            except Exception:
                continue

            # 多维度检测
            self._check_injection(filepath, source)
            self._check_broken_access_control(filepath, source)
            self._check_sensitive_data_exposure(filepath, source)
            self._check_xss(filepath, source)
            self._check_insecure_deserialization(filepath, source)
            self._check_logging_sensitive_info(filepath, source)
            self._check_hardcoded_secrets(filepath, source)
            self._check_path_traversal(filepath, source)
            self._check_weak_crypto(filepath, source)

        # 去重
        self._deduplicate()

        # 赋予唯一 ID
        for i, f in enumerate(self._findings):
            f["id"] = f"AUDIT-{i+1:04d}"

        # 统计
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in self._findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # OWASP 覆盖
        owasp_covered = set()
        for f in self._findings:
            if f.get("owasp_category"):
                owasp_covered.add(f["owasp_category"])

        return {
            "audit_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "code_directory": str(code_dir),
                "files_scanned": self._scanned_files,
                "owasp_categories_covered": sorted(owasp_covered),
                "tool": "V4 Pro Security Auditor v1.0",
            },
            "summary": {
                "total_findings": len(self._findings),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "medium": severity_counts["medium"],
                "low": severity_counts["low"],
                "info": severity_counts["info"],
                "risk_score": self._calculate_risk_score(severity_counts),
            },
            "findings": self._findings,
            "remediation_priority": self._build_remediation_plan(),
        }

    # ── OWASP 检测方法 ──────────────────────────────────────

    def _check_injection(self, filepath: Path, source: str) -> None:
        """A03:2021 – 注入检测（SQL、命令、LDAP 等）。"""
        lines = source.split("\n")

        # SQL 注入
        sql_patterns = [
            (r"execute\s*\(\s*['\"].*%s", "SQL 注入: 使用 %s 格式化 SQL 查询"),
            (r"execute\s*\(\s*f['\"]", "SQL 注入: 使用 f-string 拼接 SQL 查询"),
            (r"execute\s*\(\s*['\"].*\".*\+", "SQL 注入: 使用字符串拼接构造 SQL"),
            (r"rawQuery\s*\(\s*.*\+", "SQL 注入: rawQuery 使用字符串拼接"),
        ]

        for pattern, title in sql_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity="critical",
                        owasp="A03:2021 – Injection",
                        cwe="CWE-89",
                        snippet=line.strip()[:120],
                        recommendation="使用参数化查询（PreparedStatement / ? 占位符）替代字符串拼接",
                    )

        # 命令注入
        cmd_patterns = [
            (r"os\.system\s*\(\s*.*\+", "命令注入: os.system 使用字符串拼接"),
            (r"subprocess\.(call|Popen)\s*\(\s*.*\+", "命令注入: subprocess 使用字符串拼接"),
            (r"eval\s*\(\s*.*\+", "代码注入: eval 使用字符串拼接"),
        ]

        for pattern, title in cmd_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity="critical",
                        owasp="A03:2021 – Injection",
                        cwe="CWE-78",
                        snippet=line.strip()[:120],
                        recommendation="使用 subprocess.run([...]) 列表参数方式，避免字符串拼接",
                    )

    def _check_broken_access_control(self, filepath: Path, source: str) -> None:
        """A01:2021 – 访问控制失效。"""
        lines = source.split("\n")

        # 缺少权限检查的端点
        if filepath.suffix == ".py":
            has_auth_decorator = any(
                "login_required" in line or "@require_auth" in line or "@permission" in line
                for line in lines
            )
            has_endpoint = any(
                "@app.route" in line or "@router." in line
                for line in lines
            )

            if has_endpoint and not has_auth_decorator:
                # 只在有路由装饰器的文件中检查
                for i, line in enumerate(lines, 1):
                    if "@app.route" in line or "@router." in line:
                        self._add_finding(
                            filepath=filepath,
                            line=i,
                            title="可能的访问控制缺失: 路由未标注权限检查装饰器",
                            severity="high",
                            owasp="A01:2021 – 访问控制失效",
                            cwe="CWE-862",
                            snippet=line.strip()[:120],
                            recommendation="为敏感端点添加 @login_required 或类似的权限检查装饰器",
                        )

    def _check_sensitive_data_exposure(self, filepath: Path, source: str) -> None:
        """A04:2021 – 敏感数据暴露 / A02:2021 – 加密机制失效。"""
        lines = source.split("\n")

        # 硬编码密钥
        secret_patterns = [
            (r"""(?i)(password|passwd|secret)\s*=\s*["'][^"']{4,}["']""", "硬编码密码"),
            (r"""(?i)(api_key|apikey)\s*=\s*["'][^"']{8,}["']""", "硬编码 API Key"),
            (r"""(?i)(token|jwt_secret)\s*=\s*["'][^"']{8,}["']""", "硬编码 Token/JWT 密钥"),
            (r"""(?i)aws_.*key\s*=\s*["'][^"']+["']""", "硬编码 AWS 密钥"),
        ]

        for pattern, title in secret_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    # 跳过注释行
                    if line.strip().startswith("#") or line.strip().startswith("//"):
                        continue
                    # 跳过 .env.example 等示例文件
                    if "example" in filepath.name.lower():
                        continue
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=f"敏感数据暴露: {title}",
                        severity="critical",
                        owasp="A04:2021 – 不安全的设计",
                        cwe="CWE-798",
                        snippet=line.strip()[:120],
                        recommendation="使用环境变量或密钥管理服务（如 AWS Secrets Manager、HashiCorp Vault）存储敏感信息",
                    )

        # HTTP 明文传输
        for i, line in enumerate(lines, 1):
            if re.search(r"http://(?!localhost|127\.0\.0\.1)", line):
                # 检查是否是 URL 字符串而非注释
                if "http://" in line and "api" in line.lower():
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title="敏感数据暴露: API 调用使用 HTTP 明文传输",
                        severity="high",
                        owasp="A02:2021 – 加密机制失效",
                        cwe="CWE-319",
                        snippet=line.strip()[:120],
                        recommendation="使用 HTTPS 加密所有 API 通信",
                    )

    def _check_xss(self, filepath: Path, source: str) -> None:
        """A03:2021 – XSS 跨站脚本。"""
        if filepath.suffix not in (".js", ".ts", ".jsx", ".tsx", ".html"):
            return

        lines = source.split("\n")
        xss_patterns = [
            (r"innerHTML\s*=", "XSS: 使用 innerHTML 直接插入内容", "critical"),
            (r"outerHTML\s*=", "XSS: 使用 outerHTML 直接插入内容", "high"),
            (r"document\.write\s*\(", "XSS: 使用 document.write()", "high"),
            (r"eval\s*\(.*\+", "XSS: eval 拼接用户输入", "critical"),
            (r"dangerouslySetInnerHTML", "XSS: React dangerouslySetInnerHTML", "high"),
        ]

        for pattern, title, severity in xss_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity=severity,
                        owasp="A03:2021 – Injection (XSS)",
                        cwe="CWE-79",
                        snippet=line.strip()[:120],
                        recommendation="对用户输入进行 HTML 转义，使用 textContent 替代 innerHTML，或使用 DOMPurify 等库清理 HTML",
                    )

    def _check_insecure_deserialization(self, filepath: Path, source: str) -> None:
        """A08:2021 – 软件和数据完整性故障（不安全反序列化）。"""
        if filepath.suffix != ".py":
            return

        lines = source.split("\n")
        deser_patterns = [
            (r"pickle\.loads?\(", "不安全反序列化: 使用 pickle.loads()", "critical"),
            (r"cPickle\.loads?\(", "不安全反序列化: 使用 cPickle.loads()", "critical"),
            (r"dill\.loads?\(", "不安全反序列化: 使用 dill.loads()", "critical"),
            (r"yaml\.load\s*\(", "不安全反序列化: 使用 yaml.load() 而非 safe_load()", "critical"),
            (r"marshal\.loads?\(", "不安全反序列化: 使用 marshal.loads()", "high"),
        ]

        for pattern, title, severity in deser_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    # 跳过规则定义行（scanner.py 自身的模式匹配不是实际漏洞）
                    if 'r"' in line or "r'" in line:
                        continue
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity=severity,
                        owasp="A08:2021 – 软件和数据完整性故障",
                        cwe="CWE-502",
                        snippet=line.strip()[:120],
                        recommendation="使用 json.loads() 或 yaml.safe_load() 替代不安全的反序列化函数",
                    )

    def _check_logging_sensitive_info(self, filepath: Path, source: str) -> None:
        """A09:2021 – 安全日志记录和监控故障。"""
        lines = source.split("\n")

        sensitive_in_log = [
            (r"log.*password", "日志泄露: 日志中可能包含密码"),
            (r"log.*token", "日志泄露: 日志中可能包含 Token"),
            (r"log.*secret", "日志泄露: 日志中可能包含密钥"),
            (r"log.*credit", "日志泄露: 日志中可能包含信用卡信息"),
            (r"print.*password", "日志泄露: print 输出可能包含密码"),
        ]

        for pattern, title in sensitive_in_log:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity="medium",
                        owasp="A09:2021 – 安全日志记录和监控故障",
                        cwe="CWE-532",
                        snippet=line.strip()[:120],
                        recommendation="在日志中脱敏处理敏感字段，或使用专用日志过滤器自动脱敏",
                    )

    def _check_hardcoded_secrets(self, filepath: Path, source: str) -> None:
        """通用硬编码密钥检测（补充 AST 分析）。"""
        if filepath.suffix != ".py":
            return

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name_lower = target.id.lower()
                        sensitive_names = [
                            "password", "passwd", "secret", "api_key",
                            "apikey", "token", "private_key",
                        ]
                        if any(s in name_lower for s in sensitive_names):
                            if isinstance(node.value, ast.Constant):
                                val = node.value.value
                                if isinstance(val, str) and len(val) > 4:
                                    self._add_finding(
                                        filepath=filepath,
                                        line=node.lineno,
                                        title=f"硬编码敏感信息: {target.id}",
                                        severity="critical",
                                        owasp="A07:2021 – 身份识别和身份验证失败",
                                        cwe="CWE-798",
                                        snippet=f"{target.id} = '***'",
                                        recommendation=f"将 {target.id} 移到环境变量或配置文件中",
                                    )

    def _check_path_traversal(self, filepath: Path, source: str) -> None:
        """路径遍历检测。"""
        lines = source.split("\n")

        traversal_patterns = [
            (r"\.\./", "路径遍历: 代码中包含 ../"),
            (r"os\.path\.join\s*\(.*request", "路径遍历: 用户输入参与路径拼接"),
            (r"open\s*\(\s*.*\+.*request", "路径遍历: 用户输入直接用于文件打开"),
        ]

        for pattern, title in traversal_patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity="high",
                        owasp="A01:2021 – 访问控制失效",
                        cwe="CWE-22",
                        snippet=line.strip()[:120],
                        recommendation="使用 pathlib.Path.resolve() 规范化路径，并验证最终路径在允许的基目录内",
                    )

    def _check_weak_crypto(self, filepath: Path, source: str) -> None:
        """弱加密检测。"""
        lines = source.split("\n")

        weak_crypto = [
            (r"hashlib\.md5\s*\(", "弱加密: 使用 MD5 哈希", "CWE-328"),
            (r"hashlib\.sha1\s*\(", "弱加密: 使用 SHA1 哈希", "CWE-328"),
            (r"random\.random\s*\(", "弱随机数: 使用 random.random() 非加密安全随机数", "CWE-338"),
            (r"random\.randint\s*\(", "弱随机数: 使用 random.randint() 非加密安全随机数", "CWE-338"),
        ]

        for pattern, title, cwe in weak_crypto:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    self._add_finding(
                        filepath=filepath,
                        line=i,
                        title=title,
                        severity="medium",
                        owasp="A02:2021 – 加密机制失效",
                        cwe=cwe,
                        snippet=line.strip()[:120],
                        recommendation="使用 hashlib.sha256() 替代 MD5/SHA1，使用 secrets 模块替代 random",
                    )

    # ── 辅助方法 ──────────────────────────────────────────────

    def _add_finding(
        self,
        filepath: Path,
        line: int,
        title: str,
        severity: str,
        owasp: str,
        cwe: str,
        snippet: str,
        recommendation: str,
    ) -> None:
        """添加一条安全发现。"""
        self._findings.append({
            "file": str(filepath),
            "line": line,
            "title": title,
            "severity": severity,
            "owasp_category": owasp,
            "cwe": cwe,
            "code_snippet": snippet,
            "recommendation": recommendation,
            "confidence": "high" if severity in ("critical", "high") else "medium",
        })

    def _deduplicate(self) -> None:
        """去重：同文件同行同标题的发现保留一个。"""
        seen = set()
        unique = []
        for f in self._findings:
            key = (f["file"], f["line"], f["title"])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        self._findings = unique

    def _calculate_risk_score(self, counts: dict[str, int]) -> float:
        """
        计算综合风险评分 (0-100)。

        权重: critical=10, high=5, medium=2, low=1, info=0.2
        """
        weights = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0.2}
        raw = sum(counts.get(sev, 0) * weight for sev, weight in weights.items())
        # 归一化到 0-100（假设每个文件的最高风险是 20）
        normalized = min(raw, 100)
        return round(normalized, 1)

    def _build_remediation_plan(self) -> list[dict]:
        """生成修复优先级计划。"""
        plan = []

        # 按严重程度排序
        critical = [f for f in self._findings if f["severity"] == "critical"]
        high = [f for f in self._findings if f["severity"] == "high"]

        if critical:
            plan.append({
                "priority": 1,
                "action": f"立即修复 {len(critical)} 个严重漏洞",
                "findings": [f["id"] for f in critical],
                "deadline": "24 小时内",
            })

        if high:
            plan.append({
                "priority": 2,
                "action": f"尽快修复 {len(high)} 个高危漏洞",
                "findings": [f["id"] for f in high],
                "deadline": "本周内",
            })

        medium = [f for f in self._findings if f["severity"] == "medium"]
        if medium:
            plan.append({
                "priority": 3,
                "action": f"计划修复 {len(medium)} 个中危漏洞",
                "findings": [f["id"] for f in medium],
                "deadline": "下个迭代",
            })

        return plan

    @staticmethod
    def _collect_files(root: Path) -> list[Path]:
        """收集所有可审计的源码文件。"""
        exclude_dirs = {
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            ".tox", "egg-info", "dist", "build", ".mypy_cache",
        }
        extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html",
            ".xml", ".yml", ".yaml", ".json", ".tf",
        }

        files = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in extensions:
                parts = set(path.parts)
                if not parts & exclude_dirs:
                    files.append(path)
        return files
