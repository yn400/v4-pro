"""
独立安全审计模块 (SecurityAuditor)。

v4-pro audit 命令的实现 — 与 verify 的安全扫描共用同一套检测引擎
（v4_pro.verify.security_scan.SecurityScanner），保证两个入口的结果一致。

v2.0 变化:
- 检测逻辑统一到 SecurityScanner（此前是两套正则，规则漂移、误报翻倍）
- 保留审计报告 schema: audit_metadata / summary / findings / remediation_priority
- OWASP/CWE 映射由规则表统一维护
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v4_pro.verify.security_scan import SecurityScanner

logger = logging.getLogger(__name__)

# verify 严重度 → 审计严重度
_SEV_MAP = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}


class SecurityAuditor:
    """
    独立安全审计器。

    用法:
        auditor = SecurityAuditor()
        report = auditor.audit(Path("./generated/"))
    """

    def __init__(self):
        self._scanned_files = 0

    def audit(self, code_dir: Path, extra_test_paths: list[str] | None = None) -> dict[str, Any]:
        """
        执行全面安全审计。

        Args:
            code_dir: 代码目录

        Returns:
            审计报告字典（schema 与 1.x 兼容）
        """
        code_dir = Path(code_dir)

        scanner = SecurityScanner()
        scan_result = scanner.scan(code_dir, extra_test_paths=extra_test_paths)
        self._scanned_files = scan_result["summary"].get("files_scanned", 0)

        findings = []
        for issue in scan_result["issues"]:
            findings.append({
                "file": issue.get("file", ""),
                "line": issue.get("line", 0),
                "title": issue.get("title", ""),
                "severity": _SEV_MAP.get(issue.get("severity", "P3"), "low"),
                "rule_id": issue.get("rule_id", ""),
                "owasp_category": issue.get("owasp_category", ""),
                "cwe": issue.get("cwe", ""),
                "code_snippet": issue.get("code_snippet", ""),
                "recommendation": issue.get("suggestion", ""),
                "confidence": "high" if issue.get("severity") in ("P0", "P1") else "medium",
            })

        for i, f in enumerate(findings):
            f["id"] = f"AUDIT-{i+1:04d}"

        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        owasp_covered = sorted({f["owasp_category"] for f in findings if f.get("owasp_category")})

        return {
            "audit_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "code_directory": str(code_dir),
                "files_scanned": self._scanned_files,
                "owasp_categories_covered": owasp_covered,
                "tool": "V4 Pro Security Auditor v2.0",
            },
            "summary": {
                "total_findings": len(findings),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "medium": severity_counts["medium"],
                "low": severity_counts["low"],
                "info": severity_counts["info"],
                "risk_score": self._calculate_risk_score(severity_counts),
            },
            "findings": findings,
            "remediation_priority": self._build_remediation_plan(findings),
        }

    @staticmethod
    def _calculate_risk_score(counts: dict[str, int]) -> float:
        """综合风险评分 (0-100): critical=10, high=5, medium=2, low=1, info=0.2。"""
        weights = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0.2}
        raw = sum(counts.get(sev, 0) * weight for sev, weight in weights.items())
        return round(min(raw, 100), 1)

    @staticmethod
    def _build_remediation_plan(findings: list[dict]) -> list[dict]:
        plan = []
        critical = [f for f in findings if f["severity"] == "critical"]
        high = [f for f in findings if f["severity"] == "high"]
        medium = [f for f in findings if f["severity"] == "medium"]

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
        if medium:
            plan.append({
                "priority": 3,
                "action": f"计划修复 {len(medium)} 个中危漏洞",
                "findings": [f["id"] for f in medium],
                "deadline": "下个迭代",
            })
        return plan
