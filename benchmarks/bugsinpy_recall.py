"""
基准 A — 真实人类 bug 检出与定位（BugsInPy 数据集）。

数据: BugsInPy（soarsmu/BugsInPy）——17 个知名开源项目的 493 个真实 bug。
      固定 seed 从 5 个项目抽取 24 个 bug，用 diff 头中的 pre-image blob sha
      还原"带缺陷版本的完整文件"（真实历史代码，非合成）。

测什么（诚实声明）:
- v4-pro 内置确定性检测器（SEC/SA/SMELL, allow_external=False）对真实人类 bug 的
  文件级命中（该文件出现 P0/P1）与行级定位（发现落在修复删除行 ±3 行内）
- BugsInPy 的 bug 多为逻辑/行为缺陷，相当部分不在确定性模式检测的射程内，
  预期整体命中率有限——报告同时给出按缺陷类别的分解（异常处理/安全相关/其他）
- 幻觉依赖（PHANTOM/*）不参与本基准（需要注册表网络，且属于基准 C 的范围）

运行: python benchmarks/bugsinpy_recall.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from v4_pro.smells import AiSmellDetector  # noqa: E402
from v4_pro.verify.security_scan import SecurityScanner  # noqa: E402
from v4_pro.verify.static_analysis import StaticAnalyzer  # noqa: E402

DATA = Path(__file__).parent / "data"
SAMPLE = DATA / "bugsinpy_sample.json"


def gh_token() -> str:
    p = subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=10)
    for line in p.stdout.strip().split("\n"):
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


PROJECT_REPO = {
    "black": "psf/black",
    "httpie": "httpie/httpie",
    "tornado": "tornado/tornado",
    "fastapi": "fastapi/fastapi",
    "cookiecutter": "cookiecutter/cookiecutter",
}


def gh_json(url: str, token: str) -> dict:
    import urllib.request
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + token)
    req.add_header("User-Agent", "v4-pro")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def fetch_buggy_file(project: str, bug_id: str, file_path: str, token: str) -> bytes:
    """bug.info 提供 buggy_commit_id；用它在原项目仓库取带缺陷版本文件。"""
    import base64
    info = gh_json(
        f"https://api.github.com/repos/soarsmu/BugsInPy/contents/projects/{project}/bugs/{bug_id}/bug.info",
        token,
    )
    info_text = base64.b64decode(info["content"]).decode("utf-8")
    m = re.search(r'buggy_commit_id="([0-9a-f]+)"', info_text)
    if not m:
        raise ValueError("bug.info 无 buggy_commit_id")
    buggy_commit = m.group(1)
    repo = PROJECT_REPO[project]
    entry = gh_json(
        f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={buggy_commit}",
        token,
    )
    return base64.b64decode(entry["content"])


def parse_patch(diff_text: str) -> dict | None:
    """解析单文件补丁: 返回 {path, pre_sha, removed_lines(set), categories(set)}。"""
    files = re.findall(r"^diff --git a/(\S+) b/(\S+)$", diff_text, re.M)
    idx_shas = re.findall(r"^index ([0-9a-f]+)\.\.([0-9a-f]+)", diff_text, re.M)
    if not files or not idx_shas:
        return None
    path = files[0][1]
    pre_sha = idx_shas[0][0]

    removed: set[int] = set()
    old_ln = None
    categories: set[str] = set()
    for line in diff_text.split("\n"):
        hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+", line)
        if hunk:
            old_ln = int(hunk.group(1))
            continue
        if old_ln is None:
            continue
        if line.startswith("-") and not line.startswith("---"):
            body = line[1:]
            removed.add(old_ln)
            if re.search(r"\bexcept\b", body):
                categories.add("exception")
            if re.search(r"(?i)(hashlib|random|pickle|eval\(|exec\(|subprocess|secret|password|token|sql|verify)", body):
                categories.add("security")
            old_ln += 1
        elif line.startswith("+") and not line.startswith("+++"):
            continue
        else:
            old_ln += 1

    if not removed:
        return None
    if not categories:
        categories.add("other")
    return {"path": path, "pre_sha": pre_sha, "removed": removed, "categories": categories}


def scan_file(path: Path) -> list[dict]:
    issues: list[dict] = []
    issues += SecurityScanner().scan(path.parent if path.suffix == ".py" else path.parent,
                                     )["issues"] if path.parent.exists() else []
    return issues


def main() -> None:
    token = gh_token()
    cases = json.loads(SAMPLE.read_text(encoding="utf-8"))
    print(f"样本: {len(cases)} 个真实 bug\n")

    rows = []
    for case in cases:
        parsed = parse_patch(case["diff"])
        if not parsed:
            rows.append({"case": f"{case['project']}#{case['bug_id']}",
                         "category": "unparseable", "hit": None, "localized": None})
            continue
        try:
            content = fetch_buggy_file(case["project"], case["bug_id"], parsed["path"], token)
        except Exception as e:
            rows.append({"case": f"{case['project']}#{case['bug_id']}",
                         "category": "fetch-failed", "hit": None, "localized": None,
                         "err": str(e)[:60]})
            continue

        fname = Path(parsed["path"]).name or "buggy.py"
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / fname
            f.write_bytes(content)
            issues: list[dict] = []
            issues += SecurityScanner().scan(f.parent)["issues"]
            issues += AiSmellDetector().scan(f.parent)["issues"]
            issues += StaticAnalyzer().analyze(f.parent, allow_external=False)["issues"]

        p0p1 = [i for i in issues if i["severity"] in ("P0", "P1")]
        hit = bool(p0p1)
        localized = any(
            any(abs(i["line"] - ln) <= 3 for ln in parsed["removed"])
            for i in p0p1
        )
        cat = "+".join(sorted(parsed["categories"]))
        rows.append({"case": f"{case['project']}#{case['bug_id']}",
                     "category": cat, "hit": hit, "localized": localized,
                     "findings": [f"{i['rule_id']}:{i['line']}" for i in p0p1][:5]})
        time.sleep(0.1)

    total = [r for r in rows if r["hit"] is not None]
    hits = [r for r in total if r["hit"]]
    localized_hits = [r for r in hits if r["localized"]]

    lines = [
        "# 基准 A — 真实人类 bug 检出与定位（BugsInPy）",
        "",
        f"- 数据: BugsInPy 真实开源项目 bug，5 个项目固定 seed 抽样 {len(cases)} 个",
        "  （black / httpie / tornado / fastapi / cookiecutter）",
        "- 方法: 用 pre-image blob 还原带缺陷版本完整文件，内置检测器扫描，",
        "  行级定位 = P0/P1 发现落在修复删除行 ±3 行内",
        "",
        f"- **文件级命中（出现 P0/P1）**: {len(hits)}/{len(total)} = **{len(hits)/len(total)*100:.0f}%**",
        f"- **行级定位命中（±3 行）**: {len(localized_hits)}/{len(total)} = **{len(localized_hits)/len(total)*100:.0f}%**",
        "",
        "按缺陷类别分解:",
    ]
    cats: dict[str, list] = {}
    for r in total:
        cats.setdefault(r["category"], []).append(r)
    for cat, rs in sorted(cats.items()):
        h = sum(1 for r in rs if r["hit"])
        lz = sum(1 for r in rs if r["localized"])
        lines.append(f"- {cat}: {h}/{len(rs)} 命中, {lz}/{len(rs)} 行级定位")
    lines.append("")
    lines.append("逐用例:")
    lines.append("| 用例 | 类别 | 命中 | 行级定位 | 发现 |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        findings = ", ".join(r.get("findings", [])) or "-"
        hit_s = str(r["hit"]) if r["hit"] is not None else r.get("category", "?")
        lines.append(f"| {r['case']} | {r['category']} | {hit_s} | {r['localized']} | {findings} |")

    report = "\n".join(lines)
    out = Path(__file__).parent / "RESULTS_BUGSINPY.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
