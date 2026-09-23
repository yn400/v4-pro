"""
门禁基础设施测试 — 掩码/抑制/diff/基线/SARIF。
"""

import subprocess
from pathlib import Path

from v4_pro.gate import (
    build_suppression_map,
    changed_lines,
    filter_by_diff,
    is_suppressed,
    is_test_file,
    load_baseline,
    load_gate_config,
    mark_baseline,
    mask_comments,
    mask_strings_and_comments,
    severity_at_or_above,
    to_sarif,
)


class TestMasking:
    def test_comments_masked_strings_kept(self):
        src = 'x = "http://api.example.com"  # http://comment.example.com\n'
        masked = mask_comments(src)
        assert "http://api.example.com" in masked
        assert "http://comment.example.com" not in masked

    def test_multiline_docstring_masked(self):
        src = 's = 1\n"""\nyaml.load(\n"""\nt = 2\n'
        masked = mask_strings_and_comments(src)
        assert "yaml.load(" not in masked
        assert "s = 1" in masked and "t = 2" in masked

    def test_line_numbers_preserved(self):
        src = "a = 1\nb = 2  # note\nc = 3\n"
        masked = mask_comments(src)
        assert len(masked.split("\n")) == len(src.split("\n"))


class TestSuppression:
    def test_bare_ignore(self):
        m = build_suppression_map("bad()  # v4pro:ignore\n")
        assert m == {1: {"*"}}

    def test_rule_specific_ignore(self):
        m = build_suppression_map("bad()  # v4pro:ignore=SEC/sql-fstring\n")
        assert m == {1: {"SEC/sql-fstring"}}

    def test_suppression_applies(self):
        m = build_suppression_map("x = 1  # v4pro:ignore=SEC/weak-hash\n")
        assert is_suppressed({"line": 1, "rule_id": "SEC/weak-hash"}, m)
        assert not is_suppressed({"line": 1, "rule_id": "SEC/sql-fstring"}, m)
        assert not is_suppressed({"line": 2, "rule_id": "SEC/weak-hash"}, m)


class TestSeverity:
    def test_ordering(self):
        # 阈值 P0: 只有 P0 达标；阈值 P1: P0 和 P1 都算
        assert severity_at_or_above("P0", "P0")
        assert not severity_at_or_above("P1", "P0")
        assert severity_at_or_above("P0", "P1")
        assert severity_at_or_above("P1", "P1")
        assert not severity_at_or_above("P2", "P1")
        assert severity_at_or_above("P0", "P3")


class TestTestFileDetection:
    def test_paths(self):
        assert is_test_file(Path("proj/tests/test_app.py"))
        assert is_test_file(Path("proj/app_test.py"))
        assert is_test_file(Path("proj/src/user.spec.ts"))
        assert not is_test_file(Path("proj/src/app.py"))


class TestDiffFilter:
    def test_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        changed = {"a.py": {1, 2}}
        issues = [
            {"file": str(tmp_path / "a.py"), "line": 1},
            {"file": str(tmp_path / "b.py"), "line": 1},
        ]
        kept = filter_by_diff(issues, changed, tmp_path)
        assert len(kept) == 1
        assert kept[0]["file"].endswith("a.py")


class TestBaseline:
    def test_mark(self):
        issues = [{"file": "a.py", "line": 3, "rule_id": "SEC/weak-hash"}]
        baseline = {("a.py", 3, "SEC/weak-hash")}
        mark_baseline(issues, baseline)
        assert issues[0]["baseline"] is True

    def test_load(self, tmp_path):
        p = tmp_path / "base.json"
        p.write_text('{"issues": [{"file": "a.py", "line": 3, "rule_id": "X"}]}')
        assert load_baseline(p) == {("a.py", 3, "X")}


class TestGateConfig:
    def test_defaults(self, tmp_path):
        cfg = load_gate_config(tmp_path)
        assert cfg["fail_on"] == "P0"
        assert cfg["phantom"]["offline"] is False

    def test_user_override(self, tmp_path):
        (tmp_path / ".v4pro.json").write_text('{"fail_on": "P1", "phantom": {"offline": true}}')
        cfg = load_gate_config(tmp_path)
        assert cfg["fail_on"] == "P1"
        assert cfg["phantom"]["offline"] is True
        assert "exclude" in cfg  # 默认值保留


class TestSarif:
    def test_valid_structure(self):
        report = {
            "checks": {
                "security_scan": {
                    "issues": [{
                        "rule_id": "SEC/sql-fstring", "severity": "P0",
                        "title": "SQL 注入", "file": "db.py", "line": 5,
                        "suggestion": "参数化查询", "baseline": False,
                    }],
                },
            },
        }
        sarif = to_sarif(report)
        assert sarif["version"] == "2.1.0"
        run = sarif["runs"][0]
        assert run["tool"]["driver"]["name"] == "v4-pro"
        assert run["results"][0]["ruleId"] == "SEC/sql-fstring"
        assert run["results"][0]["level"] == "error"
        assert run["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 5

    def test_baseline_excluded(self):
        report = {
            "checks": {
                "c": {"issues": [{
                    "rule_id": "X", "severity": "P2", "title": "t",
                    "file": "a.py", "line": 1, "baseline": True,
                }]},
            },
        }
        assert to_sarif(report)["runs"][0]["results"] == []


class TestChangedLinesGit:
    def test_real_git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.py").write_text("line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.py").write_text("line1\nline2 changed\nline3\n")
        changed = changed_lines(tmp_path, "HEAD")
        lines = changed.get("a.py", set())
        assert 2 in lines  # 被修改的第 2 行必须在变更集中
