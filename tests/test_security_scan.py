"""
安全扫描模块测试。
"""

import tempfile
from pathlib import Path

from v4_pro.verify.security_scan import SecurityScanner


class TestSecurityScanner:
    """SecurityScanner 单元测试。"""

    def test_empty_directory(self):
        """测试空目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = SecurityScanner().scan(Path(tmp))
            assert result["passed"] is True
            assert result["issues"] == []

    def test_detect_eval(self):
        """测试检测 eval()。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = "result = eval(user_input)"
            (Path(tmp) / "test.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            eval_issues = [
                i for i in result["issues"]
                if "eval" in i.get("title", "").lower()
            ]
            assert len(eval_issues) >= 1
            assert eval_issues[0]["severity"] == "P0"

    def test_detect_pickle(self):
        """测试检测 pickle.loads()。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = "import pickle; data = pickle.loads(user_data)"
            (Path(tmp) / "test.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            pickle_issues = [
                i for i in result["issues"]
                if "反序列化" in i.get("title", "")
            ]
            assert len(pickle_issues) >= 1

    def test_detect_hardcoded_secret(self):
        """测试检测硬编码密钥。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'API_KEY = "sk-abc123def456ghi789"'
            (Path(tmp) / "config.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            secret_issues = [
                i for i in result["issues"]
                if "硬编码" in i.get("title", "")
            ]
            assert len(secret_issues) >= 1
            assert secret_issues[0]["severity"] == "P0"

    def test_detect_sql_injection_fstring(self):
        """测试检测 f-string SQL 注入。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
            (Path(tmp) / "db.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            sql_issues = [
                i for i in result["issues"]
                if "SQL" in i.get("title", "")
            ]
            assert len(sql_issues) >= 1

    def test_detect_xss_innerhtml(self):
        """测试检测 innerHTML XSS。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = "el.innerHTML = userInput;"
            (Path(tmp) / "app.js").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            xss_issues = [
                i for i in result["issues"]
                if "innerHTML" in i.get("title", "") or "XSS" in i.get("title", "")
            ]
            assert len(xss_issues) >= 1

    def test_detect_path_traversal(self):
        """测试检测路径遍历。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'open("../etc/passwd")'
            (Path(tmp) / "file.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            path_issues = [
                i for i in result["issues"]
                if "路径遍历" in i.get("title", "")
            ]
            assert len(path_issues) >= 1

    def test_clean_code_passes(self):
        """测试干净的代码通过扫描。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = """
def add(a: int, b: int) -> int:
    '''Add two numbers.'''
    return a + b

def main():
    result = add(1, 2)
    logger.info("Result: %d", result)
"""
            (Path(tmp) / "clean.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            p0_issues = [i for i in result["issues"] if i["severity"] == "P0"]
            assert len(p0_issues) == 0

    def test_issues_have_owasp(self):
        """测试安全问题的 OWASP 分类。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'eval(user_input)'
            (Path(tmp) / "test.py").write_text(code)

            result = SecurityScanner().scan(Path(tmp))

            for issue in result["issues"]:
                assert "owasp_category" in issue or issue.get("severity") != "P0"
