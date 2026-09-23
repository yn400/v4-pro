"""
v4-pro 基准测试 — 测量内置检测器在标注数据集上的检出率与误报率。

方法（诚实声明）:
- slop 集: 15 个合成 "AI 生成风格" 文件，每文件手工标注应被检出的 rule_id，
  共 35 个预期发现。合成数据由项目作者构造，模拟 AI 生成代码的高频失败模式，
  不声称等同于真实世界 AI 代码分布。
- clean 集: Python 标准库的 10 个经典模块（真实人类代码），预期 P0/P1 为零。
  标准库文件在运行时从当前解释器读取，不随仓库分发。
- 范围: 内置确定性检测器（SEC/SA/SMELL），allow_external=False 保证可复现；
  幻觉依赖检测（PHANTOM/*）依赖注册表网络查询，不在本基准内，
  其能力由 examples/ + tests/test_phantom.py 覆盖。

运行: python benchmarks/run_benchmark.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from v4_pro.smells import AiSmellDetector  # noqa: E402
from v4_pro.verify.security_scan import SecurityScanner  # noqa: E402
from v4_pro.verify.static_analysis import StaticAnalyzer  # noqa: E402

SLOP_DIR = Path(__file__).parent / "cases" / "slop"
CLEAN_MODULES = [
    "string.py", "textwrap.py", "struct.py", "bisect.py", "heapq.py",
    "fractions.py", "dataclasses.py", "types.py", "queue.py", "selectors.py",
]


def scan_dir(tmp: Path) -> list[str]:
    """跑全部内置检测器，返回 rule_id 列表。"""
    rule_ids: list[str] = []
    security = SecurityScanner().scan(tmp)
    rule_ids += [i["rule_id"] for i in security["issues"]]
    smells = AiSmellDetector().scan(tmp)
    rule_ids += [i["rule_id"] for i in smells["issues"]]
    static = StaticAnalyzer().analyze(tmp, allow_external=False)
    rule_ids += [i["rule_id"] for i in static["issues"]]
    return rule_ids


def run_slop_cases() -> dict:
    results = {
        "total_expected": 0, "total_hit": 0,
        "missed": [], "unexpected_p0p1": [],
        "per_case": [],
    }
    for expected_file in sorted(SLOP_DIR.glob("*.expected.json")):
        case_py = expected_file.name.replace(".expected.json", ".py")
        case_path = SLOP_DIR / case_py
        labels = json.loads(expected_file.read_text(encoding="utf-8"))["expect"]

        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(case_path, Path(tmp) / case_py)
            rule_ids = set(scan_dir(Path(tmp)))

        hits = [rid for rid in labels if rid in rule_ids]
        missed = [rid for rid in labels if rid not in rule_ids]
        unexpected = [
            rid for rid in rule_ids
            if rid not in labels and rid.split("/")[0] in ("SEC", "SMELL", "SA")
        ]
        results["total_expected"] += len(labels)
        results["total_hit"] += len(hits)
        if missed:
            results["missed"].append({"case": case_py, "missed": missed})
        if unexpected:
            results["unexpected_p0p1"].append({"case": case_py, "unexpected": unexpected})
        results["per_case"].append({
            "case": case_py, "expected": len(labels), "hit": len(hits),
            "extra": len(unexpected),
        })
    return results


def run_clean_cases() -> dict:
    results = {"files": 0, "findings_p0p1": [], "detail": []}
    lib = Path(sys.prefix) / "Lib"
    for mod in CLEAN_MODULES:
        src = lib / mod
        if not src.is_file():
            results["detail"].append({"file": mod, "error": "not found"})
            continue
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(src, Path(tmp) / mod)
            p0p1 = []
            for r in (
                SecurityScanner().scan(tmp),
                AiSmellDetector().scan(tmp),
                StaticAnalyzer().analyze(tmp, allow_external=False),
            ):
                for issue in r["issues"]:
                    if issue["severity"] in ("P0", "P1"):
                        p0p1.append(f"{issue['rule_id']}({issue['severity']})")
        results["files"] += 1
        if p0p1:
            results["findings_p0p1"].append({"file": mod, "findings": p0p1})
        results["detail"].append({"file": mod, "p0p1": len(p0p1)})
    return results


def main() -> None:
    slop = run_slop_cases()
    clean = run_clean_cases()

    recall = slop["total_hit"] / slop["total_expected"] * 100 if slop["total_expected"] else 0
    lines = []
    lines.append("# v4-pro 内置检测器基准报告")
    lines.append("")
    lines.append("> 合成标注集（15 文件 / 31 预期发现）+ 标准库真实人类代码（10 文件）。")
    lines.append("> 内置确定性检测器（SEC/SA/SMELL），allow_external=False。复现：`python benchmarks/run_benchmark.py`")
    lines.append("")
    lines.append(f"- **检出率（recall）**: {slop['total_hit']}/{slop['total_expected']} = **{recall:.1f}%**")
    lines.append(f"- **合成集意外发现（超预期报告）**: {len(slop['unexpected_p0p1'])} 例")
    lines.append(f"- **干净集误报（标准库代码上出现 P0/P1）**: {len(clean['findings_p0p1'])}/{clean['files']} 文件")
    lines.append("")
    if slop["missed"]:
        lines.append("## 漏检明细")
        for m in slop["missed"]:
            lines.append(f"- `{m['case']}`: 缺 {', '.join(m['missed'])}")
        lines.append("")
    if slop["unexpected_p0p1"]:
        lines.append("## 超预期报告明细")
        for u in slop["unexpected_p0p1"]:
            lines.append(f"- `{u['case']}`: {', '.join(u['unexpected'])}")
        lines.append("")
    if clean["findings_p0p1"]:
        lines.append("## 干净集误报明细")
        for f in clean["findings_p0p1"]:
            lines.append(f"- `{f['file']}`: {', '.join(f['findings'])}")
        lines.append("")
    lines.append("## 逐用例")
    lines.append("")
    lines.append("| 用例 | 预期 | 命中 | 超预期 |")
    lines.append("|---|---|---|---|")
    for pc in slop["per_case"]:
        lines.append(f"| {pc['case']} | {pc['expected']} | {pc['hit']} | {pc['extra']} |")
    report = "\n".join(lines)
    out = Path(__file__).parent / "RESULTS.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
