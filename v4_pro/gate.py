"""
质量门禁基础设施 — 所有检查器共用的能力。

包含:
- Python 注释/字符串/文档字符串掩码（消除正则扫描的注释误报）
- 行级抑制注释 (# v4pro:ignore / # v4pro:ignore=RULE_ID)
- .v4pro.json 项目配置加载
- git diff 变更行过滤（PR 门禁只看改动行）
- 基线（baseline）对比 — 棘轮模式，存量问题不阻断新增
- SARIF 2.1.0 输出（GitHub code scanning 兼容）
- 严重度阈值判定
"""

from __future__ import annotations

import fnmatch
import io
import json
import re
import subprocess
import tokenize
from pathlib import Path
from typing import Any

# ── 严重度 ──────────────────────────────────────────────────

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SEVERITIES = list(SEVERITY_ORDER)


def severity_at_or_above(sev: str, threshold: str) -> bool:
    """判断严重度是否达到阈值（P0 最严重）。"""
    return SEVERITY_ORDER.get(sev, 9) <= SEVERITY_ORDER.get(threshold, 0)


# ── 噪声掩码 ────────────────────────────────────────────────

def mask_comments(source: str) -> str:
    """
    将 Python 注释内容替换为空格，保留字符串与行号。

    用于需要读取字符串内容的规则（如硬编码密钥）。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _regex_mask_comments(source)
    lines = source.split("\n")
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            line_no = tok.start[0]
            if line_no <= len(lines):
                line = lines[line_no - 1]
                col = tok.start[1]
                lines[line_no - 1] = line[:col] + " " * (len(line) - col)
    return "\n".join(lines)


def mask_strings_and_comments(source: str) -> str:
    """
    将 Python 字符串字面量内容与注释替换为空格，保留换行与行号。

    用于不需要字符串内容的规则（如 SQL 注入、路径遍历），
    可消除"规则定义字符串里恰好包含危险模式"这类自指误报。
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _regex_mask_comments(source)
    lines = source.split("\n")
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            _blank_span(lines, tok.start, tok.end)
        elif tok.type == tokenize.STRING:
            _blank_keep_quotes(lines, tok)
    return "\n".join(lines)


def _blank_span(lines: list[str], start: tuple[int, int], end: tuple[int, int]) -> None:
    """把 [start, end) 范围的字符替换为空格。"""
    if start[0] == end[0]:
        line = lines[start[0] - 1]
        lines[start[0] - 1] = line[:start[1]] + " " * (end[1] - start[1]) + line[end[1]:]
    else:
        first = lines[start[0] - 1]
        lines[start[0] - 1] = first[:start[1]] + " " * (len(first) - start[1])
        for ln in range(start[0], end[0] - 1):
            lines[ln] = " " * len(lines[ln])
        last = lines[end[0] - 1]
        lines[end[0] - 1] = " " * end[1] + last[end[1]:]


def _blank_keep_quotes(lines: list[str], tok: tokenize.TokenInfo) -> None:
    """掩掉字符串内容但保留引号（前缀字符后第一个引号起，到结尾引号止）。"""
    text = tok.string
    # 找到前缀(r/b/f/u 组合)之后的第一个引号
    i = 0
    while i < len(text) and text[i] not in "\"'":
        i += 1
    prefix_len = i
    # 结尾引号：三引号优先
    if text[i:i + 3] in ("'''", '"""'):
        q = 3
    else:
        q = 1
    start = (tok.start[0], tok.start[1] + prefix_len + q)
    end_line, end_col = tok.end
    end = (end_line, end_col - q) if end_col >= q else (end_line, end_col)
    if start[0] == end[0] and start[1] <= end[1]:
        _blank_span(lines, start, end)
    else:
        # 跨行字符串：首行从 start 掩到行尾，中间整行掩掉，末行掩到 end
        _blank_span(lines, start, (start[0], len(lines[start[0] - 1])))
        for ln in range(start[0], end[0] - 1):
            if ln >= start[0]:
                lines[ln] = " " * len(lines[ln])
        if end[0] > start[0]:
            _blank_span(lines, (end[0], 0), end)


