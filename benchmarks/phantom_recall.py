"""
基准 C — 真实攻击包信号覆盖测试。

数据: OSV (Open Source Vulnerabilities) 官方 PyPI 转储中的恶意包公告
      （MAL-* 条目，含 OpenSSF/厂商披露的真实供应链攻击），去重未撤回共 11,744 个。
      固定随机种子采样 150 个，逐个跑完整 PhantomDependencyChecker 管线。

测什么（诚实声明）:
- v4-pro 的幻觉/碰瓷/新包三类信号对**真实攻击包名**的覆盖率
- 我们不做行为分析——恶意代码行为检测不在范围内，
  正常名字 + 长期存在的恶意包不在此基准的信号射程内（结果会量化这条边界）

运行: python benchmarks/phantom_recall.py
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from v4_pro.phantom import PhantomDependencyChecker  # noqa: E402

DATA = Path(__file__).parent / "data"
SAMPLE_N = 150
SEED = 42


def main() -> None:
    malicious: dict[str, str] = json.loads(
        (DATA / "osv_malicious_pypi.json").read_text(encoding="utf-8")
    )
    random.seed(SEED)
    names = random.sample(sorted(malicious.keys()), SAMPLE_N)

    print(f"采样 {len(names)} 个真实恶意 PyPI 包（OSV MAL 公告，seed={SEED}）\n")

    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "none": 0}
    by_rule: dict[str, int] = {}
    flagged_names: list[dict] = []
    unflagged: list[str] = []

    cache_file = DATA / ".phantom_cache.json"
    tmp = Path(tempfile.mkdtemp())
    for name in names:
        d = tmp / f"case_{name}"
        d.mkdir(exist_ok=True)
        (d / "app.py").write_text(f"import {name}\n", encoding="utf-8")

    # 多轮执行: 每轮只对未缓存的查询触网，unverified 随轮次排干
    checker = PhantomDependencyChecker(cache_path=cache_file)
    report = None
    for pass_no in range(1, 4):
        report = checker.scan(tmp)
        unverified = sum(
            1 for i in report["issues"]
            if i.get("rule_id") == "PHANTOM/unverified"
        )
        print(f"  第 {pass_no} 轮: 未核实剩余 {unverified}")
        if unverified == 0:
            break
        time.sleep(3)

    per_name: dict[str, list[dict]] = {}
    for i in report["issues"]:
        m = i["file"].replace("\\", "/").split("/")[-2]
        per_name.setdefault(m, []).append(i)

    for idx, name in enumerate(names, 1):
        issues = per_name.get(f"case_{name}", [])
        severities = [
            i["severity"] for i in issues
            if i.get("rule_id", "").startswith("PHANTOM/")
        ]
        rules = [i["rule_id"] for i in issues
                 if i.get("rule_id", "").startswith("PHANTOM/")]

        if "P0" in severities:
            counts["P0"] += 1
        elif "P1" in severities:
            counts["P1"] += 1
        elif "P2" in severities:
            counts["P2"] += 1
        elif "P3" in severities:
            counts["P3"] += 1
        else:
            counts["none"] += 1
            unflagged.append(name)
        for rid in rules:
            by_rule[rid] = by_rule.get(rid, 0) + 1
        if any(s in ("P0", "P1") for s in severities):
            flagged_names.append({"name": name, "rules": rules})

        if idx % 25 == 0:
            print(f"  进度 {idx}/{len(names)} | 当前: {counts}")
        time.sleep(0.1)  # 对注册表友好

    verified = SAMPLE_N - counts["P3"]
    signal_rate = (SAMPLE_N - counts["none"] - counts["P3"]) / verified * 100
    p0_rate = counts["P0"] / SAMPLE_N * 100
    lines = [
        "# 基准 C — 真实攻击包信号覆盖（OSV 数据）",
        "",
        "- 数据: OSV PyPI 转储 MAL 公告（OpenSSF/厂商披露的真实供应链攻击），",
        f"  去重 11,744 个，固定 seed 采样 {SAMPLE_N} 个",
        "- 方法: 逐个构造 import 场景，跑完整 PhantomDependencyChecker 管线（实时注册表查证）",
        "",
        f"- **信号覆盖率（剔除网络失败后）**: {SAMPLE_N - counts['none'] - counts['P3']}/{verified} = **{signal_rate:.1f}%**",
        f"- 网络失败未能核实: {counts['P3']} 个（不计入覆盖率，重跑可续查）",
        f"- **P0 直接拦截率**: {counts['P0']}/{SAMPLE_N} = **{p0_rate:.1f}%**",
        f"- 信号分解: {json.dumps(by_rule, ensure_ascii=False)}",
        f"- 未触发任何信号: {counts['none']} 个（多为'正常名字 + 包已下架/存在已久'——行为分析不在范围内）",
        "",
        "未触发名单（诚实公示）:",
    ]
    lines += [f"- {n}" for n in unflagged]
    report = "\n".join(lines)

    out = Path(__file__).parent / "RESULTS_PHANTOM.md"
    out.write_text(report + "\n", encoding="utf-8")
    print()
    print(report)
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
