"""CI/CD 集成 — 将 audit JSON 转为 GitHub Actions 行内注解。

用法:
    v4-pro audit --code ./src/ --format json > report.json
    python -m v4_pro.ci_check report.json
"""

import json
import re
import sys
from pathlib import Path


def _sanitize(text: str) -> str:
    """清理控制字符和不可见字符。"""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]", "", text)
    return text.strip()[:200]


def main():
    # Force UTF-8 for GitHub Actions output
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # Python < 3.7

    args = sys.argv[1:]
    if not args:
        print("Usage: python -m v4_pro.ci_check <audit-report.json>")
        sys.exit(1)

    report_path = Path(args[0])
    if not report_path.exists():
        print(f"File not found: {report_path}")
        sys.exit(1)

    report = json.loads(report_path.read_bytes())
    findings = report.get("findings", [])

    if not findings:
        print("✅ v4-pro: No issues found")
        return

    critical_findings = [f for f in findings if f.get("severity") == "critical"]
    high_findings = [f for f in findings if f.get("severity") == "high"]

    for finding in findings:
        severity = finding.get("severity", "warning")
        level = "error" if severity in ("critical", "high") else "warning"
        title = _sanitize(finding.get("title", "Unknown issue"))
        file_path = _sanitize(finding.get("file", ""))
        line = finding.get("line", 1)

        # GitHub Actions annotation
        msg = f"::{level} file={file_path},line={line},title={title}::{title}"
        print(msg)

        rec = _sanitize(finding.get("recommendation", ""))
        if rec:
            print(f"::notice file={file_path},line={line}::Suggestion: {rec}")

    # Summary
    print("::group::V4 Pro Audit Summary")
    total = len(findings)
    critical = len(critical_findings)
    high = len(high_findings)
    print(f"Critical: {critical} | High: {high} | Total: {total}")
    print("::endgroup::")

    if critical > 0:
        print(f"❌ {critical} critical issue(s) found — PR blocked")
        sys.exit(1)
    print("✅ V4 Pro quality gate passed")


if __name__ == "__main__":
    main()