def _regex_mask_comments(source: str) -> str:
    """tokenize 失败时的兜底注释掩码。"""
    lines = source.split("\n")
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            lines[i] = " " * len(line)
        elif "  #" in line or "\t#" in line:
            idx = line.find("#")
            if idx > 0 and not _in_string(line, idx):
                lines[i] = line[:idx] + " " * (len(line) - idx)
    return "\n".join(lines)


def _in_string(line: str, idx: int) -> bool:
    """粗略判断 idx 位置是否在字符串内（兜底用）。"""
    count_single = line[:idx].count("'") - line[:idx].count("\\'")
    count_double = line[:idx].count('"') - line[:idx].count('\\"')
    return (count_single % 2 == 1) or (count_double % 2 == 1)


def mask_js_comments(source: str) -> str:
    """JS/TS 注释掩码（最佳努力）。"""
    source = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), source, flags=re.S)
    out_lines = []
    for line in source.split("\n"):
        idx = _js_comment_index(line)
        if idx >= 0:
            out_lines.append(line[:idx] + " " * (len(line) - idx))
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _js_comment_index(line: str) -> int:
    in_s = in_d = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            in_d = not in_d
        elif c == "/" and not in_s and not in_d:
            if line[i:i + 2] == "//":
                return i
            if line[i:i + 2] == "/*":
                return i
        i += 1
    return -1


# ── 抑制注释 ────────────────────────────────────────────────

_SUPPRESS_RE = re.compile(r"#\s*v4pro:ignore\b\s*(?:[:=]\s*([\w/\-.,]+))?")


def build_suppression_map(masked_source: str) -> dict[int, set[str]]:
    """
    解析抑制注释，返回 {行号: {规则ID 或 "*"}}。

    支持:
        bad_call()  # v4pro:ignore
        bad_call()  # v4pro:ignore=SEC/sql-fstring
        bad_call()  # v4pro:ignore=SEC/sql-fstring,SMELL/except-swallow
    """
    result: dict[int, set[str]] = {}
    for i, line in enumerate(masked_source.split("\n"), 1):
        m = _SUPPRESS_RE.search(line)
        if m:
            ids = m.group(1)
            if ids:
                result[i] = {rid.strip() for rid in ids.split(",") if rid.strip()}
            else:
                result[i] = {"*"}
    return result


def is_suppressed(issue: dict, supp_map: dict[int, set[str]]) -> bool:
    """判断一条发现是否被其所在行的抑制注释覆盖。"""
    rules = supp_map.get(int(issue.get("line", 0) or 0))
    if not rules:
        return False
    rid = issue.get("rule_id", "")
    return "*" in rules or rid in rules


# ── 文件分类 ────────────────────────────────────────────────

def is_test_file(path: Path, extra_test_paths: list[str] | None = None) -> bool:
    """判断是否测试文件（测试文件享受宽松规则）。"""
    parts = {p.lower() for p in path.parts}
    test_dirs = {"test", "tests", "__tests__", "spec", *(p.lower() for p in (extra_test_paths or []))}
    if parts & test_dirs:
        return True
    name = path.name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name == "conftest.py"
    )


def path_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """按 glob 模式判断文件是否被排除。"""
    if not patterns:
        return False
    try:
        rel = path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat) for pat in patterns)


# ── 项目配置 ────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "fail_on": "P0",
    "exclude": [],
    "disable_rules": [],
    "test_paths": [],
    "phantom": {
        "offline": False,
        "allowlist": [],
        "timeout": 5,
        "cache_ttl_exists": 30,
        "cache_ttl_missing": 7,
    },
    "semgrep": {
        "enabled": True,   # 检测到 semgrep 时自动启用深度扫描
        "timeout": 180,
    },
}


