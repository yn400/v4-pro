"""
静态分析模块测试。
"""

import tempfile
from pathlib import Path

from v4_pro.verify.static_analysis import StaticAnalyzer


class TestStaticAnalyzer:
    """StaticAnalyzer 单元测试。"""

    def test_empty_directory(self):
        """测试空目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = StaticAnalyzer().analyze(Path(tmp))
            assert result["passed"] is True
            assert result["issues"] == []
            assert result["summary"]["files_scanned"] == 0

    def test_nonexistent_directory(self):
        """测试不存在的目录。"""
        result = StaticAnalyzer().analyze(Path("/nonexistent/path"))
        assert result["passed"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "P0"

    def test_builtin_python_check_bare_except(self):
        """测试内置规则 — 裸 except。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = """
def foo():
    try:
        x = 1 / 0
    except:
        pass
"""
            (Path(tmp) / "test.py").write_text(code)

            result = StaticAnalyzer().analyze(Path(tmp))

            bare_except_issues = [
                i for i in result["issues"]
                if "裸 except" in i.get("title", "")
            ]
            assert len(bare_except_issues) >= 1

    def test_builtin_python_check_print(self):
        """测试内置规则 — print 语句。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'print("hello world")'
            (Path(tmp) / "test.py").write_text(code)

            result = StaticAnalyzer().analyze(Path(tmp))

            print_issues = [
                i for i in result["issues"]
                if "print" in i.get("title", "").lower()
            ]
            assert len(print_issues) >= 1

    def test_builtin_python_check_todo(self):
        """测试内置规则 — TODO 检测。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = """
def process():
    # TODO: optimize this
    pass
"""
            (Path(tmp) / "test.py").write_text(code)

            result = StaticAnalyzer().analyze(Path(tmp))

            todo_issues = [
                i for i in result["issues"]
                if "TODO" in i.get("title", "")
            ]
            # 注释行中的 TODO 应该被跳过
            assert len(todo_issues) == 0

    def test_builtin_check_star_import(self):
        """测试内置规则 — star import。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = "from os import *"
            (Path(tmp) / "test.py").write_text(code)

            result = StaticAnalyzer().analyze(Path(tmp))

            star_issues = [
                i for i in result["issues"]
                if "import *" in i.get("title", "")
            ]
            assert len(star_issues) >= 1

    def test_issues_have_ids(self):
        """测试所有问题都有唯一 ID。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = """
import os
print("test")
except:
    pass
"""
            (Path(tmp) / "test.py").write_text(code)

            result = StaticAnalyzer().analyze(Path(tmp))

            ids = [i.get("id", "") for i in result["issues"]]
            assert all(ids)
            assert len(ids) == len(set(ids))  # 唯一

    def test_excludes_dirs(self):
        """测试排除 __pycache__ 等目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            pycache = Path(tmp) / "__pycache__"
            pycache.mkdir()
            (pycache / "cached.py").write_text("print('cached')")

            src_file = Path(tmp) / "src.py"
            src_file.write_text("print('source')")

            result = StaticAnalyzer().analyze(Path(tmp))
            # 应该只扫描 src.py，不扫描 __pycache__
            files = result["summary"]["files_scanned"]
            assert files == 1
