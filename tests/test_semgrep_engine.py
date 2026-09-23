"""
Semgrep 深度扫描引擎测试 — 全部 mock，不依赖本机安装 semgrep。
"""
import json
from pathlib import Path
from unittest.mock import patch

import yaml

from v4_pro.verify.semgrep_engine import COVERED_BUILTIN_RULES, SemgrepEngine, is_available

FIXTURE = {
    "results": [
        {
            "check_id": "ai-slop-python.v4-sql-fstring-execute",
            "path": "db.py",
            "start": {"line": 10},
            "extra": {"severity": "ERROR", "message": "SQL 注入", "lines": "cursor.execute(f\"...\")"},
        },
        {
            "check_id": "ai-slop-js.v4-js-eval",
            "path": "app.js",
            "start": {"line": 3},
            "extra": {"severity": "WARNING", "message": "eval", "lines": "eval(x)"},
        },
        {
            "check_id": "ai-slop-python.v4-sql-fstring-execute",
            "path": "db.py",
            "start": {"line": 10},
            "extra": {"severity": "ERROR", "message": "SQL 注入", "lines": "dup"},
        },
    ],
    "errors": [],
}


class TestParsing:
    def test_map_and_dedupe(self, tmp_path):
        eng = SemgrepEngine(rules_dir=tmp_path)
        with patch("v4_pro.verify.semgrep_engine.subprocess.run") as mr, \
             patch("v4_pro.verify.semgrep_engine.is_available", return_value=True):
            mr.return_value = type("P", (), {
                "stdout": json.dumps(FIXTURE), "returncode": 0,
            })()
            r = eng.scan(tmp_path)
        assert len(r["issues"]) == 2  # 重复的被去重
        first = r["issues"][0]
        assert first["severity"] == "P0"
        assert first["rule_id"] == "semgrep/v4-sql-fstring-execute"
        assert first["line"] == 10
        second = r["issues"][1]
        assert second["severity"] == "P1"  # WARNING -> P1

    def test_unavailable_degrades(self, tmp_path):
        eng = SemgrepEngine(rules_dir=tmp_path)
        with patch("v4_pro.verify.semgrep_engine.is_available", return_value=False):
            r = eng.scan(tmp_path)
        assert r["passed"] is True
        assert r["issues"] == []
        assert any("未安装" in n for n in r["summary"]["notes"])

    def test_crash_degrades(self, tmp_path):
        eng = SemgrepEngine(rules_dir=tmp_path)
        with patch("v4_pro.verify.semgrep_engine.is_available", return_value=True), \
             patch("v4_pro.verify.semgrep_engine.subprocess.run", side_effect=OSError("boom")):
            r = eng.scan(tmp_path)
        assert r["passed"] is True
        assert any("运行失败" in n for n in r["summary"]["notes"])


class TestCoveredRules:
    def test_expected_builtin_rules_covered(self):
        for rid in (
            "SEC/sql-fstring", "SEC/dynamic-exec", "SEC/unsafe-deserialize",
            "SEC/weak-hash", "SEC/document-write", "SEC/subprocess-shell",
        ):
            assert rid in COVERED_BUILTIN_RULES


class TestBundledRules:
    def test_rules_yaml_valid(self):
        rules_dir = Path("v4_pro/semgrep_rules")
        assert rules_dir.is_dir()
        count = 0
        for f in rules_dir.glob("*.yaml"):
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            for rule in data["rules"]:
                assert rule.get("id"), f"{f.name} 缺 id"
                assert rule.get("languages"), f"{rule['id']} 缺 languages"
                assert rule.get("severity") in ("ERROR", "WARNING", "INFO")
                assert rule.get("message")
                count += 1
        assert count >= 14  # 规则数量底线

    def test_availability_probe(self):
        # 不关心结果，只要求函数可调用且返回布尔
        assert isinstance(is_available(), bool)
