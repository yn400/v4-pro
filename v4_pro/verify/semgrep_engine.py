"""
Semgrep 深度扫描引擎（可选增强）。

内置一套 AI 场景 semgrep 规则（v4_pro/semgrep_rules/），
当用户机器上装有 semgrep 时自动启用，提供 AST 级检测深度
（正则规则无法做到的代码结构匹配）；未安装则自动降级为内置规则。

设计原则:
- 增强而非依赖: semgrep 缺失/超时/出错都不影响门禁本身
- 去重: semgrep 覆盖到的内置规则在 semgrep 生效时自动让位
- 结果并入门禁报告，共享基线/抑制/SARIF 全套机制
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent / "semgrep_rules"

_SEV_MAP = {"ERROR": "P0", "WARNING": "P1", "INFO": "P2"}

# semgrep 规则集覆盖到的内置规则 id —— semgrep 生效时这些内置规则自动让位，避免一鱼两报
COVERED_BUILTIN_RULES = {
    "SEC/dynamic-exec",
    "SEC/unsafe-deserialize",
    "SEC/unsafe-yaml",
    "SEC/sql-percent-format",
    "SEC/sql-fstring",
    "SEC/sql-concat",
    "SEC/os-command",
    "SEC/os-command-concat",
    "SEC/subprocess-shell",
    "SEC/weak-hash",
    "SEC/weak-random",
    "SEC/document-write",
}


def is_available() -> bool:
    """semgrep 是否在 PATH 中。"""
    return shutil.which("semgrep") is not None


class SemgrepEngine:
    """Semgrep 深度扫描引擎。"""

    def __init__(self, timeout: int = 180, rules_dir: Path | None = None):
        self._timeout = timeout
        self._rules_dir = rules_dir or RULES_DIR

    def is_available(self) -> bool:
        return is_available()

    def scan(self, code_dir: Path) -> dict[str, Any]:
        """
        运行 semgrep（内置规则集），返回标准 check 报告结构。

        任何失败都降级为空结果 + note，绝不抛出阻断门禁。
        """
        empty: dict[str, Any] = {"passed": True, "issues": [], "summary": {"tool": "semgrep", "notes": []}}
        if not self.is_available():
            empty["summary"]["notes"].append("semgrep 未安装，深度扫描跳过")
            return empty
        try:
            proc = subprocess.run(
                [
                    "semgrep", "scan",
                    "--config", str(self._rules_dir),
                    "--json", "--quiet",
                    "--metrics=off",
                    str(code_dir),
                ],
                capture_output=True, text=True, timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("semgrep 运行失败，降级跳过: %s", e)
            empty["summary"]["notes"].append(f"semgrep 运行失败: {e}")
            return empty

        notes: list[str] = []
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            logger.warning("semgrep 输出无法解析，降级跳过")
            empty["summary"]["notes"].append("semgrep 输出解析失败")
            return empty

        for err in data.get("errors", []):
            msg = str(err.get("message", ""))[:120] if isinstance(err, dict) else str(err)[:120]
            if msg:
                notes.append(f"规则警告: {msg}")

        issues: list[dict] = []
        for r in data.get("results", []):
            extra = r.get("extra", {})
            check_id = str(r.get("check_id", "unknown")).split(".")[-1]
            sev = _SEV_MAP.get(extra.get("severity", "INFO"), "P2")
            start = r.get("start", {})
            issues.append({
                "severity": sev,
                "rule_id": f"semgrep/{check_id}",
                "title": extra.get("message", check_id)[:150],
                "file": r.get("path", ""),
                "line": start.get("line", 1),
                "suggestion": extra.get("message", ""),
                "code_snippet": (r.get("extra", {}).get("lines") or "")[:120],
            })

        seen = set()
        unique = []
        for issue in issues:
            key = (issue["file"], issue["line"], issue["rule_id"])
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        for i, issue in enumerate(unique):
            issue.setdefault("id", f"SG-{i+1:03d}")
            issue.setdefault("category", "semgrep")

        p0 = [x for x in unique if x["severity"] == "P0"]
        return {
            "passed": not p0,
            "issues": unique,
            "summary": {
                "tool": "semgrep",
                "rules_dir": str(self._rules_dir),
                "notes": notes,
            },
        }
