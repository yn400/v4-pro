"""
安全审计模块测试。
"""

import tempfile
from pathlib import Path

from v4_pro.audit.scanner import SecurityAuditor


class TestSecurityAuditor:
    """SecurityAuditor 单元测试。"""

    def test_empty_directory(self):
        """测试空目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            report = SecurityAuditor().audit(Path(tmp))
            assert report["summary"]["total_findings"] == 0
            assert "audit_metadata" in report
            assert "findings" in report

    def test_detect_sql_injection(self):
        """测试检测 SQL 注入。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
            (Path(tmp) / "db.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            sql_findings = [
                f for f in report["findings"]
                if "SQL" in f.get("title", "")
            ]
            assert len(sql_findings) >= 1
            assert sql_findings[0]["severity"] == "critical"
            assert sql_findings[0]["cwe"] == "CWE-89"

    def test_detect_hardcoded_password(self):
        """测试检测硬编码密码。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'PASSWORD = "super_secret_123"'
            (Path(tmp) / "config.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            secret_findings = [
                f for f in report["findings"]
                if "密码" in f.get("title", "") or "password" in f.get("title", "").lower()
            ]
            assert len(secret_findings) >= 1

    def test_detect_xss_innerhtml(self):
        """测试检测 XSS — innerHTML。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'el.innerHTML = userInput;'
            (Path(tmp) / "app.js").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            xss_findings = [
                f for f in report["findings"]
                if "XSS" in f.get("title", "")
            ]
            assert len(xss_findings) >= 1

    def test_detect_insecure_deserialization(self):
        """测试检测不安全反序列化。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'import pickle; data = pickle.loads(user_input)'
            (Path(tmp) / "loader.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            deser_findings = [
                f for f in report["findings"]
                if "反序列化" in f.get("title", "")
            ]
            assert len(deser_findings) >= 1

    def test_detect_weak_crypto(self):
        """测试检测弱加密。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'import hashlib; h = hashlib.md5(data)'
            (Path(tmp) / "hash.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            crypto_findings = [
                f for f in report["findings"]
                if "MD5" in f.get("title", "")
            ]
            assert len(crypto_findings) >= 1

    def test_report_structure(self):
        """测试报告结构完整性。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'eval(user_input)'
            (Path(tmp) / "test.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            assert "audit_metadata" in report
            assert "summary" in report
            assert "findings" in report
            assert "remediation_priority" in report

            meta = report["audit_metadata"]
            assert "timestamp" in meta
            assert "files_scanned" in meta
            assert "owasp_categories_covered" in meta

            summary = report["summary"]
            assert "total_findings" in summary
            assert "critical" in summary
            assert "risk_score" in summary

    def test_owasp_coverage(self):
        """测试 OWASP 分类覆盖。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = '''
API_KEY = "sk-secret"
eval(user_input)
cursor.execute(f"SELECT * FROM {table}")
hashlib.md5(data)
'''
            (Path(tmp) / "vuln.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            owasp = report["audit_metadata"]["owasp_categories_covered"]
            # 应该至少覆盖 3 个 OWASP 类别
            assert len(owasp) >= 3

    def test_findings_have_ids(self):
        """测试所有发现都有唯一 ID。"""
        with tempfile.TemporaryDirectory() as tmp:
            code = 'eval(x); exec(y); API_KEY = "secret"'
            (Path(tmp) / "test.py").write_text(code)

            report = SecurityAuditor().audit(Path(tmp))

            ids = [f.get("id") for f in report["findings"]]
            assert all(ids)
            assert len(ids) == len(set(ids))