def load_gate_config(root: Path) -> dict[str, Any]:
    """加载 .v4pro.json（若存在），与默认值深合并。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    for name in (".v4pro.json", "v4pro.json"):
        p = Path(root) / name
        if p.is_file():
            try:
                user = json.loads(p.read_text(encoding="utf-8"))
                for k, v in user.items():
                    if k == "phantom" and isinstance(v, dict):
                        cfg["phantom"].update(v)
                    else:
                        cfg[k] = v
            except (json.JSONDecodeError, OSError):
                pass
            break
    return cfg


# ── git diff 变更行 ─────────────────────────────────────────

def changed_lines(repo_root: Path, base: str) -> dict[str, set[int]]:
    """
    返回 {相对路径posix: {变更行号}}，基于 `git diff -U0 base`。

    未跟踪文件视为整文件变更。git 不可用或非仓库时返回空 dict。
    """
    result: dict[str, set[int]] = {}
    try:
        proc = subprocess.run(
            ["git", "diff", "-U0", "--no-color", base],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return result
        current: str | None = None
        for line in proc.stdout.split("\n"):
            if line.startswith("+++ b/"):
                current = line[6:].strip()
            elif line.startswith("@@") and current:
                m = re.search(r"\+(\d+)(?:,(\d+))?", line)
                if m:
                    start = int(m.group(1))
                    count = int(m.group(2)) if m.group(2) else 1
                    if count > 0:
                        result.setdefault(current, set()).update(range(start, start + count))
        # 未跟踪文件：视为整文件变更
        proc2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30,
        )
        if proc2.returncode == 0:
            for f in proc2.stdout.split("\n"):
                f = f.strip()
                if f:
                    result.setdefault(f, set()).add(1)  # 1 号行在变更集中即代表整文件
    except (OSError, subprocess.TimeoutExpired):
        return result
    return result


def filter_by_diff(issues: list[dict], changed: dict[str, set[int]], repo_root: Path) -> list[dict]:
    """只保留落在变更行上的发现。"""
    if not changed:
        return issues
    kept = []
    for issue in issues:
        f = Path(issue.get("file", ""))
        try:
            rel = f.resolve().relative_to(Path(repo_root).resolve()).as_posix()
        except (ValueError, OSError):
            rel = f.as_posix()
        lines = changed.get(rel)
        if lines is None:
            continue
        ln = int(issue.get("line", 0) or 0)
        if ln in lines or 1 in lines:  # 1 in lines 表示整文件变更
            kept.append(issue)
    return kept


# ── 基线 ────────────────────────────────────────────────────

def load_baseline(path: Path) -> set[tuple[str, int, str]]:
    """从历史 verify 报告加载基线 {(file, line, rule_id)}。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    keys = set()
    for issue in data.get("issues", []):
        keys.add((issue.get("file", ""), int(issue.get("line", 0) or 0), issue.get("rule_id", "")))
    for check in data.get("checks", {}).values():
        for issue in check.get("issues", []):
            keys.add((issue.get("file", ""), int(issue.get("line", 0) or 0), issue.get("rule_id", "")))
    return keys


def mark_baseline(issues: list[dict], baseline: set[tuple[str, int, str]]) -> None:
    """给命中基线的发现打上 baseline 标记（不计入门禁判定）。"""
    for issue in issues:
        key = (issue.get("file", ""), int(issue.get("line", 0) or 0), issue.get("rule_id", ""))
        issue["baseline"] = key in baseline


# ── SARIF 输出 ──────────────────────────────────────────────

_LEVEL = {"P0": "error", "P1": "warning", "P2": "note", "P3": "note"}


def to_sarif(report: dict, tool_version: str = "2.0.0") -> dict:
    """把 verify 报告转成 SARIF 2.1.0（GitHub code scanning 兼容）。"""
    rules: dict[str, dict] = {}
    results = []
    for check_name, check in report.get("checks", {}).items():
        for issue in check.get("issues", []):
            rid = issue.get("rule_id", f"{check_name}/unknown")
            if rid not in rules:
                rules[rid] = {
                    "id": rid,
                    "shortDescription": {"text": issue.get("title", rid)},
                    "defaultConfiguration": {"level": _LEVEL.get(issue.get("severity", "P2"), "note")},
                }
            if issue.get("baseline"):
                continue
            results.append({
                "ruleId": rid,
                "level": _LEVEL.get(issue.get("severity", "P2"), "note"),
                "message": {"text": issue.get("suggestion", issue.get("title", ""))},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": Path(issue.get("file", "?")).as_posix()},
                        "region": {"startLine": int(issue.get("line", 1) or 1)},
                    }
                }],
            })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "v4-pro",
                    "version": tool_version,
                    "informationUri": "https://github.com/yn400/v4-pro",
                    "rules": list(rules.values()),
                }
            },
            "results": results,
        }],
    }
